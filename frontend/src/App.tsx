import { useEffect, useState } from 'react'
import { fetchStatus, type Status } from './api/status'

type Load = { state: 'loading' } | { state: 'error' } | { state: 'ready'; status: Status }

export default function App() {
  const [load, setLoad] = useState<Load>({ state: 'loading' })

  useEffect(() => {
    fetchStatus()
      .then((status) => setLoad({ state: 'ready', status }))
      .catch(() => setLoad({ state: 'error' }))
  }, [])

  return (
    <main className="shell">
      <header className="masthead">
        <h1>Can an AI impersonate a customer?</h1>
        {load.state === 'ready' && load.status.mock && <span className="badge-mock">MOCK</span>}
      </header>

      {load.state === 'error' && (
        <p role="alert" className="error">
          Cannot reach the Twin Lab API.
        </p>
      )}
      {load.state === 'ready' && (
        <dl className="status">
          <dt>Model</dt>
          <dd>{load.status.model || 'not configured'}</dd>
          <dt>Data</dt>
          <dd>{load.status.data_source}</dd>
        </dl>
      )}
    </main>
  )
}
