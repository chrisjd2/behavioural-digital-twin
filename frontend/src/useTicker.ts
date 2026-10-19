import { useEffect, useRef } from 'react'

const FRAME_MS = 50

/** Calls `onTick(elapsed ms)` about 20 times a second while `running`. */
export function useTicker(running: boolean, onTick: (dtMs: number) => void) {
  const latest = useRef(onTick)
  useEffect(() => {
    latest.current = onTick
  })
  useEffect(() => {
    if (!running) return
    let last = Date.now()
    const timer = setInterval(() => {
      const now = Date.now()
      latest.current(now - last)
      last = now
    }, FRAME_MS)
    return () => clearInterval(timer)
  }, [running])
}
