"use client";

import RiskTimeline from "./RiskTimeline";
import { AlertIcon, CheckCircleIcon, InfoIcon } from "./Icons";
import {
  RISK_LABELS,
  RISK_VARS,
  type AnalyzeResponse,
  type ConditionRisk,
} from "../lib/types";

interface Props {
  result: AnalyzeResponse;
}

/** Risk at the last projected age — the headline number per condition. */
function endpointRisk(condition: ConditionRisk) {
  return condition.projections[condition.projections.length - 1];
}

export default function AssessmentResults({ result }: Props) {
  const { assessment, extraction_notes: notes } = result;
  const { profile } = assessment;

  // Highest end-of-timeline risk first: that ordering matches what a reader
  // most wants to see, and keeps the chart legend in the same order.
  const sorted = [...assessment.conditions].sort(
    (a, b) => endpointRisk(b).probability - endpointRisk(a).probability,
  );

  const bmi =
    profile.height_cm && profile.weight_kg
      ? (
          profile.weight_kg / Math.pow(profile.height_cm / 100, 2)
        ).toFixed(1)
      : null;

  return (
    <div className="stack">
      <div className="banner banner-warning">
        <AlertIcon size={17} className="banner-icon" />
        <div>
          <strong>Not a medical diagnosis</strong>
          {assessment.disclaimer}
        </div>
      </div>

      {assessment.summary && (
        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>Summary</h2>
            </div>
          </div>
          <div className="card-body">
            <p className="summary-lede">{assessment.summary}</p>

            <div className="metric-row">
              <div className="metric">
                <div className="metric-label">Age</div>
                <div className="metric-value">{profile.age}</div>
              </div>
              {bmi && (
                <div className="metric">
                  <div className="metric-label">BMI</div>
                  <div className="metric-value">{bmi}</div>
                </div>
              )}
              {profile.systolic_bp && profile.diastolic_bp && (
                <div className="metric">
                  <div className="metric-label">Blood pressure</div>
                  <div className="metric-value">
                    {profile.systolic_bp}/{profile.diastolic_bp}
                  </div>
                </div>
              )}
              {profile.smoking && (
                <div className="metric">
                  <div className="metric-label">Smoking</div>
                  <div className="metric-value" style={{ fontSize: "0.95rem" }}>
                    {profile.smoking}
                  </div>
                </div>
              )}
              <div className="metric">
                <div className="metric-label">Conditions</div>
                <div className="metric-value">{sorted.length}</div>
              </div>
            </div>
          </div>
        </section>
      )}

      {sorted.length > 0 && (
        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>Projected risk by age</h2>
              <p>
                Estimated probability of having developed each condition by the
                given age. Click a condition to show or hide it.
              </p>
            </div>
          </div>
          <div className="card-body">
            <RiskTimeline conditions={sorted} patientAge={profile.age} />
          </div>
        </section>
      )}

      <section className="card">
        <div className="card-header">
          <div className="card-title-group">
            <h2>Conditions</h2>
            <p>Ordered by projected risk at age 45.</p>
          </div>
        </div>
        <div className="card-body">
          <div className="condition-list">
            {sorted.map((condition) => {
              const endpoint = endpointRisk(condition);
              const color = RISK_VARS[endpoint.level];
              return (
                <article key={condition.condition} className="condition">
                  <header className="condition-header">
                    <div>
                      <h3>{condition.condition}</h3>
                      <span className="category">{condition.category}</span>
                    </div>
                    <div className="condition-score">
                      <span className="badge" style={{ background: color }}>
                        {RISK_LABELS[endpoint.level]}
                      </span>
                      <span className="score">
                        {(endpoint.probability * 100).toFixed(1)}%
                        <span className="score-age"> by {endpoint.age}</span>
                      </span>
                    </div>
                  </header>

                  <div className="mini-timeline">
                    {condition.projections.map((p) => (
                      <div key={p.age} className="mini-point">
                        <span className="mini-age">{p.age}</span>
                        <span className="mini-track">
                          <span
                            className="mini-bar"
                            style={{
                              background: RISK_VARS[p.level],
                              // Scaled against 50% so typical values stay
                              // visible; anything above pins to full width.
                              width: `${Math.min(100, p.probability * 200)}%`,
                            }}
                          />
                        </span>
                        <span className="mini-value">
                          {(p.probability * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>

                  {condition.rationale && <p>{condition.rationale}</p>}

                  {condition.drivers.length > 0 && (
                    <div className="factors">
                      <span className="factors-label">Raising risk</span>
                      <ul>
                        {condition.drivers.map((driver) => (
                          <li key={driver}>{driver}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {condition.protective_factors.length > 0 && (
                    <div className="factors factors-good">
                      <span className="factors-label">Lowering risk</span>
                      <ul>
                        {condition.protective_factors.map((factor) => (
                          <li key={factor}>{factor}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <footer className="condition-footer">
                    <span
                      className={`tag${
                        condition.confidence === "low" ? " tag-low" : ""
                      }`}
                    >
                      {condition.confidence} confidence
                    </span>
                    {condition.modifiable && (
                      <span className="tag">modifiable</span>
                    )}
                  </footer>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      {assessment.recommendations.length > 0 && (
        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>What to do about it</h2>
              <p>Ordered by priority.</p>
            </div>
          </div>
          <div className="card-body">
            <div className="recommendations">
              {assessment.recommendations.map((rec) => (
                <article
                  key={rec.title}
                  className={`recommendation recommendation-${rec.priority}`}
                >
                  <header>
                    <span className={`priority priority-${rec.priority}`}>
                      {rec.priority}
                    </span>
                    <h3>{rec.title}</h3>
                  </header>
                  <p>{rec.detail}</p>
                  {rec.targets.length > 0 && (
                    <p className="targets">Reduces: {rec.targets.join(", ")}</p>
                  )}
                </article>
              ))}
            </div>
          </div>
        </section>
      )}

      {(assessment.missing_data.length > 0 || notes.length > 0) && (
        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>Data quality</h2>
              <p>What was read, and what would sharpen the estimate.</p>
            </div>
          </div>
          <div className="card-body stack" style={{ gap: 14 }}>
            {notes.length > 0 && (
              <div className="banner banner-info">
                <CheckCircleIcon size={17} className="banner-icon" />
                <div>
                  <strong>Reading your upload</strong>
                  <ul className="plain-list" style={{ marginTop: 5 }}>
                    {notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            {assessment.missing_data.length > 0 && (
              <div className="banner banner-warning">
                <InfoIcon size={17} className="banner-icon" />
                <div>
                  <strong>Would improve these estimates</strong>
                  <ul className="plain-list" style={{ marginTop: 5 }}>
                    {assessment.missing_data.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      <p className="provenance">
        Generated by the <code>{assessment.engine}</code> engine
        {assessment.model ? ` (${assessment.model})` : ""} at{" "}
        {new Date(assessment.generated_at).toLocaleString()}. Re-running the same
        input will produce different numbers.
      </p>
    </div>
  );
}
