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
  metrics?: Partial<ModelRankRow>;
}

export interface ModelsCatalog {
  default_model: string;
  winner: string | null;
  previous_winner?: string | null;
  engines: string[];
  desk_engines?: string[];
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
}

export interface LivePlanResponse {
  ok: boolean;
  symbol: string;
  account?: number;
  peak?: number;
  drawdown?: number;
  live?: {
    go_long?: boolean;
    soft_long?: boolean;
    confidence?: number;
    vol_z?: number;
    price?: number;
    atr_pct?: number;
    above_vwap?: boolean;
    swing_uptrend?: boolean;
    macd_positive?: boolean;
    signal_strength?: number;
    timestamp?: string;
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
  decision?: {
    mode?: RiskMode;
    vehicle?: string;
    action?: string;
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
  conviction?: number;
  risk_pct?: number;
  max_loss_dollars?: number;
  vol_z?: number;
  price?: number;
  go_long?: boolean;
  blended_confidence?: number;
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
  options_from_ticket?: LivePlanResponse["options"];
  structure?: OptionsStructure | null;
  structure_error?: string | null;
  live_error?: string | null;
  playbook: OptionsPlaybook;
  research: {
    v22_variant: string;
    robust_path: string;
    note: string;
  };
  asof_utc?: string;
}

export interface LiveScanResponse {
  ok: boolean;
  account?: number;
  macro?: LivePlanResponse["macro"];
  count?: number;
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
  status: "ok" | "error" | "pending";
  error?: string | null;
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
