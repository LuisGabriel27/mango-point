import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

export default function LogoutConfirmationModal({ onConfirm, onClose }) {
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)

  useEffect(() => {
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    cancelRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      if (previousFocus?.isConnected) previousFocus.focus()
    }
  }, [])

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return
      const buttons = dialogRef.current.querySelectorAll('button:not([disabled])')
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [onClose])

  return createPortal(
    <div
      className="orchard-modal-backdrop logout-confirmation-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          event.preventDefault()
          onClose()
        }
      }}
    >
      <section
        ref={dialogRef}
        className="orchard-modal-dialog logout-confirmation-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="logout-confirmation-title"
        aria-describedby="logout-confirmation-description"
      >
        <header className="orchard-modal-header">
          <h2 id="logout-confirmation-title" className="orchard-modal-title">Log out of MangoPoint?</h2>
          <button type="button" className="btn-close" aria-label="Close logout confirmation" onClick={onClose} />
        </header>
        <div className="logout-confirmation-body">
          <i className="bi bi-box-arrow-right" aria-hidden="true" />
          <p id="logout-confirmation-description">You’ll need to sign in again to continue.</p>
        </div>
        <footer className="logout-confirmation-actions">
          <button ref={cancelRef} type="button" className="btn btn-light" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-success" onClick={onConfirm}>Log out</button>
        </footer>
      </section>
    </div>,
    document.body,
  )
}
