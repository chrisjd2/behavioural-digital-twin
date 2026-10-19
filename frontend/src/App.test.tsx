import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Status } from './api/status'

function mockStatus(status: Status) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(status), { status: 200 })),
  )
}

const base: Status = {
  mock: false,
  demo_mode: false,
  model: 'gemini-test-001',
  data_source: 'none',
  call_count: 0,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('poses the question and shows the model from /api/status', async () => {
    mockStatus(base)
    render(<App />)

    expect(
      screen.getByRole('heading', { name: /can an ai impersonate a customer/i }),
    ).toBeInTheDocument()
    expect(await screen.findByText('gemini-test-001')).toBeInTheDocument()
    expect(screen.queryByText('MOCK')).not.toBeInTheDocument()
  })

  it('shows a MOCK badge in mock mode', async () => {
    mockStatus({ ...base, mock: true })
    render(<App />)

    expect(await screen.findByText('MOCK')).toBeInTheDocument()
  })

  it('shows an error rather than an empty state when the API is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 500 })),
    )
    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot reach the twin lab api/i)
  })
})
