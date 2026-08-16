"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import type { PatientProfile } from "../lib/types";

/**
 * Patient detail form.
 *
 * Fields populate from an extraction result and are marked as auto-filled, so
 * the user can see what came from the document and correct it before it feeds
 * the risk model. Every field stays editable — extraction is a starting point,
 * not an authority.
 */

export interface IntakeFormHandle {
  buildProfile: () => Partial<PatientProfile>;
}

interface Props {
  /** Values read from an uploaded report; populates the form when it changes. */
  extracted: PatientProfile | null;
  onSubmit: (profile: Partial<PatientProfile>) => void;
  busy: boolean;
  submitLabel: string;
  /** Age is required unless an image will be read during analysis. */
  ageOptional: boolean;
}

type FormState = Record<string, string>;

const EMPTY: FormState = {
  age: "",
  sex: "",
  height_cm: "",
  weight_kg: "",
  systolic_bp: "",
  diastolic_bp: "",
  smoking: "",
  alcohol: "",
  activity: "",
  shift_pattern: "",
  stress_level: "",
  sleep_hours: "",
  family_history: "",
  existing_conditions: "",
};

const NUMERIC_FIELDS = [
  "age",
  "height_cm",
  "weight_kg",
  "systolic_bp",
  "diastolic_bp",
  "sleep_hours",
] as const;

const ENUM_FIELDS = [
  "sex",
  "smoking",
  "alcohol",
  "activity",
  "shift_pattern",
  "stress_level",
] as const;

const LIST_FIELDS = ["family_history", "existing_conditions"] as const;

export default function IntakeForm({
  extracted,
  onSubmit,
  busy,
  submitLabel,
  ageOptional,
}: Props) {
  const [values, setValues] = useState<FormState>(EMPTY);
  const [autoFilled, setAutoFilled] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // Tracks which extraction has been applied, so re-renders don't clobber edits
  // the user has made since. A new upload produces a new object identity.
  const appliedRef = useRef<PatientProfile | null>(null);

  useEffect(() => {
    if (!extracted || appliedRef.current === extracted) return;
    appliedRef.current = extracted;

    const next: FormState = { ...EMPTY };
    const filled = new Set<string>();

    for (const key of NUMERIC_FIELDS) {
      const value = extracted[key as keyof PatientProfile];
      if (typeof value === "number") {
        next[key] = String(value);
        filled.add(key);
      }
    }
    for (const key of ENUM_FIELDS) {
      const value = extracted[key as keyof PatientProfile];
      if (typeof value === "string" && value) {
        next[key] = value;
        filled.add(key);
      }
    }
    for (const key of LIST_FIELDS) {
      const value = extracted[key as keyof PatientProfile];
      if (Array.isArray(value) && value.length > 0) {
        next[key] = value.join(", ");
        filled.add(key);
      }
    }

    setValues(next);
    setAutoFilled(filled);
    setError(null);
  }, [extracted]);

  function update(field: string, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
    // Once edited, a field is the user's, not the document's.
    if (autoFilled.has(field)) {
      setAutoFilled((prev) => {
        const next = new Set(prev);
        next.delete(field);
        return next;
      });
    }
  }

  const labs = extracted?.labs ?? [];

  const profile = useMemo(() => {
    const built: Record<string, unknown> = {};

    for (const key of NUMERIC_FIELDS) {
      const raw = values[key];
      if (raw.trim() !== "") {
        const parsed = Number(raw);
        if (Number.isFinite(parsed)) built[key] = parsed;
      }
    }
    for (const key of ENUM_FIELDS) {
      if (values[key]) built[key] = values[key];
    }
    for (const key of LIST_FIELDS) {
      const items = values[key]
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (items.length > 0) built[key] = items;
    }

    // Carry lab results through — they are shown read-only but must reach the
    // engine, and the form has no editor for them.
    if (labs.length > 0) built.labs = labs;

    return built as Partial<PatientProfile>;
  }, [values, labs]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!ageOptional && profile.age === undefined) {
      setError("Enter the patient's age, or upload a report containing one.");
      return;
    }
    if (
      profile.age !== undefined &&
      (profile.age < 0 || profile.age > 120)
    ) {
      setError("Age must be between 0 and 120.");
      return;
    }
    // Both are optional and nullable in the schema, so check for a number
    // rather than only for undefined.
    const { systolic_bp: systolic, diastolic_bp: diastolic } = profile;
    if (
      typeof systolic === "number" &&
      typeof diastolic === "number" &&
      systolic <= diastolic
    ) {
      setError(
        "Systolic blood pressure must be higher than diastolic — check the values.",
      );
      return;
    }

    onSubmit(profile);
  }

  function fieldClass(name: string) {
    return autoFilled.has(name) ? "field field-autofilled" : "field";
  }

  function autoTag(name: string) {
    return autoFilled.has(name) ? (
      <span className="autofill-tag">from report</span>
    ) : null;
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-section">
        <div className="section-title">Demographics</div>
        <div className="field-grid">
          <div className={fieldClass("age")}>
            <label htmlFor="age">
              Age {!ageOptional && <span aria-hidden>*</span>} {autoTag("age")}
            </label>
            <input
              id="age"
              type="number"
              min={0}
              max={120}
              value={values.age}
              disabled={busy}
              onChange={(e) => update("age", e.target.value)}
              placeholder="34"
            />
          </div>

          <div className={fieldClass("sex")}>
            <label htmlFor="sex">Sex {autoTag("sex")}</label>
            <select
              id="sex"
              value={values.sex}
              disabled={busy}
              onChange={(e) => update("sex", e.target.value)}
            >
              <option value="">Not specified</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className={fieldClass("height_cm")}>
            <label htmlFor="height">Height (cm) {autoTag("height_cm")}</label>
            <input
              id="height"
              type="number"
              value={values.height_cm}
              disabled={busy}
              onChange={(e) => update("height_cm", e.target.value)}
              placeholder="178"
            />
          </div>

          <div className={fieldClass("weight_kg")}>
            <label htmlFor="weight">Weight (kg) {autoTag("weight_kg")}</label>
            <input
              id="weight"
              type="number"
              value={values.weight_kg}
              disabled={busy}
              onChange={(e) => update("weight_kg", e.target.value)}
              placeholder="82"
            />
          </div>
        </div>
      </div>

      <div className="form-section">
        <div className="section-title">Vitals</div>
        <div className="field-grid">
          <div className={fieldClass("systolic_bp")}>
            <label htmlFor="systolic">
              Systolic BP {autoTag("systolic_bp")}
            </label>
            <input
              id="systolic"
              type="number"
              value={values.systolic_bp}
              disabled={busy}
              onChange={(e) => update("systolic_bp", e.target.value)}
              placeholder="128"
            />
          </div>

          <div className={fieldClass("diastolic_bp")}>
            <label htmlFor="diastolic">
              Diastolic BP {autoTag("diastolic_bp")}
            </label>
            <input
              id="diastolic"
              type="number"
              value={values.diastolic_bp}
              disabled={busy}
              onChange={(e) => update("diastolic_bp", e.target.value)}
              placeholder="82"
            />
          </div>

          <div className={fieldClass("sleep_hours")}>
            <label htmlFor="sleep">
              Sleep (hrs/night) {autoTag("sleep_hours")}
            </label>
            <input
              id="sleep"
              type="number"
              step="0.5"
              value={values.sleep_hours}
              disabled={busy}
              onChange={(e) => update("sleep_hours", e.target.value)}
              placeholder="7"
            />
          </div>
        </div>
      </div>

      <div className="form-section">
        <div className="section-title">Lifestyle</div>
        <div className="field-grid">
          <div className={fieldClass("smoking")}>
            <label htmlFor="smoking">Smoking {autoTag("smoking")}</label>
            <select
              id="smoking"
              value={values.smoking}
              disabled={busy}
              onChange={(e) => update("smoking", e.target.value)}
            >
              <option value="">Not specified</option>
              <option value="never">Never</option>
              <option value="former">Former</option>
              <option value="current">Current</option>
            </select>
          </div>

          <div className={fieldClass("alcohol")}>
            <label htmlFor="alcohol">Alcohol {autoTag("alcohol")}</label>
            <select
              id="alcohol"
              value={values.alcohol}
              disabled={busy}
              onChange={(e) => update("alcohol", e.target.value)}
            >
              <option value="">Not specified</option>
              <option value="none">None</option>
              <option value="occasional">Occasional</option>
              <option value="moderate">Moderate</option>
              <option value="heavy">Heavy</option>
            </select>
          </div>

          <div className={fieldClass("activity")}>
            <label htmlFor="activity">Activity {autoTag("activity")}</label>
            <select
              id="activity"
              value={values.activity}
              disabled={busy}
              onChange={(e) => update("activity", e.target.value)}
            >
              <option value="">Not specified</option>
              <option value="sedentary">Sedentary</option>
              <option value="light">Light</option>
              <option value="moderate">Moderate</option>
              <option value="active">Active</option>
            </select>
          </div>

          <div className={fieldClass("shift_pattern")}>
            <label htmlFor="shift">
              Work pattern {autoTag("shift_pattern")}
            </label>
            <select
              id="shift"
              value={values.shift_pattern}
              disabled={busy}
              onChange={(e) => update("shift_pattern", e.target.value)}
            >
              <option value="">Not specified</option>
              <option value="day">Day shift</option>
              <option value="rotating">Rotating shift</option>
              <option value="night">Night shift</option>
            </select>
          </div>

          <div className={fieldClass("stress_level")}>
            <label htmlFor="stress">Stress {autoTag("stress_level")}</label>
            <select
              id="stress"
              value={values.stress_level}
              disabled={busy}
              onChange={(e) => update("stress_level", e.target.value)}
            >
              <option value="">Not specified</option>
              <option value="low">Low</option>
              <option value="moderate">Moderate</option>
              <option value="high">High</option>
              <option value="severe">Severe</option>
            </select>
          </div>
        </div>
      </div>

      <div className="form-section">
        <div className="section-title">History</div>
        <div className="stack" style={{ gap: 14 }}>
          <div className={fieldClass("family_history")}>
            <label htmlFor="family">
              Family history {autoTag("family_history")}
            </label>
            <input
              id="family"
              type="text"
              value={values.family_history}
              disabled={busy}
              onChange={(e) => update("family_history", e.target.value)}
              placeholder="type 2 diabetes, heart disease (comma separated)"
            />
          </div>

          <div className={fieldClass("existing_conditions")}>
            <label htmlFor="conditions">
              Existing conditions {autoTag("existing_conditions")}
            </label>
            <input
              id="conditions"
              type="text"
              value={values.existing_conditions}
              disabled={busy}
              onChange={(e) => update("existing_conditions", e.target.value)}
              placeholder="hypertension, asthma (comma separated)"
            />
          </div>
        </div>
      </div>

      {labs.length > 0 && (
        <div className="form-section">
          <div className="section-title">
            Lab results — read from the report
          </div>
          <div className="metric-row">
            {labs.map((lab) => (
              <div className="metric" key={lab.name}>
                <div className="metric-label">{lab.name}</div>
                <div className="metric-value">
                  {lab.value}
                  {lab.unit ? (
                    <span
                      style={{
                        fontSize: "0.72rem",
                        color: "var(--text-muted)",
                        marginLeft: 4,
                      }}
                    >
                      {lab.unit}
                    </span>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="banner banner-danger" style={{ marginTop: 20 }}>
          <span className="banner-icon">!</span>
          <div>{error}</div>
        </div>
      )}

      <div className="btn-row" style={{ marginTop: 22 }}>
        <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
