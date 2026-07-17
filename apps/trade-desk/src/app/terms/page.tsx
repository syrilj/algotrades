import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — Trade Desk",
  description: "Terms of use, simulated trading risks, and educational research constraints.",
};

export default function TermsPage() {
  return (
    <div className="td-legal-page">
      <div className="td-lp-grid" aria-hidden="true" />
      
      <header className="td-legal-header">
        <div className="td-legal-header__inner">
          <Link href="/" className="td-lp-brand">
            <span className="td-lp-brand__mark">TD</span>
            <span className="td-lp-brand__text">
              <span>Trade</span>
              <span>Desk</span>
            </span>
          </Link>
          <Link href="/" className="td-lp-btn td-lp-btn--ghost">
            Back to Home
          </Link>
        </div>
      </header>

      <main className="td-legal-content">
        <article className="td-legal-article">
          <header className="td-legal-article__header">
            <span className="td-lp-kicker">Operator Agreement</span>
            <h1>Terms of Service</h1>
            <p className="td-legal-meta">Last updated: July 16, 2026</p>
          </header>

          <section>
            <h2>1. Agreement to Terms</h2>
            <p>
              By accessing, deploying, or interacting with the Trade Desk operator workstation (locally or over a local network host), you agree to be bound by these Terms of Service. If you do not agree, do not run the Next.js development server or compile the backtesting engines.
            </p>
          </section>

          <section>
            <h2>2. Research & Simulation Scope</h2>
            <p>
              Trade Desk is an educational and research workstation designed for modeling equity trajectories, analyzing historical volume profile confluences, running walk-forward genetic optimizations, and practicing paper risk tickets.
            </p>
            <ul>
              <li>
                <strong>No Live Order Desk:</strong> The terminal does not connect to live stock or options brokers. Action verdicts (e.g. <code>BUY NOW</code>, <code>STAND ASIDE</code>) represent simulated paper conditions, not live orders.
              </li>
              <li>
                <strong>No Financial Advice:</strong> The model scripts (such as <code>v72_dual_sleeve</code>, <code>v39d_confluence</code>, and <code>v71_live_confidence</code>) are academic/backtesting studies on a fixed symbol bag. Nothing shown constitutes investment advice or a solicitation to buy/sell assets.
              </li>
            </ul>
          </section>

          <section>
            <h2>3. Risks of Simulated Trading</h2>
            <p>
              Simulated performance is subject to significant drift compared to live execution. Backtests on local 1H adjusted data are run at fixed cash scales (e.g., $1,000 or $1,000,000) under simplified assumptions. Live execution involves slippage, liquidity constraints, transaction fees, bid-ask spreads, and data latency that backtesting models cannot perfectly simulate.
            </p>
            <p>
              In particular, the temporary and permanent market impact overlay using the Almgren-Chriss engine (e.g., <code>AlmgrenChrissGlobalEquityEngine</code>) is a mathematical estimation and does not represent actual market impact or execution fill rates.
            </p>
          </section>

          <section>
            <h2>4. Source and Local Data Contracts</h2>
            <p>
              You are responsible for obtaining your own clean historical or streaming data feeds (for example, via yfinance, LSE API, or local databases). We do not guarantee the completeness, accuracy, or point-in-time integrity of external feeds. Any data errors can lead to erroneous signals.
            </p>
          </section>

          <section>
            <h2>5. Disclaimer of Warranties</h2>
            <p>
              THE SOFTWARE IS PROVIDED &quot;AS IS&quot;, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE.
            </p>
          </section>

          <section>
            <h2>6. Governing Law</h2>
            <p>
              These terms are governed by the laws of your local jurisdiction, as all computation and storage are carried out locally on your machine.
            </p>
          </section>
        </article>
      </main>

      <footer className="td-legal-footer">
        <p className="td-lp-footnote">
          Trade Desk is simulation and analysis software. Simulated metrics are not live broker executions.
        </p>
      </footer>
    </div>
  );
}
