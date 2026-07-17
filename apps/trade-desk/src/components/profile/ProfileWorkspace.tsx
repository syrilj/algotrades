"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Check,
  Database,
  HardDrive,
  ShieldCheck,
  UserRound,
} from "lucide-react";

export const PROFILE_STORAGE_KEY = "td-operator-profile-v1";

type OperatorProfile = {
  displayName: string;
  initials: string;
  defaultSymbol: string;
  defaultModel: string;
  studyCapital: number;
  maxSymbolWeight: number;
  riskMode: "conservative" | "balanced" | "research";
  dataSource: "local" | "live-fallback";
  interval: "1H" | "1D";
};

const DEFAULT_PROFILE: OperatorProfile = {
  displayName: "Local operator",
  initials: "TD",
  defaultSymbol: "TSLA",
  defaultModel: "v72_dual_sleeve",
  studyCapital: 1000,
  maxSymbolWeight: 50,
  riskMode: "balanced",
  dataSource: "local",
  interval: "1H",
};

const MODEL_OPTIONS = [
  { value: "v72_dual_sleeve", label: "v72 · dual sleeve", note: "Promoted combined book" },
  { value: "v39d_confluence", label: "v39d · confluence", note: "Tighter drawdown core" },
  { value: "v71_live_confidence", label: "v71 · confidence", note: "High win-rate sleeve" },
] as const;

export function ProfileWorkspace() {
  const [profile, setProfile] = useState<OperatorProfile>(DEFAULT_PROFILE);
  const [saved, setSaved] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(PROFILE_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<OperatorProfile>;
        setProfile({ ...DEFAULT_PROFILE, ...parsed });
      }
    } catch {
      // A malformed local profile should never block the workspace.
    } finally {
      setLoaded(true);
    }
  }, []);

  const selectedModel = useMemo(
    () => MODEL_OPTIONS.find((option) => option.value === profile.defaultModel) ?? MODEL_OPTIONS[0],
    [profile.defaultModel],
  );

  const update = <K extends keyof OperatorProfile>(key: K, value: OperatorProfile[K]) => {
    setProfile((current) => ({ ...current, [key]: value }));
    setSaved(false);
  };

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized: OperatorProfile = {
      ...profile,
      displayName: profile.displayName.trim() || DEFAULT_PROFILE.displayName,
      initials: profile.initials.trim().slice(0, 3).toUpperCase() || DEFAULT_PROFILE.initials,
      defaultSymbol: profile.defaultSymbol.trim().toUpperCase() || DEFAULT_PROFILE.defaultSymbol,
      studyCapital: Math.max(100, Number(profile.studyCapital) || DEFAULT_PROFILE.studyCapital),
      maxSymbolWeight: Math.min(100, Math.max(1, Number(profile.maxSymbolWeight) || 50)),
    };
    setProfile(normalized);
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(normalized));
    window.dispatchEvent(new CustomEvent("td-profile-updated", { detail: normalized }));
    setSaved(true);
  };

  return (
    <form className="td-profile" onSubmit={save}>
      <aside className="td-profile__identity">
        <div className="td-profile__avatar" aria-hidden="true">{profile.initials || "TD"}</div>
        <p className="td-profile__overline">LOCAL OPERATOR</p>
        <h2>{profile.displayName || "Local operator"}</h2>
        <p>
          A workspace identity for research defaults. This is stored in this browser;
          it is not a brokerage account or cloud login.
        </p>
        <dl className="td-profile__summary">
          <div><dt>Default model</dt><dd>{selectedModel.label}</dd></div>
          <div><dt>Study capital</dt><dd>${profile.studyCapital.toLocaleString()}</dd></div>
          <div><dt>Risk ceiling</dt><dd>{profile.maxSymbolWeight}% / symbol</dd></div>
          <div><dt>Data path</dt><dd>{profile.dataSource === "local" ? "Local only" : "Live + fallback"}</dd></div>
        </dl>
        <div className="td-profile__local-note">
          <HardDrive size={14} />
          <span>Saved to local browser storage</span>
        </div>
      </aside>

      <div className="td-profile__forms">
        <section className="td-profile__section">
          <header><UserRound size={16} /><div><h2>Operator identity</h2><p>Used in workspace chrome and research exports.</p></div></header>
          <div className="td-profile__fields td-profile__fields--two">
            <label>
              <span>Display name</span>
              <input value={profile.displayName} onChange={(event) => update("displayName", event.target.value)} maxLength={40} />
            </label>
            <label>
              <span>Initials</span>
              <input value={profile.initials} onChange={(event) => update("initials", event.target.value.toUpperCase())} maxLength={3} />
            </label>
            <label>
              <span>Default symbol</span>
              <input value={profile.defaultSymbol} onChange={(event) => update("defaultSymbol", event.target.value.toUpperCase())} maxLength={8} />
            </label>
            <label>
              <span>Default model</span>
              <select value={profile.defaultModel} onChange={(event) => update("defaultModel", event.target.value)}>
                {MODEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <small>{selectedModel.note}</small>
            </label>
          </div>
        </section>

        <section className="td-profile__section">
          <header><ShieldCheck size={16} /><div><h2>Paper risk rails</h2><p>Defaults for sizing views. Model-level caps still take precedence.</p></div></header>
          <div className="td-profile__fields td-profile__fields--two">
            <label>
              <span>Study capital (USD)</span>
              <input type="number" min="100" step="100" value={profile.studyCapital} onChange={(event) => update("studyCapital", Number(event.target.value))} />
            </label>
            <label>
              <span>Maximum symbol weight (%)</span>
              <input type="number" min="1" max="100" step="1" value={profile.maxSymbolWeight} onChange={(event) => update("maxSymbolWeight", Number(event.target.value))} />
            </label>
          </div>
          <fieldset className="td-profile__segmented">
            <legend>Risk posture</legend>
            {(["conservative", "balanced", "research"] as const).map((mode) => (
              <label key={mode} className={profile.riskMode === mode ? "is-selected" : ""}>
                <input type="radio" name="risk-mode" checked={profile.riskMode === mode} onChange={() => update("riskMode", mode)} />
                <strong>{mode}</strong>
                <small>{mode === "conservative" ? "Half-size studies" : mode === "balanced" ? "Model defaults" : "Full cap exploration"}</small>
              </label>
            ))}
          </fieldset>
        </section>

        <section className="td-profile__section">
          <header><Database size={16} /><div><h2>Data contract</h2><p>Choose the preferred observation path; fallbacks remain visible on every result.</p></div></header>
          <div className="td-profile__fields td-profile__fields--two">
            <label>
              <span>Preferred source</span>
              <select value={profile.dataSource} onChange={(event) => update("dataSource", event.target.value as OperatorProfile["dataSource"])}>
                <option value="local">Local adjusted data</option>
                <option value="live-fallback">Live feed with fallback</option>
              </select>
            </label>
            <label>
              <span>Primary interval</span>
              <select value={profile.interval} onChange={(event) => update("interval", event.target.value as OperatorProfile["interval"])}>
                <option value="1H">1 hour</option>
                <option value="1D">1 day</option>
              </select>
            </label>
          </div>
        </section>

        <div className="td-profile__actions">
          <p>{saved ? <><Check size={13} /> Profile saved locally.</> : loaded ? "Unsaved changes remain local to this form." : "Loading local profile…"}</p>
          <button className="td-btn td-btn-primary" type="submit" disabled={!loaded}>Save profile</button>
        </div>
      </div>
    </form>
  );
}
