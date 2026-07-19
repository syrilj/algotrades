"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import {
  ArrowRight,
  Check,
  Database,
  Gauge,
  ShieldCheck,
  BarChart3,
  ScanSearch,
  CircleDollarSign,
  FlaskConical,
  ChartNoAxesCombined,
  Brain,
  Layers3,
} from "lucide-react";
import { CHAMPIONS, WINNER_BAG, STATS, FEATURES } from "./landingData";
import { analyzeHref } from "@/lib/routes";

// Icon mapping for features
const iconMap: Record<string, React.ElementType> = {
  ScanSearch,
  CircleDollarSign,
  FlaskConical,
  ShieldCheck,
  ChartNoAxesCombined,
  Brain,
};

// Model card with clean operator aesthetic
interface ModelCardProps {
  model: (typeof CHAMPIONS)[number];
  index: number;
}

function ModelCard({ model, index }: ModelCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  const metrics = model.metrics.slice(0, 4);
  
  return (
    <div
      className={`relative transition-all duration-300 ${
        isHovered ? "-translate-y-2" : ""
      }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="relative bg-surface-card border border-hairline rounded-lg p-6 h-full">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-muted text-sm font-mono">0{index + 1}</span>
            <span className="px-2 py-1 bg-brand-soft text-brand text-xs rounded border border-brand">
              {model.winner ? "CHAMPION" : model.role.split(" ")[0]}
            </span>
          </div>
        </div>
        
        <h3 className="text-ink text-lg font-bold mb-2">
          {model.id.replace(/_/g, " ")}
        </h3>
        
        <p className="text-body text-sm mb-6 line-clamp-2">
          {model.blurb}
        </p>
        
        <div className="grid grid-cols-2 gap-4 mb-6">
          {metrics.map((metric, i) => (
            <div key={i} className="bg-surface-soft rounded p-3">
              <dt className="text-muted text-xs font-mono uppercase">{metric.label.replace("*", "")}</dt>
              <dd className="text-ink text-base font-bold">{metric.value}</dd>
            </div>
          ))}
        </div>
        
        <Link
          href={analyzeHref({ symbol: "TSLA", model: model.id })}
          className="inline-flex items-center gap-2 text-brand hover:text-brand-muted transition-colors text-sm font-medium"
        >
          See it work <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}

// Stats display
function Stat({ value, label, sub }: { value: string; label: string; sub: string }) {
  return (
    <div className="text-center">
      <div className="text-3xl md:text-4xl font-bold text-ink mb-2">
        {value}
      </div>
      <div className="text-body-strong text-base">{label}</div>
      <div className="text-muted text-sm">{sub}</div>
    </div>
  );
}

// Symbol ticker
function SymbolTicker({ code, name }: { code: string; name: string }) {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <Link
      href={analyzeHref({ symbol: code, model: "auto" })}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded border transition-all duration-200 ${
        isHovered
          ? "bg-surface-soft border-hairline-strong"
          : "border-hairline hover:border-hairline-strong"
      }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <strong className="text-ink font-bold text-lg">{code}</strong>
      <span className="text-muted text-sm">{name}</span>
    </Link>
  );
}

// Pipeline visualization
function PipelineVisualization() {
  const steps = [
    { label: "Data", icon: Database },
    { label: "Features", icon: BarChart3 },
    { label: "Models", icon: Brain },
    { label: "Decision", icon: Gauge },
    { label: "Paper", icon: CircleDollarSign },
  ];
  
  return (
    <div className="relative flex items-center justify-between max-w-4xl mx-auto">
      {steps.map((step, index) => (
        <div key={index} className="flex flex-col items-center z-10">
          <div className="flex items-center gap-2 mb-2">
            <step.icon className="w-5 h-5 text-brand" />
            <span className="text-body text-sm font-medium">{step.label}</span>
          </div>
          <div className="w-3 h-3 rounded-full bg-brand" />
        </div>
      ))}
      
      {/* Connecting lines */}
      <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-hairline -z-10" />
    </div>
  );
}

// Feature card
function FeatureCard({ feature }: { feature: (typeof FEATURES)[number] }) {
  const Icon = iconMap[feature.icon] || Brain;
  
  return (
    <div className="relative bg-surface-card border border-hairline rounded-lg p-6">
      <div className="w-12 h-12 rounded-lg bg-surface-soft flex items-center justify-center mb-5">
        <Icon className="w-6 h-6 text-brand" />
      </div>
      <h3 className="text-ink text-lg font-bold mb-3">{feature.title}</h3>
      <p className="text-body text-sm leading-relaxed mb-5">{feature.body}</p>
      <Link
        href={feature.href}
        className="inline-flex items-center gap-2 text-brand hover:text-brand-muted transition-colors text-sm font-medium"
      >
        Explore <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  );
}

// Main landing page component
export function TradeDeskLandingClean() {
  const [scrolled, setScrolled] = useState(false);
  
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);
  
  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* Navigation */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-200 ${
          scrolled
            ? "bg-canvas/95 backdrop-blur border-b border-hairline"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3">
              <div className="w-9 h-9 rounded border border-brand flex items-center justify-center">
                <span className="text-brand font-bold text-sm">TD</span>
              </div>
              <div className="flex flex-col">
                <span className="text-ink font-bold text-lg">Trade Desk</span>
                <span className="text-muted text-xs">Research operator terminal</span>
              </div>
            </Link>
            
            <nav className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-body hover:text-ink transition-colors text-sm font-medium">Features</a>
              <a href="#models" className="text-body hover:text-ink transition-colors text-sm font-medium">Models</a>
              <a href="#how-it-works" className="text-body hover:text-ink transition-colors text-sm font-medium">How it works</a>
              <a href="#stats" className="text-body hover:text-ink transition-colors text-sm font-medium">Stats</a>
            </nav>
            
            <div className="flex items-center gap-4">
              <Link href="/profile" className="hidden sm:inline-flex items-center gap-2 px-4 py-2 rounded border border-hairline text-body hover:bg-surface-soft transition-colors text-sm">
                Profile
              </Link>
              <Link href="/command" className="inline-flex items-center gap-2 px-5 py-2.5 rounded border border-brand bg-brand text-canvas font-medium hover:bg-brand-muted transition-colors">
                Open Desk
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </header>
      
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center pt-24 pb-16">
        <div className="max-w-7xl mx-auto px-6 text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded border border-hairline mb-8">
            <div className="w-2 h-2 rounded-full bg-brand animate-pulse" />
            <span className="text-muted text-sm">Research with a visible safety check</span>
          </div>
          
          {/* Main headline */}
          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold mb-6 leading-tight">
            Know the plan.<br />
            <em className="text-body-strong">See the risk.</em>
          </h1>
          
          {/* Subheadline */}
          <p className="text-lg md:text-xl text-body max-w-3xl mx-auto mb-10">
            Pick a stock. Trade Desk shows what the models see, what could go wrong, and what to do next.
          </p>
          
          {/* CTA Buttons */}
          <div className="flex flex-wrap items-center justify-center gap-4 mb-12">
            <Link
              href="/command?symbol=TSLA&model=auto"
              className="inline-flex items-center gap-3 px-8 py-4 rounded border border-brand bg-brand text-canvas font-semibold hover:bg-brand-muted transition-colors"
            >
              Try TSLA
              <ArrowRight className="w-5 h-5" />
            </Link>
            <Link
              href="#product"
              className="inline-flex items-center gap-3 px-8 py-4 rounded border border-hairline text-ink font-semibold hover:bg-surface-soft transition-colors"
            >
              See the product
            </Link>
          </div>
          
          {/* Proof points */}
          <div className="flex flex-wrap items-center justify-center gap-6 text-sm">
            <span className="flex items-center gap-2 text-body-strong">
              <Check size={14} className="text-brand" />
              Real market inputs
            </span>
            <span className="flex items-center gap-2 text-body-strong">
              <Check size={14} className="text-brand" />
              Tested models
            </span>
            <span className="flex items-center gap-2 text-body-strong">
              <Check size={14} className="text-brand" />
              Paper plans only
            </span>
          </div>
        </div>
        
        {/* Hero visual - clean trading interface mockup */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-full max-w-5xl pointer-events-none">
          <div className="relative w-full h-80">
            <div className="absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-canvas to-transparent" />
            <div className="absolute left-1/4 top-1/4 w-72 h-40 bg-surface-card border border-hairline rounded-lg p-5 shadow-lg">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-brand animate-pulse" />
                <span className="text-muted text-xs">LIVE · TSLA / 1H</span>
                <span className="text-ink font-bold ml-auto">$248.40</span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center mb-4">
                <div>
                  <div className="text-muted text-xs">Model Score</div>
                  <div className="text-ink text-xl font-bold text-brand">0.82</div>
                </div>
                <div>
                  <div className="text-muted text-xs">Signal</div>
                  <div className="text-ink text-xl font-bold">BUY NOW</div>
                </div>
                <div>
                  <div className="text-muted text-xs">Confidence</div>
                  <div className="text-ink text-xl font-bold">High</div>
                </div>
              </div>
              <div className="text-muted text-xs">Market → Setup → Safety → Paper plan</div>
            </div>
            
            <div className="absolute right-1/4 top-1/2 -translate-y-1/2 w-56 h-28 bg-surface-card border border-hairline rounded-lg p-4 shadow-lg">
              <div className="text-muted text-xs mb-1">Ensemble Performance</div>
              <div className="text-ink text-2xl font-bold">+513%</div>
              <div className="text-muted text-xs">Return</div>
              <div className="flex gap-3 mt-2 text-xs">
                <div>
                  <div className="text-muted">Sharpe</div>
                  <div className="text-ink font-bold">3.08</div>
                </div>
                <div>
                  <div className="text-muted">Win Rate</div>
                  <div className="text-ink font-bold">72%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      
      {/* Popular Symbols */}
      <section className="py-12">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-8">
            <span className="text-muted text-sm font-mono uppercase tracking-widest">START WITH</span>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {WINNER_BAG.map((item) => (
              <SymbolTicker key={item.code} code={item.code} name={item.name} />
            ))}
          </div>
        </div>
      </section>
      
      {/* Product Section */}
      <section id="product" className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="text-brand text-sm font-mono uppercase tracking-widest">One desk, four jobs</span>
            <h2 className="text-3xl md:text-5xl font-bold text-ink mt-4 mb-4">
              From &ldquo;what is happening?&rdquo;<br />
              to &ldquo;what is my risk?&rdquo;
            </h2>
            <p className="text-body max-w-2xl mx-auto">
              Switch between analysis, paper execution, options, and model research without losing the stock you are studying.
            </p>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((feature) => (
              <FeatureCard key={feature.key} feature={feature} />
            ))}
          </div>
        </div>
      </section>
      
      {/* How it works */}
      <section id="how-it-works" className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="text-brand text-sm font-mono uppercase tracking-widest">No black box</span>
            <h2 className="text-3xl md:text-5xl font-bold text-ink mt-4 mb-4">
              Four steps. One clear answer.
            </h2>
          </div>
          
          <div className="relative">
            <PipelineVisualization />
          </div>
        </div>
      </section>
      
      {/* Models Section */}
      <section id="models" className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="text-brand text-sm font-mono uppercase tracking-widest">Different tools for different jobs</span>
            <h2 className="text-3xl md:text-5xl font-bold text-ink mt-4 mb-4">
              Meet the model team.
            </h2>
            <p className="text-body max-w-2xl mx-auto">
              No single model wins at everything. The desk routes each one to the job it does best.
            </p>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {CHAMPIONS.map((model, index) => (
              <ModelCard key={model.id} model={model} index={index} />
            ))}
          </div>
          
          <div className="text-center mt-12">
            <p className="text-muted text-sm">
              *Historical simulations, not promised returns. Models are judged on locked data they did not train on.
            </p>
          </div>
        </div>
      </section>
      
      {/* Stats Section */}
      <section id="stats" className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="text-brand text-sm font-mono uppercase tracking-widest">By the numbers</span>
            <h2 className="text-3xl md:text-5xl font-bold text-ink mt-4 mb-4">
              Performance Metrics
            </h2>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {STATS.map((stat) => (
              <Stat key={stat.label} {...stat} />
            ))}
          </div>
        </div>
      </section>
      
      {/* Final CTA */}
      <section className="py-28">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded border border-brand mb-8">
            <Layers3 className="w-4 h-4 text-brand" />
            <span className="text-brand text-sm font-medium">READY TO EXPLORE?</span>
          </div>
          <h2 className="text-4xl md:text-6xl font-bold text-ink mb-6">
            Start with one stock.
          </h2>
          <p className="text-xl text-body mb-10 max-w-2xl mx-auto">
            The desk will show the rest.
          </p>
          <Link
            href="/command"
            className="inline-flex items-center gap-3 px-10 py-4 rounded border border-brand bg-brand text-canvas font-semibold text-lg hover:bg-brand-muted transition-colors"
          >
            Open Trade Desk
            <ArrowRight className="w-6 h-6" />
          </Link>
        </div>
      </section>
      
      {/* Footer */}
      <footer className="py-16 border-t border-hairline">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-12 mb-12">
            <div>
              <Link href="/" className="flex items-center gap-3 mb-6">
                <div className="w-9 h-9 rounded border border-brand flex items-center justify-center">
                  <span className="text-brand font-bold text-sm">TD</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-ink font-bold text-lg">Trade Desk</span>
                </div>
              </Link>
              <p className="text-muted text-sm mb-6">
                Market research that shows its work.
              </p>
              <div className="flex items-center gap-2 text-muted text-sm">
                <div className="w-2 h-2 rounded-full bg-brand" />
                <span>Local research system</span>
              </div>
            </div>
            
            <div>
              <h4 className="text-ink font-bold mb-6">Explore</h4>
              <ul className="space-y-3">
                <li><Link href="/command" className="text-muted hover:text-ink transition-colors text-sm">Analyze a stock</Link></li>
                <li><Link href="/live" className="text-muted hover:text-ink transition-colors text-sm">Paper execution</Link></li>
                <li><Link href="/live?mode=options" className="text-muted hover:text-ink transition-colors text-sm">Options</Link></li>
                <li><Link href="/positions" className="text-muted hover:text-ink transition-colors text-sm">Portfolio</Link></li>
              </ul>
            </div>
            
            <div>
              <h4 className="text-ink font-bold mb-6">Research</h4>
              <ul className="space-y-3">
                <li><Link href="/research?view=leaderboard" className="text-muted hover:text-ink transition-colors text-sm">Model leaderboard</Link></li>
                <li><Link href="/research?view=backtest" className="text-muted hover:text-ink transition-colors text-sm">Backtests</Link></li>
                <li><Link href="/research?view=evolve" className="text-muted hover:text-ink transition-colors text-sm">Model lab</Link></li>
                <li><Link href="/analysis-agent" className="text-muted hover:text-ink transition-colors text-sm">Analysis agent</Link></li>
              </ul>
            </div>
            
            <div>
              <h4 className="text-ink font-bold mb-6">Workspace</h4>
              <ul className="space-y-3">
                <li><Link href="/profile" className="text-muted hover:text-ink transition-colors text-sm">Profile</Link></li>
                <li><Link href="/privacy" className="text-muted hover:text-ink transition-colors text-sm">Privacy</Link></li>
                <li><Link href="/terms" className="text-muted hover:text-ink transition-colors text-sm">Terms</Link></li>
              </ul>
            </div>
          </div>
          
          <div className="border-t border-hairline pt-8">
            <div className="flex flex-col md:flex-row items-center justify-between gap-6">
              <div className="text-muted text-sm">
                © 2026 Trade Desk
              </div>
              <p className="text-muted text-sm text-center md:text-left max-w-2xl">
                Quantitative research and paper-risk software. Not investment advice. Never sends broker orders.
              </p>
              <div className="text-muted text-sm">
                TradingAlgoWork / local
              </div>
            </div>
          </div>
        </div>
      </footer>
      
      {/* Scroll to top button */}
      {scrolled && (
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="fixed bottom-8 right-8 w-10 h-10 rounded border border-brand bg-canvas flex items-center justify-center text-brand hover:bg-brand hover:text-canvas transition-colors"
        >
          <ArrowRight className="w-5 h-5 rotate-90" />
        </button>
      )}
    </div>
  );
}
