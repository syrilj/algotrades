from __future__ import annotations

import hmac
import math
import os
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .contracts import CoverageMode, Opportunity, RankedOpportunity
from .decision import rank_opportunities
from .supervisor import StreamSupervisor
from .vault_client import LSEVaultClient, LSEVaultError, VaultResult

# Make tools/ and services/ available so the /plan endpoint can import live_plan.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "services"))

_live_plan_module: Any = None
_SYMBOL_RE = re.compile(
    r"^(?:[A-Za-z0-9^][A-Za-z0-9.^\-]{0,23}|[A-Za-z]{3}/[A-Za-z]{3})$"
)
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}$")


def _get_live_plan() -> Any:
    global _live_plan_module
    if _live_plan_module is None:
        import live_plan

        _live_plan_module = live_plan
    return _live_plan_module


def _bounded_float(value: Any, name: str, *, default: float, low: float, high: float) -> float:
    try:
        number = float(default if value in (None, "") else value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be numeric") from exc
    if not math.isfinite(number) or not low <= number <= high:
        raise HTTPException(status_code=400, detail=f"{name} must be between {low} and {high}")
    return number


def _bounded_int(value: Any, name: str, *, default: int, low: int, high: int) -> int:
    number = _bounded_float(value, name, default=float(default), low=float(low), high=float(high))
    if not number.is_integer():
        raise HTTPException(status_code=400, detail=f"{name} must be an integer")
    return int(number)


def _validated_identifier(value: Any, name: str, pattern: re.Pattern[str]) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not pattern.fullmatch(text):
        raise HTTPException(status_code=400, detail=f"invalid {name}")
    return text


def create_app(
    supervisor: Optional[StreamSupervisor] = None,
    vault_client: Optional[LSEVaultClient] = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sup = app.state.supervisor
        if sup is not None and not sup.is_running():
            sup.start()
        yield
        if sup is not None and sup.is_running():
            sup.stop()
        vault = getattr(app.state, "vault_client", None)
        if vault is not None:
            vault.close()

    app = FastAPI(title="market-runtime", version="0.2.0", lifespan=lifespan)
    app.state.supervisor = supervisor
    app.state.vault_client = vault_client
    app.state.request_metrics = {
        "requests": 0,
        "errors": 0,
        "latency_ms_total": 0.0,
        "latency_ms_max": 0.0,
        "by_path": {},
    }
    app.state.request_metrics_lock = threading.Lock()

    @app.middleware("http")
    async def runtime_guard_and_metrics(request: Request, call_next: Any):
        """Optional service auth plus low-overhead request telemetry.

        Health remains public for container probes. When
        MARKET_RUNTIME_API_TOKEN is configured every other endpoint requires
        either ``X-API-Key`` or a bearer token.
        """
        started = time.perf_counter()
        configured = os.environ.get("MARKET_RUNTIME_API_TOKEN", "").strip()
        if configured and request.url.path not in {"/health"}:
            supplied = request.headers.get("x-api-key", "").strip()
            auth = request.headers.get("authorization", "").strip()
            if not supplied and auth.lower().startswith("bearer "):
                supplied = auth[7:].strip()
            if not supplied or not hmac.compare_digest(supplied, configured):
                return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        response = None
        failed = False
        try:
            response = await call_next(request)
            failed = response.status_code >= 500
            return response
        except Exception:
            failed = True
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            with app.state.request_metrics_lock:
                metrics = app.state.request_metrics
                metrics["requests"] += 1
                metrics["errors"] += int(failed)
                metrics["latency_ms_total"] += elapsed_ms
                metrics["latency_ms_max"] = max(metrics["latency_ms_max"], elapsed_ms)
                path_row = metrics["by_path"].setdefault(
                    request.url.path, {"requests": 0, "errors": 0, "latency_ms_total": 0.0}
                )
                path_row["requests"] += 1
                path_row["errors"] += int(failed)
                path_row["latency_ms_total"] += elapsed_ms

    @app.get("/health")
    def health() -> dict[str, Any]:
        if app.state.supervisor is None:
            return {"status": "degraded", "supervisor": "not configured"}
        runtime = app.state.supervisor.runtime_status()
        coverage = app.state.supervisor.coverage()
        healthy = bool(runtime["running"] and coverage.mode != CoverageMode.STALE)
        return {
            "status": "ok" if healthy else "degraded",
            **runtime,
            "coverage": coverage.to_dict(),
            "request_metrics": _request_metrics_snapshot(),
        }

    def _request_metrics_snapshot() -> dict[str, Any]:
        with app.state.request_metrics_lock:
            raw = app.state.request_metrics
            requests = int(raw["requests"])
            return {
                "requests": requests,
                "errors": int(raw["errors"]),
                "error_rate": float(raw["errors"]) / requests if requests else 0.0,
                "latency_ms_mean": float(raw["latency_ms_total"]) / requests if requests else 0.0,
                "latency_ms_max": float(raw["latency_ms_max"]),
                "by_path": {
                    path: {
                        "requests": int(values["requests"]),
                        "errors": int(values["errors"]),
                        "latency_ms_mean": (
                            float(values["latency_ms_total"]) / int(values["requests"])
                            if values["requests"] else 0.0
                        ),
                    }
                    for path, values in raw["by_path"].items()
                },
            }

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        return {"service": "market-runtime", **_request_metrics_snapshot()}

    @app.get("/model-health")
    def model_health() -> dict[str, Any]:
        try:
            import model_monitoring

            return model_monitoring.build_health_report(settle_due=False)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"model health unavailable: {exc}") from exc

    @app.get("/coverage")
    def coverage() -> dict[str, Any]:
        if app.state.supervisor is None:
            raise HTTPException(status_code=503, detail="supervisor not configured")
        return app.state.supervisor.coverage().to_dict()

    @app.get("/instruments")
    def instruments() -> dict[str, Any]:
        if app.state.supervisor is None:
            raise HTTPException(status_code=503, detail="supervisor not configured")
        return {
            "instruments": [i.to_dict() for i in app.state.supervisor.instruments()],
        }

    @app.get("/ticks/{instrument_id}")
    def ticks(instrument_id: str) -> dict[str, Any]:
        if app.state.supervisor is None:
            raise HTTPException(status_code=503, detail="supervisor not configured")
        tick = app.state.supervisor.latest(instrument_id)
        if tick is None:
            raise HTTPException(status_code=404, detail="tick not found")
        return tick.to_dict()

    @app.get("/bars/{instrument_id}")
    def bars(instrument_id: str, timeframe: str = "1m") -> dict[str, Any]:
        if app.state.supervisor is None:
            raise HTTPException(status_code=503, detail="supervisor not configured")
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "bars": [b.to_dict() for b in app.state.supervisor.bars(instrument_id, timeframe)],
        }

    @app.get("/opportunities")
    def opportunities() -> dict[str, Any]:
        if app.state.supervisor is None:
            raise HTTPException(status_code=503, detail="supervisor not configured")
        rows = getattr(app.state.supervisor, "opportunities", []) or []
        ranked = rank_opportunities(rows)
        return {
            "opportunities": [r.to_dict() for r in ranked],
        }

    def _vault() -> LSEVaultClient:
        client = app.state.vault_client
        if client is None:
            raise HTTPException(status_code=503, detail="LSE vault client not configured")
        return client

    def _vault_response(call: Any) -> dict[str, Any]:
        try:
            result: VaultResult = call()
        except LSEVaultError as exc:
            status = exc.status if 400 <= exc.status <= 599 else 502
            raise HTTPException(status_code=status, detail=exc.detail) from exc
        return {
            "ok": True,
            "data": result.data,
            "meta": {"source": "lse_vault", "data_bytes": result.data_bytes},
        }

    @app.get("/data/usage")
    def vault_usage() -> dict[str, Any]:
        return _vault_response(lambda: _vault().usage())

    @app.get("/data/catalog")
    def vault_catalog(dataset: Optional[str] = None) -> dict[str, Any]:
        return _vault_response(lambda: _vault().catalog(dataset=dataset))

    @app.get("/data/meta")
    def vault_meta() -> dict[str, Any]:
        return _vault_response(lambda: _vault().meta())

    @app.get("/data/reference")
    def vault_reference_index() -> dict[str, Any]:
        return _vault_response(lambda: _vault().reference_index())

    @app.get("/data/candles")
    def vault_candles(
        symbol: str,
        timeframe: str = "1m",
        start: Optional[str] = None,
        end: Optional[str] = None,
        order: str = Query("asc", pattern="^(asc|desc)$"),
        limit: int = Query(5000, ge=1, le=5000),
        dataset: Optional[str] = None,
    ) -> dict[str, Any]:
        return _vault_response(
            lambda: _vault().candles(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                order=order,
                limit=limit,
                dataset=dataset,
            )
        )

    @app.get("/data/series")
    def vault_series(
        symbol: str,
        dataset: Optional[str] = None,
        timeframe: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        order: str = Query("asc", pattern="^(asc|desc)$"),
        limit: int = Query(5000, ge=1, le=5000),
    ) -> dict[str, Any]:
        return _vault_response(
            lambda: _vault().series(
                symbol=symbol,
                dataset=dataset,
                timeframe=timeframe,
                start=start,
                end=end,
                order=order,
                limit=limit,
            )
        )

    @app.get("/data/reference/{dataset}")
    def vault_reference_rows(
        dataset: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        order: str = Query("asc", pattern="^(asc|desc)$"),
        limit: int = Query(5000, ge=1, le=5000),
        region: Optional[str] = None,
        event: Optional[str] = None,
        released: Optional[int] = Query(None, ge=0, le=1),
        symbol: Optional[str] = None,
        type: Optional[str] = None,
        report_type: Optional[str] = None,
        period: Optional[str] = None,
    ) -> dict[str, Any]:
        return _vault_response(
            lambda: _vault().reference_rows(
                dataset,
                start=start,
                end=end,
                order=order,
                limit=limit,
                region=region,
                event=event,
                released=released,
                symbol=symbol,
                type=type,
                report_type=report_type,
                period=period,
            )
        )

    @app.get("/data/options/chain")
    def vault_options_chain(
        underlying: str,
        type: Optional[str] = Query(None, pattern="^(call|put)$"),
        expiry: Optional[str] = None,
        strike: Optional[float] = None,
        strike_min: Optional[float] = None,
        strike_max: Optional[float] = None,
        min_dte: Optional[int] = Query(None, ge=0),
        max_dte: Optional[int] = Query(None, ge=0),
        limit: int = Query(5000, ge=1, le=5000),
    ) -> dict[str, Any]:
        return _vault_response(
            lambda: _vault().options_chain(
                underlying=underlying,
                type=type,
                expiry=expiry,
                strike=strike,
                strike_min=strike_min,
                strike_max=strike_max,
                min_dte=min_dte,
                max_dte=max_dte,
                limit=limit,
            )
        )

    @app.get("/data/options/flow")
    def vault_options_flow(
        underlying: Optional[str] = None,
        type: Optional[str] = Query(None, pattern="^(call|put)$"),
        min_premium: Optional[float] = Query(None, ge=0),
        expiry: Optional[str] = None,
        max_dte: Optional[int] = Query(None, ge=0),
        start: Optional[str] = None,
        end: Optional[str] = None,
        order: str = Query("desc", pattern="^(asc|desc)$"),
        limit: int = Query(5000, ge=1, le=5000),
    ) -> dict[str, Any]:
        return _vault_response(
            lambda: _vault().options_flow(
                underlying=underlying,
                type=type,
                min_premium=min_premium,
                expiry=expiry,
                max_dte=max_dte,
                start=start,
                end=end,
                order=order,
                limit=limit,
            )
        )

    @app.get("/data/options/candles")
    def vault_option_candles(
        ticker: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        order: str = Query("asc", pattern="^(asc|desc)$"),
        limit: int = Query(5000, ge=1, le=5000),
    ) -> dict[str, Any]:
        return _vault_response(
            lambda: _vault().option_candles(
                ticker=ticker,
                start=start,
                end=end,
                order=order,
                limit=limit,
            )
        )

    def _stream_ready() -> tuple[bool, Any, str]:
        """Return (ready, adapter_or_None, mode_label).

        Production is LSE-only and always fails closed without a healthy
        stream. Development may opt into the same behavior with
        MARKET_RUNTIME_REQUIRE_STREAM=1.
        """
        import os

        supervisor = app.state.supervisor
        production = os.environ.get("MARKET_RUNTIME_ENV", "development").strip().lower() in {
            "production",
            "prod",
        }
        require_raw = os.environ.get("MARKET_RUNTIME_REQUIRE_STREAM", "0")
        require = production or require_raw.strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if supervisor is None:
            if require:
                raise HTTPException(status_code=503, detail="supervisor not configured")
            return False, None, "no_supervisor"
        coverage = supervisor.coverage()
        ready = bool(
            supervisor.is_running()
            and coverage.mode not in {CoverageMode.WARMING, CoverageMode.STALE}
        )
        if require and not ready:
            raise HTTPException(
                status_code=503,
                detail=f"market stream not ready: {coverage.mode.value}",
            )
        adapter = supervisor.adapter if ready else None
        return ready, adapter, coverage.mode.value

    def _annotate_runtime(payload: dict[str, Any], stream_ready: bool, mode: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        runtime = payload.get("runtime")
        if not isinstance(runtime, dict):
            runtime = {}
            payload["runtime"] = runtime
        runtime["stream_ready"] = stream_ready
        runtime["coverage_mode"] = mode
        runtime["data_path"] = "lse_stream" if stream_ready else "development_fallback"
        return payload

    @app.post("/plan")
    def plan(request: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        """Run live_plan. Production accepts only a healthy LSE data path."""
        live_plan = _get_live_plan()
        stream_ready, adapter, mode = _stream_ready()

        account = _bounded_float(request.get("account"), "account", default=1000.0, low=1.0, high=1_000_000_000.0)
        peak = request.get("peak")
        peak = (
            _bounded_float(peak, "peak", default=account, low=1.0, high=1_000_000_000.0)
            if peak not in (None, "") and str(peak).strip()
            else None
        )
        history_str = request.get("history")
        history = None
        if isinstance(history_str, str) and history_str.strip():
            try:
                history = [float(x) for x in history_str.split(",") if x.strip()]
                if len(history) > 256 or any(not math.isfinite(x) for x in history):
                    raise ValueError("history exceeds 256 finite values")
            except ValueError:
                raise HTTPException(status_code=400, detail="history must be comma-separated numbers")
        model = _validated_identifier(request.get("model"), "model", _MODEL_RE)
        use_model = not bool(request.get("no_model"))

        if request.get("scan"):
            symbols_str = request.get("symbols")
            symbols = (
                [s.strip() for s in symbols_str.split(",") if s.strip()]
                if isinstance(symbols_str, str) and symbols_str.strip()
                else None
            )
            if symbols is not None:
                if len(symbols) > 200 or any(not _SYMBOL_RE.fullmatch(symbol) for symbol in symbols):
                    raise HTTPException(status_code=400, detail="symbols must contain at most 200 valid identifiers")
            out = live_plan.scan(
                symbols=symbols,
                account=account,
                peak=peak,
                use_model=False,
                lse_adapter=adapter,
            )
            return _annotate_runtime(out if isinstance(out, dict) else {"ok": True, "data": out}, stream_ready, mode)

        symbol = _validated_identifier(request.get("symbol"), "symbol", _SYMBOL_RE)
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol required")

        out = live_plan.plan_symbol(
            symbol=str(symbol),
            account=account,
            peak=peak,
            history=history,
            model=model,
            use_model=use_model,
            open_equity=_bounded_int(request.get("open_equity"), "open_equity", default=0, low=0, high=10000),
            open_options=_bounded_int(request.get("open_options"), "open_options", default=0, low=0, high=10000),
            portfolio_state_verified=bool(request.get("portfolio_verified")),
            lse_adapter=adapter,
        )
        return _annotate_runtime(out if isinstance(out, dict) else {"result": out}, stream_ready, mode)

    @app.post("/analyze")
    def analyze(request: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        """Structured analysis-agent report (Facts → Decision → Suggestion)."""
        symbol = _validated_identifier(request.get("symbol"), "symbol", _SYMBOL_RE)
        if not symbol or not str(symbol).strip():
            raise HTTPException(status_code=400, detail="symbol required")
        account = _bounded_float(request.get("account"), "account", default=1000.0, low=1.0, high=1_000_000_000.0)
        model = _validated_identifier(request.get("model"), "model", _MODEL_RE)
        if model in ("", "auto"):
            model = None
        horizon = str(request.get("horizon") or "swing")
        top_n = _bounded_int(request.get("top_n"), "top_n", default=3, low=1, high=20)

        stream_ready, _adapter, mode = _stream_ready()
        try:
            import analysis_agent as aa
        except ImportError as exc:
            raise HTTPException(status_code=500, detail=f"analysis_agent unavailable: {exc}") from exc

        out = aa.run_analysis(
            symbol=str(symbol).strip(),
            account=account,
            model=model,
            top_n=top_n,
            horizon=horizon,
        )
        if isinstance(out, dict):
            out = aa._sanitize_nan(out)
            return _annotate_runtime(out, stream_ready, mode)
        return {"ok": True, "data": out, "runtime": {"stream_ready": stream_ready, "coverage_mode": mode}}

    return app
