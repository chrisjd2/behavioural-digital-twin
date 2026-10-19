/** Step 0 Hook (ADR-0008): question, guess, history, guess again, reveal. */
export type HookState = { stage: 'title' | 'guess' | 'reveal'; history: boolean }

export type HookCommand = 'next' | 'prev' | 'history' | 'reveal'

/** A presenter key: a state change, or full screen (which the browser owns). */
export type HookKey = HookCommand | 'fullscreen'

export const INITIAL: HookState = { stage: 'title', history: false }

export function step(state: HookState, command: HookCommand): HookState {
  const { stage, history } = state
  switch (command) {
    case 'next':
      if (stage === 'title') return { stage: 'guess', history: false }
      if (stage === 'guess')
        return history ? { ...state, stage: 'reveal' } : { ...state, history: true }
      return state
    case 'prev':
      if (stage === 'reveal') return { ...state, stage: 'guess' }
      if (stage === 'guess') return history ? { ...state, history: false } : INITIAL
      return state
    case 'history':
      // The reveal makes room for the predictions; the history comes back with Back.
      return stage === 'guess' ? { ...state, history: !history } : state
    case 'reveal':
      if (stage === 'title') return state
      return { ...state, stage: stage === 'reveal' ? 'guess' : 'reveal' }
  }
}

const KEYS: Record<string, HookKey> = {
  // Up and down are left to the browser, so the presenter can still scroll.
  ArrowRight: 'next',
  PageDown: 'next', // presentation clickers send PageDown / PageUp
  ArrowLeft: 'prev',
  PageUp: 'prev',
  h: 'history',
  r: 'reveal',
  f: 'fullscreen',
}

export function commandFor(event: KeyboardEvent): HookKey | undefined {
  if (event.ctrlKey || event.metaKey || event.altKey) return undefined
  return KEYS[event.key.length === 1 ? event.key.toLowerCase() : event.key]
}
