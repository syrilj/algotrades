"use client";

import { useCallback, useEffect, useState } from "react";
import { PicksList, type PickRow } from "@/components/picks/PicksList";
import {
  PicksPanel,
  type PicksPanelValue,
} from "@/components/picks/PicksPanel";
import type { ApiEnvelope, ModelsCatalog } from "@/lib/types";

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function parseSymbols(raw: string): string[] {
  return raw
    .split(/[,\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
}

function normalizePickRow(item: unknown): PickRow | null {
  const root = asRecord(item);
  if (!root) return null;

  const state = asRecord(root.state) ?? root;
  const plan = asRecord(root.plan);
  const size = asRecord(root.size) ?? asRecord(root.sizing);
  const symbol = str(state.symbol) ?? str(root.symbol);
  if (!symbol) return null;

  return {
    symbol: symbol.toUpperCase(),
    action:
      str(plan?.action) ?? str(root.action) ?? str(state.action) ?? "WAIT",
    setupKind:
      str(state.setup_kind) ?? str(root.setup_kind) ?? str(root.setupKind),
    price: num(state.price) ?? num(root.price),
    confidence: num(state.confidence) ?? num(root.confidence),
    dollarRisk:
      num(size?.dollar_risk) ??
      num(size?.dollarRisk) ??
      num(root.dollar_risk) ??
      num(root.dollarRisk),
    doNext: str(plan?.do_next) ?? str(root.do_next) ?? str(root.doNext),
    model: str(root.model) ?? str(state.model),
  };
}

function extractPickRows(payload: unknown): PickRow[] {
  const env = asRecord(payload);
  const data: unknown = env?.data ?? payload;

  if (Array.isArray(data)) {
    return data.map(normalizePickRow).filter(Boolean) as PickRow[];
  }

  const rec = asRecord(data);
  if (!rec) return [];

  for (const key of ["picks", "rows", "results", "items", "groups"]) {
    const v = rec[key];
    if (!Array.isArray(v)) continue;
    if (key === "groups") {
      const flat: PickRow[] = [];
      for (const g of v) {
        const gr = asRecord(g);
        const nested = gr?.rows ?? gr?.picks ?? gr?.items;
        if (Array.isArray(nested)) {
          for (const r of nested) {
            const n = normalizePickRow(r);
            if (n) flat.push(n);
          }
        }
      }
      return flat;
    }
    return v.map(normalizePickRow).filter(Boolean) as PickRow[];
  }

  const single = normalizePickRow(data);
  return single ? [single] : [];
}

async function fetchModels(): Promise<string[]> {
  const res = await fetch("/api/models");
  const json = (await res.json()) as ApiEnvelope<ModelsCatalog> | ModelsCatalog;
  const catalog =
    "data" in json && json.data ? json.data : (json as ModelsCatalog);
  const ids =
    catalog.models?.map((m) => m.id) ??
    catalog.all_versions ??
    catalog.engines ??
    [];
  return [...new Set(ids)].filter(Boolean);
}

export default function PicksPage() {
  const [panel, setPanel] = useState<PicksPanelValue>({
    horizon: "day",
    model: "auto",
    sectors: ["mag7", "memory", "photonics"],
    symbols: "",
  });
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<PickRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scanned, setScanned] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchModels()
      .then((ids) => {
        if (!cancelled) setModels(ids);
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        horizon: panel.horizon,
      };
      if (panel.model && panel.model !== "auto") body.model = panel.model;
      if (panel.sectors.length) body.sectors = panel.sectors;
      const symbols = parseSymbols(panel.symbols);
      if (symbols.length) body.symbols = symbols;

      const res = await fetch("/api/picks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const json: unknown = await res.json().catch(() => null);
      const env = asRecord(json);
      if (!res.ok || (env && env.ok === false)) {
        throw new Error(
          str(env?.error) ?? `Picks request failed (${res.status})`,
        );
      }

      setRows(extractPickRows(json));
      setScanned(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Picks request failed");
    } finally {
      setLoading(false);
    }
  }, [panel]);

  return (
    <div className="flex min-h-full flex-col bg-[var(--td-ink-900,#12181F)] text-[var(--td-ink-200,#CBD5E1)]">
      <header className="border-b border-[var(--td-ink-600,#334155)] px-4 py-3">
        <h1 className="text-[20px] font-semibold text-[var(--td-ink-100,#E2E8F0)]">
          Picks
        </h1>
        <p className="text-[12px] text-[var(--td-ink-400,#64748B)]">
          Horizon + sector scan · grouped by action
        </p>
      </header>

      <PicksPanel
        value={panel}
        models={models}
        loading={loading}
        onChange={setPanel}
        onRun={() => {
          void run();
        }}
      />

      <PicksList
        rows={rows}
        loading={loading}
        error={error}
        emptyHint={
          scanned
            ? "Scan returned no live setups for this filter."
            : "Choose horizon and sectors, then Scan."
        }
      />
    </div>
  );
}
