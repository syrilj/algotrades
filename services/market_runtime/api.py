from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .contracts import Opportunity, RankedOpportunity
from .decision import rank_opportunities
from .supervisor import StreamSupervisor

# Make tools/ and services/ available so the /plan endpoint can import live_plan.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "services"))

_live_plan_module: Any = None


def _get_live_plan() -> Any:
    global _live_plan_module
    if _live_plan_module is None:
        import live_plan

        _live_plan_module = live_plan
    return _live_plan_module


def create_app(supervisor: Optional[StreamSupervisor] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        sup = app.state.supervisor
        if sup is not None and not sup.is_running():
            sup.start()
        yield
        if sup is not None and sup.is_running():
            sup.stop()

    app = FastAPI(title="market-runtime", version="0.1.0", lifespan=lifespan)
    app.state.supervisor = supervisor

    @app.get("/health")
    def health() -> dict[str, Any]:
        if app.state.supervisor is None:
            return {"status": "ok", "supervisor": "not configured"}
        return {
            "status": "ok",
            "running": app.state.supervisor.is_running(),
            "coverage": app.state.supervisor.coverage().to_dict(),
        }

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

    @app.post("/plan")
    def plan(request: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        """Run live_plan from the streaming service."""
        live_plan = _get_live_plan()

        account = float(request.get("account", 1000.0))
        peak = request.get("peak")
        peak = float(peak) if peak not in (None, "") and str(peak).strip() else None
        history_str = request.get("history")
        history = None
        if isinstance(history_str, str) and history_str.strip():
            try:
                history = [float(x) for x in history_str.split(",") if x.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="history must be comma-separated numbers")
        model = request.get("model") or None
        use_model = not bool(request.get("no_model"))

        if request.get("scan"):
            symbols_str = request.get("symbols")
            symbols = [s.strip() for s in symbols_str.split(",") if s.strip()] if isinstance(symbols_str, str) and symbols_str.strip() else None
            return live_plan.scan(
                symbols=symbols,
                account=account,
                peak=peak,
                use_model=False,
            )

        symbol = request.get("symbol")
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol required")

        return live_plan.plan_symbol(
            symbol=str(symbol),
            account=account,
            peak=peak,
            history=history,
            model=model,
            use_model=use_model,
        )

    return app
