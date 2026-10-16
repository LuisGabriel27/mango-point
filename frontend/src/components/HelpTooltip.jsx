import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// Portal help outside the scrolling controls so long descriptions are never clipped.
export default function HelpTooltip({ label, children }) {
  const id = useId()
  const triggerRef = useRef(null)
  const tooltipRef = useRef(null)
  const closeTimer = useRef(null)
  const pinned = useRef(false)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState(null)

  const cancelClose = () => window.clearTimeout(closeTimer.current)
  const close = () => {
    cancelClose()
    pinned.current = false
    setOpen(false)
    setPosition(null)
  }
  const show = () => {
    cancelClose()
    document.dispatchEvent(new CustomEvent('mp-control-help-open', { detail: id }))
    setOpen(true)
  }
  const leave = () => {
    cancelClose()
    closeTimer.current = window.setTimeout(() => {
      if (!pinned.current && document.activeElement !== triggerRef.current) close()
    }, 150)
  }

  useEffect(() => () => window.clearTimeout(closeTimer.current), [])

  useEffect(() => {
    if (!open) return undefined

    const place = () => {
      const trigger = triggerRef.current
      const tooltip = tooltipRef.current
      if (!trigger || !tooltip) return
      const anchor = trigger.getBoundingClientRect()
      const box = tooltip.getBoundingClientRect()
      const padding = 12
      const gap = 8
      const below = anchor.bottom + gap
      const top = below + box.height <= window.innerHeight - padding
        ? below
        : Math.max(padding, anchor.top - gap - box.height)
      setPosition({
        left: Math.max(padding, Math.min(anchor.left, window.innerWidth - box.width - padding)),
        top: Math.min(top, window.innerHeight - box.height - padding),
      })
    }
    const outside = (event) => {
      if (!triggerRef.current?.contains(event.target) && !tooltipRef.current?.contains(event.target)) close()
    }
    const escape = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        close()
      }
    }
    const scroll = (event) => {
      if (!tooltipRef.current?.contains(event.target)) close()
    }
    const otherHelp = (event) => {
      if (event.detail !== id) close()
    }
    place()
    window.addEventListener('resize', place)
    document.addEventListener('scroll', scroll, true)
    document.addEventListener('pointerdown', outside)
    // Handle help before a containing dialog or mobile workspace handles Escape.
    window.addEventListener('keydown', escape, true)
    document.addEventListener('mp-control-help-open', otherHelp)
    return () => {
      window.removeEventListener('resize', place)
      document.removeEventListener('scroll', scroll, true)
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('keydown', escape, true)
      document.removeEventListener('mp-control-help-open', otherHelp)
    }
  }, [open, children])

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="control-help-button"
        aria-label={`Help: ${label}`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={show}
        onMouseLeave={leave}
        onFocus={show}
        onBlur={close}
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
          if (pinned.current) close()
          else {
            pinned.current = true
            show()
          }
        }}
      >
        <i className="bi bi-question-circle" aria-hidden="true" />
      </button>
      {open && createPortal(
        <div
          ref={tooltipRef}
          id={id}
          role="tooltip"
          className="control-help-tooltip"
          style={{ ...position, visibility: position ? 'visible' : 'hidden' }}
          onMouseEnter={show}
          onMouseLeave={leave}
        >
          <strong className="control-help-title">{label}</strong>
          {children}
        </div>,
        document.body,
      )}
    </>
  )
}
