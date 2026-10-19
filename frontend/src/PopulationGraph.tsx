import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { RunPopulation } from './api/runs'
import { labelPosition, layout } from './populationLayout'

const MOVES: Record<string, (i: number, n: number) => number> = {
  ArrowRight: (i, n) => (i + 1) % n,
  ArrowDown: (i, n) => (i + 1) % n,
  ArrowLeft: (i, n) => (i - 1 + n) % n,
  ArrowUp: (i, n) => (i - 1 + n) % n,
  Home: () => 0,
  End: (_, n) => n - 1,
}

type Props = {
  population: RunPopulation
  selected: string | null
  onSelect: (userId: string) => void
  /** Laid out at the full step width, so opening the reader panel only scales the picture. */
  width: number
  windowHeight: number
}

/** One Tab stop: arrow keys move between readers (grouped by top category), Enter opens one. */
export default function PopulationGraph({
  population,
  selected,
  onSelect,
  width,
  windowHeight,
}: Props) {
  const graph = useMemo(
    () => layout(population, width, windowHeight),
    [population, width, windowHeight],
  )
  const [active, setActive] = useState(0)
  const [pointed, setPointed] = useState<string | null>(null)
  const readers = useRef<(SVGCircleElement | null)[]>([])
  const shown = new Set([selected, pointed].filter((id) => id !== null))

  function onKeyDown(event: KeyboardEvent, index: number) {
    const move = MOVES[event.key]
    if (move) {
      event.preventDefault()
      const next = move(index, graph.agents.length)
      setActive(next)
      readers.current[next]?.focus()
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect(graph.agents[index].id)
    }
  }

  const classes = [graph.narrow && 'graph-narrow', selected && 'has-selection'].filter(Boolean)
  return (
    <div className="graph">
      <svg
        viewBox={`0 0 ${graph.width} ${graph.height}`}
        width="100%"
        role="group"
        aria-label={`${population.agents.length} readers around the ${population.categories.length} categories they clicked. Use the arrow keys to move between readers.`}
        className={classes.join(' ') || undefined}
      >
        <g className="links" aria-hidden="true">
          {graph.links
            .filter((l) => shown.has(l.source.id))
            .map((l) => (
              <line
                key={`${l.source.id}>${l.target.id}`}
                x1={l.source.x}
                y1={l.source.y}
                x2={l.target.x}
                y2={l.target.y}
                strokeWidth={1 + 4 * l.weight}
              />
            ))}
        </g>
        {graph.categories.map((c) => {
          const label = labelPosition(c, graph.width, graph.narrow)
          return (
            <g key={c.id} className="category-node" aria-hidden="true">
              <circle cx={c.x} cy={c.y} r={c.r} stroke={c.colour} />
              <text
                x={label.x}
                y={label.y}
                textAnchor={label.anchor}
                dominantBaseline={label.baseline}
              >
                {c.label}
                {!graph.narrow && <tspan className="category-count"> {c.users}</tspan>}
              </text>
            </g>
          )
        })}
        {graph.agents.map(({ id, agent, x, y, r, colour }, i) => (
          <circle
            key={id}
            ref={(el) => {
              readers.current[i] = el
            }}
            data-user-id={id}
            className="agent-node"
            cx={x}
            cy={y}
            r={id === selected ? r + 3 : r}
            fill={colour}
            role="button"
            tabIndex={i === active ? 0 : -1}
            aria-label={`Reader ${id}: ${agent.n_history} past clicks in ${agent.categories.map((c) => c.category).join(', ')}`}
            aria-pressed={id === selected}
            onClick={() => {
              setActive(i)
              onSelect(id)
            }}
            onKeyDown={(e) => onKeyDown(e, i)}
            onFocus={() => setPointed(id)}
            onBlur={() => setPointed(null)}
            onMouseEnter={() => setPointed(id)}
            onMouseLeave={() => setPointed(null)}
          >
            <title>{`Reader ${id}`}</title>
          </circle>
        ))}
      </svg>
    </div>
  )
}
