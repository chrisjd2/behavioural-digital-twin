/** Arms and baselines in plain language (CONTEXT.md §3). Colours live in index.css as --arm-*. */
export type ArmCard = {
  id: string
  name: string
  knows: string
  description: string
}

export const ARMS: ArmCard[] = [
  {
    id: 'a',
    name: 'Plain LLM',
    knows: 'Nothing about the reader',
    description: 'Guesses for “a typical Microsoft News reader”. The bar to beat.',
  },
  {
    id: 'b',
    name: 'Invented persona',
    knows: 'A made-up character',
    description:
      'A name, age, job and personality seeded from the user ID only. Not from this user’s data.',
  },
  {
    id: 'c',
    name: 'Twin + memory',
    knows: 'Their real past clicks',
    description: 'Sees the past clicks most like each headline, plus the most recent ones.',
  },
  {
    id: 'd',
    name: 'Twin + profile + memory',
    knows: 'Past clicks and a profile of them',
    description:
      'Memories plus a short profile of what they read, every point backed by a past click.',
  },
]

export const CONTROL: ArmCard = {
  id: 'e',
  name: 'Wrong twin',
  knows: 'Someone else’s profile and clicks',
  description: 'Arm D given a different reader. Tests whether gains are personal.',
}

export const BASELINES: ArmCard[] = [
  {
    id: 'popularity',
    name: 'Popularity',
    knows: 'What other readers clicked earlier',
    description: 'Ranks headlines by how often everyone else clicked them before this moment.',
  },
  {
    id: 'random',
    name: 'Random',
    knows: 'Nothing',
    description: 'A shuffle. The floor every method has to clear.',
  },
]

const ARM_NAMES = new Map(
  [...ARMS, CONTROL, ...BASELINES].map((a) => [a.id, a.name] as [string, string]),
)

/** An arm id from a run file ('A', 'random') in plain language. */
export const armName = (arm: string) => ARM_NAMES.get(arm.toLowerCase()) ?? arm

/** The CSS class carrying the arm's colour; baselines share the grey. */
export const armClass = (arm: string) =>
  arm.length === 1 ? `arm-${arm.toLowerCase()}` : 'baseline'
