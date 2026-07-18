"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import {
  ArrowRight,
  Check,
  Database,
  Gauge,
  ShieldCheck,
  Zap,
  Code2,
  Brain,
  Target,
  Clock,
  Award,
  Rocket,
  Sparkles,
  ScanSearch,
  CircleDollarSign,
  FlaskConical,
  ChartNoAxesCombined,
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

// Animated gradient background component
function GradientBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute -top-40 -right-40 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl animate-blob" />
      <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl animate-blob animation-delay-2000" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-r from-purple-500/5 to-blue-500/5 rounded-full blur-3xl" />
    </div>
  );
}

// Floating particles effect
function FloatingParticles() {
  const particles = Array.from({ length: 20 });
  
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {particles.map((_, i) => (
        <div
          key={i}
          className="absolute rounded-full bg-gradient-to-b from-white/20 to-white/5"
          style={{
            width: `${Math.random() * 4 + 2}px`,
            height: `${Math.random() * 4 + 2}px`,
            left: `${Math.random() * 100}%`,
            top: `${Math.random() * 100}%`,
            animation: `float ${Math.random() * 10 + 10}s linear infinite`,
            animationDelay: `${Math.random() * 5}s`,
          }}
        />
      ))}
    </div>
  );
}

// Model card with hover effects
interface ModelCardProps {
  model: (typeof CHAMPIONS)[number];
  index: number;
}

function ModelCard({ model, index }: ModelCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  
  const metrics = model.metrics.slice(0, 4);
  
  return (
    <div
      className={`relative group/model-card transition-all duration-500 ${
        isHovered ? "transform -translate-y-4 scale-[1.02]" : ""
      }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Glow effect */}
      <div
        className={`absolute inset-0 rounded-2xl bg-gradient-to-b from-purple-500/10 to-blue-500/5 transition-opacity duration-500 ${
          isHovered ? "opacity-100" : "opacity-0"
        }`}
      />
      
      {/* Border glow */}
      <div
        className={`absolute inset-0 rounded-2xl border transition-all duration-500 ${
          isHovered
            ? "border-purple-400/30 shadow-lg shadow-purple-500/10"
            : "border-white/5"
        }`}
      />
      
      <div className="relative bg-black/20 backdrop-blur-lg rounded-2xl p-6 h-full border border-white/5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-white/60 text-sm font-mono">0{index + 1}</span>
            <span className="px-2 py-1 bg-purple-500/10 text-purple-300 text-xs rounded-full border border-purple-500/20">
              {model.winner ? "CHAMPION" : model.role.split(" ")[0]}
            </span>
          </div>
          {model.winner && (
            <Award className="w-5 h-5 text-yellow-400" />
          )}
        </div>
        
        <h3 className="text-white text-xl font-bold mb-2 group-hover/model-card:text-purple-200 transition-colors">
          {model.id.replace(/_/g, " ")}
        </h3>
        
        <p className="text-white/60 text-sm mb-6 line-clamp-2">
          {model.blurb}
        </p>
        
        <div className="grid grid-cols-2 gap-4 mb-6">
          {metrics.map((metric, i) => (
            <div key={i} className="bg-white/5 rounded-lg p-3">
              <dt className="text-white/40 text-xs font-mono uppercase">{metric.label.replace("*", "")}</dt>
              <dd className="text-white text-lg font-bold">{metric.value}</dd>
            </div>
          ))}
        </div>
        
        <Link
          href={analyzeHref({ symbol: "TSLA", model: model.id })}
          className="inline-flex items-center gap-2 text-purple-300 hover:text-purple-200 transition-colors text-sm font-medium"
        >
          See it work <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}

// Stats display with animation
function AnimatedStat({ value, label, sub, index }: { value: string; label: string; sub: string; index: number }) {
  const [isVisible, setIsVisible] = useState(false);
  
  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), index * 200);
    return () => clearTimeout(timer);
  }, [index]);
  
  return (
    <div className={`text-center transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
      <div className="text-4xl md:text-5xl font-bold text-white mb-2">
        {value}
      </div>
      <div className="text-white/80 text-lg">{label}</div>
      <div className="text-white/40 text-sm">{sub}</div>
    </div>
  );
}

// Feature pill
function FeaturePill({ icon: Icon, text }: { icon: React.ElementType; text: string }) {
  return (
    <div className="inline-flex items-center gap-2 px-4 py-2 bg-white/5 rounded-full border border-white/10 text-white/80 text-sm">
      <Icon className="w-4 h-4" />
      <span>{text}</span>
    </div>
  );
}

// Symbol ticker with animation
function AnimatedTicker({ code, name }: { code: string; name: string }) {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <Link
      href={analyzeHref({ symbol: code, model: "auto" })}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg border transition-all duration-300 ${
        isHovered
          ? "bg-white/10 border-white/20 transform scale-105"
          : "border-white/5 hover:border-white/10"
      }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <strong className="text-white font-bold text-lg">{code}</strong>
      <span className="text-white/60 text-sm">{name}</span>
      <ArrowRight className="w-4 h-4 text-purple-400 opacity-0 group-hover:opacity-100 transition-opacity" />
    </Link>
  );
}

// Pipeline visualization
function PipelineVisualization() {
  const steps = [
    { label: "Data", icon: Database, color: "text-purple-400" },
    { label: "Features", icon: Code2, color: "text-blue-400" },
    { label: "Models", icon: Brain, color: "text-green-400" },
    { label: "Decision", icon: Target, color: "text-orange-400" },
    { label: "Paper", icon: Gauge, color: "text-red-400" },
  ];
  
  return (
    <div className="relative flex items-center justify-between max-w-4xl mx-auto">
      {steps.map((step, index) => (
        <div key={index} className="flex flex-col items-center z-10">
          <div className="flex items-center gap-2 mb-2">
            <step.icon className={`w-6 h-6 ${step.color}`} />
            <span className="text-white/80 text-sm font-medium">{step.label}</span>
          </div>
          <div className="w-4 h-4 rounded-full bg-gradient-to-br from-purple-400 to-blue-500" />
        </div>
      ))}
      
      {/* Connecting lines */}
      <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-400/30 via-blue-400/30 to-transparent -z-10" />
    </div>
  );
}

// Main landing page component
export function TradeDeskLandingNew() {
  const [scrolled, setScrolled] = useState(false);
  
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);
  
  return (
    <div className="min-h-screen bg-black text-white overflow-x-hidden">
      {/* Background effects */}
      <GradientBackground />
      <FloatingParticles />
      
      {/* Navigation */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-black/80 backdrop-blur-xl border-b border-white/5"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3 group">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center">
                <span className="text-white font-bold text-lg">TD</span>
              </div>
              <div className="flex flex-col">
                <span className="text-white font-bold text-xl">Trade Desk</span>
                <span className="text-white/40 text-xs">Research Terminal</span>
              </div>
            </Link>
            
            <nav className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-white/60 hover:text-white transition-colors text-sm font-medium">Features</a>
              <a href="#models" className="text-white/60 hover:text-white transition-colors text-sm font-medium">Models</a>
              <a href="#how-it-works" className="text-white/60 hover:text-white transition-colors text-sm font-medium">How it works</a>
              <a href="#stats" className="text-white/60 hover:text-white transition-colors text-sm font-medium">Stats</a>
            </nav>
            
            <div className="flex items-center gap-4">
              <Link href="/profile" className="hidden sm:inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white/80 hover:bg-white/10 transition-colors text-sm">
                Profile
              </Link>
              <Link href="/command" className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-500 to-blue-600 text-white font-medium hover:shadow-lg hover:shadow-purple-500/25 transition-all">
                Open Desk
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </header>
      
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center pt-24 pb-16">
        <div className="max-w-7xl mx-auto px-6 text-center relative z-10">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 mb-8">
            <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
            <span className="text-white/80 text-sm">Next-generation trading research</span>
          </div>
          
          {/* Main headline */}
          <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold mb-6 leading-tight">
            Trade with
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-blue-400">
              Confidence
            </span>
          </h1>
          
          {/* Subheadline */}
          <p className="text-xl md:text-2xl text-white/70 max-w-3xl mx-auto mb-10">
            Advanced ML models analyze market data in real-time. 
            See the signal, understand the risk, make informed decisions.
          </p>
          
          {/* CTA Buttons */}
          <div className="flex flex-wrap items-center justify-center gap-4 mb-12">
            <Link
              href="/command?symbol=TSLA&model=auto"
              className="inline-flex items-center gap-3 px-8 py-4 rounded-xl bg-gradient-to-r from-purple-500 to-purple-600 text-white font-semibold hover:shadow-lg hover:shadow-purple-500/30 transition-all group"
            >
              <Zap className="w-5 h-5" />
              Try with TSLA
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              href="#features"
              className="inline-flex items-center gap-3 px-8 py-4 rounded-xl bg-white/5 border border-white/10 text-white font-semibold hover:bg-white/10 transition-all"
            >
              <Sparkles className="w-5 h-5" />
              Explore Features
            </Link>
          </div>
          
          {/* Feature pills */}
          <div className="flex flex-wrap items-center justify-center gap-3">
            <FeaturePill icon={Check} text="Real market data" />
            <FeaturePill icon={ShieldCheck} text="Tested models" />
            <FeaturePill icon={Gauge} text="Paper trading" />
            <FeaturePill icon={Clock} text="Real-time" />
          </div>
        </div>
        
        {/* Hero visual - 3D effect */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-full max-w-6xl h-96 pointer-events-none">
          <div className="relative w-full h-full">
            {/* Simulated trading interface */}
            <div className="absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-black/80 to-transparent" />
            <div className="absolute left-1/4 top-1/4 w-80 h-48 bg-black/30 backdrop-blur-xl rounded-2xl border border-white/10 p-6 shadow-2xl shadow-purple-500/10">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-3 h-3 rounded-full bg-green-400 animate-pulse" />
                <span className="text-white/80 text-sm">LIVE</span>
                <span className="text-white font-bold ml-auto">TSLA</span>
                <span className="text-green-400 text-lg font-bold">$248.40</span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <div className="text-white/60 text-xs">Model Score</div>
                  <div className="text-white text-2xl font-bold text-green-400">0.82</div>
                </div>
                <div>
                  <div className="text-white/60 text-xs">Signal</div>
                  <div className="text-white text-2xl font-bold text-purple-400">BUY</div>
                </div>
                <div>
                  <div className="text-white/60 text-xs">Confidence</div>
                  <div className="text-white text-2xl font-bold">High</div>
                </div>
              </div>
            </div>
            
            {/* Floating model cards */}
            <div className="absolute right-1/4 top-1/2 -translate-y-1/2 w-64 h-32 bg-gradient-to-br from-purple-500/20 to-blue-500/20 rounded-2xl backdrop-blur-lg border border-white/10 p-4 shadow-xl">
              <div className="text-white/60 text-xs mb-2">Ensemble Performance</div>
              <div className="text-white text-3xl font-bold">+513%</div>
              <div className="text-white/60 text-sm">Return</div>
              <div className="flex gap-4 mt-2">
                <div>
                  <div className="text-white/60 text-xs">Sharpe</div>
                  <div className="text-white font-bold">3.08</div>
                </div>
                <div>
                  <div className="text-white/60 text-xs">Win Rate</div>
                  <div className="text-white font-bold">72%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      
      {/* Popular Symbols */}
      <section className="py-16 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-10">
            <span className="text-white/40 text-sm font-mono uppercase tracking-widest">START WITH</span>
            <h2 className="text-3xl md:text-4xl font-bold text-white mt-2">Popular Symbols</h2>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-4">
            {WINNER_BAG.map((item) => (
              <AnimatedTicker key={item.code} code={item.code} name={item.name} />
            ))}
          </div>
        </div>
      </section>
      
      {/* Features Section */}
      <section id="features" className="py-24 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="inline-block px-4 py-1 rounded-full bg-purple-500/10 text-purple-300 text-sm font-medium mb-4">
              Powerful Features
            </span>
            <h2 className="text-4xl md:text-6xl font-bold text-white mb-4">
              Everything you need for
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-blue-400">
                {" "}smart trading
              </span>
            </h2>
            <p className="text-xl text-white/60 max-w-2xl mx-auto">
              From real-time analysis to paper trading, our platform has you covered.
            </p>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {FEATURES.map((feature, index) => {
              const Icon = iconMap[feature.icon] || Brain;
              return (
                <div
                  key={feature.key}
                  className="relative group/feature bg-black/20 backdrop-blur-lg rounded-2xl p-8 border border-white/5 hover:border-purple-500/20 transition-all duration-500"
                  style={{
                    animationDelay: `${index * 100}ms`,
                  }}
                >
                  <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-purple-500 to-transparent opacity-0 group-hover/feature:opacity-100 transition-opacity duration-500" />
                  <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500/20 to-blue-500/20 flex items-center justify-center mb-6">
                    <Icon className="w-7 h-7 text-purple-400" />
                  </div>
                  <h3 className="text-white text-xl font-bold mb-3">{feature.title}</h3>
                  <p className="text-white/60 text-sm leading-relaxed mb-6">{feature.body}</p>
                  <Link
                    href={feature.href}
                    className="inline-flex items-center gap-2 text-purple-300 hover:text-purple-200 transition-colors text-sm font-medium"
                  >
                    Explore
                    <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      </section>
      
      {/* How it works */}
      <section id="how-it-works" className="py-24 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="inline-block px-4 py-1 rounded-full bg-blue-500/10 text-blue-300 text-sm font-medium mb-4">
              How it works
            </span>
            <h2 className="text-4xl md:text-6xl font-bold text-white mb-4">
              From Data to Decision
            </h2>
            <p className="text-xl text-white/60 max-w-2xl mx-auto">
              Our pipeline transforms raw market data into actionable trading signals.
            </p>
          </div>
          
          <div className="relative">
            <PipelineVisualization />
          </div>
        </div>
      </section>
      
      {/* Models Section */}
      <section id="models" className="py-24 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="inline-block px-4 py-1 rounded-full bg-green-500/10 text-green-300 text-sm font-medium mb-4">
              Meet the Models
            </span>
            <h2 className="text-4xl md:text-6xl font-bold text-white mb-4">
              Different tools for
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-green-400 to-blue-400">
                {" "}different jobs
              </span>
            </h2>
            <p className="text-xl text-white/60 max-w-2xl mx-auto">
              No single model wins at everything. Each one specializes in different market conditions.
            </p>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {CHAMPIONS.map((model, index) => (
              <ModelCard key={model.id} model={model} index={index} />
            ))}
          </div>
          
          <div className="text-center mt-12">
            <p className="text-white/40 text-sm">
              *Historical simulations, not promised returns. Models are judged on locked data they did not train on.
            </p>
          </div>
        </div>
      </section>
      
      {/* Stats Section */}
      <section id="stats" className="py-24 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <span className="inline-block px-4 py-1 rounded-full bg-orange-500/10 text-orange-300 text-sm font-medium mb-4">
              Performance Metrics
            </span>
            <h2 className="text-4xl md:text-6xl font-bold text-white mb-4">
              By the Numbers
            </h2>
            <p className="text-xl text-white/60 max-w-2xl mx-auto">
              Our models have been battle-tested across various market conditions.
            </p>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {STATS.map((stat, index) => (
              <AnimatedStat key={stat.label} {...stat} index={index} />
            ))}
          </div>
        </div>
      </section>
      
      {/* Final CTA */}
      <section className="py-32 relative">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-purple-500/10 text-purple-300 text-sm font-medium mb-8">
            <Rocket className="w-4 h-4" />
            Ready to explore?
          </div>
          <h2 className="text-5xl md:text-7xl font-bold text-white mb-6">
            Start with one stock
          </h2>
          <p className="text-xl text-white/70 mb-10 max-w-2xl mx-auto">
            The desk will show you the rest. Analyze, learn, and make confident trading decisions.
          </p>
          <Link
            href="/command"
            className="inline-flex items-center gap-3 px-10 py-5 rounded-2xl bg-gradient-to-r from-purple-500 to-blue-600 text-white font-semibold text-lg hover:shadow-lg hover:shadow-purple-500/30 transition-all group"
          >
            <Sparkles className="w-6 h-6" />
            Open Trade Desk
            <ArrowRight className="w-6 h-6 group-hover:translate-x-2 transition-transform" />
          </Link>
        </div>
      </section>
      
      {/* Footer */}
      <footer className="relative py-20 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-12 mb-16">
            <div>
              <Link href="/" className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center">
                  <span className="text-white font-bold text-lg">TD</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-white font-bold text-xl">Trade Desk</span>
                </div>
              </Link>
              <p className="text-white/60 text-sm mb-6">
                Market research that shows its work. Quantitative analysis for smart traders.
              </p>
              <div className="flex items-center gap-2 text-white/40 text-sm">
                <div className="w-2 h-2 rounded-full bg-green-400" />
                <span>Local research system</span>
              </div>
            </div>
            
            <div>
              <h4 className="text-white font-bold mb-6">Explore</h4>
              <ul className="space-y-4">
                <li><Link href="/command" className="text-white/60 hover:text-white transition-colors text-sm">Analyze a stock</Link></li>
                <li><Link href="/live" className="text-white/60 hover:text-white transition-colors text-sm">Paper execution</Link></li>
                <li><Link href="/live?mode=options" className="text-white/60 hover:text-white transition-colors text-sm">Options</Link></li>
                <li><Link href="/positions" className="text-white/60 hover:text-white transition-colors text-sm">Portfolio</Link></li>
              </ul>
            </div>
            
            <div>
              <h4 className="text-white font-bold mb-6">Research</h4>
              <ul className="space-y-4">
                <li><Link href="/research?view=leaderboard" className="text-white/60 hover:text-white transition-colors text-sm">Model leaderboard</Link></li>
                <li><Link href="/research?view=backtest" className="text-white/60 hover:text-white transition-colors text-sm">Backtests</Link></li>
                <li><Link href="/research?view=evolve" className="text-white/60 hover:text-white transition-colors text-sm">Model lab</Link></li>
                <li><Link href="/analysis-agent" className="text-white/60 hover:text-white transition-colors text-sm">Analysis agent</Link></li>
              </ul>
            </div>
            
            <div>
              <h4 className="text-white font-bold mb-6">Workspace</h4>
              <ul className="space-y-4">
                <li><Link href="/profile" className="text-white/60 hover:text-white transition-colors text-sm">Profile</Link></li>
                <li><Link href="/privacy" className="text-white/60 hover:text-white transition-colors text-sm">Privacy</Link></li>
                <li><Link href="/terms" className="text-white/60 hover:text-white transition-colors text-sm">Terms</Link></li>
              </ul>
            </div>
          </div>
          
          <div className="border-t border-white/5 pt-12">
            <div className="flex flex-col md:flex-row items-center justify-between gap-8">
              <div className="text-white/40 text-sm">
                © 2026 Trade Desk
              </div>
              <p className="text-white/40 text-sm text-center md:text-left max-w-2xl">
                Quantitative research and paper-risk software. Not investment advice. Never sends broker orders.
              </p>
              <div className="text-white/40 text-sm">
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
          className="fixed bottom-8 right-8 w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-blue-600 text-white flex items-center justify-center shadow-lg hover:shadow-purple-500/30 transition-all"
        >
          <ArrowRight className="w-5 h-5 rotate-90" />
        </button>
      )}
    </div>
  );
}
