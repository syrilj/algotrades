"use client";

import Link from "next/link";
import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  Brain,
  ChartNoAxesCombined,
  Check,
  ChevronDown,
  CircleDollarSign,
  FlaskConical,
  Layers3,
  Menu,
  ScanSearch,
  ShieldCheck,
  X,
} from "lucide-react";

import { analyzeHref } from "@/lib/routes";
import { CHAMPIONS, FAQ, FEATURES, STATS, WINNER_BAG } from "./landingData";

const EASE = [0.16, 1, 0.3, 1] as const;

const iconMap: Record<string, LucideIcon> = {
  ScanSearch,
  CircleDollarSign,
  FlaskConical,
  ShieldCheck,
  ChartNoAxesCombined,
  Brain,
};

const CURL = `$ curl -X POST /api/analyze \\
  -H "Content-Type: application/json" \\
  -d '{"symbol":"TSLA","model":"auto"}'`;

const RESPONSE = `{
  "ok": true,
  "symbol": "TSLA",
  "signal": "BUY NOW",
  "score": 0.82,
  "confidence": "High",
  "plan": {
    "entry": 248.40,
    "risk_pct": 1.5
  }
}`;

const STEPS = [
  { title: "Pick a symbol", detail: "Enter any ticker or select one from the live symbol bag." },
  { title: "Run the pipeline", detail: "Point-in-time features, meta-classifier, and Kelly sizing execute in one pass." },
  { title: "Get a verdict", detail: "A structured label, paper plan, and risk notes land in the desk." },
];

const modelPalette = [
  { color: "var(--td-action-buy-now)", soft: "var(--td-success)", label: "green" },
  { color: "var(--td-action-buy-breakout)", soft: "var(--td-m-blue-light)", label: "blue" },
  { color: "var(--td-m-violet)", soft: "var(--td-m-violet)", label: "violet" },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, ease: EASE },
  },
};

const fadeInVariants = {
  hidden: { opacity: 0, y: 28 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: EASE },
  },
};

function FadeIn({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
      variants={{
        hidden: fadeInVariants.hidden,
        visible: {
          ...fadeInVariants.visible,
          transition: { ...fadeInVariants.visible.transition, delay },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function StaggerContainer({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
      variants={{
        hidden: containerVariants.hidden,
        visible: {
          ...containerVariants.visible,
          transition: { ...containerVariants.visible.transition, delayChildren: delay },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={itemVariants} className={className}>
      {children}
    </motion.div>
  );
}

function AnimatedLogo({ className }: { className?: string }) {
  return (
    <motion.svg
      viewBox="0 0 40 40"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      initial="hidden"
      animate="visible"
    >
      <motion.rect
        x="2"
        y="2"
        width="36"
        height="36"
        rx="8"
        stroke="var(--td-brand)"
        strokeWidth="2"
        variants={{
          hidden: { pathLength: 0, opacity: 0 },
          visible: { pathLength: 1, opacity: 1, transition: { duration: 0.8, ease: EASE } },
        }}
      />
      <motion.path
        d="M8 28 L14 28 L14 18 L20 18"
        stroke="var(--td-ink)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        variants={{
          hidden: { pathLength: 0, opacity: 0 },
          visible: { pathLength: 1, opacity: 1, transition: { duration: 0.6, ease: EASE, delay: 0.3 } },
        }}
      />
      <motion.path
        d="M10 30 L18 22 L24 26 L32 14"
        stroke="var(--td-brand)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        variants={{
          hidden: { pathLength: 0, opacity: 0 },
          visible: { pathLength: 1, opacity: 1, transition: { duration: 0.7, ease: EASE, delay: 0.5 } },
        }}
      />
      <motion.circle
        cx="32"
        cy="14"
        r="2.5"
        fill="var(--td-warning)"
        variants={{
          hidden: { scale: 0, opacity: 0 },
          visible: { scale: 1, opacity: 1, transition: { duration: 0.3, delay: 1.1, ease: EASE } },
        }}
      />
    </motion.svg>
  );
}

function CodeWindow({ title, children }: { title: string; children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.98 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.7, ease: EASE, delay: 0.2 }}
      className="rounded-lg border border-hairline bg-surface overflow-hidden shadow-2xl shadow-black/30 text-left"
    >
      <div className="flex items-center gap-3 px-4 py-3 border-b border-hairline bg-surface-soft">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-danger/80" />
          <span className="w-2.5 h-2.5 rounded-full bg-warning/80" />
          <span className="w-2.5 h-2.5 rounded-full bg-success/80" />
        </div>
        <span className="text-xs font-mono text-muted">{title}</span>
      </div>
      <pre className="p-5 overflow-x-auto text-sm font-mono text-body leading-relaxed">
        <code>{children}</code>
      </pre>
    </motion.div>
  );
}

function SymbolTicker({ code, name }: { code: string; name: string }) {
  return (
    <motion.div
      whileHover={{ y: -3, scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.18, ease: EASE }}
    >
      <Link
        href={analyzeHref({ symbol: code, model: "auto" })}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-hairline bg-surface hover:border-brand/40 transition-colors"
      >
        <span className="font-bold text-foreground">{code}</span>
        <span className="text-muted text-sm">{name}</span>
      </Link>
    </motion.div>
  );
}

function FeatureCard({ feature }: { feature: (typeof FEATURES)[number] }) {
  const Icon = iconMap[feature.icon] || Brain;
  return (
    <motion.div
      whileHover={{ y: -6 }}
      transition={{ duration: 0.2, ease: EASE }}
      className="group rounded-lg border border-hairline bg-surface p-6 hover:border-brand/30 transition-colors"
    >
      <div className="w-12 h-12 rounded-lg bg-surface-soft flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300">
        <Icon className="w-6 h-6 text-brand" />
      </div>
      <h3 className="text-xl font-bold text-foreground mb-3">{feature.title}</h3>
      <p className="text-body mb-5 leading-relaxed">{feature.body}</p>
      <Link
        href={feature.href}
        className="inline-flex items-center gap-2 text-sm font-medium text-brand hover:underline"
      >
        Explore <ArrowRight className="w-4 h-4" />
      </Link>
    </motion.div>
  );
}

function seededWalk(seed: string, endValue: number, steps = 24): number[] {
  // Deterministic pseudo-random walk that ends at endValue (normalized 0-1)
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 9973;
  const out: number[] = [0.1];
  for (let i = 1; i < steps; i++) {
    h = (h * 9301 + 49297) % 233280;
    const r = h / 233280;
    const trend = (i / (steps - 1)) * endValue;
    const noise = (r - 0.5) * 0.35;
    out.push(Math.max(0.05, Math.min(0.95, trend + noise)));
  }
  out[out.length - 1] = Math.max(0.15, Math.min(0.95, endValue));
  return out;
}

function Sparkline({
  seed,
  end,
  color,
  soft,
}: {
  seed: string;
  end: number;
  color: string;
  soft: string;
}) {
  const id = useId();
  const points = useMemo(() => seededWalk(seed, end), [seed, end]);
  const width = 200;
  const height = 48;
  const step = width / (points.length - 1);
  const y = (v: number) => height - v * (height - 8) - 4;
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${i * step} ${y(p)}`)
    .join(" ");
  const area = `${d} L ${width} ${height} L 0 ${height} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-12" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`grad-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={soft} stopOpacity="0.45" />
          <stop offset="100%" stopColor={soft} stopOpacity="0" />
        </linearGradient>
      </defs>
      <motion.path
        d={area}
        fill={`url(#grad-${id})`}
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, ease: EASE }}
      />
      <motion.path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1.2, ease: EASE }}
      />
    </svg>
  );
}

function parseReturn(model: (typeof CHAMPIONS)[number]): number {
  const raw = model.metrics.find((m) => m.label.toLowerCase().includes("return"))?.value ?? "0%";
  const n = parseFloat(raw.replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(n) ? n / 1000 : 0.2;
}

function ModelCard({ model, index }: { model: (typeof CHAMPIONS)[number]; index: number }) {
  const palette = modelPalette[index % modelPalette.length];
  const end = parseReturn(model);

  return (
    <motion.div
      whileHover={{ y: -6 }}
      transition={{ duration: 0.2, ease: EASE }}
      className="rounded-lg border border-hairline bg-surface overflow-hidden hover:border-brand/30 transition-colors"
      style={{ borderTopColor: palette.color }}
    >
      <div className="h-1 w-full" style={{ background: palette.color }} />
      <div className="p-6">
        <div className="flex items-start justify-between mb-4">
          <span className="text-muted text-sm font-mono">0{index + 1}</span>
          <span
            className="px-2 py-1 rounded text-xs border"
            style={{ color: palette.color, borderColor: `${palette.color}40`, background: `${palette.color}14` }}
          >
            {model.winner ? "CHAMPION" : model.role.split(" ")[0]}
          </span>
        </div>
        <h3 className="text-lg font-bold text-foreground mb-2">
          {model.id.replace(/_/g, " ")}
        </h3>
        <p className="text-body text-sm mb-5 line-clamp-2">{model.blurb}</p>

        <div className="mb-5">
          <Sparkline seed={model.id} end={end} color={palette.color} soft={palette.soft} />
        </div>

        <div className="grid grid-cols-2 gap-3 mb-6">
          {model.metrics.slice(0, 4).map((metric, i) => (
            <div key={i} className="bg-surface-soft rounded p-3">
              <dt className="text-muted text-xs font-mono uppercase">
                {metric.label.replace("*", "")}
              </dt>
              <dd className="text-foreground font-bold">{metric.value}</dd>
            </div>
          ))}
        </div>
        <Link
          href={analyzeHref({ symbol: "TSLA", model: model.id })}
          className="inline-flex items-center gap-2 text-sm font-medium hover:underline"
          style={{ color: palette.color }}
        >
          See it work <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </motion.div>
  );
}

function FAQItem({
  item,
  isOpen,
  onToggle,
}: {
  item: (typeof FAQ)[number];
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-surface overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between gap-4 p-5 text-left"
      >
        <span className="font-semibold text-foreground">{item.q}</span>
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2, ease: EASE }}
        >
          <ChevronDown className="w-5 h-5 text-muted flex-shrink-0" />
        </motion.div>
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: EASE }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 text-body leading-relaxed">{item.a}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function HeroBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.18 }}
        transition={{ duration: 1.2, ease: EASE }}
        className="absolute -top-1/4 -left-1/4 w-[150%] h-[150%]"
        style={{
          background:
            "radial-gradient(circle at 50% 40%, color-mix(in oklch, var(--td-brand) 18%, transparent), transparent 60%)",
        }}
      >
        <motion.div
          animate={{ x: [0, 80, 0], y: [0, 40, 0] }}
          transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
          className="w-full h-full"
        />
      </motion.div>
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-canvas/60 to-canvas" />
    </div>
  );
}

function PerformanceChart() {
  const width = 800;
  const height = 240;
  const steps = 30;

  const lines = useMemo(() => {
    return CHAMPIONS.map((m, i) => {
      const palette = modelPalette[i % modelPalette.length];
      const end = parseReturn(m);
      const pts = seededWalk(m.id, end, steps);
      const stepX = width / (steps - 1);
      const y = (v: number) => height - v * (height - 32) - 16;
      const d = pts.map((p, j) => `${j === 0 ? "M" : "L"} ${j * stepX} ${y(p)}`).join(" ");
      return { d, color: palette.color, name: m.id.replace(/_/g, " ") };
    });
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.7, ease: EASE }}
      className="rounded-lg border border-hairline bg-surface p-6"
    >
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-bold text-foreground">Model paths (simulated)</h3>
        <div className="flex items-center gap-4 text-xs">
          {lines.map((line, i) => (
            <span key={i} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ background: line.color }} />
              <span className="text-body">{line.name}</span>
            </span>
          ))}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t, i) => (
          <line
            key={i}
            x1="0"
            y1={t * height}
            x2={width}
            y2={t * height}
            stroke="var(--td-hairline)"
            strokeDasharray="4 4"
            opacity={0.5}
          />
        ))}
        {lines.map((line, i) => (
          <motion.path
            key={i}
            d={line.d}
            fill="none"
            stroke={line.color}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.6, ease: EASE, delay: i * 0.15 }}
          />
        ))}
      </svg>
    </motion.div>
  );
}

const lightTheme = {
  "--td-canvas": "#F5F3F0",
  "--td-surface-soft": "#EFEDEA",
  "--td-surface-card": "#FFFFFF",
  "--td-surface-elevated": "#FFFFFF",
  "--td-carbon": "#E8E6E3",
  "--td-hairline": "#DEDCDB",
  "--td-hairline-strong": "#D0CECC",
  "--td-ink": "#2B2B2B",
  "--td-body": "#5C5C5C",
  "--td-body-strong": "#414141",
  "--td-muted": "#8C8C8C",
  "--td-brand": "#FE5B17",
  "--td-brand-muted": "#E04D10",
  "--td-brand-deep": "#8C2F00",
  "--td-brand-soft": "rgba(254, 91, 23, 0.14)",
  "--td-accent": "#FE5B17",
  "--td-success": "#0fa336",
  "--td-warning": "#f4b400",
  "--td-danger": "#e22718",
  "--background": "#F5F3F0",
  "--foreground": "#2B2B2B",
} as React.CSSProperties;

export function TradeDeskLandingFirecrawl() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const navLinks = [
    { href: "#features", label: "Features" },
    { href: "#how-it-works", label: "How it works" },
    { href: "#models", label: "Models" },
    { href: "#faq", label: "FAQ" },
  ];

  return (
    <div className="min-h-screen bg-canvas text-foreground" style={lightTheme}>
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: EASE }}
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-200 ${
          scrolled
            ? "bg-canvas/90 backdrop-blur border-b border-hairline"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3 group">
              <motion.div whileHover={{ scale: 1.08, rotate: 3 }} transition={{ duration: 0.2 }}>
                <AnimatedLogo className="w-9 h-9" />
              </motion.div>
              <div className="flex flex-col">
                <span className="text-foreground font-bold text-lg">Trade Desk</span>
                <span className="text-muted text-xs">Research operator terminal</span>
              </div>
            </Link>

            <nav className="hidden md:flex items-center gap-8">
              {navLinks.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  className="text-body hover:text-foreground transition-colors text-sm font-medium"
                >
                  {link.label}
                </a>
              ))}
            </nav>

            <div className="flex items-center gap-4">
              <Link
                href="/command"
                className="hidden sm:inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-hairline text-body hover:bg-surface-soft transition text-sm"
              >
                Profile
              </Link>
              <Link
                href="/command"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-brand text-white font-medium hover:opacity-90 transition"
              >
                Open Desk
                <ArrowRight className="w-4 h-4" />
              </Link>
              <button
                type="button"
                onClick={() => setMobileOpen((v) => !v)}
                className="md:hidden p-2 rounded-lg border border-hairline text-foreground"
                aria-label="Toggle navigation"
              >
                {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>

          <AnimatePresence>
            {mobileOpen && (
              <motion.nav
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: EASE }}
                className="md:hidden overflow-hidden"
              >
                <div className="mt-4 pb-4 border-t border-hairline pt-4 flex flex-col gap-3">
                  {navLinks.map((link) => (
                    <a
                      key={link.href}
                      href={link.href}
                      onClick={() => setMobileOpen(false)}
                      className="text-body hover:text-foreground transition-colors text-sm font-medium"
                    >
                      {link.label}
                    </a>
                  ))}
                  <Link
                    href="/command"
                    onClick={() => setMobileOpen(false)}
                    className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-brand text-white font-medium"
                  >
                    Open Desk <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              </motion.nav>
            )}
          </AnimatePresence>
        </div>
      </motion.header>

      {/* Hero */}
      <section className="relative pt-32 pb-20 md:pt-48 md:pb-32 overflow-hidden">
        <HeroBackground />
        <div className="max-w-7xl mx-auto px-6 relative">
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="max-w-4xl mx-auto text-center"
          >
            <StaggerItem>
              <motion.div
                whileHover={{ scale: 1.05, rotate: 2 }}
                transition={{ duration: 0.25, ease: EASE }}
                className="inline-block mb-8"
              >
                <AnimatedLogo className="w-16 h-16 mx-auto" />
              </motion.div>
            </StaggerItem>

            <StaggerItem>
              <h1 className="text-4xl md:text-6xl lg:text-7xl font-display font-bold tracking-tight mb-6">
                Power your research with{" "}
                <span className="bg-gradient-to-r from-brand to-brand-muted bg-clip-text text-transparent">
                  clean, model-ready market data
                </span>
              </h1>
            </StaggerItem>

            <StaggerItem>
              <p className="text-lg md:text-xl text-body max-w-2xl mx-auto mb-10">
                Pick a ticker. Trade Desk ingests live prices, runs point-in-time feature
                pipelines, and surfaces model verdicts in one research terminal.
              </p>
            </StaggerItem>

            <StaggerItem>
              <div className="flex flex-wrap items-center justify-center gap-4 mb-16">
                <Link
                  href={analyzeHref({ symbol: "TSLA", model: "auto" })}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-brand text-white font-semibold hover:opacity-90 transition"
                >
                  Try TSLA <ArrowRight className="w-4 h-4" />
                </Link>
                <Link
                  href="#features"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-hairline text-foreground hover:bg-surface-soft transition"
                >
                  See the product
                </Link>
              </div>
            </StaggerItem>

            <StaggerItem className="max-w-2xl mx-auto">
              <CodeWindow title="bash">{CURL}</CodeWindow>
            </StaggerItem>

            <StaggerItem>
              <div className="flex flex-wrap items-center justify-center gap-6 mt-12 text-sm">
                <span className="flex items-center gap-2 text-body-strong">
                  <Check className="w-4 h-4 text-brand" />
                  Real market inputs
                </span>
                <span className="flex items-center gap-2 text-body-strong">
                  <Check className="w-4 h-4 text-brand" />
                  Point-in-time features
                </span>
                <span className="flex items-center gap-2 text-body-strong">
                  <Check className="w-4 h-4 text-brand" />
                  Paper plans only
                </span>
              </div>
            </StaggerItem>
          </motion.div>
        </div>
      </section>

      {/* Symbol ticker bar */}
      <section className="border-y border-hairline bg-surface-soft/30">
        <div className="max-w-7xl mx-auto px-6 py-10">
          <StaggerContainer>
            <StaggerItem>
              <p className="text-center text-muted text-sm mb-6">Start with a ticker</p>
            </StaggerItem>
            <div className="flex flex-wrap items-center justify-center gap-3">
              {WINNER_BAG.map((item) => (
                <StaggerItem key={item.code}>
                  <SymbolTicker code={item.code} name={item.name} />
                </StaggerItem>
              ))}
            </div>
          </StaggerContainer>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24">
        <div className="max-w-7xl mx-auto px-6">
          <FadeIn className="text-center mb-16">
            <span className="text-brand font-mono text-sm uppercase tracking-widest">Features</span>
            <h2 className="text-3xl md:text-5xl font-display font-bold mt-4 mb-4">
              One desk, every stage of the trade
            </h2>
            <p className="text-body max-w-2xl mx-auto">
              Search tickers, run models, simulate paper plans — all without leaving the
              research surface.
            </p>
          </FadeIn>

          <StaggerContainer className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((feature) => (
              <StaggerItem key={feature.key}>
                <FeatureCard feature={feature} />
              </StaggerItem>
            ))}
          </StaggerContainer>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-24 border-y border-hairline">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <FadeIn>
              <span className="text-brand font-mono text-sm uppercase tracking-widest">
                How it works
              </span>
              <h2 className="text-3xl md:text-4xl font-display font-bold mt-4 mb-4">
                One API call. A complete verdict.
              </h2>
              <p className="text-body mb-8">
                Send a symbol and model. Trade Desk returns a structured analysis — setup,
                risk, and paper plan.
              </p>
              <div className="relative">
                <motion.div
                  initial={{ scaleY: 0 }}
                  whileInView={{ scaleY: 1 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.8, ease: EASE, delay: 0.2 }}
                  className="absolute left-4 top-4 bottom-4 w-px bg-hairline origin-top"
                />
                <ol className="space-y-6 relative z-10">
                  {STEPS.map((step, i) => (
                    <motion.li
                      key={step.title}
                      initial={{ opacity: 0, x: -16 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.5, ease: EASE, delay: i * 0.1 }}
                      className="flex gap-4"
                    >
                      <span className="flex-shrink-0 w-8 h-8 rounded-full border border-hairline bg-surface-soft flex items-center justify-center text-sm font-mono text-brand">
                        0{i + 1}
                      </span>
                      <div>
                        <h4 className="font-semibold text-foreground">{step.title}</h4>
                        <p className="text-body text-sm">{step.detail}</p>
                      </div>
                    </motion.li>
                  ))}
                </ol>
              </div>
            </FadeIn>

            <FadeIn delay={0.2}>
              <CodeWindow title="response.json">{RESPONSE}</CodeWindow>
            </FadeIn>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section id="stats" className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <StaggerContainer className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            {STATS.map((stat) => (
              <StaggerItem key={stat.label}>
                <motion.div
                  whileHover={{ scale: 1.05 }}
                  transition={{ duration: 0.2, ease: EASE }}
                  className="rounded-lg border border-hairline bg-surface-soft/30 p-6"
                >
                  <div className="text-3xl md:text-4xl font-bold text-foreground mb-2">
                    {stat.value}
                  </div>
                  <div className="text-body-strong">{stat.label}</div>
                  <div className="text-muted text-sm">{stat.sub}</div>
                </motion.div>
              </StaggerItem>
            ))}
          </StaggerContainer>
        </div>
      </section>

      {/* Models */}
      <section id="models" className="py-24 border-t border-hairline">
        <div className="max-w-7xl mx-auto px-6">
          <FadeIn className="text-center mb-16">
            <span className="text-brand font-mono text-sm uppercase tracking-widest">Models</span>
            <h2 className="text-3xl md:text-5xl font-display font-bold mt-4 mb-4">
              Meet the model team
            </h2>
            <p className="text-body max-w-2xl mx-auto">
              No single model wins at everything. The desk routes each one to the job it does
              best.
            </p>
          </FadeIn>

          <div className="mb-12">
            <PerformanceChart />
          </div>

          <StaggerContainer className="grid md:grid-cols-3 gap-6">
            {CHAMPIONS.map((model, index) => (
              <StaggerItem key={model.id}>
                <ModelCard model={model} index={index} />
              </StaggerItem>
            ))}
          </StaggerContainer>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="py-24">
        <div className="max-w-3xl mx-auto px-6">
          <FadeIn className="text-center mb-12">
            <span className="text-brand font-mono text-sm uppercase tracking-widest">FAQ</span>
            <h2 className="text-3xl md:text-5xl font-display font-bold mt-4 mb-4">
              Questions & answers
            </h2>
          </FadeIn>

          <StaggerContainer className="space-y-4">
            {FAQ.map((item, i) => (
              <StaggerItem key={i}>
                <FAQItem
                  item={item}
                  isOpen={openFaq === i}
                  onToggle={() => setOpenFaq(openFaq === i ? null : i)}
                />
              </StaggerItem>
            ))}
          </StaggerContainer>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-24 border-t border-hairline">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <FadeIn>
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-brand bg-brand/10 text-brand text-sm font-medium mb-6">
              <Layers3 className="w-4 h-4" />
              READY TO EXPLORE?
            </div>
            <h2 className="text-4xl md:text-6xl font-display font-bold text-foreground mb-6">
              Start with one stock.
            </h2>
            <p className="text-body mb-10 max-w-2xl mx-auto">
              The desk will show the rest.
            </p>
            <Link
              href="/command"
              className="inline-flex items-center gap-3 px-10 py-4 rounded-lg bg-brand text-white font-semibold text-lg hover:opacity-90 transition"
            >
              Open Trade Desk <ArrowRight className="w-6 h-6" />
            </Link>
          </FadeIn>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-16 border-t border-hairline">
        <div className="max-w-7xl mx-auto px-6">
          <FadeIn>
            <div className="grid md:grid-cols-4 gap-12 mb-12">
              <div>
                <Link href="/" className="flex items-center gap-3 mb-4 group">
                  <motion.div whileHover={{ scale: 1.08, rotate: 3 }} transition={{ duration: 0.2 }}>
                    <AnimatedLogo className="w-9 h-9" />
                  </motion.div>
                  <span className="font-bold text-lg text-foreground">Trade Desk</span>
                </Link>
                <p className="text-muted text-sm">Market research that shows its work.</p>
              </div>

              <div>
                <h4 className="text-foreground font-bold mb-4">Explore</h4>
                <ul className="space-y-3">
                  <li><Link href="/command" className="text-muted hover:text-foreground transition-colors text-sm">Analyze a stock</Link></li>
                  <li><Link href="/live" className="text-muted hover:text-foreground transition-colors text-sm">Paper execution</Link></li>
                  <li><Link href="/live?mode=options" className="text-muted hover:text-foreground transition-colors text-sm">Options</Link></li>
                  <li><Link href="/positions" className="text-muted hover:text-foreground transition-colors text-sm">Portfolio</Link></li>
                </ul>
              </div>

              <div>
                <h4 className="text-foreground font-bold mb-4">Research</h4>
                <ul className="space-y-3">
                  <li><Link href="/research?view=backtest" className="text-muted hover:text-foreground transition-colors text-sm">Backtests</Link></li>
                  <li><Link href="/research?view=evolve" className="text-muted hover:text-foreground transition-colors text-sm">Model lab</Link></li>
                  <li><Link href="/analysis-agent" className="text-muted hover:text-foreground transition-colors text-sm">Analysis agent</Link></li>
                </ul>
              </div>

              <div>
                <h4 className="text-foreground font-bold mb-4">Workspace</h4>
                <ul className="space-y-3">
                  <li><Link href="/profile" className="text-muted hover:text-foreground transition-colors text-sm">Profile</Link></li>
                  <li><Link href="/privacy" className="text-muted hover:text-foreground transition-colors text-sm">Privacy</Link></li>
                  <li><Link href="/terms" className="text-muted hover:text-foreground transition-colors text-sm">Terms</Link></li>
                </ul>
              </div>
            </div>

            <div className="border-t border-hairline pt-8">
              <div className="flex flex-col md:flex-row items-center justify-between gap-6 text-muted text-sm text-center md:text-left">
                <span>© 2026 Trade Desk</span>
                <span className="max-w-2xl">
                  Quantitative research and paper-risk software. Not investment advice. Never sends broker orders.
                </span>
                <span>TradingAlgoWork / local</span>
              </div>
            </div>
          </FadeIn>
        </div>
      </footer>
    </div>
  );
}
