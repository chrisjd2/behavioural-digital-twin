import { useState } from 'react'
import Explorer from './Explorer'
import Presenter from './Presenter'

/** Presenter deck by default (ADR-0012); the free stepper is one click away. */
export default function App() {
  const [mode, setMode] = useState<'present' | 'explore'>('present')
  const [index, setIndex] = useState(0)

  return mode === 'present' ? (
    <Presenter index={index} onIndex={setIndex} onExplore={() => setMode('explore')} />
  ) : (
    <Explorer onPresent={() => setMode('present')} />
  )
}
