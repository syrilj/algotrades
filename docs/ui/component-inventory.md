# Trade Desk — Component Inventory

React components for `apps/trade-desk`. Props keyed to `tools/trade_desk.py` JSON (`--json`).

Tokens/icons: [`DESIGN_TOKENS.md`](./DESIGN_TOKENS.md). Screens: [`SCREENS.md`](./SCREENS.md). Spec: [`TRADE_DESK_UI.md`](./TRADE_DESK_UI.md). Leaderboard: [`LEADERBOARD.md`](./LEADERBOARD.md).

---

## Shell

### `AppShell`

| Prop | Type | Notes |
|------|------|-------|
| `activeNav` | `'analyze' \| 'watch' \| 'picks' \| 'leaderboard' \| 'models'` | |
| `children` | `ReactNode` | |

### `DeskNav`

Links mirroring CLI verbs. Compact; no marketing CTAs.

---

## Shared controls

### `SymbolField`

| Prop | Type | CLI |
|------|------|-----|
| `value` | `string` | symbol / `--symbol` |
| `onChange` | `(s: string) => void` | |
| `multi` | `boolean?` | watchlist comma mode |

### `AccountRiskFields`

| Prop | Type | CLI |
|------|------|-----|
| `account` | `number` | `--account` |
| `riskPct` | `number` | `--risk-pct` (0.01 = 1%) |

### `ModelSelect`

| Prop | Type | CLI |
|------|------|-----|
| `value` | `string` | `--model` (`auto` \| engine id) |
| `engines` | `string[]` | `list_engine_models()` |
| `defaultModel` | `string` | `DEFAULT_MODEL` |

### `HorizonToggle`

`value: 'day' \| 'week'` → `--horizon`

### `SectorChips`

| Prop | Type | CLI |
|------|------|-----|
| `selected` | `string[]` | `--sectors` |
| `options` | `string[]` | ROTATION_SECTORS + `beta` |

### `AdvancedParams`

`period`, `every`, `interval`, `top`, `enginesOnly`, `ticks` — disclosed.

### `RunButton`

Primary brand CTA; loading disables + `aria-busy`.

---

## Analyze

### `AnalyzeForm`

Composes controls → `POST /api/analyze`.

### `PipelineFlow` (hero)

| Prop | Type | Source |
|------|------|--------|
| `state` | `AnalyzeState` | `payload.state` |
| `plan` | `PlainPlan` | `_plain_plan(state)` or server-included |
| `model` | `string` | `payload.model` |
| `phase` | `'idle' \| 'running' \| 'done' \| 'error'` | UI |
| `activeStage` | `0..7` | animation cursor |

Stages bind: price/asof → poc/val/vah → `flags.htf_ha_green` → `setup_kind` → filter flags → `sleeve_fraction`/`confidence` → meta (if v15+) → `plan.action` + sizing.

### `PipelineNode`

| Prop | Type |
|------|------|
| `id` | stage id |
| `title` | string |
| `icon` | Lucide icon |
| `status` | `'idle' \| 'running' \| 'pass' \| 'fail' \| 'neutral'` |
| `metrics` | `{ label: string; value: string }[]` |

### `TimingStack`

Advisory labels from `near_ema22`, `above_ema22`, `above_ema200`, `vol_surge`, `vol_dry` (+ sector context if present).

### `VerdictPanel`

| Prop | Type | Source |
|------|------|--------|
| `action` | `string` | `plan.action` |
| `why` | `string` | `plan.why` |
| `doNext` | `string` | `plan.do_next` |
| `model` | `string` | `payload.model` |
| `selectionReason` | `string?` | `model_selection.reason` |
| `asof` | `string` | `state.asof` |
| `confidence` | `number` | `state.confidence` |
| `confidenceNote` | `string?` | `plan.confidence_note` |
| `hitProbability` | `number` | `state.hit_probability` |

### `ConfidenceMeter`

`value: number` (0–1); animate once on mount/update.

### `SizingBlock`

| Prop | Source |
|------|--------|
| `entry`, `stop`, `trailArm`, `riskPerShare` | `state.*` |
| `shares`, `notional`, `dollarRisk`, `riskPct`, `account` | `sizing.*` |
| `isActionable` | action in `BUY NOW` \| `BUY BREAKOUT` |

### `ValueZoneBar`

`val`, `vah`, `poc`, `price`, optional `breakoutLevel`, `vwap`.

### `GateChecklist`

| Prop | Type | Source |
|------|------|--------|
| `items` | `{ key; label; ok: boolean }[]` | `plan.checklist` |

### `SymbolModelRanks` → prefer `TopModelsStrip`

Compact Analyze footer. Deep-links to Leaderboard.

| Prop | Source |
|------|--------|
| `ranks` | `model_ranks_for_symbol[]` — `rank`, `model`, `win_rate`, `sharpe`, `score?` |
| `symbol` | current analyze symbol |
| `onOpenLeaderboard` | → `/leaderboard?symbol=` |
| `onUseAuto` | callback |

---

## Leaderboard

### `LeaderboardPage` / `LeaderboardControls`

| Prop | Type | CLI |
|------|------|-----|
| `mode` | `'portfolio' \| 'symbol'` | `rank` vs `rank --symbol` |
| `symbol` | `string` | `--symbol` |
| `enginesOnly` | `boolean` | `--engines-only` |
| `sortKey` | `'score' \| 'win_rate' \| 'sharpe' \| 'profit_factor' \| 'max_drawdown' \| 'total_return'` | client sort |
| `sortDir` | `'asc' \| 'desc'` | default score desc |
| `winnerId` | `string?` | `WINNER.json.winner` |
| `defaultModelId` | `string` | `DEFAULT_MODEL` |

### `EnginesOnlyToggle`

`checked` / `onChange` → `--engines-only` (filter `has_engine`).

### `LeaderboardTable`

| Prop | Type | Source |
|------|------|--------|
| `rows` | `LeaderboardRow[]` | `rank_models` / `rank_models_for_symbol` JSON |
| `selectedModel` | `string?` | UI |
| `onSelect` | `(model: string) => void` | |
| `onSort` | `(key, dir) => void` | |

### `ModelRankRow`

| Prop | Source field |
|------|----------------|
| `rank` | `rank` |
| `model` | `model` |
| `score` | `score` |
| `winRate` | `win_rate` |
| `sharpe` | `sharpe` |
| `profitFactor` | `profit_factor` |
| `maxDrawdown` | `max_drawdown` |
| `totalReturn` | `total_return` |
| `tradeCount` | `trade_count` |
| `hasEngine` | `has_engine` |
| `source` | `source` |
| `specialist` | `specialist` (symbol mode) |
| `isWinner` | model === WINNER |
| `isDefault` | model === DEFAULT_MODEL |
| `status` | parsed MODEL.md (optional) |

### `ScoreBar`

| Prop | Type |
|------|------|
| `value` | `number` (composite 0–1+) |
| `max` | `number` (column max for relative fill) |

Uses `--td-score-bar` / `--td-score-track`. Tabular mono label beside bar.

### `RankMedal`

| Prop | Type |
|------|------|
| `rank` | `number` |
| `variant` | `'gold' \| 'silver' \| 'bronze' \| 'plain'` | ranks 1–3 use medal tokens; else plain `#` |

### `WinnerBadge` / `DefaultBadge` / `EngineBadge` / `StatusBadge`

| Badge | When |
|-------|------|
| Winner | `WINNER.json.winner` |
| Default | `DEFAULT_MODEL` |
| Engine | `has_engine` |
| Status | `active` / `frozen` / `satellite` / `fail_oos` from MODEL.md |

### `ModelRankCard` (side panel / expand)

Hypothesis one-liner, when-to-use, key metrics, links: `/models/[id]`, Analyze with model, Use auto.

### `TopModelsStrip`

Analyze secondary — top 3 ranks + “Leaderboard →”.

---

## Models

### `ModelDetailHeader`

`modelId`, metrics from findings/cards, CTA → Analyze with model, back → Leaderboard.

---

## Types (sketch)

```ts
type LeaderboardRow = {
  rank: number;
  model: string;
  score: number;
  win_rate: number;
  sharpe: number;
  profit_factor: number;
  max_drawdown: number;
  total_return: number;
  trade_count?: number;
  has_engine: boolean;
  source?: string;
  code?: string;       // symbol mode
  specialist?: string; // symbol mode
};
```

---

## Rank / Models (legacy names)

`RankTable` → alias of `LeaderboardTable` (deprecated).

### `ModelDetailHeader` (see above)

---

## Types (analyze sketch)

```ts
type AnalyzePayload = {
  model: string;
  model_selection?: { reason?: string; model?: string; score?: number };
  state: AnalyzeState;
  sizing: Sizing;
  model_ranks_for_symbol?: LeaderboardRow[];
};

type PlainPlan = {
  action: string;
  why: string;
  do_next: string;
  checklist: { ok: boolean; label: string; key: string }[];
  confidence_note: string;
};

type SnapshotRow = {
  symbol: string;
  action: string;
  why: string;
  do_next: string;
  setup_kind?: string;
  price: number;
  stop: number;
  rvol?: number;
  vol_surge?: boolean;
  vol_dry?: boolean;
  ema22?: number;
  ema200?: number;
  above_ema22?: boolean;
  above_ema200?: boolean;
  near_ema22?: boolean;
  breakout_level?: number;
  confidence: number;
};
```

Align field names exactly with CLI JSON (`snake_case` at API boundary; map to camelCase in UI if desired).

---

## Suggested file tree

```
apps/trade-desk/
  app/
    layout.tsx
    analyze/page.tsx
    watch/page.tsx
    picks/page.tsx
    leaderboard/page.tsx
    rank/page.tsx              # redirect → /leaderboard
    models/[id]/page.tsx
    api/analyze/route.ts
    api/watch/route.ts
    api/picks/route.ts
    api/leaderboard/route.ts
    api/rank/route.ts          # alias
    api/models/route.ts
  components/
    shell/
    controls/
    analyze/
    watch/
    picks/
    leaderboard/
      LeaderboardTable.tsx
      ModelRankRow.tsx
      ScoreBar.tsx
      RankMedal.tsx
      WinnerBadge.tsx
      EnginesOnlyToggle.tsx
      ModelRankCard.tsx
      TopModelsStrip.tsx
  lib/trade-desk/
    types.ts
    client.ts
    mapPlan.ts
```

---

## Watch

### `WatchBoard`

| Prop | Type | Source |
|------|------|--------|
| `rows` | `SnapshotRow[]` | `_snapshot_row` / watch JSON |
| `alerts` | `string[]?` | action change messages |
| `lastTick` | `string?` | ISO time |
| `onSelectSymbol` | `(sym: string) => void` | |

### `WatchRow`

Fields: `symbol`, `action`, `price`, `confidence`, `rvol`, `vol_surge`, `vol_dry`, `ema22`, `ema200`, `above_ema22`, `near_ema22`, `do_next`, `setup_kind`, `breakout_level`.

### `WatchControls`

`symbols`, `every`, `interval`, `model`, `account`, `riskPct`, running toggle.

---

## Picks

### `PicksFilters`

horizon, model, sectors, symbols, top (rotate).

### `PicksGroups`

Groups rows by action / `setup_kind` (mirror `_print_picks` / `_print_rotate`).

### `PickRow`

`symbol`, `action`, `setup_kind`, `price`, `confidence`, `dollar_risk`, tip/do_next.