"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { formatNum } from "@/lib/format";
import type { GammaResponse, GammaStrike } from "@/lib/types";

const BRAND = "var(--td-brand)";
const AVOID = "var(--td-action-avoid)";
const BUY = "var(--td-action-buy-now)";
const INK = "var(--td-ink-100)";
const MUTED = "var(--td-ink-500)";

const CHART_H = 360;
const TOP_PAD = 34;
const BOTTOM_PAD = 34;
const PLOT_H = CHART_H - TOP_PAD - BOTTOM_PAD;
const BASELINE_Y = TOP_PAD + PLOT_H / 2;
const MIN_SLOT_W = 12;

function useGammaLayout(data: GammaResponse, wrapWidth: number) {
  return useMemo(() => {
    const spot = data.spot;
    const put = data.put_wall ?? data.expected_move_low ?? spot * 0.75;
    const call = data.call_wall ?? data.expected_move_high ?? spot * 1.25;
    const low = data.expected_move_low ?? spot * 0.85;
    const high = data.expected_move_high ?? spot * 1.15;
    const displayMin = Math.min(spot * 0.8, put * 0.97, low * 0.97);
    const displayMax = Math.max(spot * 1.2, call * 1.03, high * 1.03);

    const filtered = data.by_strike
      .filter((s) => s.strike >= displayMin && s.strike <= displayMax)
      .filter((s) => Math.abs(s.call_gex) > 1e-9 || Math.abs(s.put_gex) > 1e-9)
      .sort((a, b) => a.strike - b.strike);

    const n = filtered.length;
    const maxAbs = Math.max(1, ...filtered.map((s) => Math.abs(s.net_gex)));
    const minWidth = n > 0 ? n * MIN_SLOT_W : 320;
    const width = Math.max(minWidth, wrapWidth || minWidth);
    const slotW = n > 0 ? width / n : width;
    const barW = Math.max(slotW * 0.62, 3);

    const xForIndex = (i: number) => slotW * (i + 0.5);

    const xForValue = (value: number) => {
      if (n === 0) return width / 2;
      if (value <= filtered[0].strike) return xForIndex(0);
      if (value >= filtered[n - 1].strike) return xForIndex(n - 1);
      for (let i = 0; i < n - 1; i++) {
        const a = filtered[i];
        const b = filtered[i + 1];
        if (value >= a.strike && value <= b.strike) {
          const t = (value - a.strike) / (b.strike - a.strike || 1);
          return xForIndex(i) + t * (xForIndex(i + 1) - xForIndex(i));
        }
      }
      return width / 2;
    };

    const labelStep = Math.max(1, Math.ceil(46 / slotW));

    return { filtered, maxAbs, width, minWidth, barW, xForIndex, xForValue, labelStep };
  }, [data, wrapWidth]);
}

function tagForStrike(data: GammaResponse, strike: number): string | null {
  if (data.call_wall != null && Math.abs(data.call_wall - strike) < 1e-9) return "CALL WALL";
  if (data.put_wall != null && Math.abs(data.put_wall - strike) < 1e-9) return "PUT WALL";
  if (data.approx_flip_strike != null && Math.abs(data.approx_flip_strike - strike) < 1e-9) return "FLIP";
  if (data.max_pain != null && Math.abs(data.max_pain - strike) < 1e-9) return "MAX PAIN";
  return null;
}

export function GammaScene({ data }: { data: GammaResponse }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [wrapWidth, setWrapWidth] = useState(0);
  const [hover, setHover] = useState<{ strike: GammaStrike; index: number } | null>(null);
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
  const layout = useGammaLayout(data, wrapWidth);
  const { filtered, maxAbs, width, minWidth, barW, xForIndex, xForValue, labelStep } = layout;

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    setWrapWidth(el.clientWidth);
    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver((entries) => {
            const cr = entries[0]?.contentRect;
            if (cr) setWrapWidth(cr.width);
          })
        : null;
    ro?.observe(el);
    return () => ro?.disconnect();
  }, []);

  const anchorForX = (x: number) => (x < 50 ? "start" : x > width - 50 ? "end" : "middle");

  const handleMove = (e: React.MouseEvent) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPointer({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  if (filtered.length === 0) {
    return (
      <div className="flex h-96 w-full items-center justify-center text-[13px]" style={{ color: MUTED }}>
        No strikes with measurable gamma in range.
      </div>
    );
  }

  const wallMarkers: { value: number; label: string; color: string }[] = [
    { value: data.call_wall ?? NaN, label: `CALL WALL ${formatNum(data.call_wall ?? 0)}`, color: BUY },
    { value: data.put_wall ?? NaN, label: `PUT WALL ${formatNum(data.put_wall ?? 0)}`, color: AVOID },
  ].filter((m) => Number.isFinite(m.value));

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="relative"
    >
      <div
        ref={wrapRef}
        className="relative w-full overflow-x-auto"
        style={{ minHeight: CHART_H, minWidth }}
      >
        <svg
          width={width}
          height={CHART_H}
          viewBox={`0 0 ${width} ${CHART_H}`}
          onMouseMove={handleMove}
          onMouseLeave={() => {
            setHover(null);
            setPointer(null);
          }}
        >
          {/* expected move band */}
          {data.expected_move_low != null && data.expected_move_high != null ? (
            <rect
              x={xForValue(data.expected_move_low)}
              y={TOP_PAD}
              width={Math.max(xForValue(data.expected_move_high) - xForValue(data.expected_move_low), 1)}
              height={PLOT_H}
              fill="var(--td-brand-soft)"
              fillOpacity={0.22}
            />
          ) : null}

          {/* zero baseline */}
          <line x1={0} x2={width} y1={BASELINE_Y} y2={BASELINE_Y} stroke={INK} strokeWidth={1.5} />

          {/* bars */}
          {filtered.map((s, i) => {
            const net = s.net_gex;
            const h = (Math.abs(net) / maxAbs) * (PLOT_H / 2);
            const x = xForIndex(i) - barW / 2;
            const y = net >= 0 ? BASELINE_Y - h : BASELINE_Y;
            const isHover = hover?.index === i;
            const tag = tagForStrike(data, s.strike);
            return (
              <g key={s.strike}>
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={Math.max(h, 0.5)}
                  fill={net >= 0 ? BRAND : AVOID}
                  fillOpacity={isHover ? 1 : 0.8}
                  stroke={isHover ? INK : "none"}
                  strokeWidth={isHover ? 1 : 0}
                  onMouseEnter={() => setHover({ strike: s, index: i })}
                >
                  <title>
                    {`Strike ${formatNum(s.strike)}; Net GEX ${formatNum(s.net_gex, 0)}; Call ${formatNum(s.call_gex, 0)}; Put ${formatNum(s.put_gex, 0)}`}
                    {tag ? `; ${tag}` : ""}
                  </title>
                </rect>
                {i % labelStep === 0 ? (
                  <text
                    x={xForIndex(i)}
                    y={CHART_H - BOTTOM_PAD + 16}
                    textAnchor="middle"
                    fontSize={10}
                    fontFamily="var(--td-font-mono)"
                    fill={MUTED}
                  >
                    {formatNum(s.strike, 0)}
                  </text>
                ) : null}
              </g>
            );
          })}

          {/* y-axis labels */}
          <text x={width - 4} y={TOP_PAD - 12} fontSize={10} fontFamily="var(--td-font-mono)" fill={MUTED} textAnchor="end">
            +{formatNum(maxAbs, 0)}
          </text>
          <text x={4} y={BASELINE_Y - 4} fontSize={10} fontFamily="var(--td-font-mono)" fill={MUTED}>
            0
          </text>
          <text x={4} y={CHART_H - BOTTOM_PAD + 16} fontSize={10} fontFamily="var(--td-font-mono)" fill={MUTED}>
            -{formatNum(maxAbs, 0)}
          </text>

          {/* wall markers */}
          {wallMarkers.map((m, i) => {
            const x = xForValue(m.value);
            return (
              <g key={m.label}>
                <line
                  x1={x}
                  x2={x}
                  y1={TOP_PAD}
                  y2={CHART_H - BOTTOM_PAD}
                  stroke={m.color}
                  strokeWidth={1.5}
                  strokeDasharray="4 2"
                  opacity={0.9}
                />
                <text
                  x={x}
                  y={TOP_PAD - 20 - i * 6}
                  textAnchor={anchorForX(x)}
                  fontSize={10}
                  fontFamily="var(--td-font-mono)"
                  fill={m.color}
                >
                  {m.label}
                </text>
              </g>
            );
          })}

          {/* spot line and label, drawn last */}
          <line
            x1={xForValue(data.spot)}
            x2={xForValue(data.spot)}
            y1={TOP_PAD}
            y2={CHART_H - BOTTOM_PAD}
            stroke={INK}
            strokeWidth={2}
            strokeDasharray="4 2"
          />
          <text
            x={xForValue(data.spot)}
            y={TOP_PAD - 6}
            textAnchor={anchorForX(xForValue(data.spot))}
            fontSize={10}
            fontWeight={600}
            fontFamily="var(--td-font-mono)"
            fill={INK}
          >
            SPOT {formatNum(data.spot)}
          </text>
        </svg>
      </div>

      {hover && pointer ? (
        <div
          className="pointer-events-none absolute z-10 border px-2 py-1 text-[11px] tabular"
          style={{
            left: Math.min(pointer.x + 12, (wrapRef.current?.clientWidth ?? width) - 160),
            top: Math.max(pointer.y - 64, 0),
            background: "var(--td-surface-card)",
            borderColor: "var(--td-hairline)",
            color: "var(--td-ink-100)",
            fontFamily: "var(--td-font-mono)",
          }}
        >
          <div>STRIKE {formatNum(hover.strike.strike)}</div>
          <div style={{ color: hover.strike.net_gex >= 0 ? BRAND : AVOID }}>
            Net GEX {formatNum(hover.strike.net_gex, 0)}
          </div>
          <div style={{ color: MUTED }}>
            Call {formatNum(hover.strike.call_gex, 0)} · Put {formatNum(hover.strike.put_gex, 0)}
          </div>
          <div style={{ color: MUTED }}>
            Dist {formatNum(((hover.strike.strike - data.spot) / data.spot) * 100, 1)}%
          </div>
          {tagForStrike(data, hover.strike.strike) ? (
            <div style={{ color: INK }}>{tagForStrike(data, hover.strike.strike)}</div>
          ) : null}
        </div>
      ) : null}
    </motion.div>
  );
}
