import { NextResponse } from "next/server";

import { sanitizeSymbol } from "@/lib/format";
import { runLivePlan, runOptionsPicker } from "@/lib/tradeDesk";
import type { ApiEnvelope, LivePlanResponse, OptionsPlanResponse } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const PLAYBOOK = {
  account_fit: "$1k-style book: max risk ~10–15% premium per idea, prefer 1 structure at a time.",
  default_structure: "ATM long call ~21 DTE (OOS default). Spreads if capital / IV requires.",
  preferred: ["IONQ", "AVGO", "HOOD", "MU", "APLD"],
  avoid_atm: [] as string[],
  rules: [
    "Equity SIDE / size = WINNER (v39b_live_adapt) via live_plan — react to nodes + VPA.",
    "Options structure = OPTIONS_WINNER (v29/v32 path) + options_picker — never naked short premium.",
    "Skip 0–3 DTE lottery; prefer ~21 DTE ATM so theta/side DNA can work.",
    "FOMC day + elevated VIX → no new risk.",
    "Paper closes feed live_adapt size mult for next tickets (IB-ready LAST_TICKET.json).",
    "Live structure still goes through options_picker + risk_manager gates.",
  ],
  live_variant: "v29_coldstart_opts",
  equity_winner: "v39b_live_adapt",
  live_engine_note:
    "Equity: WINNER v39b_live_adapt. Options OOS champion: v29_coldstart_opts / OPTIONS_WINNER.json. Desk does not auto-route to IB.",
  oos_artifact: "runs/poc_va_v29_oos_challenge/REPORT.md",
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
      : 0.18;
  const riskOk = Number.isFinite(riskPct) && riskPct > 0 && riskPct <= 1;

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
        ...(riskOk ? ["--risk-pct", String(riskPct)] : []),
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
    playbook: PLAYBOOK,
    research: {
      v22_variant: "v22_robust_conservative",
      robust_path: "/robust",
      note: PLAYBOOK.live_engine_note,
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
