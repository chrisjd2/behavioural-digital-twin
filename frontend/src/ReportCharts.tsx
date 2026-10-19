/** Hand-rolled SVG charts for the Report (ADR-0009: no chart library). x positions are in %. */
import type { ReactNode } from 'react'
import type { Estimate, Reliability } from './api/report'
import { armClass, armName, ciBar, percent, position, type Domain } from './reportModel'

const ROW = 44
const BAR = 20
const AXIS = 26

export type Row = {
  key: string
  label: ReactNode
  className: string // carries --arm
  estimate: Estimate // low/high equal to mean: no whisker
  value: string
  tooltip: string
}

export type Reference = {
  key: string
  label: string
  value: number
  kind: 'baseline' | 'feed' | 'sample'
}

type Props = {
  title: string
  rows: Row[]
  domain: Domain
  ticks: number[]
  tick: (value: number) => string
  references?: Reference[]
  mark?: 'bar' | 'dot'
  zeroLine?: boolean
}

/** Text anchored so a label near either edge stays inside the track. */
function anchor(x: number): 'start' | 'middle' | 'end' {
  if (x < 12) return 'start'
  if (x > 88) return 'end'
  return 'middle'
}

/**
 * One row per arm: a bar (or dot) at the estimate with its 95% CI as a whisker. Labels and
 * values are HTML beside the SVG so they stay legible at any width. Reference lines run the
 * full height, labelled above the plot on their own line each.
 */
export function BarChart({
  title,
  rows,
  domain,
  ticks,
  tick,
  references = [],
  mark = 'bar',
  zeroLine = false,
}: Props) {
  const top = references.length * 22 + (references.length ? 6 : 0)
  const plotHeight = rows.length * ROW
  const height = top + plotHeight + AXIS
  return (
    <div className="bar-chart">
      <ul className="bar-labels" style={{ paddingTop: top }} aria-hidden="true">
        {rows.map((row) => (
          <li key={row.key} className={row.className} style={{ height: ROW }}>
            {row.label}
          </li>
        ))}
      </ul>
      <svg
        className="bar-track"
        width="100%"
        height={height}
        role="img"
        aria-label={`${title}: ${rows.map((r) => r.tooltip).join('; ')}`}
      >
        {ticks.map((t) => (
          <g key={t} className="tick">
            <line
              x1={`${position(t, domain)}%`}
              x2={`${position(t, domain)}%`}
              y1={top}
              y2={top + plotHeight}
            />
            <text
              x={`${position(t, domain)}%`}
              y={height - 6}
              textAnchor={anchor(position(t, domain))}
            >
              {tick(t)}
            </text>
          </g>
        ))}
        {zeroLine && (
          <line
            className="zero-line"
            x1={`${position(0, domain)}%`}
            x2={`${position(0, domain)}%`}
            y1={top - 4}
            y2={top + plotHeight}
          />
        )}
        {rows.map((row, i) => {
          const bar = ciBar(row.estimate, domain)
          const y = top + i * ROW + ROW / 2
          const whisker = row.estimate.low !== row.estimate.high
          return (
            <g key={row.key} className={`bar-row ${row.className}`}>
              <title>{row.tooltip}</title>
              <rect className="hit" x="0" width="100%" y={y - ROW / 2} height={ROW} />
              {mark === 'bar' ? (
                <rect
                  className="bar"
                  x={`${bar.start}%`}
                  width={`${bar.width}%`}
                  y={y - BAR / 2}
                  height={BAR}
                  rx="4"
                />
              ) : (
                <circle className="dot" cx={`${bar.mean}%`} cy={y} r="8" />
              )}
              {whisker && (
                <g className="whisker">
                  <line x1={`${bar.low}%`} x2={`${bar.high}%`} y1={y} y2={y} />
                  <line x1={`${bar.low}%`} x2={`${bar.low}%`} y1={y - 8} y2={y + 8} />
                  <line x1={`${bar.high}%`} x2={`${bar.high}%`} y1={y - 8} y2={y + 8} />
                </g>
              )}
            </g>
          )
        })}
        {references.map((ref, i) => {
          const x = position(ref.value, domain)
          return (
            <g key={ref.key} className={`reference reference-${ref.kind}`}>
              <title>{ref.label}</title>
              <line x1={`${x}%`} x2={`${x}%`} y1={i * 22 + 20} y2={top + plotHeight} />
              <text x={`${x}%`} y={i * 22 + 15} textAnchor={anchor(x)}>
                {ref.label}
              </text>
            </g>
          )
        })}
      </svg>
      <ul className="bar-values" style={{ paddingTop: top }} aria-hidden="true">
        {rows.map((row) => (
          <li key={row.key} style={{ height: ROW }}>
            {row.value}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Arm chip and name, the row label every chart shares. */
export function ArmLabel({ arm }: { arm: string }) {
  return (
    <>
      {arm.length === 1 ? (
        <span className="chip">{arm}</span>
      ) : (
        <span className="chip chip-baseline" aria-hidden="true" />
      )}
      <span className="arm-name">{armName(arm)}</span>
      {arm === 'E' && <span className="control-tag">control</span>}
    </>
  )
}

const SIZE = 160
const PAD = 26

/** Predicted p_click (x) against the share really clicked (y), one small chart per arm. */
export function ReliabilityDiagrams({ reliability }: { reliability: Reliability[] }) {
  const scale = (v: number) => PAD + v * (SIZE - PAD - 8)
  const flip = (v: number) => SIZE - scale(v)
  return (
    <div className="reliability">
      {reliability.map(({ arm, bins }) => {
        const points = bins
          .filter((b) => b.n > 0 && b.mean_p_click !== null)
          .map((b) => ({ ...b, x: b.mean_p_click ?? 0, y: b.clicks / b.n }))
        return (
          <figure key={arm} className={`reliability-panel ${armClass(arm)}`}>
            <figcaption>
              <ArmLabel arm={arm} />
            </figcaption>
            <svg
              viewBox={`0 0 ${SIZE} ${SIZE}`}
              role="img"
              aria-label={`Arm ${arm} reliability: ${points
                .map((p) => `predicted ${percent(p.x, 0)}, clicked ${percent(p.y, 0)} of ${p.n}`)
                .join('; ')}`}
            >
              <rect
                className="frame"
                x={scale(0)}
                y={flip(1)}
                width={scale(1) - scale(0)}
                height={scale(1) - scale(0)}
              />
              <line className="diagonal" x1={scale(0)} y1={flip(0)} x2={scale(1)} y2={flip(1)} />
              <polyline
                className="curve"
                points={points.map((p) => `${scale(p.x)},${flip(p.y)}`).join(' ')}
              />
              {points.map((p) => (
                <circle key={p.low} className="point" cx={scale(p.x)} cy={flip(p.y)} r="4">
                  <title>
                    {`Predicted ${percent(p.low, 0)}–${percent(p.high, 0)}: ${p.n} predictions, ${percent(p.y, 0)} clicked`}
                  </title>
                </circle>
              ))}
              <text x={scale(0)} y={SIZE - 4}>
                0
              </text>
              <text x={scale(1)} y={SIZE - 4} textAnchor="end">
                100% predicted
              </text>
              <text x={4} y={flip(1) + 4}>
                100%
              </text>
              <text x={4} y={flip(0)}>
                0
              </text>
            </svg>
          </figure>
        )
      })}
    </div>
  )
}
