"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";

const VARIANTS = [
  { id: "v22_robust", label: "v22 robust (balanced)" },
  { id: "v22_robust_conservative", label: "v22 robust conservative (live-safe)" },
  { id: "v22_robust_trend_only", label: "v22 robust trend-only" },
  { id: "v22_robust_vol_only", label: "v22 robust vol-only" },
];

export default function RobustBacktestPage() {
  const [variant, setVariant] = useState("v22_robust_conservative");
  const [symbols, setSymbols] = useState("IONQ, AVGO, HOOD, MU");
  const [startDate, setStartDate] = useState("2024-08-01");
  const [endDate, setEndDate] = useState("2026-07-11");
  const [initialCash, setInitialCash] = useState(1000000);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; metrics?: Record<string, number>; error?: string } | null>(null);

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("/api/robust-backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant,
          symbols: symbols.split(",").map((s) => s.trim()).filter(Boolean),
          startDate,
          endDate,
          initialCash,
        }),
      });
      const json = await res.json();
      setResult(json);
    } catch (e) {
      setResult({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  };

  const m = result?.metrics;

  return (
    <main className="td-page">
      <PageHeader
        title="v22 Robust backtest"
        description="Research only — offline options variants. Live structure lives on Options desk; risk mode on Live."
        actions={
          <Link href="/options" className="td-btn td-btn-primary no-underline">
            Options desk
          </Link>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="p-4 rounded-sm" style={{ background: "var(--td-ink-900)", border: "1px solid var(--td-ink-700)" }}>
          <div className="flex flex-col gap-3">
            <label>
              <span className="text-[12px]" style={{ color: "var(--td-ink-300)" }}>Variant</span>
              <select className="td-input w-full" value={variant} onChange={(e) => setVariant(e.target.value)}>
                {VARIANTS.map((v) => (
                  <option key={v.id} value={v.id}>{v.label}</option>
                ))}
              </select>
            </label>
            <label>
              <span className="text-[12px]" style={{ color: "var(--td-ink-300)" }}>Symbols (comma separated, .US added)</span>
              <input className="td-input w-full" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className="text-[12px]" style={{ color: "var(--td-ink-300)" }}>Start</span>
                <input className="td-input w-full" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </label>
              <label>
                <span className="text-[12px]" style={{ color: "var(--td-ink-300)" }}>End</span>
                <input className="td-input w-full" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </label>
            </div>
            <label>
              <span className="text-[12px]" style={{ color: "var(--td-ink-300)" }}>Initial cash</span>
              <input className="td-input w-full" type="number" value={initialCash} onChange={(e) => setInitialCash(Number(e.target.value))} />
            </label>
            <button className="td-btn td-btn-primary" onClick={run} disabled={loading}>
              {loading ? "Running…" : "Run backtest"}
            </button>
          </div>
        </div>

        <div className="p-4 rounded-sm" style={{ background: "var(--td-ink-900)", border: "1px solid var(--td-ink-700)" }}>
          <h2 className="text-[14px] font-medium mb-3">Results</h2>
          {!result ? (
            <p className="text-[13px]" style={{ color: "var(--td-ink-400)" }}>Run a backtest to see metrics.</p>
          ) : result.error ? (
            <p className="text-[13px]" style={{ color: "var(--td-action-avoid)" }}>{result.error}</p>
          ) : m ? (
            <div className="grid grid-cols-2 gap-3 text-[13px]">
              <div><span style={{ color: "var(--td-ink-400)" }}>Final value</span><br/>${m.final_value?.toLocaleString?.() ?? m.final_value}</div>
              <div><span style={{ color: "var(--td-ink-400)" }}>Total return</span><br/>{(m.total_return * 100).toFixed(2)}%</div>
              <div><span style={{ color: "var(--td-ink-400)" }}>Annual return</span><br/>{(m.annual_return * 100).toFixed(2)}%</div>
              <div><span style={{ color: "var(--td-ink-400)" }}>Max drawdown</span><br/>{(m.max_drawdown * 100).toFixed(2)}%</div>
              <div><span style={{ color: "var(--td-ink-400)" }}>Sharpe</span><br/>{m.sharpe?.toFixed(2)}</div>
              <div><span style={{ color: "var(--td-ink-400)" }}>Trades</span><br/>{m.trade_count}</div>
              <div><span style={{ color: "var(--td-ink-400)" }}>Win rate</span><br/>{(m.win_rate * 100).toFixed(1)}%</div>
              <div><span style={{ color: "var(--td-ink-400)" }}>Calmar</span><br/>{m.calmar?.toFixed(2)}</div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="p-4 rounded-sm text-[13px]" style={{ background: "var(--td-ink-900)", border: "1px solid var(--td-ink-700)" }}>
        <h3 className="font-medium mb-2">How to use this</h3>
        <p style={{ color: "var(--td-ink-300)" }}>
          Start with <strong>v22 robust conservative</strong> for research windows. Positive returns across tested ranges with worst drawdown under 2%. Original v22 is overfit to 2024-2025 — not a live ticket by itself.
        </p>
        <p className="mt-2" style={{ color: "var(--td-ink-400)" }}>
          For a live structure + do-next steps, open{" "}
          <Link href="/options" style={{ color: "var(--td-brand)" }}>
            Options
          </Link>{" "}
          (picker + risk mode). This page does not send orders.
        </p>
      </div>
    </main>
  );
}
