#!/usr/bin/env python3
"""Portfolio optimiser — MPT, efficient frontier, risk parity, factor tilt.

Reads JSON from a file (``--input``) and prints JSON.

Example:
    python3 tools/portfolio_optimizer.py --input input.json --json

Input schema (method="mpt"):
    {
      "method": "mpt",
      "risk_free": 0.03,
      "allow_short": false,
      "frontier_points": 50,
      "assets": [
        {"name": "Equities", "ret": 0.12, "vol": 0.20},
        {"name": "Bonds", "ret": 0.06, "vol": 0.10}
      ],
      "correlation": [[1.0, 0.3], [0.3, 1.0]]
    }

Other methods: "risk_parity", "factor_tilt".
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json_friendly(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return float(obj)
    return obj


def _covariance(vols: np.ndarray, corr: np.ndarray) -> np.ndarray:
    s = np.diag(vols)
    return s @ corr @ s


def _portfolio_stats(
    weights: np.ndarray, rets: np.ndarray, cov: np.ndarray
) -> tuple[float, float, float]:
    w = np.asarray(weights)
    port_ret = float(w @ rets)
    port_var = float(w @ cov @ w)
    port_vol = math.sqrt(max(port_var, 0.0))
    return port_ret, port_vol, port_var


def _format_weights(weights: np.ndarray, names: list[str]) -> dict[str, float]:
    return {
        name: round(float(w), 4)
        for name, w in zip(names, weights)
    }


def _max_sharpe(
    rets: np.ndarray, cov: np.ndarray, risk_free: float, allow_short: bool = False
) -> dict[str, Any]:
    n = len(rets)
    bounds = [(-1.0, 1.0) if allow_short else (0.0, 1.0)] * n

    def neg_sharpe(w: np.ndarray) -> float:
        pr, pv, _ = _portfolio_stats(w, rets, cov)
        return -(pr - risk_free) / max(pv, 1e-12)

    cons = {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}
    w0 = np.ones(n) / n
    res = minimize(
        neg_sharpe,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"ftol": 1e-9, "maxiter": 200},
    )
    w = res.x if res.success else w0
    pr, pv, pvar = _portfolio_stats(w, rets, cov)
    return {
        "weights": [round(float(x), 4) for x in w],
        "return": round(pr, 5),
        "risk": round(pv, 5),
        "variance": round(pvar, 6),
        "sharpe": round((pr - risk_free) / max(pv, 1e-12), 4),
    }


def _min_variance(
    rets: np.ndarray, cov: np.ndarray, allow_short: bool = False
) -> dict[str, Any]:
    n = len(rets)
    bounds = [(-1.0, 1.0) if allow_short else (0.0, 1.0)] * n

    def variance(w: np.ndarray) -> float:
        return float(w @ cov @ w)

    cons = {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}
    w0 = np.ones(n) / n
    res = minimize(
        variance,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"ftol": 1e-9, "maxiter": 200},
    )
    w = res.x if res.success else w0
    pr, pv, pvar = _portfolio_stats(w, rets, cov)
    return {
        "weights": [round(float(x), 4) for x in w],
        "return": round(pr, 5),
        "risk": round(pv, 5),
        "variance": round(pvar, 6),
        "sharpe": round((pr - 0.0) / max(pv, 1e-12), 4),
    }


def _efficient_frontier(
    rets: np.ndarray,
    cov: np.ndarray,
    risk_free: float,
    n_points: int = 50,
    allow_short: bool = False,
) -> list[dict[str, Any]]:
    n = len(rets)
    min_var = _min_variance(rets, cov, allow_short)
    min_ret = min_var["return"]
    max_ret = float(np.max(rets))
    if max_ret <= min_ret:
        targets = [min_ret]
    else:
        targets = np.linspace(min_ret, max_ret, n_points)

    bounds = [(-1.0, 1.0) if allow_short else (0.0, 1.0)] * n
    base_cons = {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}
    frontier: list[dict[str, Any]] = []

    for t in targets:
        cons = [
            base_cons,
            {"type": "eq", "fun": lambda w, t=t: float(w @ rets - t)},
        ]

        def objective(w: np.ndarray) -> float:
            return float(w @ cov @ w)

        res = minimize(
            objective,
            np.ones(n) / n,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"ftol": 1e-9, "maxiter": 200},
        )
        if res.success:
            pr, pv, _ = _portfolio_stats(res.x, rets, cov)
            frontier.append({
                "return": round(pr, 5),
                "risk": round(pv, 5),
                "sharpe": round((pr - risk_free) / max(pv, 1e-12), 4),
                "weights": [round(float(x), 4) for x in res.x],
            })
    return frontier


def run_mpt(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets", [])
    if not assets or len(assets) < 2:
        raise ValueError("mpt requires at least 2 assets")

    names = [a.get("name", f"Asset{i}") for i, a in enumerate(assets)]
    rets = np.array([float(a.get("ret", 0.0)) for a in assets])
    vols = np.array([float(a.get("vol", 0.0)) for a in assets])
    n = len(assets)

    corr = np.array(payload.get("correlation", [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]))
    if corr.shape != (n, n):
        raise ValueError("correlation matrix must be square and match asset count")

    risk_free = float(payload.get("risk_free", 0.03))
    allow_short = bool(payload.get("allow_short", False))
    n_points = min(max(int(payload.get("frontier_points", 50)), 10), 200)

    cov = _covariance(vols, corr)
    max_sharpe = _max_sharpe(rets, cov, risk_free, allow_short)
    min_var = _min_variance(rets, cov, allow_short)
    frontier = _efficient_frontier(rets, cov, risk_free, n_points, allow_short)

    # Capital Market Line from tangency (max Sharpe) portfolio
    cml: list[dict[str, float]] = []
    if max_sharpe["risk"] > 0:
        for allocation in [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]:
            pr = risk_free + allocation * (max_sharpe["return"] - risk_free)
            pv = allocation * max_sharpe["risk"]
            cml.append({
                "allocation": round(allocation, 4),
                "return": round(pr, 5),
                "risk": round(pv, 5),
                "sharpe": round((pr - risk_free) / max(pv, 1e-12), 4) if pv > 0 else round(max_sharpe["sharpe"], 4),
            })

    return {
        "method": "mpt",
        "risk_free": risk_free,
        "assets": [
            {
                "name": name,
                "ret": round(float(ret), 4),
                "vol": round(float(vol), 4),
            }
            for name, ret, vol in zip(names, rets, vols)
        ],
        "correlation": corr.tolist(),
        "max_sharpe": max_sharpe,
        "min_variance": min_var,
        "efficient_frontier": frontier,
        "capital_market_line": cml,
    }


def _inverse_volatility(vols: np.ndarray) -> np.ndarray:
    inv = 1.0 / np.maximum(vols, 1e-12)
    return inv / np.sum(inv)


def _equal_risk_contribution(cov: np.ndarray) -> np.ndarray:
    n = cov.shape[0]

    def budget_error(w: np.ndarray) -> float:
        w = np.asarray(w)
        total = w @ cov @ w
        if total <= 0:
            return 1e12
        mrc = cov @ w
        rc = w * mrc
        target = total / n
        return float(np.sum((rc - target) ** 2))

    cons = {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}
    bounds = [(0.0, 1.0)] * n
    w0 = _inverse_volatility(np.sqrt(np.diag(cov)))
    res = minimize(
        budget_error,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"ftol": 1e-12, "maxiter": 300},
    )
    return res.x if res.success else w0


def _risk_contribution(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
    w = np.asarray(weights)
    total = w @ cov @ w
    if total <= 0:
        return np.zeros_like(w)
    mrc = cov @ w
    return w * mrc / total


def run_risk_parity(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets", [])
    if not assets or len(assets) < 2:
        raise ValueError("risk_parity requires at least 2 assets")

    names = [a.get("name", f"Asset{i}") for i, a in enumerate(assets)]
    vols = np.array([float(a.get("vol", 0.0)) for a in assets])
    n = len(assets)
    corr = np.array(payload.get("correlation", [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]))
    if corr.shape != (n, n):
        raise ValueError("correlation matrix must be square and match asset count")

    cov = _covariance(vols, corr)
    inv_vol_w = _inverse_volatility(vols)
    erc_w = _equal_risk_contribution(cov)
    equal_w = np.ones(n) / n

    inv_vol_ret, inv_vol_risk, _ = _portfolio_stats(inv_vol_w, np.zeros(n), cov)
    erc_ret, erc_risk, _ = _portfolio_stats(erc_w, np.zeros(n), cov)
    equal_ret, equal_risk, _ = _portfolio_stats(equal_w, np.zeros(n), cov)

    return {
        "method": "risk_parity",
        "assets": names,
        "vols": [round(float(v), 4) for v in vols],
        "correlation": corr.tolist(),
        "equal_weight": {
            "weights": _format_weights(equal_w, names),
            "risk": round(equal_risk, 5),
            "risk_contribution": {
                name: round(float(rc), 4)
                for name, rc in zip(names, _risk_contribution(equal_w, cov))
            },
        },
        "inverse_volatility": {
            "weights": _format_weights(inv_vol_w, names),
            "risk": round(inv_vol_risk, 5),
            "risk_contribution": {
                name: round(float(rc), 4)
                for name, rc in zip(names, _risk_contribution(inv_vol_w, cov))
            },
        },
        "equal_risk_contribution": {
            "weights": _format_weights(erc_w, names),
            "risk": round(erc_risk, 5),
            "risk_contribution": {
                name: round(float(rc), 4)
                for name, rc in zip(names, _risk_contribution(erc_w, cov))
            },
        },
    }


# Default factor premia and vols from the LSE educational content.
_FACTOR_DEFAULTS = {
    "Value": {"premium": 0.032, "vol": 0.05},
    "Momentum": {"premium": 0.075, "vol": 0.08},
    "Quality": {"premium": 0.041, "vol": 0.05},
    "Size": {"premium": 0.028, "vol": 0.07},
    "Low Volatility": {"premium": 0.035, "vol": 0.04},
}


def run_factor_tilt(payload: dict[str, Any]) -> dict[str, Any]:
    market_ret = float(payload.get("market_return", 0.08))
    market_vol = float(payload.get("market_vol", 0.15))
    risk_free = float(payload.get("risk_free", 0.03))
    factors = payload.get("factors", _FACTOR_DEFAULTS)
    tilts = payload.get("tilts", {})

    factor_list = []
    for name, data in factors.items():
        factor_list.append({
            "name": name,
            "premium": float(data.get("premium", 0.0)),
            "vol": float(data.get("vol", 0.0)),
        })

    factor_names = [f["name"] for f in factor_list]
    premiums = np.array([f["premium"] for f in factor_list])
    vols = np.array([f["vol"] for f in factor_list])
    tvec = np.array([float(tilts.get(name, 0.0)) for name in factor_names])

    corr = payload.get("factor_correlation")
    if corr is not None:
        corr = np.array(corr)
        if corr.shape != (len(factor_list), len(factor_list)):
            corr = None

    if corr is None:
        factor_var = float(np.sum(tvec ** 2 * vols ** 2))
    else:
        cov = _covariance(vols, corr)
        factor_var = float(tvec @ cov @ tvec)

    expected_ret = market_ret + float(np.sum(tvec * premiums))
    total_var = market_vol ** 2 + factor_var
    total_vol = math.sqrt(max(total_var, 0.0))
    tracking_error = math.sqrt(max(factor_var, 0.0))
    sharpe = (expected_ret - risk_free) / max(total_vol, 1e-12)

    contributions = {"Market": round(market_ret, 4)}
    for name, premium, tilt in zip(factor_names, premiums, tvec):
        contributions[name] = round(float(tilt * premium), 4)

    return {
        "method": "factor_tilt",
        "market_return": round(market_ret, 4),
        "market_vol": round(market_vol, 4),
        "risk_free": round(risk_free, 4),
        "expected_return": round(expected_ret, 4),
        "portfolio_risk": round(total_vol, 4),
        "tracking_error": round(tracking_error, 4),
        "sharpe": round(sharpe, 4),
        "contributions": contributions,
        "tilts": {name: round(float(tilts.get(name, 0.0)), 4) for name in factor_names},
    }


def _fetch_prices(symbols: list[str], lookback_days: int = 252) -> Any:
    import pandas as pd
    import yfinance as yf
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days + 60)
    data = yf.download(
        symbols,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if data is None or data.empty:
        raise ValueError("No price data returned")

    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=symbols[0])
    # Drop columns that are all NaN (invalid symbols)
    close = close.dropna(how="all", axis=1)
    if close.shape[1] < 2:
        raise ValueError(f"Need at least 2 valid symbols; got {close.shape[1]}")
    # Forward-fill and keep rows with at least one value, then drop remaining rows
    close = close.ffill().bfill()
    close = close.dropna(how="all")
    if len(close) < 30:
        raise ValueError(f"Insufficient price history: {len(close)} rows")
    return close


def _dict_weights(weights: np.ndarray, symbols: list[str]) -> dict[str, float]:
    return {symbols[i]: round(float(w), 4) for i, w in enumerate(weights)}


def _rebalance(
    current_weights: dict[str, float],
    target_weights: np.ndarray,
    symbols: list[str],
    account: float,
    last_prices: dict[str, float],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i, s in enumerate(symbols):
        w = float(target_weights[i])
        cw = current_weights.get(s, 0.0)
        price = last_prices.get(s, 0.0)
        delta_dollar = (w - cw) * account
        out[s] = {
            "current_weight": round(cw, 4),
            "target_weight": round(w, 4),
            "delta_weight": round(w - cw, 4),
            "current_dollar": round(cw * account, 2),
            "target_dollar": round(w * account, 2),
            "delta_dollar": round(delta_dollar, 2),
            "shares_to_trade": round(delta_dollar / price, 2) if price > 0 else None,
        }
    return out


def run_portfolio(payload: dict[str, Any]) -> dict[str, Any]:
    symbols = [s.strip().upper().replace(".US", "") for s in payload.get("symbols", [])]
    if len(symbols) < 2:
        raise ValueError("portfolio requires at least 2 symbols")
    if len(set(symbols)) != len(symbols):
        raise ValueError("duplicate symbols in portfolio")

    holdings = payload.get("holdings", {}) or {}
    risk_free = float(payload.get("risk_free", 0.03))
    lookback = int(payload.get("lookback", 252))
    allow_short = bool(payload.get("allow_short", False))
    account = float(payload.get("account", 0.0))
    mode = payload.get("mode", "both")  # mpt, risk_parity, both

    prices = _fetch_prices(symbols, lookback)
    valid_symbols = list(prices.columns)
    if len(valid_symbols) < 2:
        raise ValueError("Need at least 2 valid symbols with price data")

    returns = prices.pct_change().dropna()
    ann_rets = (returns.mean() * 252).to_dict()
    ann_vols = (returns.std() * np.sqrt(252)).to_dict()
    cov = (returns.cov() * 252).reindex(valid_symbols, axis=0).reindex(valid_symbols, axis=1)
    corr = (returns.corr()).reindex(valid_symbols, axis=0).reindex(valid_symbols, axis=1)
    last_prices = prices.iloc[-1].to_dict()

    # Current market values
    market_values: dict[str, float] = {}
    for s in valid_symbols:
        shares = 0.0
        if isinstance(holdings, dict):
            shares = float(holdings.get(s, 0.0) or 0.0)
        price = float(last_prices.get(s, 0.0) or 0.0)
        market_values[s] = shares * price
    total = sum(market_values.values())
    if total <= 0:
        market_values = {s: 1.0 for s in valid_symbols}
        total = float(len(valid_symbols))
    current_weights = {s: market_values[s] / total for s in valid_symbols}
    account = account if account > 0 else total

    rets = np.array([float(ann_rets[s]) for s in valid_symbols])
    vols = np.array([float(ann_vols[s]) for s in valid_symbols])
    cov_matrix = cov.values
    corr_matrix = corr.values

    # Run optimizations
    max_sharpe = _max_sharpe(rets, cov_matrix, risk_free, allow_short)
    min_var = _min_variance(rets, cov_matrix, allow_short)
    frontier = _efficient_frontier(rets, cov_matrix, risk_free, 50, allow_short)
    inv_vol_w = _inverse_volatility(vols)
    erc_w = _equal_risk_contribution(cov_matrix)
    equal_w = np.ones(len(valid_symbols)) / len(valid_symbols)

    # CML from tangency portfolio
    cml: list[dict[str, float]] = []
    if max_sharpe["risk"] > 0:
        for alloc in [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]:
            pr = risk_free + alloc * (max_sharpe["return"] - risk_free)
            pv = alloc * max_sharpe["risk"]
            cml.append({
                "allocation": round(alloc, 4),
                "return": round(pr, 5),
                "risk": round(pv, 5),
                "sharpe": round((pr - risk_free) / max(pv, 1e-12), 4) if pv > 0 else round(max_sharpe["sharpe"], 4),
            })

    result: dict[str, Any] = {
        "method": "portfolio",
        "symbols": valid_symbols,
        "risk_free": risk_free,
        "lookback": lookback,
        "account": round(account, 2),
        "total_market_value": round(total, 2),
        "last_prices": {s: round(float(last_prices[s]), 4) for s in valid_symbols},
        "market_values": {s: round(v, 2) for s, v in market_values.items()},
        "current_weights": {s: round(w, 4) for s, w in current_weights.items()},
        "annualized": {
            "returns": {s: round(float(ann_rets[s]), 4) for s in valid_symbols},
            "vols": {s: round(float(ann_vols[s]), 4) for s in valid_symbols},
            "correlation": corr_matrix.tolist(),
            "covariance": cov_matrix.tolist(),
        },
    }

    if mode in ("mpt", "both"):
        ms_weights = np.array(max_sharpe["weights"])
        result["mpt"] = {
            "max_sharpe": {
                "weights": _dict_weights(ms_weights, valid_symbols),
                "return": max_sharpe["return"],
                "risk": max_sharpe["risk"],
                "sharpe": max_sharpe["sharpe"],
                "rebalancing": _rebalance(current_weights, ms_weights, valid_symbols, account, last_prices),
            },
            "min_variance": {
                "weights": _dict_weights(min_var["weights"], valid_symbols),
                "return": min_var["return"],
                "risk": min_var["risk"],
                "sharpe": min_var["sharpe"],
                "rebalancing": _rebalance(current_weights, min_var["weights"], valid_symbols, account, last_prices),
            },
            "efficient_frontier": frontier,
            "capital_market_line": cml,
        }

    if mode in ("risk_parity", "both"):
        result["risk_parity"] = {
            "equal_weight": {
                "weights": _dict_weights(equal_w, valid_symbols),
                "risk": round(float(np.sqrt(equal_w @ cov_matrix @ equal_w.T)), 5),
                "risk_contribution": {
                    valid_symbols[i]: round(float(rc), 4)
                    for i, rc in enumerate(_risk_contribution(equal_w, cov_matrix))
                },
                "rebalancing": _rebalance(current_weights, equal_w, valid_symbols, account, last_prices),
            },
            "inverse_volatility": {
                "weights": _dict_weights(inv_vol_w, valid_symbols),
                "risk": round(float(np.sqrt(inv_vol_w @ cov_matrix @ inv_vol_w.T)), 5),
                "risk_contribution": {
                    valid_symbols[i]: round(float(rc), 4)
                    for i, rc in enumerate(_risk_contribution(inv_vol_w, cov_matrix))
                },
                "rebalancing": _rebalance(current_weights, inv_vol_w, valid_symbols, account, last_prices),
            },
            "equal_risk_contribution": {
                "weights": _dict_weights(erc_w, valid_symbols),
                "risk": round(float(np.sqrt(erc_w @ cov_matrix @ erc_w.T)), 5),
                "risk_contribution": {
                    valid_symbols[i]: round(float(rc), 4)
                    for i, rc in enumerate(_risk_contribution(erc_w, cov_matrix))
                },
                "rebalancing": _rebalance(current_weights, erc_w, valid_symbols, account, last_prices),
            },
        }

    return result


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    method = payload.get("method", "mpt")
    if method == "mpt":
        return run_mpt(payload)
    if method == "risk_parity":
        return run_risk_parity(payload)
    if method == "factor_tilt":
        return run_factor_tilt(payload)
    if method == "portfolio":
        return run_portfolio(payload)
    raise ValueError(f"unknown method: {method}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Portfolio optimiser")
    ap.add_argument("--input", help="Path to JSON input file (or '-' for stdin)")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args(argv)

    try:
        if args.input == "-" or args.input is None:
            raw = sys.stdin.read()
        else:
            raw = Path(args.input).read_text()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"Invalid JSON: {e}", "asof_utc": _now()}))
        return 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "asof_utc": _now()}))
        return 1

    try:
        data = dispatch(payload)
        out = {"ok": True, "data": data, "asof_utc": _now()}
    except Exception as e:
        out = {"ok": False, "error": str(e), "asof_utc": _now()}

    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
