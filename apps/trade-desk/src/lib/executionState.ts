export type FreshnessLike = {
  available?: boolean;
  stale?: boolean;
  market_session?: string;
  freshness_basis?: string;
};

type ExecutionPlanLike = {
  ok?: boolean;
  live_ready?: boolean;
  symbol?: string;
  account?: number;
  decision_support_ready?: boolean;
  live?: {
    price?: number;
    go_long?: boolean;
    go_short?: boolean;
    freshness?: FreshnessLike;
  };
  confidence?: { state?: string; reasons?: string[] };
  ticket?: {
    action?: string;
    mode?: string;
    vehicle?: string;
    max_loss_dollars?: number;
    analysis_action?: string;
    execution_blocked?: boolean;
  };
  decision?: {
    mode?: string;
    analysis_action?: string;
    execution_blocked?: boolean;
    action?: string;
  };
  execution_readiness?: { ready?: boolean; blockers?: string[] };
  model?: {
    model?: string;
    entry?: number;
    stop?: number;
    action_hint?: string;
  };
  gex?: {
    spot?: number;
    price_consistent?: boolean;
  } | null;
};

/** Analysis setup (BUY NOW / WAIT) is not the same as risk mode or paper-order unlock. */
export function analysisSetupLabel(plan: ExecutionPlanLike): string {
  return (
    plan.decision?.analysis_action ||
    plan.ticket?.analysis_action ||
    plan.model?.action_hint ||
    "—"
  );
}

export function riskModeLabel(plan: ExecutionPlanLike): string {
  return plan.ticket?.mode || plan.decision?.mode || "STAND_ASIDE";
}

export type FeedPresentation = {
  canUse: boolean;
  label: string;
  tone: "live" | "closed-current" | "blocked" | "unknown";
};

export function feedPresentation(
  freshness: FreshnessLike | null | undefined,
): FeedPresentation {
  if (!freshness?.available) {
    return { canUse: false, label: "Feed unavailable", tone: "unknown" };
  }
  if (freshness.stale) {
    return {
      canUse: false,
      label: "Stale — do not execute",
      tone: "blocked",
    };
  }
  if (
    freshness.market_session === "closed" &&
    freshness.freshness_basis === "latest_completed_session"
  ) {
    return {
      canUse: true,
      label: "Latest session close",
      tone: "closed-current",
    };
  }
  return { canUse: true, label: "Live feed", tone: "live" };
}

function finitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

export function isExecutionActionable(plan: ExecutionPlanLike): boolean {
  const freshness = feedPresentation(plan.live?.freshness);
  const entry = plan.model?.entry ?? plan.live?.price;
  const stop = plan.model?.stop;
  return Boolean(
    plan.ok !== false &&
      plan.decision_support_ready &&
      plan.live_ready === true &&
      plan.execution_readiness?.ready === true &&
      plan.confidence?.state === "ENTER" &&
      plan.ticket?.action === "enter" &&
      plan.ticket?.vehicle === "equity" &&
      freshness.canUse &&
      finitePositive(plan.live?.price) &&
      finitePositive(entry) &&
      finitePositive(stop) &&
      entry !== stop &&
      finitePositive(plan.ticket?.max_loss_dollars) &&
      plan.gex?.price_consistent !== false,
  );
}

export function decisionPresentation(plan: ExecutionPlanLike): {
  eyebrow: string;
  title: string;
  detail: string;
} {
  const state = plan.confidence?.state ?? "ABSTAIN";
  const reasons = plan.confidence?.reasons ?? [];
  const setup = analysisSetupLabel(plan);
  const riskMode = riskModeLabel(plan);
  const setupNote =
    setup && setup !== "—"
      ? ` Analysis setup is "${setup}" (risk mode ${riskMode}) — that is not the same as unlocking a paper order.`
      : "";

  // "Ready" only when the same gates that unlock a paper order all pass.
  // Never claim SETUP READY from confidence alone (false ready is unsafe).
  if (isExecutionActionable(plan)) {
    return {
      eyebrow: "SETUP READY",
      title: "Ready to execute",
      detail: "The data, confidence, and risk gates passed. Review the order before logging it.",
    };
  }
  if (state === "ENTER" && plan.execution_readiness?.ready === false) {
    return {
      eyebrow: "PAPER ORDER LOCKED",
      title: "Signal cleared; order still blocked",
      detail:
        "Confidence said enter, but portfolio, data-source, risk, or sizing checks failed." +
        setupNote,
    };
  }
  if (state === "ENTER" && plan.ticket?.action === "enter") {
    return {
      eyebrow: "PAPER ORDER LOCKED",
      title: "Signal cleared; order still blocked",
      detail:
        "Confidence said enter, but feed freshness, sizing, price consistency, or vehicle checks still block an order." +
        setupNote,
    };
  }
  if (state === "WATCH") {
    return {
      eyebrow: "NO TRADE YET",
      title: "Watch the setup",
      detail:
        "The idea is valid, but an entry gate is still open. Wait for the next refresh." +
        setupNote,
    };
  }
  if (reasons.includes("market_data_stale_or_unavailable")) {
    return {
      eyebrow: "PAPER ORDER LOCKED",
      title: "Feed not ready for execution",
      detail:
        "Fresh market data is unavailable. Refresh the live feed before sizing an order." +
        setupNote,
    };
  }
  if (reasons.some((reason) => reason.includes("calibration"))) {
    return {
      eyebrow: "PAPER ORDER LOCKED",
      title: "Live calibration not active",
      detail:
        "Paper orders stay locked without an active calibration. You can still read setup, options, and gamma." +
        setupNote,
    };
  }
  return {
    eyebrow: "PAPER ORDER LOCKED",
    title: "No executable order yet",
    detail:
      "Cash is fine. Analysis can still show a setup or levels — paper size only unlocks when every execution gate passes." +
      setupNote,
  };
}

export function buildPaperOrder(plan: ExecutionPlanLike) {
  if (!isExecutionActionable(plan)) return null;
  const entry = plan.model?.entry ?? plan.live?.price;
  const stop = plan.model?.stop;
  const maxLoss = plan.ticket?.max_loss_dollars;
  if (!finitePositive(entry) || !finitePositive(stop) || !finitePositive(maxLoss)) {
    return null;
  }
  const riskPerShare = Math.abs(entry - stop);
  const side = plan.live?.go_short ? ("short" as const) : ("long" as const);
  if ((side === "long" && stop >= entry) || (side === "short" && stop <= entry)) {
    return null;
  }
  if (!finitePositive(plan.account)) return null;
  const riskShares = Math.floor(maxLoss / riskPerShare);
  const buyingPowerShares = Math.floor(plan.account / entry);
  const shares = Math.min(riskShares, buyingPowerShares);
  if (shares < 1) return null;
  return {
    symbol: String(plan.symbol ?? "").toUpperCase(),
    side,
    shares,
    entry,
    stop,
    dollarRisk: shares * riskPerShare,
    model: plan.model?.model ?? "auto",
    account: plan.account,
  };
}

export function gammaMethodology(gamma: { exposure_kind?: string } | null | undefined) {
  if (gamma?.exposure_kind === "intraday_gamma_flow_proxy") {
    return {
      label: "Intraday gamma-flow proxy",
      detail: "Uses today's option flow; it is not known dealer inventory.",
    };
  }
  return {
    label: "Dealer positioning estimate",
    detail: "Uses open interest with an inferred dealer-side sign convention.",
  };
}

type GammaFreshnessClock = string | null | undefined;

type GammaFreshnessSource = {
  options_asof?: string | null;
  asof_utc?: string | null;
  exposure_kind?: string | null;
};

export type GammaFreshness = {
  dataAsof: string | null;
  dataDate: Date;
  hasTimestamp: boolean;
  ageMinutes: number;
  staleHours: number | null;
  isStale: boolean;
  isCurrent: boolean;
  /** Age of chain last-trade stamp when known (OI can be hours old by design). */
  chainAgeMinutes: number;
  hasChainTimestamp: boolean;
  snapshotAsof: string | null;
};

function parseFreshnessClock(
  value: GammaFreshnessClock,
  now: Date,
  maxAgeMinutes: number,
): Omit<GammaFreshness, "chainAgeMinutes" | "hasChainTimestamp" | "snapshotAsof"> {
  const dataDate = new Date(value ?? 0);
  const hasTimestamp = value != null && Number.isFinite(dataDate.getTime());
  const ageMinutes = hasTimestamp
    ? Math.max(0, Math.round((now.getTime() - dataDate.getTime()) / 60_000))
    : Number.POSITIVE_INFINITY;
  const isStale = !hasTimestamp || ageMinutes > maxAgeMinutes;
  return {
    dataAsof: value ?? null,
    dataDate,
    hasTimestamp,
    ageMinutes,
    staleHours: Number.isFinite(ageMinutes) ? Math.round(ageMinutes / 60) : null,
    isStale,
    isCurrent: hasTimestamp && !isStale,
  };
}

/**
 * Snapshot usability for gamma levels.
 *
 * Pass a raw timestamp string for legacy checks, or a gamma payload object:
 * - dealer OI: clock is `asof_utc` (when we built the snapshot). Chain
 *   `options_asof` is last-trade time and is often hours old by design — it must
 *   not hide walls / squeeze.
 * - intraday flow proxy: prefer live `options_asof`, fall back to `asof_utc`.
 */
export function gammaFreshness(
  value: GammaFreshnessClock | GammaFreshnessSource,
  now = new Date(),
  maxAgeMinutes = 90,
): GammaFreshness {
  if (value == null || typeof value === "string") {
    const base = parseFreshnessClock(value, now, maxAgeMinutes);
    return {
      ...base,
      chainAgeMinutes: base.ageMinutes,
      hasChainTimestamp: base.hasTimestamp,
      snapshotAsof: value ?? null,
    };
  }

  const isFlowProxy = value.exposure_kind === "intraday_gamma_flow_proxy";
  // OI last-trade stamps are delayed; snapshot time is what decides "current".
  const clock: GammaFreshnessClock = isFlowProxy
    ? (value.options_asof ?? value.asof_utc)
    : (value.asof_utc ?? value.options_asof);

  const snapshot = parseFreshnessClock(clock, now, maxAgeMinutes);
  const chain = parseFreshnessClock(value.options_asof, now, maxAgeMinutes);

  return {
    ...snapshot,
    // Surface chain trade time for the "options updated" label when present.
    dataAsof: value.options_asof ?? value.asof_utc ?? null,
    dataDate: chain.hasTimestamp
      ? chain.dataDate
      : snapshot.dataDate,
    hasTimestamp: snapshot.hasTimestamp,
    chainAgeMinutes: chain.ageMinutes,
    hasChainTimestamp: chain.hasTimestamp,
    snapshotAsof: value.asof_utc ?? null,
  };
}

/**
 * Presentation contract for gamma desk boards.
 *
 * Viewing walls / flip / strike map is allowed whenever a parseable snapshot
 * exists. Freshness only labels age and may still block *execution* elsewhere.
 * Never hide levels solely because the snapshot is aged or markets are closed.
 */
export type GammaDeskPresentation = {
  /** Always true when `hasSnapshot` — map and levels stay mounted. */
  showLevels: boolean;
  hasSnapshot: boolean;
  isStale: boolean;
  isCurrent: boolean;
  ageMinutes: number | null;
  banner: string | null;
  sessionLabel: "live" | "latest_session" | "aged" | "unknown";
};

export function gammaDeskPresentation(
  gamma: GammaFreshnessSource | null | undefined,
  now = new Date(),
  maxAgeMinutes = 90,
): GammaDeskPresentation {
  if (!gamma) {
    return {
      showLevels: false,
      hasSnapshot: false,
      isStale: true,
      isCurrent: false,
      ageMinutes: null,
      banner: null,
      sessionLabel: "unknown",
    };
  }
  const freshness = gammaFreshness(gamma, now, maxAgeMinutes);
  const hasSnapshot = true;
  if (freshness.isCurrent) {
    return {
      showLevels: true,
      hasSnapshot,
      isStale: false,
      isCurrent: true,
      ageMinutes: freshness.hasTimestamp ? freshness.ageMinutes : null,
      banner: null,
      sessionLabel: "live",
    };
  }
  if (freshness.hasTimestamp) {
    return {
      showLevels: true,
      hasSnapshot,
      isStale: true,
      isCurrent: false,
      ageMinutes: freshness.ageMinutes,
      banner: `Snapshot is ${freshness.ageMinutes} minutes old (latest session / not live). Levels stay visible for analysis — do not treat as a live execution quote.`,
      sessionLabel: "aged",
    };
  }
  return {
    showLevels: true,
    hasSnapshot,
    isStale: true,
    isCurrent: false,
    ageMinutes: null,
    banner:
      "No usable snapshot time from the gamma run. Levels stay visible with unknown age — refresh before relying on them for timing.",
    sessionLabel: "unknown",
  };
}
