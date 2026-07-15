"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { formatNum, formatPctPoints } from "@/lib/format";
import type { GammaResponse, GammaStrike } from "@/lib/types";

const BRAND = "var(--td-brand)";
const AVOID = "var(--td-action-avoid)";
const BUY = "var(--td-action-buy-now)";
const AMBER = "var(--td-action-breakout-watch)";
const BODY = "var(--td-body)";
const INK = "var(--td-ink-100)";
const MUTED = "var(--td-ink-500)";
const GRID = "var(--td-hairline)";

const CHART_H = 360;
const TOP_PAD = 62;
const BOTTOM_PAD = 34;
const PLOT_H = CHART_H - TOP_PAD - BOTTOM_PAD;
const BASELINE_Y = TOP_PAD + PLOT_H / 2;
const MIN_SLOT_W = 12;
type ExposureSeries = "net" | "calls" | "puts";

function exposureValue(strike: GammaStrike, series: ExposureSeries): number {
  if (series === "calls") return strike.call_gex;
  if (series === "puts") return strike.put_gex;
  return strike.net_gex;
}

function useGammaLayout(data: GammaResponse, wrapWidth: number, rangePct: number | null, series: ExposureSeries) {
  return useMemo(() => {
    const spot = data.spot;
    const put = data.put_wall ?? data.expected_move_low ?? spot * 0.75;
    const call = data.call_wall ?? data.expected_move_high ?? spot * 1.25;
    const low = data.expected_move_low ?? spot * 0.85;
    const high = data.expected_move_high ?? spot * 1.15;
    const markerValues = [put, call, low, high, data.approx_flip_strike, data.max_pain].filter(
      (value): value is number => typeof value === "number" && Number.isFinite(value),
    );
    const displayMin = rangePct == null
      ? Math.min(spot * 0.8, ...markerValues.map((value) => value * 0.97))
      : spot * (1 - rangePct / 100);
    const displayMax = rangePct == null
      ? Math.max(spot * 1.2, ...markerValues.map((value) => value * 1.03))
      : spot * (1 + rangePct / 100);

    const filtered = data.by_strike
      .filter((s) => s.strike >= displayMin && s.strike <= displayMax)
      .filter((s) => Math.abs(exposureValue(s, series)) > 1e-9)
      .sort((a, b) => a.strike - b.strike);

    const n = filtered.length;
    const maxAbs = Math.max(1, ...filtered.map((s) => Math.abs(exposureValue(s, series))));
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

    return { filtered, maxAbs, width, minWidth, barW, xForIndex, xForValue, labelStep, displayMin, displayMax };
  }, [data, wrapWidth, rangePct, series]);
}

function tagForStrike(data: GammaResponse, strike: number): string | null {
  if (data.call_wall != null && Math.abs(data.call_wall - strike) < 1e-9) return "CALL WALL";
  if (data.put_wall != null && Math.abs(data.put_wall - strike) < 1e-9) return "PUT WALL";
  if (data.approx_flip_strike != null && Math.abs(data.approx_flip_strike - strike) < 1e-9) return "FLIP";
  if (data.max_pain != null && Math.abs(data.max_pain - strike) < 1e-9) return "MAX PAIN";
  return null;
}

export function GammaScene({ data }: { data: GammaResponse }) {
  const titleId = useId();
  const descId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [wrapWidth, setWrapWidth] = useState(0);
  const [hover, setHover] = useState<{ strike: GammaStrike; index: number } | null>(null);
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
  const [rangePct, setRangePct] = useState<number | null>(10);
  const [series, setSeries] = useState<ExposureSeries>("net");
  const layout = useGammaLayout(data, wrapWidth, rangePct, series);
  const { filtered, maxAbs, width, minWidth, barW, xForIndex, xForValue, labelStep, displayMin, displayMax } = layout;

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

  const seriesLabel = series === "net" ? "Net" : series === "calls" ? "Calls" : "Puts";
  const seriesColor = series === "calls" ? BUY : series === "puts" ? AVOID : BRAND;

  const callWallDist = data.dist_call_wall_pct != null ? ` (${formatPctPoints(data.dist_call_wall_pct)})` : "";
  const putWallDist = data.dist_put_wall_pct != null ? ` (${formatPctPoints(data.dist_put_wall_pct)})` : "";
  const expectedMoveVisible = data.expected_move_low != null && data.expected_move_high != null
    && data.expected_move_low >= displayMin && data.expected_move_high <= displayMax;
  const markers: { value: number; label: string; stroke: string; labelColor: string; dash: string; strokeWidth: number }[] = [
    { value: data.call_wall ?? NaN, label: `CALL WALL ${formatNum(data.call_wall)}${callWallDist}`, stroke: BUY, labelColor: BUY, dash: "4 2", strokeWidth: 1.5 },
    { value: data.put_wall ?? NaN, label: `PUT WALL ${formatNum(data.put_wall)}${putWallDist}`, stroke: AVOID, labelColor: AVOID, dash: "4 2", strokeWidth: 1.5 },
    { value: data.approx_flip_strike ?? NaN, label: `FLIP ${formatNum(data.approx_flip_strike)}`, stroke: AMBER, labelColor: AMBER, dash: "2 3", strokeWidth: 2 },
    { value: data.max_pain ?? NaN, label: `MAX PAIN ${formatNum(data.max_pain)}`, stroke: BODY, labelColor: MUTED, dash: "6 3", strokeWidth: 1 },
  ].filter((m) => Number.isFinite(m.value) && m.value >= displayMin && m.value <= displayMax);

  return (
    <div className="relative">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3 border-b pb-3" style={{ borderColor: GRID }}>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Exposure side">
          {(["net", "calls", "puts"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={series === value}
              onClick={() => setSeries(value)}
              className="td-btn td-btn-ghost px-2 py-1 text-[10px]"
              style={series === value ? { borderColor: seriesColor, color: seriesColor } : undefined}
            >
              {value}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Strike range around spot">
          <span className="mr-1 text-[10px] uppercase tracking-wider" style={{ color: MUTED }}>Strikes</span>
          {([5, 10, 20, null] as const).map((value) => (
            <button
              key={value ?? "all"}
              type="button"
              aria-pressed={rangePct === value}
              onClick={() => setRangePct(value)}
              className="td-btn td-btn-ghost px-2 py-1 text-[10px]"
              style={rangePct === value ? { borderColor: INK, color: INK } : undefined}
            >
              {value == null ? "All" : `±${value}%`}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="flex h-72 w-full items-center justify-center text-[13px]" style={{ color: MUTED }}>
          No {seriesLabel.toLowerCase()} gamma at the selected strikes.
        </div>
      ) : (
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: "easeOut" }}>
      <div
        ref={wrapRef}
        className="relative w-full overflow-x-auto"
        style={{ minHeight: CHART_H, minWidth }}
      >
        <svg
          width={width}
          height={CHART_H}
          viewBox={`0 0 ${width} ${CHART_H}`}
          role="img"
          aria-labelledby={`${titleId} ${descId}`}
          onMouseMove={handleMove}
          onMouseLeave={() => {
            setHover(null);
            setPointer(null);
          }}
        >
          <title id={titleId}>{data.symbol} gamma exposure by strike</title>
          <desc id={descId}>
            Spot {formatNum(data.spot)}. Call wall {formatNum(data.call_wall)}. Put wall {formatNum(data.put_wall)}.
            Expected move {formatNum(data.expected_move_low)} to {formatNum(data.expected_move_high)}. Flip{" "}
            {formatNum(data.approx_flip_strike)}. Max pain {formatNum(data.max_pain)}.
          </desc>
          <rect x={0} y={TOP_PAD} width={width} height={PLOT_H} fill="var(--td-canvas)" />

          {/* expected move band */}
          {expectedMoveVisible && data.expected_move_low != null && data.expected_move_high != null ? (
            <g>
              <rect
                x={xForValue(data.expected_move_low)}
                y={TOP_PAD}
                width={Math.max(xForValue(data.expected_move_high) - xForValue(data.expected_move_low), 1)}
                height={PLOT_H}
                fill="var(--td-brand-soft)"
                fillOpacity={0.22}
              />
              <text
                x={xForValue(data.expected_move_low)}
                y={TOP_PAD + 12}
                fontSize={9}
                fontFamily="var(--td-font-mono)"
                fill={MUTED}
                textAnchor="start"
              >
                EM LOW {formatNum(data.expected_move_low)}
              </text>
              <text
                x={xForValue(data.expected_move_high)}
                y={TOP_PAD + 12}
                fontSize={9}
                fontFamily="var(--td-font-mono)"
                fill={MUTED}
                textAnchor="end"
              >
                EM HIGH {formatNum(data.expected_move_high)}
              </text>
            </g>
          ) : null}

          {[0.25, 0.5, 0.75].map((p) => (
            <line
              key={p}
              x1={0}
              x2={width}
              y1={TOP_PAD + PLOT_H * p}
              y2={TOP_PAD + PLOT_H * p}
              stroke={GRID}
              strokeWidth={p === 0.5 ? 1 : 0.5}
              opacity={p === 0.5 ? 0.9 : 0.55}
            />
          ))}

          {/* zero baseline */}
          <line x1={0} x2={width} y1={BASELINE_Y} y2={BASELINE_Y} stroke={INK} strokeWidth={1.5} />

          {/* bars */}
          {filtered.map((s, i) => {
            const value = exposureValue(s, series);
            const h = (Math.abs(value) / maxAbs) * (PLOT_H / 2);
            const x = xForIndex(i) - barW / 2;
            const y = value >= 0 ? BASELINE_Y - h : BASELINE_Y;
            const isHover = hover?.index === i;
            const tag = tagForStrike(data, s.strike);
            const fill = series === "net" ? (value >= 0 ? BRAND : AVOID) : seriesColor;
            return (
              <g key={s.strike}>
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={Math.max(h, 0.5)}
                  fill={fill}
                  fillOpacity={isHover ? 1 : 0.8}
                  stroke={isHover ? INK : "none"}
                  strokeWidth={isHover ? 1 : 0}
                  onMouseEnter={() => setHover({ strike: s, index: i })}
                >
                  <title>
                    {`Strike ${formatNum(s.strike)}; ${seriesLabel} GEX ${formatNum(value, 0)}; Net ${formatNum(s.net_gex, 0)}; Call ${formatNum(s.call_gex, 0)}; Put ${formatNum(s.put_gex, 0)}`}
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
            {seriesLabel.toUpperCase()} +{formatNum(maxAbs, 0)}
          </text>
          <text x={4} y={BASELINE_Y - 4} fontSize={10} fontFamily="var(--td-font-mono)" fill={MUTED}>
            0
          </text>
          <text x={4} y={CHART_H - BOTTOM_PAD + 16} fontSize={10} fontFamily="var(--td-font-mono)" fill={MUTED}>
            -{formatNum(maxAbs, 0)}
          </text>

          {/* marker lines */}
          {markers.map((m) => {
            const x = xForValue(m.value);
            return (
              <line
                key={m.label}
                x1={x}
                x2={x}
                y1={TOP_PAD}
                y2={CHART_H - BOTTOM_PAD}
                stroke={m.stroke}
                strokeWidth={m.strokeWidth}
                strokeDasharray={m.dash}
                opacity={0.9}
              />
            );
          })}

          {/* spot line */}
          <line
            x1={xForValue(data.spot)}
            x2={xForValue(data.spot)}
            y1={TOP_PAD}
            y2={CHART_H - BOTTOM_PAD}
            stroke={INK}
            strokeWidth={2}
            strokeDasharray="4 2"
          />

          {/* marker labels */}
          {markers.map((m, i) => {
            const x = xForValue(m.value);
            return (
              <text
                key={`${m.label}-label`}
                x={x}
                y={4 + i * 12}
                textAnchor={anchorForX(x)}
                dominantBaseline="hanging"
                fontSize={10}
                fontFamily="var(--td-font-mono)"
                fill={m.labelColor}
                pointerEvents="none"
              >
                {m.label}
              </text>
            );
          })}

          {/* spot label, drawn last */}
          <text
            x={xForValue(data.spot)}
            y={TOP_PAD - 6}
            textAnchor={anchorForX(xForValue(data.spot))}
            fontSize={10}
            fontWeight={600}
            fontFamily="var(--td-font-mono)"
            fill={INK}
            pointerEvents="none"
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
          <div style={{ color: series === "net" ? (hover.strike.net_gex >= 0 ? BRAND : AVOID) : seriesColor }}>
            {seriesLabel} GEX {formatNum(exposureValue(hover.strike, series), 0)}
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
      )}
    </div>
  );
}
