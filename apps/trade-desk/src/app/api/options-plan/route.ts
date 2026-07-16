import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import {
  runLivePlan,
  runOptionsPicker,
  runOptionsUnusualFlow,
  runVolPackageScore,
} from "@/lib/tradeDesk";
import type {
  ApiEnvelope,
  LivePlanResponse,
  OptionsPlanResponse,
  UnusualOptionsFlow,
  VolPackageScore,
} from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const PLAYBOOK = {
  account_fit:
    "Small book: risk only the debit you can lose on one structure. Prefer 1 defined-risk spread at a time.",
  default_structure:
    "Default: bull call debit spread, ~14–45 DTE. Single long call only if max loss fits the risk budget.",
  preferred: ["IONQ", "APLD", "AVGO", "HOOD", "TSLA"],
  avoid_atm: ["MU"],
  rules: [
    "Only size when mode is OPTIONS_ATTACK and structure action is buy.",
    "Defined risk only — never naked short premium on a small account.",
    "Skip 0–3 DTE lottery tickets; target ~2–6 weeks so the trade has time to work.",
    "Cut losers early (−30% of premium). Trail after +40%. Flat by ~5 DTE.",
    "No new risk on FOMC day or when VIX is elevated and the book is already hot.",
    "Vol package scores are research context only — they never green-light a trade alone.",
  ],
  live_variant: "v35_softstruct_bag8",
  equity_winner: "v72_dual_sleeve",
  live_engine_note:
    "Side and size still come from the live equity ticket. Options structure is a defined-risk proposal from the options picker. Desk does not auto-send to IB.",
  oos_artifact: "models/poc_va_macdha/OPTIONS_WINNER.json",
  ib_ticket_path: "runs/live_adapt/LAST_TICKET.json",
};

function envelope<T>(
  partial: Omit<ApiEnvelope<T>, "asof"> & { asof?: string },
  status: number,
): NextResponse {
  const body: ApiEnvelope<T> = {
    ...partial,
    asof: partial.asof ?? new Date().toISOString(),
  };
  return NextResponse.json(body, { status });
}

type Body = {
  symbol?: string;
  account?: number | string;
  peak?: number | string;
  risk_pct?: number | string;
  force_structure?: boolean;
  noModel?: boolean;
};

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return envelope(
      { ok: false, command: "options-plan", error: "Invalid JSON body" },
      400,
    );
  }

  const symbol = sanitizeSymbol(body.symbol);
  if (!symbol) {
    return envelope(
      { ok: false, command: "options-plan", error: "symbol required" },
      400,
    );
  }

  const account = body.account != null ? Number(body.account) : 1000;
  if (!Number.isFinite(account) || account <= 0) {
    return envelope(
      { ok: false, command: "options-plan", error: "Invalid account" },
      400,
    );
  }

  const riskPct =
    body.risk_pct != null && body.risk_pct !== ""
      ? Number(body.risk_pct)
      : 18;
  const riskOk = Number.isFinite(riskPct) && riskPct > 0 && riskPct <= 100;

  const planArgs: string[] = ["--symbol", symbol, "--account", String(account)];
  if (body.peak != null && body.peak !== "") {
    const peak = Number(body.peak);
    if (Number.isFinite(peak) && peak > 0) planArgs.push("--peak", String(peak));
  }
  if (body.noModel) planArgs.push("--no-model");
  // Equity WINNER for side/confidence (live_plan resolves empty → WINNER)
  else planArgs.push("--model", "auto");

  let live: LivePlanResponse | null = null;
  let liveError: string | null = null;
  try {
    live = (await runLivePlan(planArgs, 90_000)) as LivePlanResponse;
  } catch (e) {
    liveError = e instanceof Error ? e.message : String(e);
  }

  // Always propose structure so the desk can show "what the contract would be"
  // even when risk mode says stand aside (clearly labeled).
  let structure: OptionsPlanResponse["structure"] = null;
  let structureError: string | null = null;
  try {
    const raw = (await runOptionsPicker(
      [
        "--symbol",
        symbol,
        "--account",
        String(account),
        // UI/route speak percent points; Python --risk-pct is a fraction.
        ...(riskOk ? ["--risk-pct", String(riskPct / 100)] : []),
      ],
      60_000,
    )) as Record<string, unknown>;
    structure = raw as OptionsPlanResponse["structure"];
  } catch (e) {
    structureError = e instanceof Error ? e.message : String(e);
  }

  if (!live && !structure) {
    return envelope(
      {
        ok: false,
        command: "options-plan",
        error: liveError || structureError || "options plan failed",
      },
      502,
    );
  }

  // Research-only vol package scores (partial failure OK).
  let volPackage: VolPackageScore | null = null;
  let volPackageError: string | null = null;
  try {
    volPackage = (await runVolPackageScore(
      ["--symbol", symbol],
      90_000,
    )) as VolPackageScore;
  } catch (e) {
    volPackageError = e instanceof Error ? e.message : String(e);
  }

  // Same-day unusual options flags from chain aggregates (partial failure OK).
  let unusualFlow: UnusualOptionsFlow | null = null;
  let unusualFlowError: string | null = null;
  try {
    unusualFlow = (await runOptionsUnusualFlow(
      ["--symbol", symbol, "--max-expiries", "6", "--max-dte", "45", "--top", "20"],
      90_000,
    )) as UnusualOptionsFlow;
  } catch (e) {
    unusualFlowError = e instanceof Error ? e.message : String(e);
  }

  const ticket = live?.ticket;
  const mode = ticket?.mode ?? live?.decision?.mode ?? "STAND_ASIDE";
  const vehicle = ticket?.vehicle ?? live?.decision?.vehicle ?? "none";

  const doNext: string[] = [];
  if (String(mode).includes("OPTIONS") && structure && structure.action === "buy") {
    doNext.push(
      `Mode ${mode}: buy ${structure.structure ?? "structure"} on ${symbol}.`,
    );
    doNext.push(
      `Long ${structure.long_strike}${structure.short_strike != null ? ` / short ${structure.short_strike}` : ""} · exp ${structure.expiry} (${structure.dte}d).`,
    );
    doNext.push(
      `Debit ~$${structure.debit_per_share} · max loss ~$${structure.max_loss_1_contract} (budget $${structure.budget}).`,
    );
    doNext.push("Exit: cut −30% · trail after +40% premium · flat by 5 DTE.");
  } else if (String(mode).includes("EQUITY")) {
    doNext.push(`Mode ${mode}: equity hedge / stock path — not options attack.`);
    doNext.push("Use Analyze for shares/stop · re-check Options only if conviction rises.");
    if (structure?.action === "buy") {
      doNext.push(
        `Reference structure (not green-lit): ${structure.structure} exp ${structure.expiry}.`,
      );
    }
  } else if (structure?.action === "skip" || structure?.error) {
    doNext.push(
      structure.reason || structure.error || "No affordable options structure.",
    );
    doNext.push("Stand aside or use equity ticket — do not force lottery premium.");
  } else if (structure?.action === "buy") {
    doNext.push(
      `Risk mode is ${mode} — structure below is a proposal only, not a go signal.`,
    );
    doNext.push(
      `${structure.structure} · exp ${structure.expiry} · max loss ~$${structure.max_loss_1_contract}.`,
    );
    doNext.push("Wait for OPTIONS_ATTACK / Live green light before sizing in.");
  } else {
    doNext.push(ticket?.steps?.[0] || `Stand aside on ${symbol}.`);
    doNext.push("Re-scan Live book or pick a preferred options name (APLD / IONQ).");
  }

  const rec = volPackage?.recommended;
  const dangerWarnings = (volPackage?.warnings ?? []).filter(
    (w) => w.severity === "danger" || w.severity === "watch",
  );
  for (const w of dangerWarnings.slice(0, 3)) {
    doNext.push(`WARN: ${w.message}`);
  }
  if (rec && rec.action === "consider" && rec.template) {
    doNext.push(
      `Vol research: ${rec.template} scored consider (edge proxy ${rec.edge_after_cost_proxy ?? "—"}) — not a live attack signal.`,
    );
  } else if (volPackageError) {
    doNext.push("Vol package scorer unavailable — directional structure path still valid.");
  }

  const topFlags = unusualFlow?.flags ?? unusualFlow?.unusual ?? [];
  if (topFlags.length > 0) {
    const head = topFlags[0];
    doNext.push(
      `Unusual flow: ${topFlags.length} flag(s) — top ${head.right}${head.strike} ${head.expiry} (${head.reason || head.reasons?.slice(0, 2).join("; ") || "chain pressure"}).`,
    );
  } else if (unusualFlow && unusualFlow.ok && topFlags.length === 0) {
    doNext.push("No unusual options flow flagged on the latest chain snapshot.");
  } else if (unusualFlowError) {
    doNext.push("Unusual flow scanner unavailable — structure ticket still valid.");
  }

  const data: OptionsPlanResponse = {
    ok: true,
    symbol,
    account,
    mode: String(mode),
    vehicle: String(vehicle),
    do_next: doNext,
    ticket: ticket ?? null,
    live: live?.live ?? null,
    macro: live?.macro ?? null,
    options_from_ticket: live?.options ?? null,
    structure,
    structure_error: structureError,
    live_error: liveError,
    vol_package: volPackage,
    vol_package_error: volPackageError,
    unusual_flow: unusualFlow,
    unusual_flow_error: unusualFlowError,
    playbook: PLAYBOOK,
    research: {
      v22_variant: "v22_robust_conservative",
      robust_path: "/robust",
      note: PLAYBOOK.live_engine_note,
      options_winner: "v35_softstruct_bag8",
      vol_program: "docs/plans/2026-07-15-options-vol-research-to-production.md",
    },
    asof_utc: live?.asof_utc ?? new Date().toISOString(),
  };

  return envelope(
    {
      ok: true,
      command: "options-plan",
      data,
      asof: data.asof_utc,
    },
    200,
  );
}
