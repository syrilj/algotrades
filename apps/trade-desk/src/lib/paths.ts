import path from "path";

/** Monorepo root: TradingAlgoWork (apps/trade-desk → ../..) */
export function repoRoot(): string {
  return path.resolve(process.cwd(), "../..");
}

export function pythonBin(): string {
  return path.join(repoRoot(), ".venv", "bin", "python3");
}

export function tradeDeskScript(): string {
  return path.join(repoRoot(), "tools", "trade_desk.py");
}

export function modelsRoot(): string {
  return path.join(repoRoot(), "models", "poc_va_macdha");
}
