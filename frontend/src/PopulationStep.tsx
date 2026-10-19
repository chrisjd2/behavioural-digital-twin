import { useEffect, useRef, useState } from 'react'
import { fetchPopulation, type RunPopulation } from './api/runs'
import AgentPanel from './AgentPanel'
import PopulationGraph from './PopulationGraph'

/**
 * The step's full width (whether or not the reader panel is open) and the window height, so
 * the graph keeps one layout and fits above the fold. jsdom has no ResizeObserver: 1000 wide.
 */
function useStepSize() {
  const [box, setBox] = useState<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(1000)
  const [windowHeight, setWindowHeight] = useState(() => window.innerHeight)
  useEffect(() => {
    if (!box || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry.contentRect.width)
      if (next > 0) setWidth((w) => (Math.abs(w - next) > 24 ? next : w))
    })
    observer.observe(box)
    return () => observer.disconnect()
  }, [box])
  useEffect(() => {
    const resize = () => setWindowHeight(window.innerHeight)
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
  return { measure: setBox, width, windowHeight }
}

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; population: RunPopulation }

/**
 * Step 2: the run's readers linked to the categories they read; select one to see what each
 * arm knew. Render with `key={runId}` so a new run starts from a clean state.
 */
export default function PopulationStep({ runId }: { runId: string }) {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [selected, setSelected] = useState<string | null>(null)
  const graph = useRef<HTMLDivElement>(null)
  const { measure, width, windowHeight } = useStepSize()

  useEffect(() => {
    let current = true
    fetchPopulation(runId)
      .then((population) => current && setLoad({ state: 'ready', population }))
      .catch(
        (error: unknown) =>
          current &&
          setLoad({
            state: 'error',
            message: error instanceof Error ? error.message : 'The request failed.',
          }),
      )
    return () => {
      current = false
    }
  }, [runId])

  if (load.state === 'loading') return <p className="muted">Loading the run’s readers…</p>
  if (load.state === 'error') {
    return (
      <p role="alert" className="result-error">
        Could not load this run’s population: {load.message}
      </p>
    )
  }
  const { population } = load
  if (population.agents.length === 0) {
    return <p className="result-empty">This run has no readers to show.</p>
  }

  function close() {
    const userId = selected
    setSelected(null)
    // Return focus to the reader the panel was opened from.
    const nodes = graph.current?.querySelectorAll<SVGElement>('[data-user-id]') ?? []
    ;[...nodes].find((n) => n.dataset.userId === userId)?.focus()
  }

  return (
    <div className={selected ? 'population with-panel' : 'population'} ref={measure}>
      <div className="population-graph" ref={graph}>
        <ul className="graph-legend">
          <li>
            <span className="legend-agent" aria-hidden="true" />
            {population.agents.length} readers, coloured by the category they click most (top six;
            the rest grey)
          </li>
          <li>
            <span className="legend-category" aria-hidden="true" />
            {population.categories.length} news categories, sized by readers
          </li>
          <li>Point at a reader to see the categories they clicked</li>
        </ul>
        {population.data_source === 'synthetic' && (
          <p className="notice">Synthetic sample: these readers are fake.</p>
        )}
        <PopulationGraph
          population={population}
          selected={selected}
          onSelect={setSelected}
          width={width}
          windowHeight={windowHeight}
        />
        {!selected && <p className="muted small">Select a reader to see what each arm knew.</p>}
      </div>
      {selected && <AgentPanel key={selected} runId={runId} userId={selected} onClose={close} />}
    </div>
  )
}
