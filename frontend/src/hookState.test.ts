import { describe, expect, it } from 'vitest'
import { commandFor, INITIAL, step, type HookCommand, type HookState } from './hookState'

function run(...commands: HookCommand[]): HookState {
  return commands.reduce(step, INITIAL)
}

describe('hook state machine', () => {
  it('walks title, guess, history, reveal with next', () => {
    expect(INITIAL).toEqual({ stage: 'title', history: false })
    expect(run('next')).toEqual({ stage: 'guess', history: false })
    expect(run('next', 'next')).toEqual({ stage: 'guess', history: true })
    expect(run('next', 'next', 'next')).toEqual({ stage: 'reveal', history: true })
    expect(run('next', 'next', 'next', 'next')).toEqual({ stage: 'reveal', history: true })
  })

  it('walks back the same way with prev', () => {
    const revealed = run('next', 'next', 'next')
    const back = (n: number) =>
      Array.from({ length: n }).reduce<HookState>((s) => step(s, 'prev'), revealed)
    expect(back(1)).toEqual({ stage: 'guess', history: true })
    expect(back(2)).toEqual({ stage: 'guess', history: false })
    expect(back(3)).toEqual(INITIAL)
    expect(back(4)).toEqual(INITIAL)
  })

  it('toggles history only while guessing', () => {
    expect(run('history')).toEqual(INITIAL)
    expect(run('next', 'history')).toEqual({ stage: 'guess', history: true })
    expect(run('next', 'history', 'history')).toEqual({ stage: 'guess', history: false })
    expect(run('next', 'reveal', 'history')).toEqual({ stage: 'reveal', history: false })
  })

  it('reveals and hides the answer from the guess, never from the title', () => {
    expect(run('reveal')).toEqual(INITIAL)
    expect(run('next', 'reveal')).toEqual({ stage: 'reveal', history: false })
    expect(run('next', 'reveal', 'reveal')).toEqual({ stage: 'guess', history: false })
  })
})

describe('presenter keys', () => {
  const key = (k: string, extra: Partial<KeyboardEventInit> = {}) =>
    commandFor(new KeyboardEvent('keydown', { key: k, ...extra }))

  it('maps arrows, clicker page keys, H, R and F', () => {
    expect(['ArrowRight', 'ArrowDown', 'PageDown'].map((k) => key(k))).toEqual([
      'next',
      'next',
      'next',
    ])
    expect(['ArrowLeft', 'ArrowUp', 'PageUp'].map((k) => key(k))).toEqual(['prev', 'prev', 'prev'])
    expect([key('h'), key('H'), key('r'), key('R'), key('f')]).toEqual([
      'history',
      'history',
      'reveal',
      'reveal',
      'fullscreen',
    ])
  })

  it('ignores other keys and modified keys', () => {
    expect(key('x')).toBeUndefined()
    expect(key('r', { ctrlKey: true })).toBeUndefined()
    expect(key('h', { metaKey: true })).toBeUndefined()
    expect(key('ArrowRight', { altKey: true })).toBeUndefined()
  })
})
