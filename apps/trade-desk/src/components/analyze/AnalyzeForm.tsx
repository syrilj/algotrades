"use client";

import { ChevronDown, Play } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { ModelsCatalog } from "@/lib/types";

export type AnalyzeFormValues = {
  symbol: string;
  account: number;
  riskPct: number;
  model: string;
  period: string;
  interval: string;
};

type AnalyzeFormProps = {
  initialSymbol?: string;
  disabled?: boolean;
  onSubmit: (values: AnalyzeFormValues) => void;
  onModelChange?: (model: string) => void;
};

export function AnalyzeForm({
  initialSymbol = "",
  disabled = false,
  onSubmit,
  onModelChange,
}: AnalyzeFormProps) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [account, setAccount] = useState(100_000);
  const [riskPct, setRiskPct] = useState(0.5);
  const [model, setModel] = useState("auto");
  const [period, setPeriod] = useState("6mo");
  const [interval, setInterval] = useState("1d");
  const [advanced, setAdvanced] = useState(false);
  const [engines, setEngines] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);

  useEffect(() => {
    if (initialSymbol) setSymbol(initialSymbol);
  }, [initialSymbol]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/models");
        const json = (await res.json()) as {
          ok?: boolean;
          data?: ModelsCatalog;
          error?: string;
        };
        if (!res.ok || json.ok === false) {
          throw new Error(json.error ?? `Models HTTP ${res.status}`);
        }
        const list = json.data?.engines ?? [];
        if (!cancelled) {
          setEngines(list);
          setModelsError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setModelsError(e instanceof Error ? e.message : "Failed to load models");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleModel = useCallback(
    (next: string) => {
      setModel(next);
      onModelChange?.(next);
    },
    [onModelChange],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const sym = symbol.trim().toUpperCase();
    if (!sym || disabled) return;
    onSubmit({
      symbol: sym,
      account,
      riskPct,
      model,
      period,
      interval,
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 border-b pb-4"
      style={{ borderColor: "var(--td-ink-700)" }}
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-[100px] flex-1">
          <span className="td-label">Symbol</span>
          <input
            className="td-input tabular uppercase"
            name="symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="TSLA"
            autoComplete="off"
            spellCheck={false}
            required
            disabled={disabled}
            style={{ fontFamily: "var(--td-font-mono)" }}
          />
        </label>

        <label className="w-[120px]">
          <span className="td-label">Account</span>
          <input
            className="td-input tabular"
            name="account"
            type="number"
            min={1000}
            step={1000}
            value={account}
            onChange={(e) => setAccount(Number(e.target.value))}
            disabled={disabled}
            style={{ fontFamily: "var(--td-font-mono)" }}
          />
        </label>

        <label className="w-[96px]">
          <span className="td-label">Risk %</span>
          <input
            className="td-input tabular"
            name="riskPct"
            type="number"
            min={0.05}
            max={5}
            step={0.05}
            value={riskPct}
            onChange={(e) => setRiskPct(Number(e.target.value))}
            disabled={disabled}
            style={{ fontFamily: "var(--td-font-mono)" }}
          />
        </label>

        <label className="min-w-[160px] flex-1">
          <span className="td-label">Model</span>
          <select
            className="td-input"
            name="model"
            value={model}
            onChange={(e) => handleModel(e.target.value)}
            disabled={disabled}
            style={{ fontFamily: "var(--td-font-mono)" }}
          >
            <option value="auto">auto</option>
            {engines.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>

        <button
          type="submit"
          className="td-btn td-btn-primary"
          disabled={disabled || !symbol.trim()}
        >
          <Play size={14} strokeWidth={1.75} aria-hidden />
          Run
        </button>
      </div>

      {modelsError ? (
        <p className="text-[11px]" style={{ color: "var(--td-action-avoid)" }}>
          Models catalog: {modelsError}
        </p>
      ) : null}

      <button
        type="button"
        className="inline-flex w-fit items-center gap-1 text-[12px]"
        style={{ color: "var(--td-ink-300)", background: "none", border: 0, cursor: "pointer" }}
        onClick={() => setAdvanced((v) => !v)}
        aria-expanded={advanced}
      >
        <ChevronDown
          size={14}
          strokeWidth={1.75}
          style={{
            transform: advanced ? "rotate(0deg)" : "rotate(-90deg)",
            transition: "transform var(--td-dur-fast) var(--td-ease)",
          }}
          aria-hidden
        />
        Advanced: period · interval
      </button>

      {advanced ? (
        <div className="flex flex-wrap gap-3">
          <label className="w-[120px]">
            <span className="td-label">Period</span>
            <select
              className="td-input"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              disabled={disabled}
            >
              {["1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="w-[120px]">
            <span className="td-label">Interval</span>
            <select
              className="td-input"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              disabled={disabled}
            >
              {["1d", "1h", "30m", "15m", "5m"].map((iv) => (
                <option key={iv} value={iv}>
                  {iv}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
    </form>
  );
}
