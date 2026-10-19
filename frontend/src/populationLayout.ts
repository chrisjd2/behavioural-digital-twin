import { forceCollide, forceSimulation, type SimulationNodeDatum } from 'd3-force'
import type { AgentNode, RunPopulation } from './api/runs'

type Node = SimulationNodeDatum & { id: string; r: number }
export type Category = Node & { label: string; users: number; angle: number; colour: string }
export type Agent = Node & { agent: AgentNode; colour: string }
export type Link = { source: Agent; target: Category; weight: number }
export type Layout = {
  categories: Category[]
  agents: Agent[] // in keyboard order: grouped by top category, round the ring
  links: Link[]
  width: number
  height: number
  narrow: boolean
}

/**
 * The six most-read categories get hues that stay apart on a washed-out projector, and apart
 * from the arm colours (slate, amber, blue, violet, teal). The rest are neutral grey.
 */
export const CATEGORY_COLOURS = ['#c8324b', '#2b8a3e', '#d4a20b', '#c2338f', '#0c7c94', '#7a4a21']
export const OTHER_CATEGORY = '#9aa0a8'

const TICKS = 300
const INNER = 0.8 // how far towards its categories a reader is drawn (1 = onto the ring)
const TOP_PULL = 0.7 // share of a reader's pull towards the category they click most
const FENCE = 0.86 // readers stay inside this share of the ring
const NARROW = 640

/** The graph never runs below the fold: its height is capped by the window. */
export function graphHeight(width: number, windowHeight: number): number {
  const narrow = width < NARROW
  const wanted = narrow ? width * 1.25 : width * 0.55
  return Math.round(Math.max(360, Math.min(wanted, windowHeight - (narrow ? 140 : 190))))
}

/**
 * Categories sit fixed on a ring, most-read first. Each reader is pulled towards the categories
 * they clicked, mostly towards the one they click most, so readers cluster by it and take its
 * colour. The simulation runs to rest up front (a still picture reads better on a projector
 * than a jiggle) and is deterministic for the same input.
 */
export function layout(population: RunPopulation, width: number, windowHeight: number): Layout {
  const narrow = width < NARROW
  const height = graphHeight(width, windowHeight)
  // Room for the longest label (with its count) beside the ring; roughly 0.6em per character.
  // On a phone the labels sit above or below their category instead, so the ring can be wide.
  const longest = Math.max(
    0,
    ...population.categories.map((c) => `${c.category} ${c.users}`.length),
  )
  const labelRoom = narrow ? 24 : Math.min(width * 0.38, 36 + longest * 10.5)
  const rx = width / 2 - labelRoom
  const ry = height / 2 - (narrow ? 36 : 48)
  const cx = width / 2
  const cy = height / 2
  const most = Math.max(1, ...population.categories.map((c) => c.users))
  const categories: Category[] = population.categories.map((c, i, all) => {
    const angle = (i / all.length) * 2 * Math.PI - Math.PI / 2
    const x = cx + rx * Math.cos(angle)
    const y = cy + ry * Math.sin(angle)
    return {
      id: `category:${c.category}`,
      label: c.category,
      users: c.users,
      angle,
      colour: CATEGORY_COLOURS[i] ?? OTHER_CATEGORY,
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
      colour: byName.get(top(agent))?.colour ?? OTHER_CATEGORY,
      r: narrow ? 4.5 : 6,
    }))
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

  return { categories, agents, links, width, height, narrow }
}

type Anchor = 'middle' | 'start' | 'end'

/** Labels run away from the ring's vertical axis, so neighbours at the top and bottom
 * spread apart instead of colliding; only a category dead on the axis is centred. */
export function labelPosition(c: Category, width: number, narrow: boolean) {
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
