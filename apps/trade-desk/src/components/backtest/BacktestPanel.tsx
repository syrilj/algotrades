"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import type { ApiEnvelope, ModelsCatalog } from "@/lib/types";

type BacktestResult = {
  ok: boolean;
  metrics?: Record<string, number>;
  error?: string;
};

export function BacktestPanel({ showHeader = true }: { showHeader?: boolean }) {
  const [variants, setVariants] = useState<{ id: string; label: string }[]>([]);
  const [variant, setVariant] = useState("");
  const [symbols, setSymbols] = useState("IONQ, AVGO, HOOD, MU");
  const [startDate, setStartDate] = useState("2024-08-01");
  const [endDate, setEndDate] = useState("2026-07-11");
  const [initialCash, setInitialCash] = useState(1000000);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);

  useEffect(() => {
    let active = true;
    const fetchModels = async () => {
      try {
        const res = await fetch("/api/models");
        const json = (await res.json()) as ApiEnvelope<ModelsCatalog>;
        if (json.ok && json.data && active) {
          const list = (json.data.engines || []).map((e) => ({
            id: e,
            label: e === json.data?.winner ? `${e} (champion)` : e,
          }));
          if (list.length > 0) {
            setVariants(list);
            const defaultVar = json.data.winner || list[0].id;
            setVariant(defaultVar);
            return;
          }
        }
      } catch (e) {
        console.error("Failed to load models catalog", e);
      }

      if (active) {
        setVariants([
          { id: "v39d_confluence", label: "v39d_confluence (champion)" },
          { id: "v50_high_win_rate", label: "v50_high_win_rate" },
          { id: "v22_robust", label: "v22 robust (balanced)" },
          { id: "v22_robust_conservative", label: "v22 robust conservative (live-safe)" },
        ]);
        setVariant("v39d_confluence");
      }
    };
    void fetchModels();
    return () => {
      active = false;
    };
  }, []);

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
      const json = (await res.json()) as BacktestResult;
      setResult(json);
    } catch (e) {
      setResult({ ok: false, error: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  };

  const m = result?.metrics;

  const content = (
    <>
      {showHeader ? (
        <PageHeader
          title="v22 Robust backtest"
          description="Research only — offline options variants. Live structure lives on Options desk; risk mode on Live."
          actions={
            <Link href="/options" className="td-btn td-btn-primary no-underline">
              Options desk
            </Link>
          }
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-sm p-4" style={{ background: "var(--td-ink-900)", border: "1px solid var(--td-ink-700)" }}>
          <div className="flex flex-col gap-3">
            <label>
              <span className="text-[12px]" style={{ color: "var(--td-ink-300)" }}>Variant</span>
              <select className="td-input w-full" value={variant} onChange={(e) => setVariant(e.target.value)}>
                {variants.map((v) => (
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

        <div className="rounded-sm p-4" style={{ background: "var(--td-ink-900)", border: "1px solid var(--td-ink-700)" }}>
          <h2 className="mb-3 text-[14px] font-medium">Results</h2>
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

      <div className="rounded-sm p-4 text-[13px]" style={{ background: "var(--td-ink-900)", border: "1px solid var(--td-ink-700)" }}>
        <h3 className="mb-2 font-medium">How to use this</h3>
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
    </>
  );

  if (showHeader) {
    return <main className="td-page">{content}</main>;
  }
  return <div className="flex flex-col gap-4">{content}</div>;
}
