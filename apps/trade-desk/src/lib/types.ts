/** Shared types mirroring trade_desk.py --json and model_registry. */

export type ActionLabel =
  | "BUY NOW"
  | "BUY BREAKOUT"
  | "BREAKOUT WATCH"
  | "PULLBACK ZONE"
  | "AVOID (structure broken)"
  | "AVOID"
  | "WAIT / AVOID"
  | "WAIT (almost ready)"
  | "WAIT"
  | string;

export interface ModelSelection {
  model: string;
  reason: string;
  score?: number;
  win_rate?: number;
  sharpe?: number;
  source?: string;
}

export interface AnalyzeFlags {
  poc_hold?: boolean;
  in_value_area?: boolean;
  htf_ha_green?: boolean;
  vwap_uptrend?: boolean;
  above_vwap?: boolean;
  vol_confirm_or_pull?: boolean;
  not_red_flag?: boolean;
  mom_pos?: boolean;
  sqz_off_or_release?: boolean;
  [key: string]: boolean | undefined;
}

export interface AnalyzeState {
  model: string;
  symbol: string;
  code?: string;
  asof?: string;
  interval?: string;
  htf?: string;
  price: number;
  atr?: number;
  poc?: number | null;
  val?: number | null;
  vah?: number | null;
  entry?: number;
  stop?: number;
  trail_arm?: number;
  risk_per_share?: number;
  confidence?: number;
  hit_probability?: number;
  prior_wr?: number;
  setup_ok?: boolean;
  setup_kind?: string;
  breakout_ready?: boolean;
  breakout_buy?: boolean;
  breakout_level?: number | null;
  pressing_high?: boolean;
  coiling?: boolean;
  hard_gates_ok?: boolean;
  sleeve_fraction?: number;
  near_ema22?: boolean;
  above_ema22?: boolean;
  above_ema200?: boolean;
  ema22?: number;
  ema200?: number;
  rvol?: number;
  vol_surge?: boolean;
  vol_dry?: boolean;
  flags?: AnalyzeFlags;
  confidence_source?: string;
  engine_confidence?: number | null;
  confidence_kind?: string;
  [key: string]: unknown;
}

export interface PositionSize {
  shares: number;
  notional: number;
  dollar_risk: number;
  risk_pct: number;
  account: number;
  reward_to_arm?: number;
  rr_to_arm?: number;
  forced_preview?: boolean;
}

export interface PlainPlan {
  action: ActionLabel;
  why: string;
  do_next: string;
  confidence_note?: string;
  checklist?: { ok: boolean; label: string; key: string }[];
}

export interface ModelRankRow {
  model: string;
  has_engine: boolean;
  rank: number;
  score: number;
  win_rate: number;
  sharpe: number;
  profit_factor?: number;
  max_drawdown?: number;
  total_return?: number;
  trade_count?: number;
  source?: string;
  code?: string;
  specialist?: string | null;
  /** Closed live paper-trading trade count backing live_wr/live_avg_R; <10 = not enough evidence. */
  live_n?: number;
  /** Fraction (0-1), not percent points — use formatPct, not formatPctPoints. */
  live_wr?: number | null;
  /** Fraction (avg R-multiple), not percent points — use formatPct, not formatPctPoints. */
  live_avg_R?: number | null;
  live_status?: "none" | "provisional" | "confirming" | "degrading";
  /** Backtest score nudged by live outcomes (±15%, gated on live_n>=10); used for rank sort. */
  blended_score?: number;
}

export interface AnalyzeResponse {
  model: string;
  model_selection?: ModelSelection;
  state: AnalyzeState;
  plan?: PlainPlan;
  size?: PositionSize;
  model_ranks_for_symbol?: ModelRankRow[];
  [key: string]: unknown;
}

export interface EngineModelInfo {
  id: string;
  has_engine: boolean;
  is_default: boolean;
  is_winner: boolean;
  /** equity = desk-native; options = wrapper (desk unwraps to equity child) */
  kind?: "equity" | "options" | "other";
  desk_compatible?: boolean;
  /** Recent research engines prioritised in pickers */
  featured?: boolean;
  metrics?: Partial<ModelRankRow>;
}

export interface ModelsCatalog {
  default_model: string;
  winner: string | null;
  previous_winner?: string | null;
  engines: string[];
  desk_engines?: string[];
  featured_desk_engines?: string[];
  all_versions: string[];
  models: EngineModelInfo[];
  updated_at?: string | null;
  selection_rule?: string | null;
}

export interface ModelMetaConfig {
  feat_cols?: string[];
  threshold?: number;
  parent?: string;
  research_stack?: string[];
  genome?: Record<string, number>;
  params?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ApiEnvelope<T> {
  ok: boolean;
  command?: string;
  data?: T;
  error?: string;
  asof?: string;
}

export interface SupplyChainPlay {
  action?: string;
  why?: string;
  do_next?: string;
  confidence?: number | null;
  price?: number | null;
  stop?: number | null;
  entry?: number | null;
  setup_ok?: boolean;
  model?: string;
}

export interface SupplyChainAnchor {
  symbol: string;
  name?: string;
  price?: number | null;
  market_cap?: number | null;
  sector?: string;
  industry?: string;
  play?: SupplyChainPlay;
}

export interface SupplyChainPartner {
  symbol: string;
  name?: string;
  product?: string;
  confidence?: string;
  source?: string;
  price?: number | null;
  ytd_return?: number | null;
  correlation_1y?: number | null;
  market_cap?: number | null;
  is_small_cap?: boolean;
  sector?: string;
  industry?: string;
  revenue?: number | null;
  revenue_yoy?: number | null;
  net_income_yoy?: number | null;
  free_cash_flow_yoy?: number | null;
  play?: SupplyChainPlay;
  score?: number;
}

export interface SupplyChainResponse {
  ok: boolean;
  symbol: string;
  asof: string;
  anchor: SupplyChainAnchor;
  suppliers: SupplyChainPartner[];
}

/** v25 hybrid live plan (tools/live_plan.py --json) */
export type RiskMode =
  | "STAND_ASIDE"
  | "EQUITY_HEDGE"
  | "OPTIONS_ATTACK"
  | "FLATTEN"
  | "HALT_NEW"
  | string;

export interface LiveTicket {
  mode: RiskMode;
  vehicle: "none" | "equity" | "options" | string;
  action: string;
  symbol: string;
  max_loss_dollars?: number;
  risk_pct?: number;
  size_mult?: number;
  conviction?: number;
  exit_rules?: Record<string, string>;
  steps?: string[];
  confidence_state?: "ENTER" | "WATCH" | "ABSTAIN" | string;
  confidence_size_limit?: number;
  proposed_risk_pct?: number;
  proposed_max_loss_dollars?: number;
  risk_pct_adapted?: number;
  max_loss_adapted?: number;
  execution_readiness?: string;
  execution_blocked?: boolean;
}

export interface ExecutionReadiness {
  schema_version?: string;
  ready?: boolean;
  status?: "READY_FOR_MANUAL_REVIEW" | "BLOCKED" | string;
  checks?: Record<string, { passed?: boolean; detail?: string }>;
  blockers?: string[];
  human_approval_required?: boolean;
  automatic_transmission_enabled?: boolean;
}

export interface LiveConfidence {
  schema_version?: string;
  state?: "ENTER" | "WATCH" | "ABSTAIN" | string;
  raw_probability?: number | null;
  raw_probability_source?: string | null;
  calibrated_probability?: number | null;
  band?: string;
  size_limit?: number;
  evidence?: string[];
  failed_checks?: string[];
  model_version?: string;
  calibration_version?: string | null;
  calibration_available?: boolean;
  /** True when using identity fallback (no model-matched artifact). */
  uncalibrated?: boolean;
  data_freshness?: {
    available?: boolean;
    stale?: boolean;
    asof_utc?: string | null;
    age_minutes?: number | null;
    max_age_minutes?: number;
    market_session?: string;
    freshness_basis?: string;
    next_open_utc?: string;
    previous_close_utc?: string;
    error?: string;
  };
  reasons?: string[];
}

export interface LivePlanResponse {
  ok: boolean;
  symbol: string;
  /** Engine id the plan was generated with (tools/live_plan.py). */
  model_used?: string;
  account?: number;
  peak?: number;
  drawdown?: number;
  live?: {
    go_long?: boolean;
    go_short?: boolean;
    soft_long?: boolean;
    soft_short?: boolean;
    confidence?: number;
    vol_z?: number;
    price?: number;
    atr_pct?: number;
    above_vwap?: boolean;
    swing_uptrend?: boolean;
    macd_positive?: boolean;
    signal_strength?: number;
    timestamp?: string;
    source?: "lse" | "yfinance" | string;
    interval?: string;
    market_session?: string;
    freshness?: LiveConfidence["data_freshness"];
    error?: string;
  };
  macro?: {
    qqq_ok?: boolean;
    macro_ok?: boolean;
    defensive?: boolean;
    qqq_trend?: string | null;
    xlp_spy_ratio_state?: string | null;
  };
  model?: {
    ok?: boolean;
    model?: string;
    confidence?: number | null;
    setup_ok?: boolean;
    entry?: number;
    stop?: number;
    action_hint?: string;
    error?: string;
  };
  blended_confidence?: number;
  confidence?: LiveConfidence;
  gex?: GammaResponse | null;
  decision_support_ready?: boolean;
  execution_readiness?: ExecutionReadiness;
  execution_risk?: {
    proposal_risk_pct?: number;
    adapt_mult?: number;
    confidence_size_limit?: number;
    uncapped_risk_pct?: number;
    hard_cap_risk_pct?: number;
    effective_risk_pct?: number;
    effective_max_loss_dollars?: number;
    capped?: boolean;
  };
  portfolio_state_verified?: boolean;
  shadow_event_id?: string | null;
  decision?: {
    mode?: RiskMode;
    vehicle?: string;
    action?: string;
    analysis_action?: string;
    confidence_state?: "ENTER" | "WATCH" | "ABSTAIN" | string;
    execution_blocked?: boolean;
    size_mult?: number;
    risk_pct?: number;
    max_loss_dollars?: number;
    conviction?: number;
    reasons?: string[];
    exit_rules?: Record<string, string>;
  };
  options?: {
    action?: string;
    structure?: string;
    expiry?: string;
    dte?: number;
    long_strike?: number;
    short_strike?: number | null;
    debit_per_share?: number;
    max_loss_1_contract?: number;
    budget?: number;
    long_delta?: number;
    reason?: string;
    error?: string;
    exit_plan?: Record<string, string>;
    warnings?: string[];
  } | null;
  ticket?: LiveTicket;
  policy_version?: string;
  asof_utc?: string;
  live_ready?: boolean;
  notes?: string[];
  error?: string;
}

export interface LiveScanRow {
  symbol: string;
  mode: RiskMode;
  vehicle: string;
  action: string;
  /** Operator setup label (BUY NOW / BREAKOUT WATCH / WAIT / AVOID / …). */
  analysis_action?: string;
  conviction?: number;
  risk_pct?: number;
  max_loss_dollars?: number;
  vol_z?: number;
  price?: number;
  go_long?: boolean;
  soft_long?: boolean;
  blended_confidence?: number;
  confidence_state?: "ENTER" | "WATCH" | "ABSTAIN" | string;
  calibrated_probability?: number | null;
  uncalibrated?: boolean;
  do_next?: string | null;
}

/** Options desk: live mode + structure pick + playbook */
export interface OptionsStructure {
  action?: string;
  structure?: string;
  symbol?: string;
  spot?: number;
  expiry?: string;
  dte?: number;
  long_strike?: number;
  short_strike?: number | null;
  debit_per_share?: number;
  max_loss_1_contract?: number;
  budget?: number;
  long_delta?: number;
  short_delta?: number | null;
  iv_long?: number;
  reason?: string;
  error?: string;
  note?: string;
  warnings?: string[];
  exit_plan?: Record<string, string>;
  contracts?: number;
  [key: string]: unknown;
}

export interface OptionsPlaybook {
  account_fit: string;
  default_structure: string;
  preferred: string[];
  avoid_atm: string[];
  rules: string[];
  live_variant: string;
  live_engine_note: string;
}

export interface RiskAssessmentResponse {
  ok: boolean;
  account: number;
  equity: number;
  peak: number;
  drawdown: number;
  mode: string;
  mode_reasons: string[];
  kelly: {
    full: number;
    half: number;
    quarter: number;
    recommended_fraction: number;
    full_dollar: number;
    half_dollar: number;
    quarter_dollar: number;
    recommended_dollar: number;
  };
  position_sizing: {
    fixed_fractional: {
      shares: number;
      risk_dollars: number;
      risk_pct: number;
      stop_loss_dollars: number;
    };
  };
  var_es: {
    parametric: { var: number; es: number };
    historical: { var: number; es: number };
    confidence: number;
    holding_days: number;
  };
  risk_adjusted: {
    sharpe: number;
    sortino: number;
    calmar: number;
  };
  drawdown_metrics: {
    current: number;
    max: number;
    average: number;
    max_duration_days: number;
  };
  portfolio: {
    variance: number;
    std: number;
    diversification_benefit_pct: number;
  };
  reasons: string[];
  asof_utc: string;
}

/** Research-only vol package score from tools/vol_package_score.py */
export interface VolPackageTemplate {
  template: string;
  score: number;
  edge_after_cost_proxy?: number | null;
  action: "consider" | "stand_aside" | "avoid" | string;
  reasons?: string[];
}

export interface VolPackageWarning {
  severity: "info" | "watch" | "danger" | string;
  code: string;
  message: string;
}

export interface VolPackageScore {
  ok: boolean;
  symbol?: string;
  features?: {
    symbol?: string;
    spot?: number;
    rv_har_ann?: number;
    rv_5d_ann?: number;
    rv_21d_ann?: number;
    atm_iv?: number;
    iv_rv_spread?: number;
    term_slope?: number;
    skew_25d?: number;
    near_dte?: number | null;
    next_dte?: number | null;
    call_volume?: number;
    put_volume?: number;
    call_oi?: number;
    put_oi?: number;
    put_call_vol_ratio?: number;
    put_call_oi_ratio?: number;
    spot_ret_1d?: number;
    spot_ret_5d?: number;
    data_quality?: string;
    reasons?: string[];
  };
  packages?: VolPackageTemplate[];
  recommended?: {
    template: string;
    action: string;
    score?: number;
    edge_after_cost_proxy?: number | null;
    reasons?: string[];
  };
  warnings?: VolPackageWarning[];
  guardrails?: {
    max_risk_pct?: number;
    cost_proxy_vol?: number;
    research_only?: boolean;
    auto_trade?: boolean;
    does_not_set_options_attack?: boolean;
  };
  asof_utc?: string;
  error?: string;
}

/** Single unusual options print/flag (LSE tape preferred; chain proxy fallback). */
export interface UnusualOptionsFlag {
  symbol: string;
  expiry: string;
  dte: number;
  right: "C" | "P" | string;
  strike: number;
  spot?: number;
  volume: number;
  open_interest?: number;
  vol_oi?: number | null;
  mid?: number | null;
  premium?: number | null;
  iv?: number | null;
  moneyness_pct?: number | null;
  score: number;
  severity?: "high" | "watch" | "info" | string;
  reasons: string[];
  reason?: string;
  unusual?: boolean;
  methodology?: string;
  /** ISO print timestamp when the source is genuine time-and-sales. */
  trade_time?: string | null;
}

export interface UnusualOptionsFlow {
  ok: boolean;
  symbol: string;
  spot?: number;
  n_scanned?: number;
  n_flagged?: number;
  flags: UnusualOptionsFlag[];
  unusual?: UnusualOptionsFlag[];
  methodology?: string;
  methodology_note?: string;
  asof_utc?: string;
  session_label?: string;
  error?: string;
  expiries_used?: string[];
  bias?: "call" | "put" | "balanced" | string;
  upstream_error?: string;
  fallback_source?: string;
}

export interface OptionsPlanResponse {
  ok: boolean;
  symbol: string;
  account?: number;
  mode: string;
  vehicle: string;
  do_next: string[];
  ticket?: LiveTicket | null;
  live?: LivePlanResponse["live"] | null;
  macro?: LivePlanResponse["macro"] | null;
  /** Model path / calibrated confidence when live plan succeeds. */
  model?: LivePlanResponse["model"] | null;
  confidence?: LivePlanResponse["confidence"] | null;
  options_from_ticket?: LivePlanResponse["options"];
  structure?: OptionsStructure | null;
  structure_error?: string | null;
  live_error?: string | null;
  /** IV–RV package scores; null if scorer failed (directional plan still valid). */
  vol_package?: VolPackageScore | null;
  vol_package_error?: string | null;
  /** Same-day unusual options activity (LSE prints preferred); partial failure OK. */
  unusual_flow?: UnusualOptionsFlow | null;
  unusual_flow_error?: string | null;
  playbook: OptionsPlaybook;
  research: {
    v22_variant: string;
    robust_path: string;
    note: string;
    options_winner?: string;
    vol_program?: string;
  };
  asof_utc?: string;
}

export interface OptionsBookConfidenceRead {
  score: number;
  label: "HIGH" | "MEDIUM" | "LOW" | "AVOID" | string;
  stance: string;
  reasons: string[];
}

export interface OptionsBookRow {
  symbol: string;
  input_symbol?: string;
  structure?: OptionsStructure | null;
  vol_package?: {
    ok?: boolean;
    recommended?: VolPackageScore["recommended"];
    warnings?: VolPackageWarning[];
    features?: Record<string, number | string | null | undefined>;
    error?: string;
  } | null;
  unusual_flow?: {
    ok?: boolean;
    n_flagged?: number;
    calls?: number;
    puts?: number;
    premium?: number;
    bias?: string;
    error?: string;
  } | null;
  confidence_read?: OptionsBookConfidenceRead;
  preferred?: boolean;
  error?: string;
  asof_utc?: string;
}

export interface OptionsBookScanResponse {
  ok: boolean;
  account?: number;
  risk_pct?: number;
  book: string[];
  rows: OptionsBookRow[];
  best?: string | null;
  n?: number;
  errors?: string[];
  note?: string;
  asof_utc?: string;
}

export interface LiveScanResponse {
  ok: boolean;
  account?: number;
  macro?: LivePlanResponse["macro"];
  count?: number;
  use_model?: boolean;
  rows?: LiveScanRow[];
  asof_utc?: string;
}

export const SECTORS = [
  "mag7",
  "memory",
  "photonics",
  "energy",
  "space",
  "quantum",
  "ai_infra",
  "banks",
  "biotech",
  "metals",
  "consumer",
  "crypto",
  "beta",
] as const;

export type Sector = (typeof SECTORS)[number];

export type PortfolioMethod = "mpt" | "risk_parity" | "factor_tilt" | "portfolio";

export interface PortfolioAssetInput {
  name: string;
  ret?: number;
  vol?: number;
}

export interface PortfolioFactorInput {
  premium: number;
  vol: number;
}

export interface PortfolioMptPoint {
  return: number;
  risk: number;
  sharpe: number;
  weights?: number[];
  allocation?: number;
}

export interface PortfolioOptimizerResponse {
  method: PortfolioMethod;
  ok: boolean;
  error?: string;
  asof_utc?: string;
  // mpt
  risk_free?: number;
  assets?: PortfolioAssetInput[] | string[];
  correlation?: number[][];
  max_sharpe?: {
    weights: number[];
    return: number;
    risk: number;
    variance: number;
    sharpe: number;
  };
  min_variance?: {
    weights: number[];
    return: number;
    risk: number;
    variance: number;
    sharpe: number;
  };
  efficient_frontier?: PortfolioMptPoint[];
  capital_market_line?: PortfolioMptPoint[];
  // risk parity
  vols?: number[];
  equal_weight?: {
    weights: Record<string, number>;
    risk: number;
    risk_contribution: Record<string, number>;
  };
  inverse_volatility?: {
    weights: Record<string, number>;
    risk: number;
    risk_contribution: Record<string, number>;
  };
  equal_risk_contribution?: {
    weights: Record<string, number>;
    risk: number;
    risk_contribution: Record<string, number>;
  };
  // factor tilt
  market_return?: number;
  market_vol?: number;
  expected_return?: number;
  portfolio_risk?: number;
  tracking_error?: number;
  sharpe?: number;
  contributions?: Record<string, number>;
  tilts?: Record<string, number>;
}

export interface PortfolioRebalanceRow {
  current_weight: number;
  target_weight: number;
  delta_weight: number;
  current_dollar: number;
  target_dollar: number;
  delta_dollar: number;
  shares_to_trade?: number | null;
}

export interface PortfolioOptimizedResult {
  weights: Record<string, number>;
  return?: number;
  risk?: number;
  sharpe?: number;
  risk_contribution?: Record<string, number>;
  rebalancing: Record<string, PortfolioRebalanceRow>;
}

export interface PortfolioOptimizationResponse {
  method: "portfolio";
  symbols: string[];
  risk_free: number;
  lookback: number;
  account: number;
  total_market_value: number;
  last_prices: Record<string, number>;
  market_values: Record<string, number>;
  current_weights: Record<string, number>;
  annualized: {
    returns: Record<string, number>;
    vols: Record<string, number>;
    correlation: number[][];
    covariance: number[][];
  };
  mpt?: {
    max_sharpe: PortfolioOptimizedResult;
    min_variance: PortfolioOptimizedResult;
    efficient_frontier: PortfolioMptPoint[];
    capital_market_line: PortfolioMptPoint[];
  };
  risk_parity?: {
    equal_weight: PortfolioOptimizedResult;
    inverse_volatility: PortfolioOptimizedResult;
    equal_risk_contribution: PortfolioOptimizedResult;
  };
}

/** --- Symbol ranker (tools/symbol_ranker.py --json) --- */
export type ClaimLevel = "THIN" | "RESEARCH" | "CLAIM" | string;
export interface RankerWindowMetrics {
  total_return?: number;
  sharpe?: number;
  calmar?: number;
  max_drawdown?: number;
  win_rate?: number;
  profit_factor?: number;
  trade_count?: number;
  status: "ok" | "error" | "pending";
  reused?: boolean;
  run_dir?: string;
  error?: string | null;
}
export interface RankerLiveStats {
  n: number;
  wins: number;
  live_wr: number;
  total_pnl: number;
  avg_R: number;
}
export interface RankerRow {
  model: string;
  engine_kind: "equity" | "options" | "other";
  desk_runnable: boolean;
  rank: number;
  score: number;
  utility: Partial<Record<"full" | "recent" | "prior", number>>;
  oos_consistency: number;
  reliability: number;
  window_metrics: Partial<Record<"full" | "recent" | "prior", RankerWindowMetrics>>;
  total_return?: number;
  max_drawdown?: number;
  sharpe?: number;
  win_rate?: number;
  trade_count?: number;
  claim_level: ClaimLevel;
  pass_bar?: { passed: boolean; reasons: string[] };
  proj_6mo_return?: number;
  hist_evidence?: {
    win_rate?: number;
    sharpe?: number;
    trade_count?: number;
    source?: string;
  } | null;
  live?: RankerLiveStats | null;
  live_blend_applied?: boolean;
  pricing?: string;
  /** Evidence-gated 0-1 confidence (Wilson-bound edge × sample × consistency × DD guard). */
  confidence?: number;
  confidence_parts?: Record<string, number>;
  confidence_reasons?: string[];
  status: "ok" | "error" | "pending";
  error?: string | null;
}
/** Symbol-level highest-confidence engine read; abstains instead of forcing a pick. */
export interface RankerRead {
  schema: number;
  symbol: string;
  horizon: "day" | "swing" | "position" | string;
  asof?: string | null;
  verdict: "TRUST" | "WATCH" | "STAND_ASIDE";
  model: string | null;
  confidence: number;
  thresholds: { watch: number; enter: number };
  runner_up?: { model: string; confidence: number } | null;
  gap?: number | null;
  reasons: string[];
}
export interface RankerResponse {
  schema: number;
  symbol: string;
  code: string;
  asof: string;
  cash: number;
  status: "complete" | "partial";
  budget_seconds?: number;
  elapsed_seconds?: number;
  windows: Record<string, { start: string; end: string; interval: string }>;
  rows: RankerRow[];
  options_rows?: RankerRow[];
  errors?: string[];
  exists: boolean;
  stale: boolean;
  age_days?: number;
  read?: RankerRead;
}

/** --- Paper ledger (tools/paper_ledger.py --json) --- */
export type TradeSide = "long" | "short";
export interface TradeTicketInput {
  symbol: string;
  side: TradeSide;
  shares: number;
  entry: number;
  stop: number;
  trailArm?: number;
  model: string;
  account?: number;
  riskPct?: number;
  dollarRisk?: number;
  action?: string;
  confidence?: number;
  override?: boolean;
  reason?: string;
}
export interface PaperPosition {
  id: string;
  symbol: string;
  side: TradeSide;
  shares: number;
  entry: number;
  stop: number;
  trail_arm?: number | null;
  model: string;
  opened_at: string;
  account?: number;
  dollar_risk: number;
  action_at_entry?: string;
  override?: boolean;
  status: "open" | "closed" | "cancelled";
  mark?: number | null;
  mark_ts?: string | null;
  unrealized_pnl?: number | null;
  unrealized_r?: number | null;
  stop_hit?: boolean;
  trail_hit?: boolean;
  exit?: number | null;
  exit_reason?: string | null;
  pnl?: number | null;
  r_multiple?: number | null;
  closed_at?: string | null;
  holding_days?: number | null;
}
export interface LedgerStatsRow {
  model: string;
  symbol: string;
  n: number;
  wins: number;
  losses: number;
  live_wr: number;
  total_pnl: number;
  avg_R: number;
  sum_R: number;
  last_close_ts?: string;
}
export interface PositionsResponse {
  positions: PaperPosition[];
  stats: { rows: LedgerStatsRow[]; overall?: Partial<LedgerStatsRow> };
  marked: boolean;
  asof: string;
}

export interface GammaStrike {
  strike: number;
  net_gex: number;
  call_gex: number;
  put_gex: number;
}

export interface GammaResponse {
  symbol: string;
  spot: number;
  spot_source: string;
  source?: string;
  lse_error: string | null;
  options_asof?: string | null;
  asof_utc: string;
  /** Full listed option expiries from the provider (for desk date pickers). */
  available_expiries?: string[];
  expiries_used: string[];
  net_dealer_gex: number;
  near_spot_dealer_gex: number;
  gex_sign: number;
  regime: string;
  call_wall: number | null;
  put_wall: number | null;
  call_wall_gex?: number;
  put_wall_gex?: number;
  dist_call_wall_pct: number | null;
  dist_put_wall_pct: number | null;
  approx_flip_strike: number | null;
  dist_flip_pct?: number | null;
  expected_move_pct: number | null;
  expected_move_low: number | null;
  expected_move_high: number | null;
  max_pain: number | null;
  otm_call_volume: number;
  otm_call_oi: number | null;
  otm_put_volume?: number;
  otm_put_oi?: number | null;
  total_oi?: number | null;
  total_volume?: number;
  /** Open interest by strike/expiry — may be absent when source is intraday flow proxy. */
  open_interest_by_strike?: Record<string, number>;
  n_contracts: number;
  weight: string;
  sign_convention: string;
  exposure_kind?: "dealer_positioning_estimate" | "intraday_gamma_flow_proxy" | string;
  formula?: string;
  unit?: string;
  sign_assumption?: string;
  price_consistent?: boolean;
  price_divergence_pct?: number;
  warnings?: string[];
  squeeze_score?: number;
  squeeze_label?: "bullish_squeeze" | "bearish_squeeze" | "neutral";
  squeeze_components?: Record<string, number>;
  by_strike: GammaStrike[];
  error?: string;
}

export interface AnalysisDriver {
  name: string;
  value: string;
  impact: "positive" | "negative" | "neutral";
}

export interface AnalysisTicket {
  mode?: string;
  vehicle?: string;
  action?: string;
  symbol?: string;
  max_loss_dollars?: number | null;
  risk_pct?: number | null;
  conviction?: number | null;
  steps?: string[];
  exit_rules?: Record<string, string>;
}

export interface AnalysisSuggestion {
  ticket: AnalysisTicket;
  options?: {
    action?: string;
    structure?: string;
    expiry?: string;
    dte?: number;
    long_strike?: number | null;
    short_strike?: number | null;
    debit_per_share?: number | null;
    max_loss_1_contract?: number | null;
    budget?: number | null;
    long_delta?: number | null;
    reason?: string;
  } | null;
  rationale: string;
  drivers: AnalysisDriver[];
  alternatives: string[];
}

export interface AnalysisDecisionConfidence {
  state?: string;
  band?: string;
  raw_probability?: number | null;
  calibrated_probability?: number | null;
  size_limit?: number | null;
  evidence?: string[];
  failed_checks?: string[];
  reasons?: string[];
}

export interface AnalysisDecisionSizing {
  price?: number | null;
  entry?: number | null;
  stop?: number | null;
  risk_per_share?: number | null;
  shares?: number;
  notional?: number | null;
  target?: number | null;
  side?: string;
}

export interface AnalysisDecision {
  confidence_state?: string;
  blended_confidence?: number | null;
  mode?: string;
  vehicle?: string;
  /** Operator setup label (BUY NOW / BREAKOUT WATCH / AVOID / …). */
  action?: string;
  analysis_action?: string;
  risk_manager_action?: string;
  execution_action?: string;
  execution_blocked?: boolean;
  risk_pct?: number | null;
  max_loss_dollars?: number | null;
  conviction?: number | null;
  reasons?: string[];
  exit_rules?: Record<string, string>;
  confidence?: AnalysisDecisionConfidence;
  sizing?: AnalysisDecisionSizing;
}

export interface AnalysisFacts {
  symbol?: string;
  price?: number | null;
  asof_utc?: string;
  live: {
    price?: number | null;
    vol_z?: number | null;
    atr_pct?: number | null;
    go_long?: boolean;
    go_short?: boolean;
    above_vwap?: boolean;
    swing_uptrend?: boolean;
    macd_positive?: boolean;
    signal_strength?: number | null;
    timestamp?: string;
  };
  macro: {
    qqq_ok?: boolean;
    macro_ok?: boolean;
    defensive?: boolean;
    qqq_trend?: string | null;
    xlp_spy_ratio_state?: string | null;
  };
  gex: {
    regime?: string;
    gex_sign?: number | null;
    spot?: number | null;
    call_wall?: number | null;
    put_wall?: number | null;
    approx_flip_strike?: number | null;
    squeeze_score?: number | null;
    squeeze_label?: string;
    expected_move_pct?: number | null;
    max_pain?: number | null;
  };
  model: {
    model?: string;
    ok?: boolean;
    confidence?: number | null;
    setup_ok?: boolean | null;
    entry?: number | null;
    stop?: number | null;
    action_hint?: string | null;
    raw_probability_source?: string | null;
  };
  top_models: ModelRankRow[];
}

export interface AnalysisReport {
  facts: AnalysisFacts;
  decision: AnalysisDecision;
  suggestion: AnalysisSuggestion;
}

export interface AnalysisAgentResponse {
  ok: boolean;
  symbol?: string;
  error?: string;
  asof_utc?: string;
  report?: AnalysisReport;
}

export interface PromotionEntry {
  id: string;
  ts: string;
  campaign?: string;
  family: string;
  model_dir?: string;
  metrics: {
    utility?: number;
    sharpe?: number;
    ret?: number;
    dd?: number;
    n?: number;
    [key: string]: number | undefined;
  };
  gates: {
    passed: boolean;
    claim_level?: string;
    [key: string]: unknown;
  };
  status: "pending" | "approved" | "rejected";
  approved_at?: string;
  rejected_at?: string;
  reject_reason?: string;
  promoted_version?: string;
  promoted_path?: string;
}

export interface WinnerHealth {
  winner: string | null;
  live_n: number;
  live_wr: number;
  threshold: number;
  trailing_n: number;
  degraded: boolean;
  asof?: string;
}

export interface PromotionPayload {
  queue: PromotionEntry[];
  winner_health: WinnerHealth;
}

/** Aggregate options-flow discovery rows used by the Top Tickers desk. */
export interface TopTickerRow {
  symbol: string;
  rank: number;
  total_premium: number;
  call_premium: number;
  put_premium: number;
  call_count: number;
  put_count: number;
  flag_count: number;
  total_volume: number;
  total_score: number;
  avg_score: number;
  max_score: number;
  short_dte_premium: number;
  otm_premium: number;
  sentiment: "bullish" | "bearish" | "neutral";
  bullish_pct: number;
}

export interface TopTickerCategory {
  key: string;
  label: string;
  description: string;
  rows: TopTickerRow[];
}

export interface TopTickersResponse {
  ok: boolean;
  categories: TopTickerCategory[];
  asof_utc: string;
  note?: string;
  error?: string;
}

/** Single off-exchange equity print (dark pool / FINRA TRF). */
export interface DarkPoolPrint {
  ts: string;
  symbol: string;
  price: number;
  size: number;
  notional: number;
  vs_market: "above" | "at" | "below" | string;
  pct_adv?: number | null;
  venue?: string | null;
}

export interface DarkPoolResponse {
  ok: boolean;
  prints: DarkPoolPrint[];
  asof_utc: string;
  note?: string;
  error?: string;
}
