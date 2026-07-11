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
  metrics?: Partial<ModelRankRow>;
}

export interface ModelsCatalog {
  default_model: string;
  winner: string | null;
  previous_winner?: string | null;
  engines: string[];
  all_versions: string[];
  models: EngineModelInfo[];
  updated_at?: string | null;
  selection_rule?: string | null;
}

export interface ApiEnvelope<T> {
  ok: boolean;
  command?: string;
  data?: T;
  error?: string;
  asof?: string;
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
