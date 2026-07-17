/** Product-accurate landing copy — ML-centric & Data Integration focused. */

/** Display tickers without venue suffix; links use the same clean codes. */
export const WINNER_BAG = [
  { code: "TSLA", name: "Tesla" },
  { code: "MU", name: "Micron" },
  { code: "SPY", name: "S&P 500" },
  { code: "IONQ", name: "IonQ" },
  { code: "APLD", name: "Applied Digital" },
  { code: "XLP", name: "Staples" },
  { code: "QQQ", name: "Nasdaq 100" },
] as const;

export const CHAMPIONS = [
  {
    id: "v72_dual_sleeve",
    role: "Hierarchical Stacking Ensemble",
    tag: "Stacking Classifier",
    blurb:
      "Combines a low-frequency sniper with a confluence core sleeve. Stacked weights are capped at 50% under a joint Kelly constraint.",
    equation: "wₜ = min(0.50, w_sniper + 0.35 · w_core)",
    logic: "Sniper has first authority; the core fills unused risk capacity. Agreement increases size, never direction.",
    limit: "The combined sleeve accepts deeper drawdown than the pure confluence core.",
    metrics: [
      { label: "Full return*", value: "+513%" },
      { label: "Max DD*", value: "−19.4%" },
      { label: "Sharpe*", value: "3.08" },
      { label: "Win rate*", value: "72%" },
    ],
    oos: "OOS Holdout: +82% return · Sharpe 2.20 · n=84 trades",
    winner: true,
  },
  {
    id: "v39d_confluence",
    role: "Confluence XGBoost Meta-Sizer",
    tag: "Gradient Boosting",
    blurb:
      "Extracts support/resistance from volume profile structures, training an XGBoost meta-model on point-in-time features to filter trades.",
    equation: "enter = rule(VA, MACD-HA) ∧ p_xgb(fₜ₋₁) ≥ τ",
    logic: "A structural rebound creates the candidate. XGBoost may reject it or resize it from lagged features.",
    limit: "Its probability score is model output, not a guaranteed success probability.",
    metrics: [
      { label: "Full return*", value: "+358%" },
      { label: "Max DD*", value: "−13.4%" },
      { label: "Sharpe*", value: "2.82" },
      { label: "Win rate*", value: "67%" },
    ],
    oos: "135 trades · local adjusted 1H · out-of-sample validated",
    winner: false,
  },
  {
    id: "v71_live_confidence",
    role: "Mean-Reversion Sniper",
    tag: "Probability Size-Up",
    blurb:
      "Gates mean-reversion signals with a trend filter, scaling up position sizing depending on RSI extreme depths.",
    equation: "q = 𝟙[P > SMA₂₅₀] · base · confidence(RSI*)",
    logic: "An oversold extreme proposes the trade only inside the long-term trend; confidence changes size, not side.",
    limit: "High historical win rate comes with fewer observations and wider uncertainty.",
    metrics: [
      { label: "Full return*", value: "+114%" },
      { label: "Max DD*", value: "−19.5%" },
      { label: "Sharpe*", value: "1.72" },
      { label: "Win rate*", value: "86%" },
    ],
    oos: "OOS Holdout: +31% return · 77% win rate · train/select locked",
    winner: false,
  },
] as const;

export const PROTOCOL_STEPS = [
  { n: "01", title: "OHLCV Gating", detail: "Point-in-time raw price feeds" },
  { n: "02", title: "Volume Profile", detail: "Support/resistance distributions" },
  { n: "03", title: "Trend Gating", detail: "Heikin-Ashi higher-timeframe filters" },
  { n: "04", title: "Rule Signal", detail: "Primary entry setup proposals" },
  { n: "05", title: "Regime Filters", detail: "Drawdown and volatility gating" },
  { n: "06", title: "Kelly Scaling", detail: "Variance-adjusted capital sizing" },
  { n: "07", title: "Meta-Classifier", detail: "XGBoost success probability scaling" },
  { n: "08", title: "Desk Verdict", detail: "Ticket label: BUY / WATCH / STAND ASIDE" },
] as const;

/** How the data stack and integrations work */
export const DATA_LAYERS = [
  {
    title: "SQLite Stream Caching",
    body: "The local StreamSupervisor persists live ticked prices directly to databases (data/market_runtime.db), maintaining a local SQLite cache for rapid feature loading.",
  },
  {
    title: "Point-in-Time Causality",
    body: "All feature calculation pipelines are strictly lagged before rolling window calculations, preventing lookahead leaks. Missing points are left empty rather than filled.",
  },
  {
    title: "LSE Live Integration",
    body: "The LSE adapter maps raw exchange ticks to system schemas, feeding current order book states to operational workspaces in real-time.",
  },
  {
    title: "yfinance Bridge Fallback",
    body: "The system automatically falls back to secondary Yahoo Finance configurations when streaming endpoints are unavailable, ensuring continuous data availability.",
  },
] as const;

/** Why macros / cross-asset context */
export const MACRO_REASONS = [
  {
    title: "Regime Conditioning",
    body: "Single-name trends are conditional on market-wide volatility (VIX), interest rates (TLT), and macro events.",
  },
  {
    title: "Surprise Indices",
    body: "Uses point-in-time macro surprise variables rather than static values to condition feature probability.",
  },
  {
    title: "Correlation Matrices",
    body: "Computes rolling correlation matrix weights to scale back exposure when asset classes lock step.",
  },
  {
    title: "Purged Cross-Validation",
    body: "Fits cross-asset and macro regimes over walk-forward folds to avoid test-set leakage.",
  },
] as const;

/** How models actually work (ML focus) */
export const MODEL_HOW = [
  {
    title: "Feature Engineering",
    body: "Raw OHLCV is transformed into point-in-time features: volume profile nodes, Heikin-Ashi trends, and rolling volatility.",
  },
  {
    title: "Supervised Sizing Layer",
    body: "Runs an XGBoost classifier over trade candidates to predict target success probability, scaling sizing down for low-probability runs.",
  },
  {
    title: "Hierarchical Stacking",
    body: "Combines decoupled model sleeves. Sniper captures outliers, while Core harvests confluences under a combined Kelly risk ceiling.",
  },
  {
    title: "Out-of-Sample Auditing",
    body: "Validates models on a locked holdout dataset. Models are promoted only if they beat baselines and clear promotion gates.",
  },
] as const;

export const ARCHITECTURE = [
  { id: "data", label: "Data Ingestion", detail: "SQLite Cache · LSE Stream Adapter · Parquet Cache" },
  { id: "feat", label: "Feature Pipeline", detail: "Point-in-time profile levels · Macro regimes" },
  { id: "sig", label: "Base Learners", detail: "Rule generators & mean-reversion filters" },
  { id: "meta", label: "Meta Classifier", detail: "XGBoost probability scaling & Kelly constraints" },
  { id: "desk", label: "Ticket Desk", detail: "Visual verdicts & paper order execution tickets" },
  { id: "lab", label: "Telemetry & Lab", detail: "MLflow run logs · Genetic evolution farm" },
] as const;

export const FEATURES = [
  {
    key: "command",
    title: "Command Center",
    body: "Inspect current features, volume levels, and XGBoost meta probabilities for any selected symbol.",
    href: "/command",
    accent: "var(--td-brand)",
  },
  {
    key: "execution",
    title: "Execution Workspace",
    body: "Review paper ticket details, volume structure, and gamma bounds on the unified execution grid.",
    href: "/live",
    accent: "var(--td-action-buy-breakout)",
  },
  {
    key: "lab",
    title: "Research Lab",
    body: "Compare model features, review walk-forward backtests, and manage promotion gate runs.",
    href: "/research",
    accent: "var(--td-warning)",
  },
  {
    key: "risk",
    title: "Risk Engine",
    body: "Simulate Almgren-Chriss transaction impact costs and configure dynamic Kelly sizing limits.",
    href: "/live",
    accent: "var(--td-success)",
  },
  {
    key: "options",
    title: "Options Analytics",
    body: "Trace options open interest, delta, and gamma walls as structural features for the meta-classifier.",
    href: "/live?mode=gamma",
    accent: "var(--td-m-violet)",
  },
  {
    key: "agent",
    title: "Analysis Agent",
    body: "Generates structured Facts → Decision → Suggestion briefs by querying live feature values.",
    href: "/analysis-agent",
    accent: "var(--td-body)",
  },
] as const;

export const HUBS = [
  {
    title: "Command",
    href: "/command",
    desc: "Inspect current ticks, profile levels, and model pipeline outputs.",
  },
  {
    title: "Execution",
    href: "/live",
    desc: "Review order tickets, options chains, and volatility bands.",
  },
  {
    title: "Portfolio",
    href: "/positions",
    desc: "Manage simulated paper portfolio risk and transaction ledgers.",
  },
  {
    title: "Lab",
    href: "/research",
    desc: "Run genetic evolutions, rank models, and audit holdout backtests.",
  },
] as const;

export const FAQ = [
  {
    q: "How does the ingestion pipeline work?",
    a: "It streams live tick feeds into a local SQLite database (market_runtime.db). If live streaming is offline, the pipeline falls back to yfinance, matching schema structures before running feature calculations.",
  },
  {
    q: "What is the role of the Meta Classifier?",
    a: "The meta-classifier is an XGBoost model. It runs over base rule signals, analyzing current features (volume profile, volatility, macro factors) to predict the success probability. It restricts entries and scales sizing based on this probability.",
  },
  {
    q: "How are lookahead leaks prevented?",
    a: "All mathematical indicators, profile levels, and Heikin-Ashi trends are strictly lagged relative to the observation timestamp. Only features available at time 't' are used for training and prediction.",
  },
  {
    q: "How are backtests validated?",
    a: "Models are trained and optimized on in-sample folds, while a separate holdout period is kept locked. Variant models promote only when they beat baseline metrics on both segments, verifying true generalization.",
  },
  {
    q: "What does Kelly Sizing accomplish?",
    a: "It dynamically adjusts position sizes based on the meta-classifier's win probability and historical win/loss ratios, aiming to optimize capital allocation under trade constraints.",
  },
  {
    q: "Is this a live brokerage terminal?",
    a: "No. This is a local quantitative research station. All order tickets and portfolio metrics represent paper simulations to study performance drift and transaction costs.",
  },
] as const;

export const STATS = [
  { value: "+513%*", label: "Ensemble Full Return", sub: "Hierarchical Stacking Study" },
  { value: "3.08*", label: "Ensemble Sharpe", sub: "Simulated Path Metric" },
  { value: "8", label: "Pipeline Stages", sub: "OHLCV to Ticket Verdict" },
  { value: "7", label: "Study Bag Symbols", sub: "TSLA, MU, SPY, QQQ..." },
 ] as const;

export const DISCLAIMER_SHORT =
  "Study software for model inspection and paper tickets. Historical metrics are simulated paths on a fixed data contract.";

export const DISCLAIMER_LONG =
  "Trade Desk is software for quantitative research, feature inspection, and paper risk tickets. Model outputs, analysis-agent text, and historical metrics are study tools for operators. They are not broker orders or personalized investment advice. You are solely responsible for any real-world trading decisions and for complying with laws and broker rules in your jurisdiction.";

export interface PipelineStepDetail {
  n: string;
  title: string;
  concept: string;
  math: string;
  stacking: string;
  metaSizer: string;
  sniper: string;
}

export const PIPELINE_DETAILS: readonly PipelineStepDetail[] = [
  {
    n: "01",
    title: "OHLCV Gating",
    concept: "Raw point-in-time adjusted bars. All features are strictly lagged to prevent lookahead leaks.",
    math: "P_{adj} = P_{raw} \\times Factor_{adj}",
    stacking: "Aggregates hourly (1H) bars locally using the GlobalEquityEngine mapping.",
    metaSizer: "Loads 1H local files; halts signal evaluation if files are missing or incomplete.",
    sniper: "Subscribes to live SQLite catalog tables, falling back to public APIs on latency spikes.",
  },
  {
    n: "02",
    title: "Volume Profile",
    concept: "Computes support/resistance distributions over lookback windows to find VAL, VAH, and POC.",
    math: "POC = \\text{argmax}_{P} (Volume_{P}), \\quad \\sum_{P \\in VA} Volume_{P} \\ge 0.70 \\times Volume_{total}",
    stacking: "Evaluates volume distributions from underlying core feeds to map ensemble boundaries.",
    metaSizer: "Clusters volume-at-price ticks to verify confluence of support around POC.",
    sniper: "Uses profile boundaries as auxiliary exit flags rather than entry gates.",
  },
  {
    n: "03",
    title: "HTF HA Bias",
    concept: "Higher-Timeframe Heikin-Ashi trends act as a gate, ensuring trades match macro direction.",
    math: "C_{HA} = \\frac{O + H + L + C}{4}, \\quad O_{HA} = \\frac{O_{prev} + C_{prev}}{2}",
    stacking: "Permits Core sleeve execution only when higher-timeframe HA trend aligns green.",
    metaSizer: "Checks 4H/1D Heikin-Ashi gates; halts entry candidates if trend is red.",
    sniper: "Bypasses trend gates to capture maximum oversold mean-reversion spikes.",
  },
  {
    n: "04",
    title: "Rule Signal",
    concept: "Triggers primary buy candidates based on volume confluence or extreme mean-reversion thresholds.",
    math: "\\text{Candidate} = \\text{Touch}(VAL) \\land (\\text{MACD}_{hist} > 0 \\lor \\text{RSI} < \\text{Threshold})",
    stacking: "Checks Sniper rules first. If inactive, processes Core volume profile rebound rules.",
    metaSizer: "Requires volume profile rebound coupled with a positive shift in MACD histogram.",
    sniper: "Triggers on oversold extremes using Heuristic Ultimate RSI calculations.",
  },
  {
    n: "05",
    title: "Regime Filters",
    concept: "Gating mechanics that block trades in high-risk regimes, such as bear markets or high volatility.",
    math: "\\text{Pass} = \\text{Price} > \\text{SMA}_{250} \\land \\sigma_{rolling} < \\text{Max Volatility}",
    stacking: "Runs dual filters: SMA(250) gates for sniper and strict max drawdown filters for core.",
    metaSizer: "Applies dynamic rolling volatility gates to block setups in chaotic markets.",
    sniper: "Mandates a long-term SMA(250) trend filter to ensure safety in reversion setups.",
  },
  {
    n: "06",
    title: "Kelly Sizing",
    concept: "Computes optimal leverage fraction using historical win rates and profit/loss ratios.",
    math: "f^* = W - \\frac{1 - W}{R}",
    stacking: "Applies joint constraints: stacks sniper and core weights under a 50% capital cap.",
    metaSizer: "Modulates entry scale dynamically based on rolling model win rate performance.",
    sniper: "Uses a static 22.5% cash scale modified by confidence adjustments.",
  },
  {
    n: "07",
    title: "Meta-Classifier",
    concept: "Runs an XGBoost model over rule candidates to estimate success probability based on current feature sets.",
    math: "P_{meta} = \\text{XGBoost}(\\mathbf{f}_{pit}) \\ge \\text{Threshold}_{prob}",
    stacking: "Applies the XGBoost meta-classifier to Core signals while leaving Sniper signals unfiltered.",
    metaSizer: "Blocks entries if XGBoost probability is below 0.55, and scales sizing proportionally.",
    sniper: "Modulates position size up to 1.55x based on features and RSI depth.",
  },
  {
    n: "08",
    title: "Desk Verdict",
    concept: "Combines all stages to output action labels (BUY NOW, WATCH, STAND ASIDE) on the ticket desk.",
    math: "\\text{Label} = \\text{Verdict}(\\text{Rule} \\land \\text{Filter} \\land P_{meta})",
    stacking: "Generates stacked ticket instructions with individual sleeve allocations.",
    metaSizer: "Renders BUY labels when confluence setups clear the 0.55 meta probability gate.",
    sniper: "Renders BUY labels on high-confidence oversold setups.",
  },
];
