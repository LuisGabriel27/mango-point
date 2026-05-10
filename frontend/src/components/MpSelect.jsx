import { useState, useEffect, useRef } from 'react'

/**
 * Custom styled select that replaces the native OS dropdown.
 * Accepts the same `value`, `onChange`, and `options` shape as a <select>.
 * options: [{ value, label }]
 */
export default function MpSelect({ value, onChange, options = [], className = '', small = false }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const selected = options.find((o) => o.value === value) ?? options[0]

  useEffect(() => {
    if (!open) return
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const handleSelect = (val) => {
    onChange(val)
    setOpen(false)
  }

  return (
    <div ref={ref} className={`mp-select-wrap${small ? ' mp-select-wrap-sm' : ''} ${className}`}>
      <button
        type="button"
        className={`mp-select-trigger${open ? ' open' : ''}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="mp-select-value">{selected?.label ?? '—'}</span>
        <i className={`bi bi-chevron-${open ? 'up' : 'down'} mp-select-arrow`} />
      </button>
      {open && (
        <ul className="mp-select-dropdown">
          {options.map((o) => (
            <li
              key={o.value}
              className={`mp-select-option${o.value === value ? ' selected' : ''}`}
              onClick={() => handleSelect(o.value)}
            >
              {o.value === value && <i className="bi bi-check2 mp-select-check" />}
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
