"use client";

import { motion } from "framer-motion";
import { ARCHITECTURE } from "./landingData";

/** Wide landscape: data → features → signals → meta → desk → lab */
export function ArchitectureLandscape() {
  return (
    <div className="td-lp-arch" aria-label="System architecture landscape">
      <div className="td-lp-arch__track">
        {ARCHITECTURE.map((node, i) => (
          <motion.div
            key={node.id}
            className="td-lp-arch__node"
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-30px" }}
            transition={{ delay: i * 0.06, duration: 0.4 }}
          >
            <span className="td-lp-arch__n">{String(i + 1).padStart(2, "0")}</span>
            <strong>{node.label}</strong>
            <p>{node.detail}</p>
            {i < ARCHITECTURE.length - 1 ? (
              <span className="td-lp-arch__arrow" aria-hidden="true">
                →
              </span>
            ) : null}
          </motion.div>
        ))}
      </div>
      <p className="td-lp-arch__note">
        End-to-end is inspectable. Nothing jumps from “AI says so” to a live fill.
        Lab promotion gates sit outside the path until a variant earns a desk seat.
      </p>
    </div>
  );
}
