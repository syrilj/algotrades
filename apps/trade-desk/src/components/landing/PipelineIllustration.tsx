"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PIPELINE_DETAILS } from "./landingData";

export function PipelineIllustration() {
  const [selectedStepN, setSelectedStepN] = useState<string>("01");
  const [selectedModel, setSelectedModel] = useState<"stacking" | "metaSizer" | "sniper">("stacking");

  const currentStep =
    PIPELINE_DETAILS.find((s) => s.n === selectedStepN) || PIPELINE_DETAILS[0];

  const modelsList = [
    { key: "stacking", label: "Hierarchical Stacking", desc: "Sleeve Stacking Ensemble" },
    { key: "metaSizer", label: "XGBoost Meta-Sizer", desc: "Confluence Meta Classifier" },
    { key: "sniper", label: "Mean-Reversion Sniper", desc: "Confidence Scaled Sniper" },
  ] as const;

  // Render a stage-specific visual interactive widget
  const renderVisualWidget = (stepN: string) => {
    switch (stepN) {
      case "01": // OHLCV Ingestion
        return (
          <div className="td-visual-widget td-vw-ingest">
            <div className="td-vw-ingest__flow">
              <div className="td-vw-ingest__node is-source">
                <span>SQLite DB / LSE adapter</span>
                <strong>Raw OHLCV Ticks</strong>
              </div>
              <div className="td-vw-ingest__line"><span className="pulse-dot" /></div>
              <div className="td-vw-ingest__node is-process">
                <span>Lagging Transform (t - 1)</span>
                <strong>PIT Gate</strong>
              </div>
              <div className="td-vw-ingest__line"><span className="pulse-dot" /></div>
              <div className="td-vw-ingest__node is-output">
                <span>Clean Feature Engine</span>
                <strong>Causal hourly bar</strong>
              </div>
            </div>
            <div className="td-vw-info">Verified: Zero lookahead bias detected.</div>
          </div>
        );
      case "02": // Volume Profile
        return (
          <div className="td-visual-widget td-vw-profile">
            <div className="td-vw-profile__chart">
              {[80, 45, 120, 190, 150, 95, 60].map((val, i) => {
                let label = "";
                let styleClass = "";
                if (i === 2) { styleClass = "is-vah"; label = "VAH (248.40)"; }
                if (i === 3) { styleClass = "is-poc"; label = "POC (241.15)"; }
                if (i === 5) { styleClass = "is-val"; label = "VAL (236.80)"; }
                return (
                  <div key={i} className={`td-vw-profile__bar ${styleClass}`} style={{ "--bar-width": `${val}px` } as React.CSSProperties}>
                    <span className="bar-fill" />
                    {label ? <span className="bar-label">{label}</span> : null}
                  </div>
                );
              })}
            </div>
            <div className="td-vw-info">Volume distribution: 70% Value Area mapped.</div>
          </div>
        );
      case "03": // HTF HA Bias
        return (
          <div className="td-visual-widget td-vw-ha">
            <div className="td-vw-ha__candles">
              <div className="ha-candle standard-candle">
                <span>Raw Close</span>
                <div className="candle-body red" style={{ height: "40px" }} />
                <span>$238.90</span>
              </div>
              <div className="ha-arrow">➔</div>
              <div className="ha-candle ha-heikin">
                <span>Heikin-Ashi</span>
                <div className="candle-body green" style={{ height: "50px" }}>
                  <div className="upper-wick" style={{ height: "15px" }} />
                </div>
                <span>$240.12 (BULLISH)</span>
              </div>
            </div>
            <div className="td-vw-info">Result: Trend Gated close filter is ACTIVE (GREEN).</div>
          </div>
        );
      case "04": // Rule Signal
        return (
          <div className="td-visual-widget td-vw-rules">
            <div className="td-vw-rules__chart">
              <svg viewBox="0 0 200 80" className="mini-chart-svg">
                <path d="M10 20 L40 35 L80 60 L110 58 L140 25 L180 15" fill="none" stroke="var(--td-muted)" strokeWidth="2" />
                <circle cx="80" cy="60" r="5" fill="var(--td-action-buy-breakout)" className="ping-dot" />
                <text x="85" y="72" fill="var(--td-action-buy-breakout)" fontSize="10" fontWeight="bold">Touch VAL</text>
              </svg>
              <div className="rules-checklists">
                <div className="check-item is-pass">✔ VAL Rebound</div>
                <div className="check-item is-pass">✔ MACD Histogram &gt; 0</div>
              </div>
            </div>
            <div className="td-vw-info">Trigger: Rebound rule satisfies core entry parameters.</div>
          </div>
        );
      case "05": // Regime Filters
        return (
          <div className="td-visual-widget td-vw-filters">
            <div className="filters-grid">
              <div className="filter-card passed">
                <span className="status-dot green" />
                <strong>SMA(250) Trend Check</strong>
                <span>Price &gt; SMA(250) (Bullish)</span>
              </div>
              <div className="filter-card passed">
                <span className="status-dot green" />
                <strong>Regime Volatility Check</strong>
                <span>Rolling Volatility within safety limits</span>
              </div>
              <div className="filter-card passed">
                <span className="status-dot green" />
                <strong>Macro Event Proximity</strong>
                <span>No major FOMC interest rate events &lt; 2 hrs</span>
              </div>
            </div>
            <div className="td-vw-info">Status: All 3 system filters cleared.</div>
          </div>
        );
      case "06": // Kelly Sizing
        return (
          <div className="td-visual-widget td-vw-kelly">
            <div className="kelly-calculator">
              <div className="kelly-metrics">
                <div><span>Win Rate (W)</span><strong>68%</strong></div>
                <div><span>Reward/Risk (R)</span><strong>2.1x</strong></div>
                <div><span>Kelly Fraction (f*)</span><strong>22.5%</strong></div>
              </div>
              <div className="kelly-progress">
                <div className="progress-track">
                  <div className="progress-bar" style={{ width: "22.5%" }} />
                </div>
                <span>Target Capital Sleeve: 22.5% Allocation</span>
              </div>
            </div>
            <div className="td-vw-info">Adjusted: Scaled down from full Kelly value to contain variance.</div>
          </div>
        );
      case "07": // Meta-Classifier
        return (
          <div className="td-visual-widget td-vw-meta">
            <div className="meta-gauge">
              <div className="gauge-outer">
                <div className="gauge-score">0.82</div>
                <span>XGBoost Probability</span>
              </div>
              <div className="meta-tree-mock">
                <span>f_macd_ha ➔ &gt; 0.12</span>
                <span>f_vol_dev ➔ &lt; 1.5</span>
                <strong className="ok">Success Rate: 82% [PASS]</strong>
              </div>
            </div>
            <div className="td-vw-info">XGBoost meta classification confirms positive expectation.</div>
          </div>
        );
      case "08": // Desk Verdict
        return (
          <div className="td-visual-widget td-vw-verdict">
            <div className="verdict-ticket">
              <div className="verdict-ticket__header">
                <span>PAPER RISK TICKET</span>
                <span className="verdict-badge">BUY NOW</span>
              </div>
              <div className="verdict-ticket__body">
                <div><span>Instrument</span><strong>MU (Micron Tech)</strong></div>
                <div><span>Ordinal confidence</span><strong>0.86 · uncalibrated</strong></div>
                <div><span>Position Scale</span><strong>34.8% (Kelly Adjusted)</strong></div>
                <div><span>Status</span><strong>Operator paper review</strong></div>
              </div>
            </div>
            <div className="td-vw-info">Desk ticket generated. Ready for operator paper review.</div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="td-lp-pipeline-explorer">
      {/* 8 horizontal step buttons */}
      <div className="td-lp-pipeline" role="tablist" aria-label="Pipeline Stages">
        {PIPELINE_DETAILS.map((step, i) => {
          const isActive = step.n === selectedStepN;
          return (
            <button
              key={step.n}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={`pipeline-panel-${step.n}`}
              id={`pipeline-tab-${step.n}`}
              className={`td-lp-pipeline__step td-lp-pipeline__step--btn ${
                isActive ? "is-active" : ""
              }`}
              onClick={() => setSelectedStepN(step.n)}
            >
              <div className="td-lp-pipeline__n">STAGE {step.n}</div>
              <h3>{step.title}</h3>
              <p className="line-clamp-2">{step.concept}</p>
              {i < PIPELINE_DETAILS.length - 1 ? (
                <span className="td-lp-pipeline__conn" aria-hidden="true" />
              ) : null}
            </button>
          );
        })}
      </div>

      {/* Detail Panel */}
      <div
        id={`pipeline-panel-${selectedStepN}`}
        role="tabpanel"
        aria-labelledby={`pipeline-tab-${selectedStepN}`}
        className="td-pipeline-detail-card"
      >
        <div className="td-pipeline-detail-card__grid">
          {/* Left Column: Concept, Math & Visual Widget */}
          <div className="td-pipeline-detail-card__main">
            <span className="td-pipeline-detail-card__badge">
              Stage {currentStep.n} · {currentStep.title}
            </span>
            <h2>{currentStep.title}</h2>
            <p className="td-pipeline-detail-card__desc">{currentStep.concept}</p>

            {/* LaTeX Math block */}
            <div className="td-pipeline-detail-card__math">
              <div className="td-pipeline-detail-card__math-label">Mathematical Concept</div>
              <div className="td-pipeline-detail-card__math-formula">
                <code>{`\\[ ${currentStep.math} \\]`}</code>
              </div>
            </div>

            {/* Stage Visual Widget */}
            <div className="td-pipeline-detail-card__widget-box">
              <div className="td-pipeline-detail-card__math-label">Interactive Stage Simulation</div>
              {renderVisualWidget(currentStep.n)}
            </div>
          </div>

          {/* Right Column: Model Comparison Tabs */}
          <div className="td-pipeline-detail-card__models">
            <div className="td-pipeline-detail-card__math-label">Compare Machine Learning Paradigm</div>
            
            {/* Tabs selector */}
            <div className="td-pipeline-model-tabs" role="tablist" aria-label="Model Engine selection">
              {modelsList.map((m) => {
                const isModelActive = selectedModel === m.key;
                return (
                  <button
                    key={m.key}
                    type="button"
                    role="tab"
                    aria-selected={isModelActive}
                    className={`td-pipeline-model-tab ${isModelActive ? "is-active" : ""}`}
                    onClick={() => setSelectedModel(m.key)}
                  >
                    <strong>{m.label}</strong>
                    <span>{m.desc}</span>
                  </button>
                );
              })}
            </div>

            {/* Behavior text block */}
            <div className="td-pipeline-model-behavior">
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedModel + "_" + selectedStepN}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  transition={{ duration: 0.2 }}
                  className="td-pipeline-model-behavior__inner"
                >
                  <div className="td-pipeline-model-behavior__badge">
                    Paradigm: {modelsList.find((m) => m.key === selectedModel)?.label}
                  </div>
                  <p>{currentStep[selectedModel]}</p>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
