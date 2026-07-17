"use client";

import { motion } from "framer-motion";

/** Animated terminal mock — research desk, not a live broker ticket. */
export function HeroProductMock() {
  return (
    <div className="td-lp-mock" aria-hidden="true">
      <div className="td-lp-mock__glow" />
      <div className="td-lp-mock__frame">
        <div className="td-lp-mock__chrome">
          <span className="td-lp-mock__dots">
            <i />
            <i />
            <i />
          </span>
          <span className="td-lp-mock__path">command · TSLA · research path</span>
          <span className="td-lp-mock__live">
            <span className="td-lp-mock__pulse" />
            STUDY
          </span>
        </div>

        <div className="td-lp-mock__body">
          <aside className="td-lp-mock__rail">
            {["Command", "Execution", "Portfolio", "Lab"].map((label, i) => (
              <div
                key={label}
                className={`td-lp-mock__rail-item${i === 0 ? " is-active" : ""}`}
              >
                {label}
              </div>
            ))}
          </aside>

          <div className="td-lp-mock__main">
            <div className="td-lp-mock__row">
              <motion.div
                className="td-lp-mock__card td-lp-mock__verdict"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25, duration: 0.5 }}
              >
                <div className="td-lp-mock__eyebrow">Research label</div>
                <motion.div
                  className="td-lp-mock__action"
                  animate={{
                    boxShadow: [
                      "0 0 0 0 rgba(15,163,54,0)",
                      "0 0 20px 0 rgba(15,163,54,0.25)",
                      "0 0 0 0 rgba(15,163,54,0)",
                    ],
                  }}
                  transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
                >
                  BUY NOW
                </motion.div>
                <div className="td-lp-mock__meta">
                  <span>not a live order</span>
                  <span>meta p 0.82</span>
                  <span>Kelly 18%*</span>
                </div>
              </motion.div>

              <motion.div
                className="td-lp-mock__card td-lp-mock__levels"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4, duration: 0.5 }}
              >
                <div className="td-lp-mock__eyebrow">Structure (VP)</div>
                <LevelRow label="VAH" value="248.40" tone="vah" />
                <LevelRow label="POC" value="241.15" tone="poc" />
                <LevelRow label="VAL" value="236.80" tone="val" />
                <LevelRow label="VWAP" value="239.92" tone="vwap" />
              </motion.div>
            </div>

            <motion.div
              className="td-lp-mock__card td-lp-mock__pipeline"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.55, duration: 0.5 }}
            >
              <div className="td-lp-mock__eyebrow">Model path · point-in-time</div>
              <div className="td-lp-mock__stages">
                {["OHLCV", "VP", "HTF", "Rule", "Filter", "Kelly", "Meta", "Label"].map(
                  (s, i) => (
                    <motion.span
                      key={s}
                      className="td-lp-mock__stage"
                      initial={{ opacity: 0.35 }}
                      animate={{ opacity: [0.35, 1, 0.35] }}
                      transition={{
                        duration: 2.8,
                        delay: i * 0.18,
                        repeat: Infinity,
                        ease: "easeInOut",
                      }}
                    >
                      {s}
                    </motion.span>
                  ),
                )}
              </div>
              <div className="td-lp-mock__chart">
                <svg viewBox="0 0 360 72" preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="lp-eq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--td-brand)" stopOpacity="0.35" />
                      <stop offset="100%" stopColor="var(--td-brand)" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <motion.path
                    d="M0 52 C 30 48, 50 40, 70 42 S 110 58, 140 36 S 200 18, 230 28 S 290 50, 320 22 S 350 14, 360 18"
                    fill="none"
                    stroke="var(--td-brand)"
                    strokeWidth="1.6"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ duration: 1.6, ease: "easeOut" }}
                  />
                  <path
                    d="M0 52 C 30 48, 50 40, 70 42 S 110 58, 140 36 S 200 18, 230 28 S 290 50, 320 22 S 350 14, 360 18 L 360 72 L 0 72 Z"
                    fill="url(#lp-eq)"
                  />
                  <line
                    x1="0"
                    y1="28"
                    x2="360"
                    y2="28"
                    stroke="var(--td-overlay-poc)"
                    strokeDasharray="3 4"
                    strokeOpacity="0.55"
                  />
                </svg>
              </div>
            </motion.div>

            <div className="td-lp-mock__ticker-row">
              {["TSLA", "MU", "SPY", "QQQ", "IONQ"].map((t, i) => (
                <motion.div
                  key={t}
                  className="td-lp-mock__ticker"
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.7 + i * 0.06 }}
                >
                  <strong>{t}</strong>
                  <span className={i % 2 === 0 ? "up" : "down"}>
                    {i % 2 === 0 ? "+1.4%" : "−0.6%"}
                  </span>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function LevelRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "vah" | "poc" | "val" | "vwap";
}) {
  return (
    <div className={`td-lp-mock__level td-lp-mock__level--${tone}`}>
      <span>{label}</span>
      <strong className="tabular">{value}</strong>
    </div>
  );
}
