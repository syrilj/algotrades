"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowUpRight,
  ChartNoAxesCombined,
  CircleDollarSign,
  FlaskConical,
  ScanSearch,
} from "lucide-react";

const VIEWS = [
  {
    id: "analyze",
    label: "Analyze",
    icon: ScanSearch,
    title: "Understand one stock",
    caption: "Price, important levels, and the model’s answer—together.",
    href: "/command?symbol=TSLA&model=auto",
  },
  {
    id: "execute",
    label: "Paper plan",
    icon: CircleDollarSign,
    title: "Turn an idea into a safe plan",
    caption: "Entry, stop, size, and maximum loss before any paper trade.",
    href: "/live?symbol=TSLA",
  },
  {
    id: "options",
    label: "Options",
    icon: ChartNoAxesCombined,
    title: "See the risk shape",
    caption: "Defined loss, time window, volatility, and payoff at a glance.",
    href: "/live?mode=options&symbol=IONQ",
  },
  {
    id: "research",
    label: "Models",
    icon: FlaskConical,
    title: "Know which model earned the job",
    caption: "Compare return, drawdown, consistency, and out-of-sample proof.",
    href: "/research?view=leaderboard",
  },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

export function ProductShowcase() {
  const [activeId, setActiveId] = useState<ViewId>("analyze");
  const active = VIEWS.find((view) => view.id === activeId) ?? VIEWS[0];

  return (
    <div className="td-showcase">
      <div className="td-showcase__tabs" role="tablist" aria-label="Trade Desk workspaces">
        {VIEWS.map((view) => (
          <button
            key={view.id}
            type="button"
            role="tab"
            aria-selected={active.id === view.id}
            className={active.id === view.id ? "is-active" : ""}
            onClick={() => setActiveId(view.id)}
          >
            <view.icon size={17} />
            <span>{view.label}</span>
          </button>
        ))}
      </div>

      <div className="td-showcase__stage" role="tabpanel">
        <header className="td-showcase__head">
          <div>
            <span>WORKSPACE / {active.label.toUpperCase()}</span>
            <h3>{active.title}</h3>
            <p>{active.caption}</p>
          </div>
          <Link href={active.href}>Open workspace <ArrowUpRight size={14} /></Link>
        </header>

        <div className="td-showcase__screen" key={active.id}>
          {active.id === "analyze" ? <AnalyzeScene /> : null}
          {active.id === "execute" ? <ExecutionScene /> : null}
          {active.id === "options" ? <OptionsScene /> : null}
          {active.id === "research" ? <ResearchScene /> : null}
        </div>
      </div>
    </div>
  );
}

function AnalyzeScene() {
  const candles = [46, 54, 43, 62, 57, 72, 68, 81, 76, 89, 84, 96];
  return (
    <div className="td-scene td-scene--analyze">
      <div className="td-scene-chart">
        <div className="td-scene-chart__top"><span>TSLA · 1 hour</span><strong>$248.40</strong></div>
        <div className="td-scene-chart__plot">
          <i className="level level--high"><b>Resistance</b></i>
          <i className="level level--mid"><b>Most traded</b></i>
          <i className="level level--low"><b>Support</b></i>
          {candles.map((height, index) => <span key={index} style={{ height: `${height}%` }} className={index === 3 || index === 4 ? "is-down" : ""} />)}
        </div>
      </div>
      <div className="td-scene-verdict">
        <span>MODEL ANSWER</span>
        <strong>WAIT</strong>
        <p>Good trend. Price is still too far from support.</p>
        <div><span>Trend</span><b>Good</b></div>
        <div><span>Price level</span><b>Too high</b></div>
        <div><span>Risk</span><b>Normal</b></div>
      </div>
    </div>
  );
}

function ExecutionScene() {
  return (
    <div className="td-scene td-scene--execution">
      <div className="td-ticket-visual">
        <header><span>PAPER PLAN</span><b>READY</b></header>
        <strong className="td-ticket-visual__symbol">MU <small>Micron</small></strong>
        <div className="td-ticket-visual__numbers">
          <div><span>Buy near</span><b>$141.20</b></div>
          <div><span>Exit if wrong</span><b>$136.80</b></div>
          <div><span>Shares</span><b>4</b></div>
          <div><span>Most you can lose</span><b>$17.60</b></div>
        </div>
        <footer>Nothing is sent to a broker</footer>
      </div>
      <div className="td-check-visual">
        <span>SAFETY CHECKS</span>
        {["Price is fresh", "Model agrees", "Risk fits", "Stop is valid"].map((label, index) => (
          <div key={label}><i>{index + 1}</i><span>{label}</span><b>✓</b></div>
        ))}
      </div>
    </div>
  );
}

function OptionsScene() {
  return (
    <div className="td-scene td-scene--options">
      <div className="td-payoff-visual">
        <header><span>IONQ · CALL SPREAD</span><b>DEFINED RISK</b></header>
        <svg viewBox="0 0 560 230" role="img" aria-label="Example call spread payoff with limited loss and limited profit">
          <line x1="34" y1="164" x2="530" y2="164" className="axis" />
          <line x1="250" y1="24" x2="250" y2="205" className="strike" />
          <path d="M34 188 L250 188 L390 60 L530 60" className="payoff" />
          <path d="M34 188 L250 188 L390 60 L530 60 L530 164 L34 164 Z" className="payoff-fill" />
          <text x="42" y="215">MAX LOSS $84</text>
          <text x="402" y="42">MAX PROFIT $216</text>
          <text x="260" y="154">BREAKEVEN</text>
        </svg>
      </div>
      <div className="td-vol-visual">
        <span>VOLATILITY</span>
        <strong>Rich</strong>
        <div><i style={{ width: "74%" }} /></div>
        <small>Options cost more than recent movement suggests.</small>
        <dl><div><dt>Time</dt><dd>28 days</dd></div><div><dt>Direction</dt><dd>Up</dd></div></dl>
      </div>
    </div>
  );
}

function ResearchScene() {
  const models = [
    { name: "v72 Dual sleeve", score: "92", width: "92%", role: "Best overall" },
    { name: "v39d Confluence", score: "86", width: "86%", role: "Lower drawdown" },
    { name: "v71 Confidence", score: "71", width: "71%", role: "Higher win rate" },
  ];
  return (
    <div className="td-scene td-scene--research">
      <div className="td-equity-visual">
        <header><span>LOCKED TEST PERIOD</span><b>Out-of-sample</b></header>
        <svg viewBox="0 0 560 220" role="img" aria-label="Illustrative model equity comparison">
          <path d="M20 190 C75 177 96 182 133 150 S215 167 260 122 S340 139 382 92 S465 91 540 35" className="line-a" />
          <path d="M20 190 C85 184 112 160 162 169 S244 138 294 145 S375 101 431 112 S497 85 540 72" className="line-b" />
        </svg>
      </div>
      <div className="td-rank-visual">
        {models.map((model, index) => (
          <div key={model.name}>
            <span>0{index + 1}</span><p><strong>{model.name}</strong><small>{model.role}</small><i><b style={{ width: model.width }} /></i></p><em>{model.score}</em>
          </div>
        ))}
      </div>
    </div>
  );
}
