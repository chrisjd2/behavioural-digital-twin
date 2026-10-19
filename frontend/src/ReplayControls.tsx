type TransportProps = {
  running: boolean
  finished: boolean
  onToggle: () => void
  nextLabel: string
  onNext: () => void
  onEnd: () => void
}

export function Transport({
  running,
  finished,
  onToggle,
  nextLabel,
  onNext,
  onEnd,
}: TransportProps) {
  return (
    <div className="transport">
      <button type="button" className="primary" disabled={finished} onClick={onToggle}>
        {running ? 'Pause' : 'Play'}
      </button>
      <button type="button" className="secondary" disabled={finished} onClick={onNext}>
        {nextLabel}
      </button>
      <button type="button" className="secondary" disabled={finished} onClick={onEnd}>
        Skip to end
      </button>
    </div>
  )
}

type ChoiceProps<T> = {
  legend: string
  name: string
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}

/** A row of pill radio buttons (speed, order). */
export function Choice<T extends string | number>({
  legend,
  name,
  options,
  value,
  onChange,
}: ChoiceProps<T>) {
  return (
    <fieldset className="speeds">
      <legend className="field-label">{legend}</legend>
      {options.map((o) => (
        <label key={o.value} className={o.value === value ? 'speed speed-on' : 'speed'}>
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={o.value === value}
            onChange={() => onChange(o.value)}
          />
          {o.label}
        </label>
      ))}
    </fieldset>
  )
}

export function Timeline({ value, max, label }: { value: number; max: number; label: string }) {
  return (
    <div className="timeline">
      <span
        className="timeline-bar"
        role="progressbar"
        aria-label="Replay"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.floor(value)}
      >
        <span style={{ width: `${max ? (100 * value) / max : 100}%` }} />
      </span>
      <p className="small muted">{label}</p>
    </div>
  )
}
