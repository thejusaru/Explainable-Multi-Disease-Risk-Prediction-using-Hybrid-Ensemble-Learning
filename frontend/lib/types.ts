/**
 * Mirrors backend/app/models/schemas.py. Keep the two in sync — the backend is
 * the source of truth and validates every field on the way out.
 */

export const PROJECTION_AGES = [25, 30, 35, 40, 45] as const;

export type RiskLevel = "low" | "moderate" | "high" | "very_high";
export type Confidence = "low" | "medium" | "high";
export type Priority = "urgent" | "high" | "medium" | "low";

export interface LabResult {
  name: string;
  value: number;
  unit?: string | null;
  reference_range?: string | null;
  flag?: "low" | "normal" | "high" | null;
}

export interface PatientProfile {
  age: number;
  sex?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  smoking?: string | null;
  alcohol?: string | null;
  activity?: string | null;
  shift_pattern?: string | null;
  stress_level?: string | null;
  sleep_hours?: number | null;
  family_history: string[];
  existing_conditions: string[];
  medications: string[];
  labs: LabResult[];
  raw_report_text?: string | null;
}

export interface RiskProjection {
  age: number;
  probability: number;
  level: RiskLevel;
}

export interface ConditionRisk {
  condition: string;
  category: string;
  projections: RiskProjection[];
  drivers: string[];
  protective_factors: string[];
  rationale: string;
  modifiable: boolean;
  confidence: Confidence;
}

export interface Recommendation {
  title: string;
  detail: string;
  priority: Priority;
  targets: string[];
}

export interface RiskAssessment {
  profile: PatientProfile;
  conditions: ConditionRisk[];
  recommendations: Recommendation[];
  summary: string;
  missing_data: string[];
  engine: string;
  model?: string | null;
  generated_at: string;
  disclaimer: string;
}

export interface AnalyzeResponse {
  assessment: RiskAssessment;
  extraction_notes: string[];
}

/** Result of reading a report without running an assessment. */
export interface ExtractResponse {
  profile: PatientProfile | null;
  fields_found: string[];
  notes: string[];
  requires_manual_entry: boolean;
  report_text?: string | null;
  image_base64?: string | null;
  image_media_type?: string | null;
}

/** Which risk engine computed (or should compute) an assessment. */
export type EngineKind = "claude" | "local";

export interface EngineOption {
  kind: EngineKind;
  label: string;
  model: string;
  available: boolean;
  detail: string;
  /** Installed Ollama models, when the local engine is reachable. */
  models: string[];
}

export interface EnginesResponse {
  default: EngineKind;
  engines: EngineOption[];
}

/**
 * Risk colours as CSS variable references rather than literal hex.
 *
 * The palette differs between light and dark themes — the light-mode reds are
 * unreadable on a dark surface — so resolving through a variable lets a single
 * inline style follow the active theme without a re-render.
 */
export const RISK_VARS: Record<RiskLevel, string> = {
  low: "var(--risk-low)",
  moderate: "var(--risk-moderate)",
  high: "var(--risk-high)",
  very_high: "var(--risk-very-high)",
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  very_high: "Very high",
};

/**
 * Distinct hues for the timeline series, defined per theme in globals.css.
 * Cycles when there are more conditions than colours.
 */
export const SERIES_VARS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
];
