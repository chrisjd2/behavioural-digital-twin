/** The presenter deck (ADR-0012): one running order of slides and existing steps. */
import { commandFor } from './hookState'

export const SECTIONS = ['About me', 'Learn', 'Tinker', 'Teach'] as const
export type Section = (typeof SECTIONS)[number]

export type ScreenId =
  | 'title'
  | 'who'
  | 'career'
  | 'life'
  | 'handoff'
  | 'brief'
  | 'mirofish'
  | 'research'
  | 'gap'
  | 'build'
  | 'population'
  | 'hook'
  | 'simulation'
  | 'report'
  | 'checkin'
  | 'takeaways'
  | 'thanks'

export type Screen = { id: ScreenId; section: Section; title: string }

export const SCREENS: Screen[] = [
  { id: 'title', section: 'About me', title: 'Chris Davies' },
  { id: 'who', section: 'About me', title: 'Who I am' },
  { id: 'career', section: 'About me', title: 'Career' },
  { id: 'life', section: 'About me', title: 'Learn · Tinker · Teach in my life' },
  { id: 'handoff', section: 'About me', title: 'Hand-off' },
  { id: 'brief', section: 'Learn', title: 'The brief' },
  { id: 'mirofish', section: 'Learn', title: 'Back to MiroFish' },
  { id: 'research', section: 'Learn', title: 'Research path' },
  { id: 'gap', section: 'Learn', title: 'The gap and my angle' },
  { id: 'build', section: 'Tinker', title: 'How I built it' },
  { id: 'population', section: 'Tinker', title: 'Population' },
  { id: 'hook', section: 'Teach', title: 'Hook' },
  { id: 'simulation', section: 'Teach', title: 'Simulation' },
  { id: 'report', section: 'Teach', title: 'Report' },
  { id: 'checkin', section: 'Teach', title: 'Check-in' },
  { id: 'takeaways', section: 'Teach', title: 'Takeaways' },
  { id: 'thanks', section: 'Teach', title: 'Thanks' },
]

export type DeckCommand = 'next' | 'prev'

export function move(index: number, command: DeckCommand, length: number): number {
  return Math.min(Math.max(index + (command === 'next' ? 1 : -1), 0), length - 1)
}

export function isTyping(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest('input, textarea, select') !== null
}

/** Only keys nothing on screen used: the Hook and reveals step through their own stages first. */
export function deckCommand(event: KeyboardEvent): DeckCommand | undefined {
  if (event.defaultPrevented || isTyping(event.target)) return undefined
  const command = commandFor(event)
  return command === 'next' || command === 'prev' ? command : undefined
}
