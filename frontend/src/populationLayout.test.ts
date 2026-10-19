import { describe, expect, it } from 'vitest'
import type { AgentNode, RunPopulation } from './api/runs'
import { CATEGORY_COLOURS, OTHER_CATEGORY, graphHeight, layout } from './populationLayout'

const CATEGORIES = ['news', 'sports', 'finance', 'tv', 'health', 'travel', 'autos', 'music']

/** `n` readers; reader i clicks mostly category i % 8, plus one click on news. */
function population(n: number): RunPopulation {
  const agents: AgentNode[] = Array.from({ length: n }, (_, i) => {
    const top = CATEGORIES[i % CATEGORIES.length]
    return {
      user_id: `U${i}`,
      n_history: 6,
      categories:
        top === 'news'
          ? [{ category: 'news', clicks: 6 }]
          : [
              { category: top, clicks: 5 },
              { category: 'news', clicks: 1 },
            ],
    }
  })
  return {
    run_id: 'r',
    population: 'test',
    data_source: 'mind',
    mock: true,
    is_result: false,
    agents,
    categories: CATEGORIES.map((category, i) => ({ category, users: 100 - i })),
  }
}

const distance = (a: { x?: number; y?: number }, b: { x?: number; y?: number }) =>
  Math.hypot((a.x ?? 0) - (b.x ?? 0), (a.y ?? 0) - (b.y ?? 0))

describe('population layout', () => {
  const graph = layout(population(300), 1360, 1080)

  it('colours the six most-read categories and greys the rest', () => {
    expect(graph.categories.map((c) => c.colour)).toEqual([
      ...CATEGORY_COLOURS,
      OTHER_CATEGORY,
      OTHER_CATEGORY,
    ])
    const music = graph.agents.find((a) => a.id === 'U7')
    expect(music?.colour).toBe(OTHER_CATEGORY)
    expect(graph.agents.find((a) => a.id === 'U1')?.colour).toBe(CATEGORY_COLOURS[1])
  })

  it('places each reader nearer its top category than the opposite side of the ring', () => {
    const sports = graph.categories[1]
    const opposite = graph.categories[5]
    const readers = graph.agents.filter((a) => a.agent.categories[0].category === 'sports')
    expect(readers.every((a) => distance(a, sports) < distance(a, opposite))).toBe(true)
  })

  it('keeps readers inside the ring and the graph', () => {
    for (const a of graph.agents) {
      expect(a.x).toBeGreaterThan(0)
      expect(a.x).toBeLessThan(graph.width)
      expect(a.y).toBeGreaterThan(0)
      expect(a.y).toBeLessThan(graph.height)
    }
  })

  it('orders readers for the keyboard by top category round the ring', () => {
    const tops = graph.agents.map((a) => a.agent.categories[0].category)
    const firstOf = CATEGORIES.map((c) => tops.indexOf(c))
    expect(firstOf).toEqual([...firstOf].sort((a, b) => a - b))
  })

  it('is deterministic', () => {
    const again = layout(population(300), 1360, 1080)
    expect(again.agents.map((a) => [a.x, a.y])).toEqual(graph.agents.map((a) => [a.x, a.y]))
  })

  it('caps the height to the window', () => {
    expect(graphHeight(1360, 700)).toBe(510)
    expect(graphHeight(1360, 2000)).toBe(748)
    expect(graphHeight(1360, 300)).toBe(360)
  })
})
