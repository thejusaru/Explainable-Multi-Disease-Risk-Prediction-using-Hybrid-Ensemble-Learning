"use client";

import { useState } from "react";
import {
  PROJECTION_AGES,
  SERIES_VARS,
  type ConditionRisk,
} from "../lib/types";

/**
 * Multi-series line chart of risk probability across the projection ages.
 *
 * Hand-rolled SVG rather than a charting dependency: the shape is fixed (five
 * x-positions, 0-1 on y) so a library would add weight without adding much.
 * Colours resolve through CSS variables so the chart follows the active theme
 * with no JS involvement.
 */

const WIDTH = 780;
const HEIGHT = 380;
const PADDING = { top: 20, right: 20, bottom: 54, left: 58 };

const PLOT_W = WIDTH - PADDING.left - PADDING.right;
const PLOT_H = HEIGHT - PADDING.top - PADDING.bottom;

interface Props {
  conditions: ConditionRisk[];
  patientAge: number;
}

export default function RiskTimeline({ conditions, patientAge }: Props) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hoverAge, setHoverAge] = useState<number | null>(null);

  const visible = conditions.filter((c) => !hidden.has(c.condition));

  // Scale the y-axis to the data rather than a fixed 0-100%: most realistic
  // probabilities sit under 30%, and a fixed axis would flatten every line into
  // an unreadable band along the bottom.
  const maxProbability = Math.max(
    0.1,
    ...visible.flatMap((c) => c.projections.map((p) => p.probability)),
  );
  const yMax = Math.min(1, Math.ceil(maxProbability * 10 + 1) / 10);

  const x = (age: number) => {
    const index = PROJECTION_AGES.indexOf(age as (typeof PROJECTION_AGES)[number]);
    const span = PROJECTION_AGES.length - 1;
    return PADDING.left + (index / span) * PLOT_W;
  };
  const y = (probability: number) =>
    PADDING.top + PLOT_H - (probability / yMax) * PLOT_H;

  const yTicks = Array.from({ length: 6 }, (_, i) => (yMax / 5) * i);

  function toggle(condition: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(condition)) next.delete(condition);
      else next.add(condition);
      return next;
    });
  }

  return (
    <>
      <div className="chart-scroll">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="chart"
          role="img"
          aria-label="Line chart of projected disease risk across ages 25 to 45"
        >
          {/* Horizontal gridlines + y-axis labels */}
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={PADDING.left}
                x2={PADDING.left + PLOT_W}
                y1={y(tick)}
                y2={y(tick)}
                className="grid-line"
              />
              <text
                x={PADDING.left - 10}
                y={y(tick) + 4}
                textAnchor="end"
                className="axis-label"
              >
                {Math.round(tick * 100)}%
              </text>
            </g>
          ))}

          <text
            className="axis-title"
            transform={`rotate(-90) translate(${-(PADDING.top + PLOT_H / 2)}, 14)`}
            textAnchor="middle"
          >
            Probability
          </text>

          {/* X-axis ticks, with the patient's current age called out */}
          {PROJECTION_AGES.map((age) => {
            const isCurrent = Math.abs(age - patientAge) <= 2;
            return (
              <g key={age}>
                <line
                  x1={x(age)}
                  x2={x(age)}
                  y1={PADDING.top}
                  y2={PADDING.top + PLOT_H}
                  className={hoverAge === age ? "grid-line-active" : "grid-line"}
                />
                <text
                  x={x(age)}
                  y={PADDING.top + PLOT_H + 22}
                  textAnchor="middle"
                  className={isCurrent ? "axis-label-current" : "axis-label"}
                >
                  {age}
                </text>
                {isCurrent && (
                  <text
                    x={x(age)}
                    y={PADDING.top + PLOT_H + 37}
                    textAnchor="middle"
                    className="axis-note"
                  >
                    now
                  </text>
                )}
                {/* Invisible hover target spanning the full plot height */}
                <rect
                  x={x(age) - PLOT_W / 8}
                  y={PADDING.top}
                  width={PLOT_W / 4}
                  height={PLOT_H}
                  fill="transparent"
                  onMouseEnter={() => setHoverAge(age)}
                  onMouseLeave={() => setHoverAge(null)}
                />
              </g>
            );
          })}

          <text
            className="axis-title"
            x={PADDING.left + PLOT_W / 2}
            y={HEIGHT - 6}
            textAnchor="middle"
          >
            Age
          </text>

          {/* One polyline + point set per visible condition */}
          {visible.map((condition) => {
            const index = conditions.findIndex(
              (c) => c.condition === condition.condition,
            );
            const color = SERIES_VARS[index % SERIES_VARS.length];
            const points = condition.projections
              .map((p) => `${x(p.age)},${y(p.probability)}`)
              .join(" ");

            return (
              <g key={condition.condition}>
                <polyline
                  points={points}
                  fill="none"
                  stroke={color}
                  strokeWidth={2.5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {condition.projections.map((p) => (
                  <g key={p.age}>
                    <circle
                      cx={x(p.age)}
                      cy={y(p.probability)}
                      r={hoverAge === p.age ? 5.5 : 3.5}
                      fill={color}
                    />
                    {hoverAge === p.age && (
                      <text
                        x={x(p.age)}
                        y={y(p.probability) - 12}
                        textAnchor="middle"
                        className="point-label"
                        fill={color}
                      >
                        {(p.probability * 100).toFixed(1)}%
                      </text>
                    )}
                  </g>
                ))}
              </g>
            );
          })}

          {/* Axis lines drawn last so they sit above the gridlines */}
          <line
            x1={PADDING.left}
            x2={PADDING.left}
            y1={PADDING.top}
            y2={PADDING.top + PLOT_H}
            className="axis-line"
          />
          <line
            x1={PADDING.left}
            x2={PADDING.left + PLOT_W}
            y1={PADDING.top + PLOT_H}
            y2={PADDING.top + PLOT_H}
            className="axis-line"
          />
        </svg>
      </div>

      <div className="legend">
        {conditions.map((condition, index) => {
          const color = SERIES_VARS[index % SERIES_VARS.length];
          const isHidden = hidden.has(condition.condition);
          return (
            <button
              key={condition.condition}
              type="button"
              className={`legend-item${isHidden ? " legend-item-off" : ""}`}
              onClick={() => toggle(condition.condition)}
              aria-pressed={!isHidden}
            >
              <span className="legend-swatch" style={{ background: color }} />
              {condition.condition}
            </button>
          );
        })}
      </div>
    </>
  );
}
