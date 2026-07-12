"use client";

import { useEffect, useState } from "react";
import { Activity } from "lucide-react";

type LiveSignal = {
  symbol: string;
  go_long: boolean;
  confidence: number;
  vol_z: number;
  signal_strength: number;
  price: number;
  error?: string;
};

export function LiveSignalPanel({ symbol }: { symbol: string }) {
  const [signal, setSignal] = useState<LiveSignal | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;

    let cancelled = false;
    setLoading(true);

    const load = () => {
      fetch(`/api/live-signal?symbol=${encodeURIComponent(symbol)}`)
        .then((r) => r.json())
        .then((data) => {
          if (!cancelled && data.data) setSignal(data.data);
        })
        .catch(() => {
          if (!cancelled) setSignal(null);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };

    load();
    const iv = window.setInterval(load, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(iv);
    };
  }, [symbol]);

  if (!symbol) return null;
  if (!signal && !loading) return null;

  const isLiveNow = Boolean(signal?.go_long && (signal?.vol_z ?? 0) >= 1.5);
  const leverage = signal?.signal_strength ?? 0;
  const volHot = Boolean(signal && signal.vol_z >= 1.5);

  return (
    <div
      className="td-panel p-3"
      style={{
        background: isLiveNow
          ? "color-mix(in oklch, var(--td-action-buy-now) 10%, var(--td-ink-900))"
          : "var(--td-ink-900)",
        borderColor: isLiveNow ? "var(--td-action-buy-now)" : "var(--td-ink-700)",
      }}
    >
      <div className="mb-2 flex items-center justify-between">
        <span
          className="text-[11px] font-semibold tracking-wide"
          style={{ color: "var(--td-ink-300)" }}
        >
          LIVE SIGNAL ·{" "}
          <span style={{ fontFamily: "var(--td-font-mono)", color: "var(--td-ink-100)" }}>
            {symbol}
          </span>
        </span>
        {loading ? (
          <Activity size={14} className="animate-spin" style={{ color: "var(--td-brand)" }} />
        ) : null}
      </div>

      {signal?.error ? (
        <span className="text-[11px]" style={{ color: "var(--td-action-avoid)" }}>
          Error: {signal.error}
        </span>
      ) : (
        <div className="flex flex-col gap-1 text-[11px]">
          <div className="flex justify-between">
            <span style={{ color: "var(--td-ink-400)" }}>Volume Z-score</span>
            <span
              className="tabular"
              style={{
                fontFamily: "var(--td-font-mono)",
                color: volHot ? "var(--td-action-buy-now)" : "var(--td-ink-200)",
              }}
            >
              {signal?.vol_z?.toFixed(2) ?? "—"}
            </span>
          </div>

          <div className="flex justify-between">
            <span style={{ color: "var(--td-ink-400)" }}>Confidence</span>
            <span className="tabular" style={{ fontFamily: "var(--td-font-mono)" }}>
              {((signal?.confidence ?? 0) * 100).toFixed(0)}%
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span style={{ color: "var(--td-ink-400)" }}>Signal</span>
            <span
              className="rounded px-2 py-0.5 text-[10px] font-semibold"
              style={{
                background: isLiveNow
                  ? "color-mix(in oklch, var(--td-action-buy-now) 22%, transparent)"
                  : "var(--td-ink-800)",
                color: isLiveNow ? "var(--td-action-buy-now)" : "var(--td-ink-300)",
                border: `1px solid ${isLiveNow ? "var(--td-action-buy-now)" : "var(--td-ink-600)"}`,
              }}
            >
              {signal?.go_long ? "GO LONG" : "NO SIGNAL"}
            </span>
          </div>

          {leverage > 0 ? (
            <div
              className="flex items-center justify-between border-t pt-1"
              style={{ borderColor: "var(--td-ink-700)" }}
            >
              <span style={{ color: "var(--td-ink-400)" }}>Options leverage</span>
              <span
                className="tabular font-semibold"
                style={{
                  fontFamily: "var(--td-font-mono)",
                  color: "var(--td-action-breakout-watch)",
                }}
              >
                {leverage}x
              </span>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
