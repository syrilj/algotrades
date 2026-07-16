import fs from "fs";
import path from "path";

/** Monorepo root: TradingAlgoWork (apps/trade-desk → ../..) */
export function repoRoot(): string {
  let current = process.cwd();
  while (current !== path.dirname(current)) {
    if (fs.existsSync(path.join(current, "requirements.txt")) || fs.existsSync(path.join(current, ".venv"))) {
      return current;
    }
    current = path.dirname(current);
  }
  return path.resolve(process.cwd(), "../..");
}

export function pythonBin(): string {
  return path.join(repoRoot(), ".venv", "bin", "python3");
}

export function tradeDeskScript(): string {
  return path.join(repoRoot(), "tools", "trade_desk.py");
}

export function livePlanScript(): string {
  return path.join(repoRoot(), "tools", "live_plan.py");
}

export function optionsPickerScript(): string {
  return path.join(repoRoot(), "tools", "options_picker.py");
}

export function volPackageScoreScript(): string {
  return path.join(repoRoot(), "tools", "vol_package_score.py");
}

export function gammaExposureScript(): string {
  return path.join(repoRoot(), "tools", "gamma_exposure.py");
}

export function optionsUnusualFlowScript(): string {
  return path.join(repoRoot(), "tools", "options_unusual_flow.py");
}

export function riskManagerScript(): string {
  return path.join(repoRoot(), "tools", "risk_manager.py");
}

export function riskAssessmentScript(): string {
  return path.join(repoRoot(), "tools", "risk_assessment.py");
}

export function vpaScanScript(): string {
  return path.join(repoRoot(), "tools", "vpa_scan.py");
}

export function sectorWatchlistScript(): string {
  return path.join(repoRoot(), "tools", "sector_watchlist.py");
}

export function sectorMoneyFlowScript(): string {
  return path.join(repoRoot(), "tools", "sector_money_flow.py");
}

export function modelsRoot(): string {
  return path.join(repoRoot(), "models", "poc_va_macdha");
}

export function evolvePipelineScript(): string {
  return path.join(repoRoot(), "tools", "evolve_pipeline.py");
}

export function portfolioOptimizerScript(): string {
  return path.join(repoRoot(), "tools", "portfolio_optimizer.py");
}

export function runsRoot(): string {
  return path.join(repoRoot(), "runs");
}

export function symbolRankerScript(): string {
  return path.join(repoRoot(), "tools", "symbol_ranker.py");
}

export function paperLedgerScript(): string {
  return path.join(repoRoot(), "tools", "paper_ledger.py");
}

export function supplyChainScript(): string {
  return path.join(repoRoot(), "tools", "supply_chain.py");
}

export function analysisAgentScript(): string {
  return path.join(repoRoot(), "tools", "analysis_agent.py");
}
