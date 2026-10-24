/** Building blocks for the presenter deck's slides (ADR-0012). */
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { isTyping } from './deck'
import { commandFor } from './hookState'
import './slides.css'

export function Slide({
  kicker,
  title,
  children,
}: {
  kicker: string
  title: string
  children?: ReactNode
}) {
  const id = useId()
  return (
    <section className="slide" aria-labelledby={id}>
      <p className="slide-kicker">{kicker}</p>
      <h2 id={id}>{title}</h2>
      <div className="slide-body">{children}</div>
    </section>
  )
}

/** Items shown one at a time, by click or by the next key, before the deck moves on. */
export function Reveal({ label, items }: { label: string; items: ReactNode[] }) {
  const [count, setCount] = useState(0)
  const countRef = useRef(count)
  countRef.current = count

  useEffect(() => {
    // On document, so it runs before the deck's window listener.
    function onKey(event: KeyboardEvent) {
      if (isTyping(event.target)) return
      const command = commandFor(event)
      const shown = countRef.current
      if (command === 'next' && shown < items.length) setCount(shown + 1)
      else if (command === 'prev' && shown > 0) setCount(shown - 1)
      else return
      event.preventDefault()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [items.length])

  return (
    <div className="slide-reveal">
      <ol className="reveal-items" aria-label={label}>
        {items.slice(0, count).map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ol>
      {count < items.length && (
        <button type="button" className="reveal-next" onClick={() => setCount(count + 1)}>
          Show next
        </button>
      )}
    </div>
  )
}

const VIDEO = /\.(mp4|webm)$/i

/** A personal photo or screenshot from frontend/public/private/, never committed (ADR-0012). */
export function PrivateMedia({ name, caption }: { name: string; caption: string }) {
  const [missing, setMissing] = useState(false)
  const src = `/private/${name}`

  if (missing) {
    return (
      <figure className="media media-missing" role="img" aria-label={caption} title={src}>
        <span className="media-missing-mark" aria-hidden="true" />
        <figcaption>{caption}</figcaption>
      </figure>
    )
  }
  return VIDEO.test(name) ? (
    <video
      className="media"
      src={src}
      aria-label={caption}
      muted
      loop
      autoPlay
      playsInline
      onError={() => setMissing(true)}
    />
  ) : (
    <img className="media" src={src} alt={caption} onError={() => setMissing(true)} />
  )
}
