import type { AnalyzeResponse } from "./types";

export type PipelineStageStatus =
  | "idle"
  | "running"
  | "pass"
  | "fail"
  | "neutral";

export interface PipelineStage {
  id: string;
  label: string;
  status: PipelineStageStatus;
  detail?: string;
  values?: Record<string, unknown>;
}

function finite(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n);
}

function actionStatus(action: string | undefined): PipelineStageStatus {
  if (!action) return "neutral";
  const a = action.toUpperCase();
  if (a.includes("BUY")) return "pass";
  if (a.includes("AVOID")) return "fail";
  return "neutral";
}

/**
 * Build visual pipeline stages from analyze state.flags + levels.
 * Statuses are pass/fail/neutral once data exists (idle/running are UI pre-run).
 */
export function buildPipelineStages(
  analyze: AnalyzeResponse,
): PipelineStage[] {
  const state = analyze.state ?? ({} as AnalyzeResponse["state"]);
  const flags = state.flags ?? {};
  const plan = analyze.plan;
  const size = analyze.size;

  const ohlcvPass = finite(state.price);
  const vpPass =
    finite(state.poc) && finite(state.val) && finite(state.vah);

  const htfFlag = flags.htf_ha_green;
  const htfStatus: PipelineStageStatus =
    htfFlag === true ? "pass" : htfFlag === false ? "fail" : "neutral";

  const setupKind = state.setup_kind;
  let ruleStatus: PipelineStageStatus = "neutral";
  if (setupKind === "structural_break" || state.setup_ok === false) {
    ruleStatus = "fail";
  } else if (state.setup_ok === true || (setupKind && setupKind !== "none")) {
    ruleStatus = "pass";
  }

  const filterBits: { key: string; ok: boolean | undefined }[] = [
    {
      key: "vwap",
      ok:
        flags.above_vwap === true || flags.vwap_uptrend === true
          ? true
          : flags.above_vwap === false && flags.vwap_uptrend === false
            ? false
            : flags.above_vwap ?? flags.vwap_uptrend,
    },
    { key: "vol", ok: flags.vol_confirm_or_pull },
    { key: "red_flag", ok: flags.not_red_flag },
    { key: "squeeze", ok: flags.sqz_off_or_release },
  ];
  const known = filterBits.filter((b) => b.ok !== undefined);
  let filterStatus: PipelineStageStatus = "neutral";
  if (known.length > 0) {
    filterStatus = known.every((b) => b.ok) ? "pass" : "fail";
  }

  const emaBits = [state.above_ema22, state.above_ema200, state.near_ema22];
  const emaKnown = emaBits.filter((b) => typeof b === "boolean");
  let structureStatus: PipelineStageStatus = "neutral";
  if (emaKnown.length > 0) {
    if (state.above_ema22 === false && state.above_ema200 === false) {
      structureStatus = "fail";
    } else if (state.above_ema22 === true || state.above_ema200 === true) {
      structureStatus = "pass";
    } else if (state.near_ema22 === true) {
      structureStatus = "pass";
    }
  }

  const sizePresent =
    size != null && finite(size.shares) && size.shares > 0;

  return [
    {
      id: "ohlcv",
      label: "OHLCV",
      status: ohlcvPass ? "pass" : "fail",
      detail: ohlcvPass ? undefined : "Missing price",
      values: {
        price: state.price,
        asof: state.asof,
        interval: state.interval,
        atr: state.atr,
      },
    },
    {
      id: "volume_profile",
      label: "Volume profile POC/VAL/VAH",
      status: vpPass ? "pass" : "fail",
      detail: vpPass ? undefined : "Incomplete POC/VAL/VAH",
      values: { poc: state.poc, val: state.val, vah: state.vah },
    },
    {
      id: "htf_ha",
      label: "HTF St.MACD-HA",
      status: htfStatus,
      detail:
        htfFlag === true
          ? "HA green"
          : htfFlag === false
            ? "HA not green"
            : "HTF flag unavailable",
      values: { htf: state.htf, htf_ha_green: htfFlag },
    },
    {
      id: "rule_candidate",
      label: "Rule candidate",
      status: ruleStatus,
      detail: setupKind ?? (state.setup_ok ? "setup_ok" : "no setup"),
      values: {
        setup_kind: setupKind,
        setup_ok: state.setup_ok,
        breakout_ready: state.breakout_ready,
      },
    },
    {
      id: "filters",
      label: "Filters VWAP/vol/red-flag/squeeze",
      status: filterStatus,
      detail:
        known.map((b) => `${b.key}:${b.ok ? "ok" : "fail"}`).join(" · ") ||
        "no filter flags",
      values: {
        above_vwap: flags.above_vwap,
        vwap_uptrend: flags.vwap_uptrend,
        vol_confirm_or_pull: flags.vol_confirm_or_pull,
        not_red_flag: flags.not_red_flag,
        sqz_off_or_release: flags.sqz_off_or_release,
      },
    },
    {
      id: "structure_ema",
      label: "Structure EMA22/200",
      status: structureStatus,
      detail:
        [
          state.above_ema22 != null
            ? `ema22:${state.above_ema22 ? "above" : "below"}`
            : null,
          state.above_ema200 != null
            ? `ema200:${state.above_ema200 ? "above" : "below"}`
            : null,
          state.near_ema22 ? "near_ema22" : null,
        ]
          .filter(Boolean)
          .join(" · ") || "EMA flags unavailable",
      values: {
        near_ema22: state.near_ema22,
        above_ema22: state.above_ema22,
        above_ema200: state.above_ema200,
        ema22: state.ema22,
        ema200: state.ema200,
      },
    },
    {
      id: "risk_kelly",
      label: "Risk/Kelly sizing",
      status: sizePresent ? "pass" : "neutral",
      detail: sizePresent
        ? `${size!.shares} sh · risk ${
            size!.risk_pct != null && Number.isFinite(size!.risk_pct)
              ? `${(size!.risk_pct * 100).toFixed(2)}%`
              : "—"
          }`
        : "No size",
      values: size
        ? {
            shares: size.shares,
            notional: size.notional,
            dollar_risk: size.dollar_risk,
            risk_pct: size.risk_pct,
            sleeve_fraction: state.sleeve_fraction,
          }
        : { sleeve_fraction: state.sleeve_fraction },
    },
    {
      id: "action",
      label: "Action",
      status: actionStatus(plan?.action),
      detail: plan?.action ?? "no plan",
      values: {
        action: plan?.action,
        why: plan?.why,
        do_next: plan?.do_next,
        confidence: state.confidence,
      },
    },
  ];
}
