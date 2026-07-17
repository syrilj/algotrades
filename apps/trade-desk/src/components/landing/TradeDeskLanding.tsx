"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Check,
  Database,
  Gauge,
  Layers3,
  ShieldCheck,
} from "lucide-react";
import { ThreeDDataFlow } from "./ThreeDDataFlow";
import { ProductShowcase } from "./ProductShowcase";
import { CHAMPIONS, WINNER_BAG } from "./landingData";
import { analyzeHref } from "@/lib/routes";

const SIMPLE_STEPS = [
  { n: "01", icon: Database, title: "Read the market", text: "Price, volume, trend, and volatility." },
  { n: "02", icon: BarChart3, title: "Find a setup", text: "Support, momentum, or an oversold bounce." },
  { n: "03", icon: ShieldCheck, title: "Check the risk", text: "Fresh data, model agreement, size, and stop." },
  { n: "04", icon: Gauge, title: "Show one answer", text: "Buy, wait, avoid, or a paper plan." },
] as const;

export function TradeDeskLanding() {
  return (
    <div className="td-lp td-lp--visual">
      <div className="td-lp-grid" aria-hidden="true" />
      <header className="td-lp-nav">
        <div className="td-lp-nav__inner">
          <Link href="/" className="td-lp-brand" aria-label="Trade Desk home">
            <span className="td-lp-brand__mark">TD</span>
            <span className="td-lp-brand__text"><span>Trade</span><span>Desk</span></span>
          </Link>
          <nav className="td-lp-nav__links" aria-label="Product navigation">
            <a href="#product">Product</a>
            <a href="#how">How it works</a>
            <a href="#models">Models</a>
          </nav>
          <div className="td-lp-nav__actions">
            <Link href="/profile" className="td-lp-btn td-lp-btn--ghost td-lp-profile-link">Profile</Link>
            <Link href="/command" className="td-lp-btn td-lp-btn--primary">Open desk <ArrowRight size={14} /></Link>
          </div>
        </div>
      </header>

      <main>
        <section className="td-lp-hero td-lp-hero--visual">
          <div className="td-lp-hero__copy">
            <div className="td-lp-badge"><span className="td-lp-badge__dot" /> Research with a visible safety check</div>
            <h1>Know the plan.<br /><em>See the risk.</em></h1>
            <p>Pick a stock. Trade Desk shows what the models see, what could go wrong, and what to do next.</p>
            <div className="td-lp-hero__ctas">
              <Link href="/command?symbol=TSLA&model=auto" className="td-lp-btn td-lp-btn--primary td-lp-btn--lg">Try TSLA <ArrowRight size={16} /></Link>
              <a href="#product" className="td-lp-btn td-lp-btn--ghost td-lp-btn--lg">See the product</a>
            </div>
            <div className="td-lp-simple-proof">
              <span><Check size={12} /> Real market inputs</span>
              <span><Check size={12} /> Tested models</span>
              <span><Check size={12} /> Paper plans only</span>
            </div>
          </div>
          <div className="td-lp-hero__visual"><ThreeDDataFlow /></div>
        </section>

        <div className="td-lp-symbol-strip" aria-label="Popular symbols">
          <span>START WITH</span>
          {WINNER_BAG.map((item) => (
            <Link key={item.code} href={analyzeHref({ symbol: item.code, model: "auto" })}>
              <strong>{item.code}</strong><small>{item.name}</small>
            </Link>
          ))}
        </div>

        <section id="product" className="td-lp-section td-lp-product-section">
          <div className="td-lp-section__head td-lp-section__head--split">
            <div><p className="td-lp-kicker">One desk, four jobs</p><h2>From “what is happening?”<br />to “what is my risk?”</h2></div>
            <p>Switch between analysis, paper execution, options, and model research without losing the stock you are studying.</p>
          </div>
          <ProductShowcase />
        </section>

        <section id="how" className="td-lp-section td-lp-how-simple">
          <div className="td-lp-section__head">
            <p className="td-lp-kicker">No black box</p>
            <h2>Four steps. One clear answer.</h2>
          </div>
          <div className="td-lp-simple-steps">
            {SIMPLE_STEPS.map((step) => (
              <article key={step.n}>
                <span>{step.n}</span><step.icon size={20} /><h3>{step.title}</h3><p>{step.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="models" className="td-lp-section td-lp-model-jobs">
          <div className="td-lp-section__head td-lp-section__head--split">
            <div><p className="td-lp-kicker">Different tools for different jobs</p><h2>Meet the model team.</h2></div>
            <p>No single model wins at everything. The desk routes each one to the job it does best.</p>
          </div>
          <div className="td-model-jobs">
            {CHAMPIONS.map((model, index) => {
              const visualValues = index === 0 ? [38, 46, 43, 59, 65, 62, 78, 91] : index === 1 ? [32, 38, 42, 47, 53, 61, 68, 76] : [28, 34, 31, 43, 49, 55, 58, 66];
              return (
                <article key={model.id} className={model.winner ? "is-primary" : ""}>
                  <header><span>0{index + 1}</span><b>{index === 0 ? "Best overall" : index === 1 ? "Steadier core" : "Selective sniper"}</b></header>
                  <div className="td-model-jobs__spark" aria-hidden="true">
                    {visualValues.map((value, i) => <i key={i} style={{ height: `${value}%` }} />)}
                  </div>
                  <h3>{model.id.replaceAll("_", " ")}</h3>
                  <p>{index === 0 ? "Combines a patient sniper with a steadier core." : index === 1 ? "Looks for price and volume agreeing near support." : "Waits for rare oversold setups inside a healthy trend."}</p>
                  <dl>
                    <div><dt>{model.metrics[0].label.replace("*", "")}</dt><dd>{model.metrics[0].value}</dd></div>
                    <div><dt>{model.metrics[1].label.replace("*", "")}</dt><dd>{model.metrics[1].value}</dd></div>
                    <div><dt>{model.metrics[3].label.replace("*", "")}</dt><dd>{model.metrics[3].value}</dd></div>
                  </dl>
                  <Link href={analyzeHref({ symbol: "TSLA", model: model.id })}>See it work <ArrowRight size={13} /></Link>
                </article>
              );
            })}
          </div>
          <p className="td-lp-metrics-note">Historical simulations, not promised returns. Models are judged on locked data they did not train on.</p>
        </section>

        <section className="td-lp-final-cta">
          <div className="td-lp-final-cta__mark"><Layers3 size={26} /></div>
          <div><span>READY TO EXPLORE?</span><h2>Start with one stock.</h2><p>The desk will show the rest.</p></div>
          <Link href="/command" className="td-lp-btn td-lp-btn--primary td-lp-btn--lg">Open Trade Desk <ArrowRight size={16} /></Link>
        </section>
      </main>

      <footer id="footer" className="td-lp-footer td-lp-footer--complete">
        <div className="td-lp-footer__main">
          <div className="td-lp-footer__brand">
            <div className="td-lp-brand"><span className="td-lp-brand__mark">TD</span><span className="td-lp-brand__text"><span>Trade</span><span>Desk</span></span></div>
            <p>Market research that shows its work.</p>
            <span className="td-lp-footer__status"><i /> Local research system</span>
          </div>
          <div><strong>Explore</strong><Link href="/command">Analyze a stock</Link><Link href="/live">Paper execution</Link><Link href="/live?mode=options">Options</Link><Link href="/positions">Portfolio</Link></div>
          <div><strong>Research</strong><Link href="/research?view=leaderboard">Model leaderboard</Link><Link href="/research?view=backtest">Backtests</Link><Link href="/research?view=evolve">Model lab</Link><Link href="/analysis-agent">Analysis agent</Link></div>
          <div><strong>Workspace</strong><Link href="/profile">Profile</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></div>
        </div>
        <div className="td-lp-footer__bottom">
          <span>© 2026 Trade Desk</span>
          <p>Quantitative research and paper-risk software. Not investment advice. Never sends broker orders.</p>
          <span>TradingAlgoWork / local</span>
        </div>
      </footer>
    </div>
  );
}
