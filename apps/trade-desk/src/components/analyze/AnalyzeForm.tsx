"use client";

import { ChevronDown, Play } from "lucide-react";
import { useCallback, useEffect, useImperativeHandle, forwardRef, useState } from "react";
import type { ModelsCatalog } from "@/lib/types";

export type AnalyzeFormValues = {
  symbol: string;
  account: number;
  riskPct: number;
  model: string;
  period: string;
  interval: string;
};

export type AnalyzeFormHandle = {
  submitWith: (patch?: Partial<AnalyzeFormValues>) => void;
  setModel: (model: string) => void;
};

type AnalyzeFormProps = {
  initialSymbol?: string;
  initialModel?: string;
  disabled?: boolean;
  onSubmit: (values: AnalyzeFormValues) => void;
  onModelChange?: (model: string) => void;
};

export const AnalyzeForm = forwardRef<AnalyzeFormHandle, AnalyzeFormProps>(
  function AnalyzeForm(
    {
      initialSymbol = "",
      initialModel = "auto",
      disabled = false,
      onSubmit,
      onModelChange,
    },
    ref,
  ) {
    const [symbol, setSymbol] = useState(initialSymbol);
    const [account, setAccount] = useState(100_000);
    const [riskPct, setRiskPct] = useState(0.5);
    const [model, setModel] = useState(initialModel || "auto");
    const [period, setPeriod] = useState("6mo");
    const [interval, setInterval] = useState("1d");
    const [advanced, setAdvanced] = useState(false);
    const [engines, setEngines] = useState<string[]>([]);
    const [modelMeta, setModelMeta] = useState<Record<string, { kind?: string; desk?: boolean }>>({});
    const [modelsError, setModelsError] = useState<string | null>(null);

    useEffect(() => {
      if (initialSymbol) setSymbol(initialSymbol);
    }, [initialSymbol]);

    useEffect(() => {
      if (initialModel) {
        setModel(initialModel);
        onModelChange?.(initialModel);
      }
      // only when URL/model seed changes
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialModel]);

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
          // Prefer desk-routable engines (featured research first from API order)
          const desk = json.data?.desk_engines ?? [];
          const all = json.data?.engines ?? [];
          const list = desk.length
            ? [...desk, ...all.filter((id) => !desk.includes(id))]
            : all;
          const meta: Record<string, { kind?: string; desk?: boolean }> = {};
          for (const m of json.data?.models ?? []) {
            meta[m.id] = { kind: m.kind, desk: m.desk_compatible };
          }
          if (!cancelled) {
            setEngines(list);
            setModelMeta(meta);
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

    const buildValues = useCallback(
      (patch?: Partial<AnalyzeFormValues>): AnalyzeFormValues | null => {
        const sym = (patch?.symbol ?? symbol).trim().toUpperCase();
        if (!sym) return null;
        return {
          symbol: sym,
          account: patch?.account ?? account,
          riskPct: patch?.riskPct ?? riskPct,
          model: patch?.model ?? model,
          period: patch?.period ?? period,
          interval: patch?.interval ?? interval,
        };
      },
      [symbol, account, riskPct, model, period, interval],
    );

    useImperativeHandle(
      ref,
      () => ({
        submitWith(patch) {
          const values = buildValues(patch);
          if (!values || disabled) return;
          if (patch?.model) {
            setModel(patch.model);
            onModelChange?.(patch.model);
          }
          if (patch?.symbol) setSymbol(patch.symbol.trim().toUpperCase());
          onSubmit(values);
        },
        setModel(next: string) {
          handleModel(next);
        },
      }),
      [buildValues, disabled, handleModel, onModelChange, onSubmit],
    );

    const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      const values = buildValues();
      if (!values || disabled) return;
      onSubmit(values);
    };

    return (
      <form onSubmit={handleSubmit} className="td-toolbar" aria-label="Analyze controls">
        <div className="td-toolbar__row">
          <label className="td-field td-field--grow">
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

          <label className="td-field td-field--account">
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

          <label className="td-field td-field--risk">
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

          <label className="td-field td-field--model">
            <span className="td-label">Model</span>
            <select
              className="td-input"
              name="model"
              value={model}
              onChange={(e) => handleModel(e.target.value)}
              disabled={disabled}
              style={{ fontFamily: "var(--td-font-mono)" }}
            >
              <option value="auto">auto · pick best for symbol</option>
              {engines.map((id) => {
                const meta = modelMeta[id];
                const tag =
                  meta?.kind === "options"
                    ? " · opts"
                    : meta?.desk === false
                      ? " · other"
                      : "";
                return (
                  <option key={id} value={id}>
                    {id}
                    {tag}
                  </option>
                );
              })}
            </select>
          </label>

          <button
            type="submit"
            className="td-btn td-btn-primary td-btn--run"
            disabled={disabled || !symbol.trim()}
          >
            <Play size={14} strokeWidth={1.75} aria-hidden />
            {disabled ? "Running…" : "Run"}
          </button>
        </div>

        {modelsError ? (
          <p className="text-[11px]" style={{ color: "var(--td-action-avoid)" }}>
            Models catalog: {modelsError}
          </p>
        ) : null}

        <button
          type="button"
          className="td-advanced-toggle"
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
          <div className="td-toolbar__row td-toolbar__row--sub">
            <label className="td-field td-field--account">
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
            <label className="td-field td-field--account">
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
  },
);
