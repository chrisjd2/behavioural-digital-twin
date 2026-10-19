import { forceCollide, forceSimulation, type SimulationNodeDatum } from 'd3-force'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { AgentNode, RunPopulation } from './api/runs'

type Node = SimulationNodeDatum & { id: string; r: number }
type Category = Node & { label: string; users: number; angle: number; colour: string }
type Agent = Node & { agent: AgentNode; colour: string }
type Link = { source: Agent; target: Category; weight: number }
type Layout = {
  categories: Category[]
  agents: Agent[] // in keyboard order: grouped by top category, round the ring
  links: Link[]
  width: number
  height: number
}

/** Muted earth tones, kept apart from the arm colours; categories past these are stone grey. */
const CATEGORY_COLOURS = [
  '#8b6f4e',
  '#6b8250',
  '#9b6074',
  '#a88a3c',
  '#8e5a45',
  '#6f8f86',
  '#85778f',
  '#8a8a5c',
  '#b08a7a',
  '#5f6b52',
]
const STONE = '#a3a09a'
const TICKS = 300
const INNER = 0.8 // how far towards its categories a reader is drawn (1 = onto the ring)
const TOP_PULL = 0.7
const FENCE = 0.86 // readers stay inside this share of the ring

/** The graph never runs below the fold: its height is capped by the window. */
function graphHeight(width: number, narrow: boolean): number {
  const room = typeof window === 'undefined' ? 900 : window.innerHeight
  const wanted = narrow ? width * 1.25 : width * 0.55
  return Math.round(Math.max(360, Math.min(wanted, room - (narrow ? 140 : 190))))
}

/**
 * Categories sit fixed on a ring, most-read first. Each reader is pulled towards the categories
 * they clicked, mostly towards the one they click most, so readers cluster by it and take its
 * colour. The simulation runs to rest up front: a still
 * picture reads better on a projector than a jiggle.
 */
function layout(population: RunPopulation, width: number): Layout {
  const narrow = width < 640
  const height = graphHeight(width, narrow)
  // Room for the longest label (with its count) beside the ring; roughly 0.6em per character.
  const longest = Math.max(
    0,
    ...population.categories.map((c) => `${c.category} ${c.users}`.length),
  )
  // On a phone the labels sit above or below their category instead, so the ring can be wide.
  const labelRoom = narrow ? 24 : Math.min(width * 0.38, 36 + longest * 10.5)
  const rx = width / 2 - labelRoom
  const ry = height / 2 - (narrow ? 36 : 48)
  const most = Math.max(1, ...population.categories.map((c) => c.users))
  const categories: Category[] = population.categories.map((c, i, all) => {
    const angle = (i / all.length) * 2 * Math.PI - Math.PI / 2
    const x = width / 2 + rx * Math.cos(angle)
    const y = height / 2 + ry * Math.sin(angle)
    return {
      id: `category:${c.category}`,
      label: c.category,
      users: c.users,
      angle,
      colour: CATEGORY_COLOURS[i] ?? STONE,
      r: (narrow ? 5 : 8) + (narrow ? 8 : 14) * Math.sqrt(c.users / most),
      x,
      y,
      fx: x,
      fy: y,
    }
  })
  const byName = new Map(categories.map((c) => [c.label, c]))
  const ring = new Map(categories.map((c, i) => [c.label, i]))
  const top = (a: AgentNode) => a.categories[0]?.category ?? ''
  const agents: Agent[] = [...population.agents]
    .sort(
      (a, b) =>
        (ring.get(top(a)) ?? Infinity) - (ring.get(top(b)) ?? Infinity) ||
        a.user_id.localeCompare(b.user_id),
    )
    .map((agent) => ({
      id: agent.user_id,
      agent,
      colour: byName.get(top(agent))?.colour ?? STONE,
      r: narrow ? 4.5 : 6,
    }))
  // A reader's top category holds most of the pull, so readers cluster by what they read most;
  // the rest of their clicks share what is left.
  const links: Link[] = agents.flatMap((a) => {
    const total = a.agent.categories.reduce((sum, c) => sum + c.clicks, 0) || 1
    return a.agent.categories.flatMap(({ category, clicks }, i) => {
      const target = byName.get(category)
      const weight = (i === 0 ? TOP_PULL : 0) + (1 - TOP_PULL) * (clicks / total)
      return target ? [{ source: a, target, weight }] : []
    })
  })

  // Each reader aims for the weighted centre of its categories, drawn in towards the middle
  // so clusters form inside the ring and never cover a category or its label.
  const cx = width / 2
  const cy = height / 2
  const aim = new Map(agents.map((a) => [a, { x: cx, y: cy }]))
  for (const l of links) {
    const point = aim.get(l.source)!
    point.x += INNER * l.weight * ((l.target.x ?? cx) - cx)
    point.y += INNER * l.weight * ((l.target.y ?? cy) - cy)
  }
  agents.forEach((a, i) => {
    // Golden-angle offsets: a deterministic start that collision can spread out.
    const point = aim.get(a)!
    a.x = point.x + Math.cos(i * 2.4) * (1 + (i % 7))
    a.y = point.y + Math.sin(i * 2.4) * (1 + (i % 7))
  })
  const limit = { x: rx * FENCE, y: ry * FENCE }

  forceSimulation<Node>(agents)
    .force('aim', (alpha) => {
      for (const a of agents) {
        const point = aim.get(a)!
        a.vx = (a.vx ?? 0) + (point.x - (a.x ?? 0)) * 0.12 * alpha
        a.vy = (a.vy ?? 0) + (point.y - (a.y ?? 0)) * 0.12 * alpha
      }
    })
    .force(
      'collide',
      forceCollide<Node>((n) => n.r + 1.5),
    )
    .force('fence', () => {
      for (const a of agents) {
        const dx = (a.x ?? 0) + (a.vx ?? 0) - cx
        const dy = (a.y ?? 0) + (a.vy ?? 0) - cy
        const out = Math.hypot(dx / limit.x, dy / limit.y)
        if (out > 1) {
          a.vx = cx + dx / out - (a.x ?? 0)
          a.vy = cy + dy / out - (a.y ?? 0)
        }
      }
    })
    .stop()
    .tick(TICKS)

  return { categories, agents, links, width, height }
}

/** The SVG's rendered width, so text stays a readable size at any screen width. */
function useWidth<T extends Element>(fallback: number) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry.contentRect.width)
      if (next > 0) setWidth((w) => (Math.abs(w - next) > 24 ? next : w))
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

type Anchor = 'middle' | 'start' | 'end'

/** Labels run away from the ring's vertical axis, so neighbours at the top and bottom
 * spread apart instead of colliding; only a category dead on the axis is centred. */
function labelPosition(c: Category, width: number, narrow: boolean) {
  const cos = Math.cos(c.angle)
  const sin = Math.sin(c.angle)
  const anchor: Anchor = Math.abs(cos) < 0.05 ? 'middle' : cos > 0 ? 'start' : 'end'
  if (narrow) {
    // On a phone labels sit above or below their category, kept inside the graph.
    const length = c.label.length * 7.2 + 4 // about 0.6em per character at 12px
    const x = c.x ?? 0
    const inside = {
      middle: Math.min(width - length / 2, Math.max(length / 2, x)),
      start: Math.min(width - length, x),
      end: Math.max(length, x),
    }
    return {
      x: inside[anchor],
      y: (c.y ?? 0) + (sin < 0 ? -(c.r + 5) : c.r + 5),
      anchor,
      baseline: (sin < 0 ? 'auto' : 'hanging') as 'auto' | 'hanging',
    }
  }
  const gap = c.r + 8
  return {
    x: (c.x ?? 0) + cos * gap,
    y: (c.y ?? 0) + sin * gap,
    anchor,
    baseline: (sin < -0.7 ? 'auto' : sin > 0.7 ? 'hanging' : 'middle') as
      'auto' | 'hanging' | 'middle',
  }
}

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
}

/** One Tab stop: arrow keys move between readers (grouped by top category), Enter opens one. */
export default function PopulationGraph({ population, selected, onSelect }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(1000)
  const graph = useMemo(() => layout(population, width), [population, width])
  const narrow = width < 640
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

  return (
    <div className="graph" ref={ref}>
      <svg
        viewBox={`0 0 ${graph.width} ${graph.height}`}
        width="100%"
        role="group"
        aria-label={`${population.agents.length} readers around the ${population.categories.length} categories they clicked. Use the arrow keys to move between readers.`}
        className={narrow ? 'graph-narrow' : undefined}
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
          const label = labelPosition(c, graph.width, narrow)
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
                {!narrow && <tspan className="category-count"> {c.users}</tspan>}
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
