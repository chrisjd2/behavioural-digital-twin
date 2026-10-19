import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationNodeDatum,
} from 'd3-force'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { AgentNode, RunPopulation } from './api/runs'

type Node = SimulationNodeDatum & { id: string; r: number }
type Category = Node & { label: string; users: number; angle: number }
type Agent = Node & { agent: AgentNode }
type Link = { source: Agent; target: Category; share: number }
type Layout = {
  categories: Category[]
  agents: Agent[]
  links: Link[]
  width: number
  height: number
}

const TICKS = 300

/**
 * Categories sit fixed on a ring; each reader is pulled towards the categories they clicked,
 * in proportion to their clicks, so readers land near what they read. The simulation runs to
 * rest up front: a still picture reads better on a projector than a jiggle.
 */
function layout(population: RunPopulation, width: number): Layout {
  const narrow = width < 640
  const height = Math.round(narrow ? width * 1.5 : Math.min(640, Math.max(480, width * 0.5)))
  // Room for the longest label (with its count) beside the ring; roughly 0.6em per character.
  const longest = Math.max(
    0,
    ...population.categories.map((c) => `${c.category} ${c.users}`.length),
  )
  const labelRoom = Math.min(width * 0.38, (narrow ? 24 : 36) + longest * (narrow ? 7 : 10.5))
  const rx = width / 2 - labelRoom
  const ry = height / 2 - (narrow ? 44 : 48)
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
      r: (narrow ? 5 : 8) + (narrow ? 9 : 16) * Math.sqrt(c.users / most),
      x,
      y,
      fx: x,
      fy: y,
    }
  })
  const byName = new Map(categories.map((c) => [c.label, c]))
  const agentR = narrow ? 5 : 7
  const agents: Agent[] = population.agents.map((agent) => ({
    id: agent.user_id,
    agent,
    r: agentR,
    x: width / 2,
    y: height / 2,
  }))
  const links: Link[] = agents.flatMap((a) => {
    const total = a.agent.categories.reduce((sum, c) => sum + c.clicks, 0) || 1
    return a.agent.categories.flatMap(({ category, clicks }) => {
      const target = byName.get(category)
      return target ? [{ source: a, target, share: clicks / total }] : []
    })
  })

  forceSimulation<Node>([...categories, ...agents])
    .force(
      'link',
      forceLink<Node, Link>(links)
        .distance(0)
        .strength((l) => 0.12 * l.share),
    )
    .force('charge', forceManyBody<Node>().strength(-12).distanceMax(120))
    .force(
      'collide',
      forceCollide<Node>((n) => n.r + 2),
    )
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

function labelPosition(c: Category) {
  const cos = Math.cos(c.angle)
  const sin = Math.sin(c.angle)
  const gap = c.r + 8
  return {
    x: (c.x ?? 0) + cos * gap,
    y: (c.y ?? 0) + sin * gap,
    anchor: (Math.abs(cos) < 0.3 ? 'middle' : cos > 0 ? 'start' : 'end') as
      'middle' | 'start' | 'end',
    baseline: (sin < -0.7 ? 'auto' : sin > 0.7 ? 'hanging' : 'middle') as
      'auto' | 'hanging' | 'middle',
  }
}

type Props = {
  population: RunPopulation
  selected: string | null
  onSelect: (userId: string) => void
}

export default function PopulationGraph({ population, selected, onSelect }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(1000)
  const graph = useMemo(() => layout(population, width), [population, width])

  function onKeyDown(event: KeyboardEvent, userId: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect(userId)
    }
  }

  return (
    <div className="graph" ref={ref}>
      <svg
        viewBox={`0 0 ${graph.width} ${graph.height}`}
        width="100%"
        role="group"
        aria-label={`${population.agents.length} readers linked to the ${population.categories.length} categories they clicked`}
        className={width < 640 ? 'graph-narrow' : undefined}
      >
        <g className="links" aria-hidden="true">
          {graph.links.map((l) => (
            <line
              key={`${l.source.id}>${l.target.id}`}
              x1={l.source.x}
              y1={l.source.y}
              x2={l.target.x}
              y2={l.target.y}
              strokeWidth={0.5 + 3 * l.share}
              className={l.source.id === selected ? 'link-selected' : undefined}
            />
          ))}
        </g>
        {graph.categories.map((c) => {
          const label = labelPosition(c)
          return (
            <g key={c.id} className="category-node" aria-hidden="true">
              <circle cx={c.x} cy={c.y} r={c.r} />
              <text
                x={label.x}
                y={label.y}
                textAnchor={label.anchor}
                dominantBaseline={label.baseline}
              >
                {c.label}
                <tspan className="category-count"> {c.users}</tspan>
              </text>
            </g>
          )
        })}
        {graph.agents.map(({ id, agent, x, y, r }) => (
          <circle
            key={id}
            data-user-id={id}
            className="agent-node"
            cx={x}
            cy={y}
            r={id === selected ? r + 3 : r}
            role="button"
            tabIndex={0}
            aria-label={`Reader ${id}: ${agent.n_history} past clicks in ${agent.categories.map((c) => c.category).join(', ')}`}
            aria-pressed={id === selected}
            onClick={() => onSelect(id)}
            onKeyDown={(e) => onKeyDown(e, id)}
          >
            <title>{`Reader ${id}`}</title>
          </circle>
        ))}
      </svg>
    </div>
  )
}
