import { useState, useEffect, useRef, useId } from 'react'

/**
 * Custom styled select that replaces the native OS dropdown.
 * Accepts the same `value`, `onChange`, and `options` shape as a <select>.
 * options: [{ value, label }]
 */
export default function MpSelect({ value, onChange, options = [], className = '', small = false, disabled = false,
  id, ariaLabel, ariaDescribedBy }) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const ref = useRef(null)
  const menuRef = useRef(null)
  const menuId = useId()
  const active = Math.max(0, Math.min(activeIndex, options.length - 1))

  const selected = options.find((o) => o.value === value) ?? options[0]

  useEffect(() => {
    if (!open) return
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  useEffect(() => {
    if (!open) return
    const menu = menuRef.current
    const option = menu?.children[active]
    if (!option) return
    if (option.offsetTop < menu.scrollTop) menu.scrollTop = option.offsetTop
    else if (option.offsetTop + option.offsetHeight > menu.scrollTop + menu.clientHeight) {
      menu.scrollTop = option.offsetTop + option.offsetHeight - menu.clientHeight
    }
  }, [open, active])

  useEffect(() => { if (disabled) setOpen(false) }, [disabled])

  const openMenu = () => {
    setActiveIndex(Math.max(0, options.findIndex((option) => option.value === value)))
    setOpen(true)
  }

  const handleSelect = (val) => {
    if (disabled) return
    setOpen(false)
    onChange(val)
  }

  const handleKeyDown = (event) => {
    if (disabled) return
    const key = event.key
    if (key === 'Tab') { setOpen(false); return }
    if (key === 'Escape') {
      if (open) { event.preventDefault(); event.stopPropagation(); setOpen(false) }
      return
    }
    if (!options.length) return
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(key)) {
      event.preventDefault()
      if (!open) {
        openMenu()
        if (key === 'Home') setActiveIndex(0)
        if (key === 'End') setActiveIndex(options.length - 1)
      } else if (key === 'Enter' || key === ' ') handleSelect(options[active].value)
      else if (key === 'Home') setActiveIndex(0)
      else if (key === 'End') setActiveIndex(options.length - 1)
      else setActiveIndex(Math.max(0, Math.min(options.length - 1, active + (key === 'ArrowDown' ? 1 : -1))))
    } else if (open && key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
      const match = options.findIndex((_, offset) => String(options[(active + offset + 1) % options.length]
        .label).toLocaleLowerCase().startsWith(key.toLocaleLowerCase()))
      if (match >= 0) { event.preventDefault(); setActiveIndex((active + match + 1) % options.length) }
    }
  }

  return (
    <div ref={ref} className={`mp-select-wrap${small ? ' mp-select-wrap-sm' : ''} ${className}`}>
      <button
        type="button"
        id={id}
        role="combobox"
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-activedescendant={open && options.length ? `${menuId}-${active}` : undefined}
        className={`mp-select-trigger${open ? ' open' : ''}`}
        onClick={() => { if (!disabled) { if (open) setOpen(false); else openMenu() } }}
        onKeyDown={handleKeyDown}
        disabled={disabled}
      >
        <span className="mp-select-value">{selected?.label ?? '—'}</span>
        <i className={`bi bi-chevron-${open ? 'up' : 'down'} mp-select-arrow`} aria-hidden="true" />
      </button>
      {open && (
        <ul ref={menuRef} id={menuId} className="mp-select-dropdown" role="listbox" aria-label={ariaLabel}>
          {options.map((o, index) => (
            <li
              key={o.value}
              id={`${menuId}-${index}`}
              role="option"
              aria-selected={o.value === value}
              className={`mp-select-option${o.value === value ? ' selected' : ''}${index === active ? ' active' : ''}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={(event) => {
                // Selectors are often rendered inside a <label>. Prevent the
                // label's default activation from clicking the trigger again
                // after this option closes the menu.
                event.preventDefault()
                event.stopPropagation()
                handleSelect(o.value)
              }}
            >
              {o.value === value && <i className="bi bi-check2 mp-select-check" aria-hidden="true" />}
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
