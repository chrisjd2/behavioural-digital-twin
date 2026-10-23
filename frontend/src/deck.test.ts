import { describe, expect, it } from 'vitest'
import { deckCommand, move, SCREENS, SECTIONS } from './deck'

function keydown(key: string, init: KeyboardEventInit = {}, target?: Element) {
  const event = new KeyboardEvent('keydown', { key, cancelable: true, ...init })
  if (target) Object.defineProperty(event, 'target', { value: target })
  return event
}

describe('running order (ADR-0012)', () => {
  it('has 17 screens, the existing steps at 11-14', () => {
    expect(SCREENS).toHaveLength(17)
    expect(SCREENS.slice(10, 14).map((s) => s.id)).toEqual([
      'population',
      'hook',
      'simulation',
      'report',
    ])
  })

  it('runs through the four sections in order', () => {
    expect(SECTIONS).toEqual(['About me', 'Learn', 'Tinker', 'Teach'])
    const counts = SECTIONS.map((section) => SCREENS.filter((s) => s.section === section).length)
    expect(counts).toEqual([5, 4, 2, 6])
    const order = SCREENS.map((s) => SECTIONS.indexOf(s.section))
    expect(order).toEqual([...order].sort((a, b) => a - b))
  })
})

describe('move', () => {
  it('steps forward and back, and stops at both ends', () => {
    expect(move(0, 'next', 17)).toBe(1)
    expect(move(5, 'prev', 17)).toBe(4)
    expect(move(0, 'prev', 17)).toBe(0)
    expect(move(16, 'next', 17)).toBe(16)
  })
})

describe('deckCommand', () => {
  it('maps arrows and clicker keys', () => {
    expect(['ArrowRight', 'PageDown'].map((k) => deckCommand(keydown(k)))).toEqual(['next', 'next'])
    expect(['ArrowLeft', 'PageUp'].map((k) => deckCommand(keydown(k)))).toEqual(['prev', 'prev'])
  })

  it('ignores other keys and modified keys', () => {
    expect(deckCommand(keydown('h'))).toBeUndefined()
    expect(deckCommand(keydown('ArrowRight', { altKey: true }))).toBeUndefined()
  })

  it('ignores a key the screen already used', () => {
    const event = keydown('ArrowRight')
    event.preventDefault()
    expect(deckCommand(event)).toBeUndefined()
  })

  it('ignores keys while typing', () => {
    for (const tag of ['input', 'textarea', 'select']) {
      expect(deckCommand(keydown('ArrowRight', {}, document.createElement(tag)))).toBeUndefined()
    }
  })
})
