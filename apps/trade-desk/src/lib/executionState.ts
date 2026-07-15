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
  };
  execution_readiness?: { ready?: boolean; blockers?: string[] };
  model?: {
    model?: string;
    entry?: number;
    stop?: number;
  };
  gex?: {
    spot?: number;
    price_consistent?: boolean;
  } | null;
};

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
      eyebrow: "NO TRADE",
      title: "Execution checks blocked this plan",
      detail: "The signal passed, but the portfolio, data-source, risk, or concrete-order checks did not. Review the failed checks before proceeding.",
    };
  }
  if (state === "ENTER" && plan.ticket?.action === "enter") {
    return {
      eyebrow: "NO TRADE",
      title: "Execution checks blocked this plan",
      detail: "Confidence said enter, but feed freshness, sizing, price consistency, or vehicle checks still block an order.",
    };
  }
  if (state === "WATCH") {
    return {
      eyebrow: "NO TRADE YET",
      title: "Watch the setup",
      detail: "The idea is valid, but an entry gate is still open. Wait for the next refresh.",
    };
  }
  if (reasons.includes("market_data_stale_or_unavailable")) {
    return {
      eyebrow: "NO TRADE",
      title: "Stand aside",
      detail: "Fresh market data is unavailable. Refresh the feed before making an execution decision.",
    };
  }
  if (reasons.some((reason) => reason.includes("calibration"))) {
    return {
      eyebrow: "NO TRADE",
      title: "Stand aside",
      detail: "The model is not actively calibrated for live sizing, so execution remains disabled.",
    };
  }
  return {
    eyebrow: "NO TRADE",
    title: "Stand aside",
    detail: "The current setup does not have enough confirmed edge. Cash is the position.",
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

export function gammaFreshness(
  value: string | null | undefined,
  now = new Date(),
  maxAgeMinutes = 90,
) {
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
