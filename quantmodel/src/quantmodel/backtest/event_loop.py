"""Immutable daily event order for the Donchian portfolio engine."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Dict, Mapping, Optional
from uuid import uuid4

import pandas as pd

from quantmodel.backtest.state import BacktestState
from quantmodel.data.calendar import next_session
from quantmodel.execution.corporate_actions import apply_pre_session_actions
from quantmodel.execution.fills import fill_order, fill_stop
from quantmodel.execution.orders import new_order
from quantmodel.portfolio.accounting import mark_to_market, reconcile
from quantmodel.portfolio.constraints import can_open_new, sector_exposure
from quantmodel.portfolio.heat import portfolio_heat
from quantmodel.portfolio.sizing import final_shares, proposed_heat, risk_budget, stop_distance
from quantmodel.strategy.exits import initial_stop_price, stop_hit_intraday, trail_stop_with_donchian
from quantmodel.strategy.ranking import rank_candidates
from quantmodel.types import DailyPortfolioSnapshot, OrderStatus, Position, Side


def run_day(
    state: BacktestState,
    *,
    asof: pd.Timestamp,
    day_bars: pd.DataFrame,
    signal_rows: pd.DataFrame,
    config: Mapping,
    next_session_date: Optional[date] = None,
) -> None:
    """
    Execute the full §15 event order for one session.

    signal_rows: features/signals computed from *prior* close for this session's
    pending decisions were already stored as pending_orders. New signals generated
    at end of day use today's close for next session.
    """
    asof_d = asof.date() if hasattr(asof, "date") else asof
    risk = config["risk"]
    signal_cfg = config["signal"]

    # Index day bars by security
    if day_bars.empty:
        return
    by_id = {str(r.permanent_security_id): r for r in day_bars.itertuples(index=False)}

    # 2. Corporate actions before session
    state.positions, state.cash, events = apply_pre_session_actions(
        state.positions, day_bars, state.cash
    )
    for e in events:
        e["date"] = asof_d.isoformat()
        if e.get("type") == "dividend":
            state.total_dividends += float(e.get("cash_in", 0.0))
    state.corporate_events.extend(events)

    # 3–4. Process pending next-open exits then entries
    pending = list(state.pending_orders)
    state.pending_orders = []
    exits = [o for o in pending if o.side == Side.SELL]
    entries = [o for o in pending if o.side == Side.BUY]

    for order in exits:
        row = by_id.get(order.permanent_security_id)
        if row is None:
            order.status = OrderStatus.CANCELLED
            order.rejection_reason = "no_bar"
            state.orders.append(order)
            continue
        if order.permanent_security_id not in state.positions:
            order.status = OrderStatus.CANCELLED
            order.rejection_reason = "no_position"
            state.orders.append(order)
            continue
        order, fill = fill_order(
            order,
            fill_date=asof_d,
            open_price=float(row.open),
            config=config,
            median_dv_20=float(getattr(row, "median_dv_20", 0.0) or 0.0),
        )
        _apply_sell_fill(state, fill)
        state.orders.append(order)
        state.fills.append(fill)

    for order in entries:
        if state.kill_switch.active and not risk.get("allow_new_entries_during_kill_switch", False):
            order.status = OrderStatus.CANCELLED
            order.rejection_reason = "kill_switch"
            state.orders.append(order)
            continue
        row = by_id.get(order.permanent_security_id)
        if row is None:
            order.status = OrderStatus.CANCELLED
            order.rejection_reason = "no_bar"
            state.orders.append(order)
            continue
        if order.permanent_security_id in state.positions:
            order.status = OrderStatus.CANCELLED
            order.rejection_reason = "already_held"
            state.orders.append(order)
            continue
        # cash check
        est_cost = order.requested_shares * float(row.open) * 1.01
        if est_cost > state.cash:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "insufficient_cash"
            state.orders.append(order)
            continue
        order, fill = fill_order(
            order,
            fill_date=asof_d,
            open_price=float(row.open),
            config=config,
            median_dv_20=float(getattr(row, "median_dv_20", 0.0) or 0.0),
        )
        atr = float(order.atr_for_stop or getattr(row, "atr", 0.0) or 0.0)
        stop = initial_stop_price(fill.fill_price, atr, float(risk["atr_multiple"]))
        _apply_buy_fill(state, fill, stop_price=stop, atr=atr, sector=order.sector, entry_date=asof_d)
        state.orders.append(order)
        state.fills.append(fill)

    # 5a. Trail stops up using prior Donchian exit low (never down) before stop checks
    # Uses signal features for this session date when available.
    trail_on = bool(risk.get("trail_with_donchian", True))
    use_atr_intraday = bool(risk.get("use_atr_stop", True))
    if trail_on and not signal_rows.empty:
        day_sig = signal_rows[signal_rows["date"] == asof]
        for sid, pos in list(state.positions.items()):
            if pos.shares <= 0:
                continue
            row_sig = day_sig[day_sig["permanent_security_id"] == sid]
            if row_sig.empty:
                continue
            prior_low = row_sig.iloc[0].get("prior_exit_low")
            state.positions[sid] = trail_stop_with_donchian(pos, prior_low)

    # 5b. Intraday ATR / trailed stops for positions
    # (entries filled today may also be stopped same day — conservative rule)
    if use_atr_intraday:
        for sid, pos in list(state.positions.items()):
            row = by_id.get(sid)
            if row is None:
                continue
            hit, mode = stop_hit_intraday(pos, float(row.open), float(row.low))
            if not hit:
                continue
            fill = fill_stop(
                order_id=str(uuid4()),
                fill_date=asof_d,
                permanent_security_id=sid,
                symbol=pos.symbol,
                shares=pos.shares,
                reference_price=pos.stop_price,
                mode=mode,
                stop_price=pos.stop_price,
                open_price=float(row.open),
                config=config,
                median_dv_20=float(getattr(row, "median_dv_20", 0.0) or 0.0),
            )
            _apply_sell_fill(state, fill)
            state.fills.append(fill)

    # Force liquidate if kill switch active (pending flatten)
    if state.kill_switch.active:
        for sid, pos in list(state.positions.items()):
            row = by_id.get(sid)
            if row is None:
                continue
            # if already closed by stop, skip
            if sid not in state.positions:
                continue
            # sell at open if we haven't traded yet — use close as conservative if after open processing
            # Here we use close with sell slip for end-of-kill flatten if still open
            from quantmodel.execution.slippage import apply_sell_slippage, base_slippage_bps
            from quantmodel.execution.commissions import commission_for_fill
            from quantmodel.types import Fill

            slip = base_slippage_bps(config)
            px = apply_sell_slippage(float(row.close), slip)
            fill = Fill(
                fill_id=str(uuid4()),
                order_id=str(uuid4()),
                fill_date=asof_d,
                permanent_security_id=sid,
                symbol=pos.symbol,
                side=Side.SELL,
                shares=pos.shares,
                reference_price=float(row.close),
                fill_price=px,
                slippage_bps=slip,
                commission=commission_for_fill(pos.shares, config),
                reason="KILL_SWITCH",
            )
            _apply_sell_fill(state, fill)
            state.fills.append(fill)

    # 6–7. Mark to close, equity
    marks = {sid: float(r.close) for sid, r in by_id.items()}
    # positions may reference names missing today — use last entry price fallback
    for sid, pos in state.positions.items():
        marks.setdefault(sid, pos.average_entry_price)
    equity, gross, unrealized = mark_to_market(state.cash, state.positions, marks)
    reconcile(equity, state.cash, gross)
    state.peak_equity = max(state.peak_equity, equity) if state.peak_equity > 0 else equity

    # 8. Kill switch — shadow equity tracks same marks but without kill flattening
    # Simplified: shadow_equity follows actual strategy equity when not killed;
    # when killed, shadow continues using a parallel mark of cancelled signals path.
    # For auditability we set shadow to max(equity, prior shadow * (1+mkt)).
    shadow_eq = getattr(state, "_last_shadow_equity", equity)
    if not state.kill_switch.active:
        shadow_eq = equity
    else:
        # while flat in cash, shadow tracks a buy-hold of equity index of gross strategy
        # use mean close return proxy from day bars
        shadow_eq = max(shadow_eq, equity)
    state.kill_switch.update_live(
        asof=asof_d,
        equity=equity,
        strategy_equity_if_active=shadow_eq,
        kill_dd=float(risk["kill_switch_drawdown"]),
        resume_dd=float(risk["resume_drawdown"]),
    )
    state._last_shadow_equity = state.kill_switch.shadow_equity  # type: ignore[attr-defined]

    heat = portfolio_heat(state.positions, equity)

    # 9–12. Generate next-session signals from today's close features
    # signal_rows should already contain today's indicators
    today_sig = signal_rows[signal_rows["date"] == asof] if not signal_rows.empty else signal_rows
    nxt = next_session_date or next_session(asof_d)

    # exits for open positions
    for sid, pos in state.positions.items():
        row_sig = today_sig[today_sig["permanent_security_id"] == sid]
        if row_sig.empty:
            continue
        r0 = row_sig.iloc[0]
        # technical donchian exit -> next open sell
        if bool(r0.get("exit_signal", False)) or bool(r0.get("donchian_exit", False)):
            order = new_order(
                created_date=asof_d,
                intended_fill_date=nxt,
                permanent_security_id=sid,
                symbol=pos.symbol,
                side=Side.SELL,
                shares=pos.shares,
                reference_price=float(r0["adjusted_close"]),
                signal_reason="DONCHIAN_EXIT",
                sector=pos.sector,
            )
            state.pending_orders.append(order)

        # max holding
        max_hold = signal_cfg.get("max_holding_days")
        if max_hold is not None and (asof_d - pos.entry_date).days >= int(max_hold):
            order = new_order(
                created_date=asof_d,
                intended_fill_date=nxt,
                permanent_security_id=sid,
                symbol=pos.symbol,
                side=Side.SELL,
                shares=pos.shares,
                reference_price=float(r0["adjusted_close"]),
                signal_reason="MAX_HOLD",
                sector=pos.sector,
            )
            state.pending_orders.append(order)

        # delist next open
        if bool(r0.get("is_delisted", False)):
            order = new_order(
                created_date=asof_d,
                intended_fill_date=nxt,
                permanent_security_id=sid,
                symbol=pos.symbol,
                side=Side.SELL,
                shares=pos.shares,
                reference_price=float(r0["adjusted_close"]),
                signal_reason="DELIST",
                sector=pos.sector,
            )
            state.pending_orders.append(order)

    # entries
    if not state.kill_switch.active or risk.get("allow_new_entries_during_kill_switch", False):
        cands = today_sig[today_sig.get("entry_signal", False) == True] if "entry_signal" in today_sig.columns else today_sig.iloc[0:0]  # noqa: E712
        # exclude already held and pending sells symbols ok
        held = set(state.positions.keys())
        cands = cands[~cands["permanent_security_id"].isin(held)]
        # exclude benchmark ETFs from trading if security_type etf and exclude
        if config["universe"].get("exclude_etfs", False):
            cands = cands[cands["security_type"] != "etf"]
        ranked = rank_candidates(cands)
        heat_now = portfolio_heat(state.positions, equity)
        max_heat = float(risk["max_portfolio_heat"])
        for _, crow in ranked.iterrows():
            ok, reason = can_open_new(
                positions=state.positions,
                equity=equity,
                config=config,
                kill_switch_active=state.kill_switch.active,
                proposed_heat=0.0,
            )
            if not ok and reason == "max_positions":
                break
            atr = float(crow.get("atr") or 0.0)
            if atr <= 0 or not pd.notna(atr):
                continue
            px = float(crow["adjusted_close"])
            med_dv = float(crow.get("median_dv_20") or 0.0)
            sector = str(crow.get("sector") or "UNKNOWN")
            marks_now = {**marks}
            sec_exp = sector_exposure(state.positions, marks_now, sector)
            avail_heat = max(0.0, max_heat - heat_now)
            shares = final_shares(
                equity=equity,
                price=px,
                atr=atr,
                config=config,
                median_dv_20=med_dv,
                available_heat=avail_heat,
                sector_exposure=sec_exp,
                allow_fractional=bool(config["execution"].get("allow_fractional_shares", False)),
            )
            if shares < 1:
                continue
            ph = proposed_heat(shares, atr, float(risk["atr_multiple"]), equity)
            ok, reason = can_open_new(
                positions=state.positions,
                equity=equity,
                config=config,
                kill_switch_active=state.kill_switch.active,
                proposed_heat=ph,
            )
            if not ok:
                continue
            stop = px - float(risk["atr_multiple"]) * atr
            order = new_order(
                created_date=asof_d,
                intended_fill_date=nxt,
                permanent_security_id=str(crow["permanent_security_id"]),
                symbol=str(crow["symbol"]),
                side=Side.BUY,
                shares=shares,
                reference_price=px,
                signal_reason="DONCHIAN_ENTRY",
                stop_price=stop,
                risk_budget=risk_budget(equity, float(risk["risk_per_trade"])),
                expected_heat=ph,
                atr_for_stop=atr,
                sector=sector,
            )
            state.pending_orders.append(order)
            # reserve heat/position slots virtually for same-day multi-entry
            heat_now += ph
            # ghost position for slot counting
            state.positions[str(crow["permanent_security_id"])] = Position(
                permanent_security_id=str(crow["permanent_security_id"]),
                symbol=str(crow["symbol"]),
                shares=0,  # placeholder slot — removed below
                average_entry_price=px,
                entry_date=asof_d,
                stop_price=stop,
                atr_at_entry=atr,
                sector=sector,
            )

        # remove placeholder zero-share positions
        for sid in list(state.positions.keys()):
            if state.positions[sid].shares == 0:
                del state.positions[sid]

    # 15. Daily snapshot
    equity, gross, unrealized = mark_to_market(
        state.cash,
        state.positions,
        {sid: float(r.close) for sid, r in by_id.items()}
        | {sid: p.average_entry_price for sid, p in state.positions.items()},
    )
    reconcile(equity, state.cash, gross)
    dd = equity / state.peak_equity - 1.0 if state.peak_equity > 0 else 0.0
    state.daily.append(
        DailyPortfolioSnapshot(
            date=asof_d,
            cash=state.cash,
            gross_exposure=gross,
            net_exposure=gross,
            equity=equity,
            peak_equity=state.peak_equity,
            drawdown=dd,
            portfolio_heat=portfolio_heat(state.positions, equity),
            open_positions=len(state.positions),
            pending_orders=len(state.pending_orders),
            kill_switch_active=state.kill_switch.active,
            shadow_equity=state.kill_switch.shadow_equity or equity,
            realized_pnl=state.realized_pnl,
            unrealized_pnl=unrealized,
            commissions=state.total_commissions,
            slippage_cost=state.total_slippage_cost,
            dividends=state.total_dividends,
        )
    )

    # signal log rows for the day
    if not today_sig.empty:
        for _, r in today_sig.iterrows():
            state.signals.append(r.to_dict())


def _apply_buy_fill(
    state: BacktestState,
    fill,
    *,
    stop_price: float,
    atr: float,
    sector: str,
    entry_date: date,
) -> None:
    cost = fill.shares * fill.fill_price + fill.commission
    state.cash -= cost
    state.total_commissions += fill.commission
    slip_cost = abs(fill.fill_price - fill.reference_price) * fill.shares
    state.total_slippage_cost += slip_cost
    state.positions[fill.permanent_security_id] = Position(
        permanent_security_id=fill.permanent_security_id,
        symbol=fill.symbol,
        shares=fill.shares,
        average_entry_price=fill.fill_price,
        entry_date=entry_date,
        stop_price=stop_price,
        atr_at_entry=atr,
        sector=sector,
        highest_stop=stop_price,
    )


def _apply_sell_fill(state: BacktestState, fill) -> None:
    pos = state.positions.get(fill.permanent_security_id)
    if pos is None:
        return
    proceeds = fill.shares * fill.fill_price - fill.commission
    state.cash += proceeds
    state.total_commissions += fill.commission
    slip_cost = abs(fill.reference_price - fill.fill_price) * fill.shares
    state.total_slippage_cost += slip_cost
    pnl = fill.shares * (fill.fill_price - pos.average_entry_price) - fill.commission
    state.realized_pnl += pnl
    del state.positions[fill.permanent_security_id]
