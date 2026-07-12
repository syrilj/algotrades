"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { formatUsd } from "@/lib/format";
import { positionsHref } from "@/lib/routes";
import type {
  AnalyzeState,
  ApiEnvelope,
  PaperPosition,
  PlainPlan,
  PositionSize,
  TradeSide,
} from "@/lib/types";

type TradeButtonProps = {
  symbol: string;
  state: AnalyzeState;
  plan: PlainPlan;
  size?: PositionSize | null;
  model: string;
  reason?: string;
};

export function TradeButton({
  symbol,
  state,
  plan,
  size,
  model,
  reason,
}: TradeButtonProps) {
  const [open, setOpen] = useState(false);
  const [side, setSide] = useState<TradeSide>("long");
  const [shares, setShares] = useState(String(size?.shares ?? 0));
  const [entry, setEntry] = useState(String(state.entry ?? state.price ?? ""));
  const [stop, setStop] = useState(String(state.stop ?? ""));
  const [override, setOverride] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logged, setLogged] = useState<PaperPosition | null>(null);

  const action = plan.action ?? "";
  const needsOverride =
    action.toUpperCase().includes("AVOID") || action.toUpperCase().includes("WAIT");

  const dollarRisk = useMemo(() => {
    const e = Number(entry);
    const s = Number(stop);
    const sh = Number(shares);
    if (!Number.isFinite(e) || !Number.isFinite(s) || !Number.isFinite(sh)) return null;
    return Math.abs(e - s) * sh;
  }, [entry, stop, shares]);

  async function confirmTrade() {
    if (needsOverride && !override) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          side,
          shares: Number(shares),
          entry: Number(entry),
          stop: Number(stop),
          trailArm: state.trail_arm,
          model,
          account: size?.account,
          riskPct: size?.risk_pct,
          dollarRisk: dollarRisk ?? undefined,
          action: plan.action,
          confidence: state.confidence,
          override: needsOverride ? override : undefined,
          reason,
        }),
      });
      const json = (await res.json()) as ApiEnvelope<{ position: PaperPosition }>;
      if (!res.ok || json.ok === false || !json.data?.position) {
        throw new Error(json.error ?? `Trade log failed (${res.status})`);
      }
      setLogged(json.data.position);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Trade log failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="td-btn td-btn-primary"
        onClick={() => {
          setOpen((v) => !v);
          setLogged(null);
          setError(null);
          setShares(String(size?.shares ?? 0));
          setEntry(String(state.entry ?? state.price ?? ""));
          setStop(String(state.stop ?? ""));
        }}
      >
        Log paper trade
      </button>

      {open ? (
        <div
          className="td-panel absolute left-0 top-full z-20 mt-2 w-[min(22rem,90vw)] p-3 shadow-lg"
          role="dialog"
          aria-label="Confirm paper trade"
        >
          {logged ? (
            <div className="flex flex-col gap-2 text-[13px]">
              <p style={{ color: "var(--td-ink-100)" }}>
                Logged {logged.id}
              </p>
              <Link href={positionsHref()} className="td-btn td-btn-ghost no-underline">
                Positions →
              </Link>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {needsOverride ? (
                <p
                  className="text-[12px]"
                  style={{ color: "var(--td-action-avoid)" }}
                >
                  Verdict is {action} — log anyway?
                  <label className="mt-2 flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={override}
                      onChange={(e) => setOverride(e.target.checked)}
                    />
                    Override
                  </label>
                </p>
              ) : null}

              <label className="flex flex-col gap-1 text-[12px]">
                <span className="td-label mb-0">Side</span>
                <select
                  className="td-input"
                  value={side}
                  onChange={(e) => setSide(e.target.value as TradeSide)}
                >
                  <option value="long">long</option>
                  <option value="short">short</option>
                </select>
              </label>

              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1 text-[12px]">
                  <span className="td-label mb-0">Shares</span>
                  <input
                    className="td-input tabular"
                    value={shares}
                    onChange={(e) => setShares(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-[12px]">
                  <span className="td-label mb-0">Entry</span>
                  <input
                    className="td-input tabular"
                    value={entry}
                    onChange={(e) => setEntry(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-[12px]">
                  <span className="td-label mb-0">Stop</span>
                  <input
                    className="td-input tabular"
                    value={stop}
                    onChange={(e) => setStop(e.target.value)}
                  />
                </label>
                <div className="flex flex-col gap-1 text-[12px]">
                  <span className="td-label mb-0">$ risk</span>
                  <span
                    className="tabular pt-2"
                    style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}
                  >
                    {dollarRisk != null ? formatUsd(dollarRisk) : "—"}
                  </span>
                </div>
              </div>

              <div
                className="text-[11px]"
                style={{ color: "var(--td-ink-400)", fontFamily: "var(--td-font-mono)" }}
              >
                {model}
                {size?.account ? ` · acct ${formatUsd(size.account, 0)}` : null}
              </div>

              {error ? (
                <div className="td-alert td-alert--error" role="alert">
                  {error}
                </div>
              ) : null}

              <div className="flex gap-2">
                <button
                  type="button"
                  className="td-btn td-btn-primary"
                  data-testid="trade-confirm"
                  disabled={busy || (needsOverride && !override)}
                  onClick={() => void confirmTrade()}
                >
                  {busy ? "Logging…" : "Confirm"}
                </button>
                <button
                  type="button"
                  className="td-btn td-btn-ghost"
                  onClick={() => setOpen(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
