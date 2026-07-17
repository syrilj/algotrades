import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Statement — Trade Desk",
  description: "Data processing, point-in-time constraints, and local sandbox policies.",
};

export default function PrivacyPage() {
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
            <span className="td-lp-kicker">Data Policy & Contracts</span>
            <h1>Privacy Statement</h1>
            <p className="td-legal-meta">Last updated: July 16, 2026</p>
          </header>

          <section>
            <h2>1. Local Workstation Principles</h2>
            <p>
              Trade Desk is structured as a locally compiled and executed research terminal. All backtesting engines, signal evaluations (such as indicators, Heikin-Ashi trends, and Volume Profile nodes), and XGBoost meta-sizing classifiers run inside your local environment using either local Parquet historical data (e.g., <code>data_cache/</code>) or live streaming tickers (e.g., via local <code>market_runtime</code> database persistence).
            </p>
            <p>
              We do not collect, transmit, or monetize your research setups, feature weights, custom model files (e.g., custom XGBoost parameters or ensembles), or the symbols in your watchlist. Your study data remains on your hardware.
            </p>
          </section>

          <section>
            <h2>2. External Data Fallbacks & API Keys</h2>
            <p>
              The terminal can query external APIs for ticks and candles depending on your local configurations:
            </p>
            <ul>
              <li>
                <strong>LSE market data (LSE_API_KEY):</strong> If configured, the backend queries LSE streaming and vault feeds. Your key stays in server environment variables and is never sent to the browser.
              </li>
              <li>
                <strong>Yahoo Finance fallback:</strong> In the absence of local files, some tools fall back to scraping unadjusted/adjusted public prices. These requests are made directly from your machine to their servers.
              </li>
              <li>
                <strong>MLflow Tracking:</strong> Runs logged to MLflow write to your local directory (<code>runs/mlruns</code>) unless you configure an external telemetry URI.
              </li>
            </ul>
          </section>

          <section>
            <h2>3. Browser Sandbox and Local Storage</h2>
            <p>
              The Next.js user interface writes minor settings to browser <code>localStorage</code> (for example, sidebar collapse state, active charts, or selected model configurations). This data does not leave your machine.
            </p>
          </section>

          <section>
            <h2>4. Security of Local Files</h2>
            <p>
              Because your databases (including <code>data/market_runtime.db</code> and baseline metrics manifests) reside on your physical computer, the security of this data depends on your machine&apos;s access controls. Ensure your workspace directory <code>/Users/syriljacob/Desktop/TradingAlgoWork</code> is secured.
            </p>
          </section>

          <section>
            <h2>5. Contact & Audits</h2>
            <p>
              Because this is an offline research tool, there is no remote cloud server auditing your trades. You can inspect all outbound connections in the terminal console or through the Next.js development server logs.
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
