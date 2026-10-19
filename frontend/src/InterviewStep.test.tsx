import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { InterviewReply, InterviewRequest, RecordedInterview } from './api/interview'
import InterviewStep from './InterviewStep'
import { IDENTITY_STARTER, SIMULATED_LABEL, STARTERS } from './labels'
import { runFixture, runPopulationFixture } from './test-fixtures'

const RUN = runFixture.run_id
const POPULATION = `/api/run/${RUN}/population`
const REPORT = `/api/run/${RUN}/report`

const reply = (text: string, mock = false, more: Partial<InterviewReply> = {}): InterviewReply => ({
  session_id: 'S1',
  run_id: RUN,
  user_id: 'U2',
  arm: 'D',
  model: 'gemini-test-001',
  text,
  mock,
  cited: [
    { news_id: 'N7', category: 'sports', subcategory: 'nfl', title: 'Packers win in overtime' },
  ],
  identity_hits: [],
  ...more,
})

const recorded: RecordedInterview = {
  run_id: RUN,
  user_id: 'U1',
  arm: 'C',
  model: 'gemini-test-001',
  mock: false,
  exchanges: [
    {
      question: 'What do you read?',
      answer: 'Health stories, mostly [N1].',
      cited: [],
      identity_hits: [],
    },
    {
      question: 'How old are you?',
      answer: "I don't know, it's not in my data.",
      cited: [],
      identity_hits: [],
    },
  ],
}

type Answer = { status: number; body: unknown }
const ok = (body: unknown): Answer => ({ status: 200, body })
const fail = (status: number, detail: string, code = 'x'): Answer => ({
  status,
  body: { code, detail },
})

/** Each URL answers from its queue in turn (the last answer repeats); POSTs are recorded. */
function stub(routes: Record<string, Answer[]>) {
  const sent: InterviewRequest[] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const queue = routes[url]
    if (!queue) throw new Error(`unexpected fetch ${url}`)
    const answer = queue.length > 1 ? queue.shift()! : queue[0]
    if (init?.method === 'POST') sent.push(JSON.parse(String(init.body)) as InterviewRequest)
    return new Response(JSON.stringify(answer.body), { status: answer.status })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { sent, fetchMock }
}

const readersReady = {
  [POPULATION]: [ok(runPopulationFixture)],
  [REPORT]: [ok({ primary: { median_user: 'U2' } })],
}

function renderStep(mockLlm = false, run = runFixture) {
  const user = userEvent.setup()
  render(<InterviewStep run={run} mockLlm={mockLlm} />)
  return user
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InterviewStep: choosing who to interview', () => {
  it('shows loading, then defaults to the median reader and arm D', async () => {
    stub(readersReady)
    renderStep()

    expect(screen.getByText(/loading the run’s readers/i)).toBeInTheDocument()
    const reader = await screen.findByRole('combobox', { name: /reader/i })
    expect(reader).toHaveValue('U2')
    expect(within(reader).getByRole('option', { name: 'U2 (median reader)' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /twin \+ profile \+ memory/i })).toBeChecked()
    expect(screen.getAllByRole('radio')).toHaveLength(5)
    expect(screen.getByText(/control/)).toBeInTheDocument()
  })

  it('falls back to the first reader when the run has no median', async () => {
    stub({ ...readersReady, [REPORT]: [ok({ primary: null })] })
    renderStep()

    expect(await screen.findByRole('combobox', { name: /reader/i })).toHaveValue('U1')
    expect(screen.queryByText(/median reader unknown/i)).not.toBeInTheDocument()
  })

  it('says when the report could not give the median reader', async () => {
    stub({ ...readersReady, [REPORT]: [fail(500, 'Report broke')] })
    renderStep()

    expect(await screen.findByRole('combobox', { name: /reader/i })).toHaveValue('U1')
    expect(screen.getByText('Median reader unknown: Report broke')).toBeInTheDocument()
  })

  it('a failed reader list is an error, not an empty one', async () => {
    stub({ [POPULATION]: [fail(500, 'Run file unreadable')], [REPORT]: [ok({})] })
    renderStep()

    expect(await screen.findByRole('alert')).toHaveTextContent('Run file unreadable')
  })

  it('a run with no readers says so', async () => {
    stub({ ...readersReady, [POPULATION]: [ok({ ...runPopulationFixture, agents: [] })] })
    renderStep()

    expect(await screen.findByText(/no readers to interview/i)).toBeInTheDocument()
  })

  it('a run with no LLM arms has no agent to ask', () => {
    stub(readersReady)
    renderStep(false, { ...runFixture, arms: ['random'] })

    expect(screen.getByText(/no agent to ask/i)).toBeInTheDocument()
  })

  it('always shows the simulated-data label, and the MOCK note on a mock server', async () => {
    stub(readersReady)
    renderStep(true)

    expect(await screen.findByText(SIMULATED_LABEL)).toBeInTheDocument()
    expect(screen.getByText('Interview replies use the MOCK LLM')).toBeInTheDocument()
  })

  it('says arm B is invented', async () => {
    stub(readersReady)
    const user = renderStep()

    await user.click(await screen.findByRole('radio', { name: /invented persona/i }))

    expect(screen.getByText(/an invented character/i)).toBeInTheDocument()
  })
})

describe('InterviewStep: the conversation', () => {
  it('sends the question with the chosen reader and arm, then shows the cited reply', async () => {
    const { sent } = stub({
      ...readersReady,
      '/api/interview': [ok(reply('I read sports, like [N7].'))],
    })
    const user = renderStep()

    await user.type(await screen.findByRole('textbox', { name: /your question/i }), 'Hi there')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByText('I read sports, like [N7].')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: /past clicks cited/i })).toHaveTextContent(
      'Packers win in overtime',
    )
    expect(sent[0]).toEqual({
      run_id: RUN,
      user_id: 'U2',
      arm: 'D',
      session_id: null,
      question: 'Hi there',
    })
    expect(screen.queryByText('recorded')).not.toBeInTheDocument()
  })

  it('continues the conversation by its session id, sending only the new question', async () => {
    const { sent } = stub({ ...readersReady, '/api/interview': [ok(reply('First answer'))] })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))
    await screen.findByText('First answer')
    await user.click(screen.getByRole('button', { name: /how old are you/i }))

    await waitFor(() => expect(sent).toHaveLength(2))
    expect(sent[1]).toMatchObject({ session_id: 'S1', question: IDENTITY_STARTER })
  })

  it('flags a reply the identity screen fired on', async () => {
    const hits = [{ kind: 'age', term: 'Is 45 years old', text: 'Is 45 years old' }]
    stub({
      ...readersReady,
      '/api/interview': [ok(reply('I am 45 years old.', false, { identity_hits: hits }))],
    })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))

    expect(await screen.findByText('identity screen: age')).toBeInTheDocument()
  })

  it('an ended conversation offers a new one instead of the fallback', async () => {
    const { sent } = stub({
      ...readersReady,
      '/api/interview': [
        fail(422, 'This conversation is full. Start a new one.', 'conversation_too_long'),
        ok(reply('Fresh start')),
      ],
    })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))
    expect(
      await screen.findByText('This conversation is full. Start a new one.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/showing recorded exchanges/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /start a new conversation/i }))
    await user.click(screen.getByRole('button', { name: STARTERS[1] }))

    expect(await screen.findByText('Fresh start')).toBeInTheDocument()
    expect(sent[1].session_id).toBeNull()
  })

  it('labels mock replies MOCK', async () => {
    stub({ ...readersReady, '/api/interview': [ok(reply('MOCK reply abc.', true))] })
    const user = renderStep(true)

    await user.click(await screen.findByRole('button', { name: /how old are you/i }))

    expect(await screen.findByText('MOCK reply abc.')).toBeInTheDocument()
    expect(screen.getByText('MOCK')).toBeInTheDocument()
  })

  it('offers an identity question that demonstrates the guardrail', async () => {
    stub(readersReady)
    renderStep()

    const identity = await screen.findByRole('button', { name: /how old are you/i })
    expect(identity).toHaveTextContent(/tests the guardrail/i)
  })

  it('a new reader starts a new conversation', async () => {
    stub({ ...readersReady, '/api/interview': [ok(reply('About sport'))] })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))
    await screen.findByText('About sport')
    await user.selectOptions(screen.getByRole('combobox', { name: /reader/i }), 'U1')

    expect(screen.queryByText('About sport')).not.toBeInTheDocument()
  })
})

describe('InterviewStep: recorded fallback', () => {
  it('on a rate limit (429), shows the recorded exchanges labelled recorded', async () => {
    stub({
      ...readersReady,
      '/api/interview': [
        fail(429, 'Interview limit reached: 30 messages an hour from one address.'),
      ],
      '/api/interview/recorded': [ok(recorded)],
    })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))

    expect(await screen.findByText(/interview limit reached/i)).toBeInTheDocument()
    expect(await screen.findByText('Health stories, mostly [N1].')).toBeInTheDocument()
    expect(screen.getAllByText('recorded')).toHaveLength(2)
    expect(
      screen.getByText(new RegExp(`reader U1, arm C \\(Twin \\+ memory\\) of run ${RUN}`)),
    ).toBeInTheDocument()
    expect(screen.getByText(SIMULATED_LABEL)).toBeInTheDocument()
  })

  it('on a failed live call, shows the recorded exchanges', async () => {
    stub({
      ...readersReady,
      '/api/interview': [fail(502, 'The live interview is unavailable right now.')],
      '/api/interview/recorded': [ok({ ...recorded, mock: true })],
    })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))

    expect(
      await screen.findByText(/the live interview is unavailable right now/i),
    ).toBeInTheDocument()
    expect(await screen.findAllByText('recorded')).toHaveLength(2)
    expect(screen.getAllByText('MOCK')).toHaveLength(2)
  })

  it('a missing recording is an error, not a blank', async () => {
    stub({
      ...readersReady,
      '/api/interview': [fail(429, 'Interview limit reached.')],
      '/api/interview/recorded': [fail(404, 'No recorded interview.')],
    })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not be loaded either: no recorded interview/i,
    )
  })

  it('fetches the recording once, however many calls fail', async () => {
    const { fetchMock } = stub({
      ...readersReady,
      '/api/interview': [fail(429, 'Interview limit reached.')],
      '/api/interview/recorded': [ok(recorded)],
    })
    const user = renderStep()

    await user.click(await screen.findByRole('button', { name: STARTERS[0] }))
    await screen.findByText('Health stories, mostly [N1].')
    await user.click(screen.getByRole('button', { name: STARTERS[1] }))
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([url]) => url === '/api/interview')).toHaveLength(2),
    )

    const recordedCalls = fetchMock.mock.calls.filter(([url]) => url === '/api/interview/recorded')
    expect(recordedCalls).toHaveLength(1)
  })
})
