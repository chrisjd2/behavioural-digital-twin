import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunEvent } from './api/simulation'
import { SIMULATED_LABEL } from './labels'
import { ARM_BEAT_MS } from './byReader'
import { REVEAL_MS } from './replay'
import App from './App'
import SimulationStep from './SimulationStep'
import { runEventsFixture, statusFixture, stubApi, type Reply } from './test-fixtures'

const RUN_ID = runEventsFixture.run.run_id
const eventsUrl = `/api/run/${RUN_ID}/events`

const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms))

async function openReplay(
  reply: Reply = runEventsFixture,
  liveRuns = false,
  order: 'By arm' | 'By reader' = 'By arm',
) {
  const fetchMock = stubApi({ status: statusFixture, urls: { [eventsUrl]: reply } })
  const onLiveRunSaved = vi.fn()
  render(<SimulationStep runId={RUN_ID} liveRuns={liveRuns} onLiveRunSaved={onLiveRunSaved} />)
  await advance(0)
  const radio = screen.queryByRole('radio', { name: order })
  if (radio) fireEvent.click(radio)
  return { fetchMock, onLiveRunSaved }
}

const feed = () => screen.getByRole('list', { name: 'Reactions' })
const replayBar = () => screen.getByRole('progressbar', { name: 'Replay' })
const armBar = (arm: string) => screen.getByRole('progressbar', { name: `Arm ${arm}` })

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('Simulation replay, by arm', () => {
  it('says openly that it is a recorded run, sped up, simulated from research data', async () => {
    await openReplay()

    expect(screen.getByText(/recorded run, sped up/i)).toBeInTheDocument()
    expect(screen.getByText(/it took 15 min/i)).toBeInTheDocument()
    expect(screen.getByText(SIMULATED_LABEL)).toBeInTheDocument()
    expect(screen.queryByText('MOCK')).not.toBeInTheDocument()
  })

  it('marks mock and synthetic runs', async () => {
    await openReplay({
      ...runEventsFixture,
      run: { ...runEventsFixture.run, mock: true, data_source: 'synthetic' },
    })

    expect(screen.getByText('MOCK')).toBeInTheDocument()
    expect(screen.getByText(/synthetic sample: these readers are fake/i)).toBeInTheDocument()
  })

  it('shows an error, not an empty replay, when the events cannot load', async () => {
    await openReplay(500)

    expect(screen.getByRole('alert')).toHaveTextContent(/could not load this run’s events/i)
    expect(screen.queryByText(/no recorded events/i)).not.toBeInTheDocument()
  })

  it('says so when a run has no events', async () => {
    await openReplay({ ...runEventsFixture, events: [] })

    expect(screen.getByText(/no recorded events to replay/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('plays a reaction card, then reveals the real click', async () => {
    await openReplay()
    await advance(600)

    const card = within(feed()).getByRole('listitem')
    expect(card).toHaveClass('arm-a') // the arm's colour
    expect(within(card).getByText('Plain LLM')).toBeInTheDocument()
    expect(within(card).getByText('How to get a six-pack in 30 days')).toBeInTheDocument()
    expect(within(card).getByText(/A U1: I would definitely read this/)).toBeInTheDocument()
    expect(within(card).getByText('70%')).toBeInTheDocument()
    expect(within(card).getByText('Did the real reader click?')).toBeInTheDocument()

    await advance(REVEAL_MS)

    expect(within(card).getByText('Real reader clicked')).toBeInTheDocument()
  })

  it('keeps playing with the network gone: events are fetched once', async () => {
    const { fetchMock } = await openReplay()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    await advance(3000)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(Number(replayBar().getAttribute('aria-valuenow'))).toBeGreaterThan(5)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('pauses and resumes', async () => {
    await openReplay()
    await advance(1000)
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    const paused = replayBar().getAttribute('aria-valuenow')

    await advance(2000)
    expect(replayBar().getAttribute('aria-valuenow')).toBe(paused)

    fireEvent.click(screen.getByRole('button', { name: 'Play' }))
    await advance(1000)
    expect(Number(replayBar().getAttribute('aria-valuenow'))).toBeGreaterThan(Number(paused))
  })

  it('plays faster at a higher speed', async () => {
    await openReplay()
    fireEvent.click(screen.getByRole('radio', { name: '4×' }))

    await advance(1000)

    expect(Number(replayBar().getAttribute('aria-valuenow'))).toBe(16) // 4 events/s × 4
  })

  it('skips to the next arm', async () => {
    await openReplay()
    fireEvent.click(screen.getByRole('button', { name: 'Skip to next arm' }))
    await advance(0)

    expect(armBar('A')).toHaveAttribute('aria-valuenow', '2')
    expect(armBar('B')).toHaveAttribute('aria-valuenow', '0')
    await advance(1500) // the next card is admitted one gap after the last
    expect(within(feed()).getAllByRole('listitem')[0]).toHaveTextContent('Invented persona')
  })

  it('skips to the end with every arm done', async () => {
    await openReplay()
    fireEvent.click(screen.getByRole('button', { name: 'Skip to end' }))
    await advance(0)

    for (const arm of ['A', 'B', 'random'])
      expect(armBar(arm)).toHaveAttribute('aria-valuenow', '2')
    expect(screen.getByText(/replay finished/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play' })).toBeDisabled()
  })
})

describe('Simulation replay, by reader', () => {
  const reader = (id: string) => screen.getByRole('article', { name: `Reader ${id}` })
  const armRows = () =>
    within(screen.getByRole('list', { name: "Each arm's prediction" })).getAllByRole('listitem')

  it('is the default, labelled as reordered in a seeded order', async () => {
    stubApi({ status: statusFixture, urls: { [eventsUrl]: runEventsFixture } })
    render(<SimulationStep runId={RUN_ID} liveRuns={false} onLiveRunSaved={vi.fn()} />)
    await advance(0)

    expect(screen.getByRole('radio', { name: 'By reader' })).toBeChecked()
    expect(
      screen.getByText(/recorded run, sped up and reordered by reader/i).parentElement,
    ).toHaveTextContent('(seeded order, not cherry-picked)')
    expect(screen.getByText(/seeded sampling order/i)).toBeInTheDocument()
    expect(screen.getByText(SIMULATED_LABEL)).toBeInTheDocument()
  })

  it('shows one reader’s headline through each arm in turn, then the real click', async () => {
    await openReplay(runEventsFixture, false, 'By reader')

    expect(within(reader('U1')).getByText('How to get a six-pack in 30 days')).toBeInTheDocument()
    expect(armRows()).toHaveLength(1)
    expect(armRows()[0]).toHaveClass('arm-a')
    expect(armRows()[0]).toHaveTextContent('Plain LLM')
    expect(armRows()[0]).toHaveTextContent('70%')
    expect(within(reader('U1')).getByText('Did the real reader click?')).toBeInTheDocument()

    await advance(ARM_BEAT_MS)
    expect(armRows()).toHaveLength(2)
    expect(armRows()[1]).toHaveClass('arm-b')

    await advance(ARM_BEAT_MS)
    expect(within(reader('U1')).getByText('Real reader clicked')).toBeInTheDocument()
  })

  it('moves on to the next reader, keeping the earlier ones below', async () => {
    await openReplay(runEventsFixture, false, 'By reader')

    fireEvent.click(screen.getByRole('button', { name: 'Next reader' }))
    await advance(0)

    expect(within(reader('U2')).getByText(/stocks slip/i)).toBeInTheDocument()
    const earlier = screen.getByRole('list', { name: 'Earlier readers' })
    expect(earlier).toHaveTextContent('How to get a six-pack in 30 days')
    expect(earlier).toHaveTextContent('Real reader clicked')
  })

  it('pauses, and skips to the end', async () => {
    await openReplay(runEventsFixture, false, 'By reader')
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    await advance(5000)
    expect(armRows()).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Skip to end' }))
    await advance(0)

    expect(screen.getByText('Replay finished: 2 readers compared.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play' })).toBeDisabled()
  })
})

describe('Live dev run', () => {
  it('is hidden when live runs are off (DEMO_MODE)', async () => {
    await openReplay(runEventsFixture, false)

    expect(screen.queryByRole('button', { name: /live dev run/i })).not.toBeInTheDocument()
  })

  it('streams reactions over SSE, then hands over the saved run', async () => {
    const sources: FakeEventSource[] = []
    class FakeEventSource {
      listeners = new Map<string, (m: MessageEvent<string>) => void>()
      onerror: (() => void) | null = null
      closed = false
      url: string
      constructor(url: string) {
        this.url = url
        sources.push(this)
      }
      addEventListener(name: string, listener: (m: MessageEvent<string>) => void) {
        this.listeners.set(name, listener)
      }
      close() {
        this.closed = true
      }
      emit(name: string, data: object) {
        this.listeners.get(name)?.(new MessageEvent(name, { data: JSON.stringify(data) }))
      }
    }
    vi.stubGlobal('EventSource', FakeEventSource)
    const { onLiveRunSaved, fetchMock } = await openReplay(runEventsFixture, true)
    stubApi({
      status: statusFixture,
      urls: { [eventsUrl]: runEventsFixture, '/api/run': { live_id: 'live-1' } },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Start a live dev run' }))
    await advance(0)

    expect(sources[0].url).toBe('/api/run/live-1/stream')
    const reaction = runEventsFixture.events.find((e: RunEvent) => e.kind === 'reaction')!
    act(() => sources[0].emit('run_event', reaction))
    const live = screen.getByRole('region', { name: 'Live dev run' })
    expect(within(live).getByText('Real reader clicked')).toBeInTheDocument()

    act(() => sources[0].emit('run_saved', { run_id: 'saved-run' }))
    expect(onLiveRunSaved).toHaveBeenCalledWith('saved-run')
    expect(sources[0].closed).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('shows why a live run failed', async () => {
    const fetchMock = stubApi({
      status: statusFixture,
      urls: {
        [eventsUrl]: runEventsFixture,
        '/api/run': {
          errorStatus: 403,
          body: { code: 'demo_mode', detail: 'Live runs are disabled in the demo.' },
        },
      },
    })
    render(<SimulationStep runId={RUN_ID} liveRuns onLiveRunSaved={vi.fn()} />)
    await advance(0)

    fireEvent.click(screen.getByRole('button', { name: 'Start a live dev run' }))
    await advance(0)

    expect(screen.getByRole('alert')).toHaveTextContent('Live runs are disabled in the demo.')
    expect(fetchMock).toHaveBeenCalledWith('/api/run', expect.objectContaining({ method: 'POST' }))
  })
})

describe('Simulation step in the app', () => {
  async function openStep(demoMode: boolean) {
    stubApi({
      status: { ...statusFixture, demo_mode: demoMode },
      runs: { runs: [runEventsFixture.run], problems: [] },
      urls: { [eventsUrl]: runEventsFixture },
    })
    render(<App />)
    await advance(0)
    fireEvent.click(screen.getByRole('button', { name: /simulation/i }))
    await advance(0)
  }

  it('replays the selected run, with live runs offered to developers', async () => {
    await openStep(false)

    expect(screen.getByText(/recorded run, sped up/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start a live dev run' })).toBeInTheDocument()
  })

  it('hides live runs in DEMO_MODE', async () => {
    await openStep(true)

    expect(screen.getByText(/recorded run, sped up/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /live dev run/i })).not.toBeInTheDocument()
  })
})
