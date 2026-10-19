import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

export default function ConfirmationModal({ title, children, confirmLabel, onConfirm, onClose,
  busy = false, error = '', danger = false, className = '', closeLabel = 'Close confirmation' }) {
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)
  useEffect(() => {
    const previousFocus = document.activeElement
    const overflow = document.body.style.overflow
    const backdrop = dialogRef.current?.closest('.confirmation-modal-backdrop')
    const background = [...document.body.children].filter((element) => element !== backdrop)
      .map((element) => [element, element.inert])
    background.forEach(([element]) => { element.inert = true })
    document.body.style.overflow = 'hidden'
    cancelRef.current?.focus()
    return () => {
      document.body.style.overflow = overflow
      background.forEach(([element, inert]) => { element.inert = inert })
      if (previousFocus?.isConnected) previousFocus.focus()
    }
  }, [])
  useEffect(() => {
    const keydown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        if (!busy) onClose()
      }
      if (event.key !== 'Tab') return
      const buttons = dialogRef.current?.querySelectorAll('button:not([disabled])')
      if (!buttons?.length) return
      const first = buttons[0], last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', keydown, true)
    return () => window.removeEventListener('keydown', keydown, true)
  }, [busy, onClose])
  return createPortal(
    <div className={`orchard-modal-backdrop confirmation-modal-backdrop ${className}`} onMouseDown={(event) => {
      event.stopPropagation()
      if (event.target === event.currentTarget) event.preventDefault()
    }} onClick={(event) => {
      event.stopPropagation()
      // Finish the pointer gesture before restoring focus to the underlying dialog.
      if (event.target === event.currentTarget && !busy) onClose()
    }}>
      <section ref={dialogRef} className="orchard-modal-dialog logout-confirmation-dialog" role="alertdialog"
        aria-modal="true" aria-labelledby="confirmation-title" aria-describedby="confirmation-description" aria-busy={busy}>
        <header className="orchard-modal-header">
          <h2 id="confirmation-title" className="orchard-modal-title">{title}</h2>
          <button type="button" className="btn-close" aria-label={closeLabel} onClick={onClose} disabled={busy} />
        </header>
        <div className="logout-confirmation-body">
          <i className={`bi bi-${danger ? 'trash3' : 'box-arrow-right'}`} aria-hidden="true" />
          <div id="confirmation-description">{children}</div>
        </div>
        {error && <div className="alert alert-danger mx-3 py-2" role="alert">{error}</div>}
        <footer className="logout-confirmation-actions">
          <button ref={cancelRef} type="button" className="btn btn-light" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className={`btn btn-${danger ? 'danger' : 'success'}`} onClick={onConfirm} disabled={busy}>
            {busy && <span className="spinner-border spinner-border-sm me-1" />}{confirmLabel}
          </button>
        </footer>
      </section>
    </div>, document.body,
  )
}
