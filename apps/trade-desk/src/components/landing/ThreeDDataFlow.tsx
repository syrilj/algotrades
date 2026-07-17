"use client";

import { useState } from "react";
import {
  ArrowRight,
  Check,
  Database,
  Gauge,
  Sigma,
  SlidersHorizontal,
} from "lucide-react";

const CANDLES = [
  { o: 52, c: 44, h: 34, l: 68, v: 34 },
  { o: 45, c: 57, h: 38, l: 66, v: 48 },
  { o: 58, c: 50, h: 42, l: 72, v: 39 },
  { o: 51, c: 36, h: 28, l: 61, v: 64 },
  { o: 38, c: 42, h: 30, l: 53, v: 42 },
  { o: 43, c: 30, h: 24, l: 50, v: 78 },
  { o: 31, c: 27, h: 18, l: 39, v: 59 },
  { o: 28, c: 20, h: 12, l: 34, v: 86 },
] as const;

const LANES = [
  {
    id: "structure",
    label: "Price level",
    value: "Back above support",
    note: "Price moved back above a level where buyers were active before.",
    formula: "POC = arg maxₚ Volume(p)",
    tone: "poc",
  },
  {
    id: "momentum",
    label: "Momentum",
    value: "Improving",
    note: "Recent movement is improving. This supports the idea but cannot create a trade alone.",
    formula: "ΔMACDₜ₋₁ > 0",
    tone: "positive",
  },
  {
    id: "regime",
    label: "Big trend",
    value: "Healthy",
    note: "The longer trend is still healthy, so a bounce setup is allowed.",
    formula: "gate = 𝟙[Pₜ₋₁ > SMA₂₅₀]",
    tone: "brand",
  },
  {
    id: "friction",
    label: "Trading cost",
    value: "Low · 3.8 bps",
    note: "Estimated trading cost is included before the paper plan is shown.",
    formula: "I(q) = ησ(q / ADV)ᵝ + γq / ADV",
    tone: "neutral",
  },
] as const;

type LaneId = (typeof LANES)[number]["id"];

/**
 * A compact, inspectable model-path instrument. The old implementation used a
 * decorative 3D spline; this version mirrors how the product is actually used:
 * observed bars become causal features, gates, a probability, then paper size.
 */
export function ThreeDDataFlow() {
  const [activeLane, setActiveLane] = useState<LaneId>("structure");
  const active = LANES.find((lane) => lane.id === activeLane) ?? LANES[0];

  return (
    <div className="td-loom" aria-label="Decision loom showing a model path from market bars to paper verdict">
      <header className="td-loom__header">
        <div>
          <span className="td-loom__eyebrow">LIVE EXAMPLE · TSLA / 1H</span>
          <strong>How the desk makes a decision</strong>
        </div>
        <div className="td-loom__clock">
          <span className="td-loom__status" aria-hidden="true" />
          <span>FRESH DATA</span>
          <time>14:00:00Z</time>
        </div>
      </header>

      <div className="td-loom__body">
        <section className="td-loom__tape" aria-label="Observed price and volume bars">
          <div className="td-loom__column-head">
            <span><Database size={12} /> market price</span>
            <span>recent</span>
          </div>
          <div className="td-loom__price-scale" aria-hidden="true">
            <span>248.40</span>
            <span>241.15</span>
            <span>236.80</span>
          </div>
          <div className="td-loom__candles" aria-hidden="true">
            <span className="td-loom__level td-loom__level--vah" />
            <span className="td-loom__level td-loom__level--poc" />
            <span className="td-loom__level td-loom__level--val" />
            {CANDLES.map((bar, index) => {
              const up = bar.c < bar.o;
              const top = Math.min(bar.o, bar.c);
              const height = Math.max(4, Math.abs(bar.c - bar.o));
              return (
                <span className="td-loom__bar" key={index}>
                  <i
                    className={`td-loom__wick${up ? " is-up" : " is-down"}`}
                    style={{ top: `${bar.h}%`, height: `${bar.l - bar.h}%` }}
                  />
                  <i
                    className={`td-loom__candle${up ? " is-up" : " is-down"}`}
                    style={{ top: `${top}%`, height: `${height}%` }}
                  />
                  <i className="td-loom__volume" style={{ height: `${bar.v * 0.25}%` }} />
                </span>
              );
            })}
          </div>
          <div className="td-loom__tape-foot">
            <span>Local adjusted OHLCV</span>
            <span>8 / 8 complete</span>
          </div>
        </section>

        <div className="td-loom__transfer" aria-hidden="true">
          <span className="td-loom__packet" />
          <ArrowRight size={14} />
        </div>

        <section className="td-loom__features" aria-label="Derived causal feature lanes">
          <div className="td-loom__column-head">
            <span><Sigma size={12} /> what the model sees</span>
            <span>4 checks</span>
          </div>
          <div className="td-loom__lane-list">
            {LANES.map((lane, index) => (
              <button
                type="button"
                key={lane.id}
                className={`td-loom__lane is-${lane.tone}${activeLane === lane.id ? " is-active" : ""}`}
                onClick={() => setActiveLane(lane.id)}
                aria-pressed={activeLane === lane.id}
              >
                <span className="td-loom__lane-index">0{index + 1}</span>
                <span>
                  <strong>{lane.label}</strong>
                  <small>{lane.value}</small>
                </span>
                <Check size={12} aria-label="Passed" />
              </button>
            ))}
          </div>
          <div className="td-loom__inspect" aria-live="polite">
            <div>
              <span>INSPECTING / {active.label.toUpperCase()}</span>
              <code>{active.value}</code>
            </div>
            <p>{active.note}</p>
          </div>
        </section>

        <div className="td-loom__transfer" aria-hidden="true">
          <span className="td-loom__packet td-loom__packet--delay" />
          <ArrowRight size={14} />
        </div>

        <section className="td-loom__decision" aria-label="Model decision and paper sizing">
          <div className="td-loom__column-head">
            <span><Gauge size={12} /> answer</span>
            <span>v72</span>
          </div>
          <div className="td-loom__score">
            <div className="td-loom__score-top">
              <span>Model score</span>
              <strong>0.68</strong>
            </div>
            <div className="td-loom__score-track" aria-label="Meta probability 0.68; gate 0.55">
              <span style={{ width: "68%" }} />
              <i style={{ left: "55%" }} />
            </div>
            <div className="td-loom__score-scale"><span>0</span><span>gate .55</span><span>1</span></div>
          </div>
          <dl className="td-loom__checks">
            <div><dt>Setup</dt><dd>PASS</dd></div>
            <div><dt>Core model</dt><dd>18%</dd></div>
            <div><dt>Sniper model</dt><dd>9%</dd></div>
            <div><dt>Size limit</dt><dd>50%</dd></div>
          </dl>
          <div className="td-loom__verdict">
            <span><SlidersHorizontal size={12} /> PAPER LABEL</span>
            <strong>BUY NOW</strong>
            <small>Target fraction <b>0.27</b> · operator review required</small>
          </div>
        </section>
      </div>

      <footer className="td-loom__footer">
        <span>Market</span><i />
        <span>Setup</span><i />
        <span>Safety</span><i />
        <span>Paper plan</span>
        <small>Illustrative trace · historical metrics are simulated</small>
      </footer>
    </div>
  );
}
