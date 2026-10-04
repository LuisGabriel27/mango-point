import { useEffect, useRef, useState } from 'react'

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  '[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export default function ZoneClearConfirmationModal({
  clearType = 'all',
  zoneCount,
  persistentCount = 0,
  scenarioCount = 0,
  onConfirm,
  onClose,
}) {
  const copy = {
    all: { title: 'Clear all zones?', action: 'Clear all zones', noun: 'zone' },
    stage: { title: 'Clear stage zones?', action: 'Clear stage zones', noun: 'stage zone' },
    status: { title: 'Clear status zones?', action: 'Clear status zones', noun: 'status zone' },
    management: { title: 'Clear management zones?', action: 'Clear management zones', noun: 'management zone' },
    cecid: { title: 'Clear weed habitats?', action: 'Clear weed habitats', noun: 'weed habitat' },
  }[clearType] || { title: 'Clear zones?', action: 'Clear zones', noun: 'zone' }
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)
  const previousFocusRef = useRef(null)
  const [clearing, setClearing] = useState(false)

  useEffect(() => {
    previousFocusRef.current = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    cancelRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      previousFocusRef.current?.focus?.()
    }
  }, [])

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !clearing) {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return
      const focusable = [...dialogRef.current.querySelectorAll(FOCUSABLE_SELECTOR)]
        .filter((element) => element.offsetParent !== null)
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable.at(-1)
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [clearing, onClose])

  const handleConfirm = async () => {
    setClearing(true)
    try {
      await onConfirm?.()
      onClose()
    } finally {
      setClearing(false)
    }
  }

  return (
    <div
      className="orchard-modal-backdrop zone-clear-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !clearing) onClose()
      }}
    >
      <section
        ref={dialogRef}
        className="orchard-modal-dialog zone-clear-modal-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="zone-clear-modal-title"
        aria-describedby="zone-clear-modal-description"
        tabIndex={-1}
      >
        <header className="orchard-modal-header zone-clear-modal-header">
          <div>
            <div className="orchard-modal-eyebrow">Zone management</div>
          <h2 id="zone-clear-modal-title" className="orchard-modal-title">{copy.title}</h2>
          </div>
          <button type="button" className="btn-close" aria-label="Close confirmation" onClick={onClose} disabled={clearing} />
        </header>

        <div className="zone-clear-modal-body">
          <div className="zone-clear-modal-warning" aria-hidden="true">
            <i className="bi bi-exclamation-triangle" />
          </div>
          <div>
            <p id="zone-clear-modal-description" className="zone-clear-modal-message">
              {zoneCount > 0
                ? <>This will remove <strong>{zoneCount} {copy.noun}{zoneCount === 1 ? '' : 's'}</strong> from the current orchard map.</>
                : <>No visible {copy.noun}s are listed, but this will still clear matching saved data from the orchard.</>}
            </p>
            <div className="zone-clear-modal-breakdown">
              {persistentCount > 0 && (
                <span><i className="bi bi-cloud-check" /><strong>{persistentCount}</strong> saved to orchard</span>
              )}
              {scenarioCount > 0 && (
                <span><i className="bi bi-hourglass-split" /><strong>{scenarioCount}</strong> scenario only</span>
              )}
            </div>
            {persistentCount > 0 && (
              <p className="zone-clear-modal-note">Saved orchard data will also be removed from future sessions.</p>
            )}
          </div>
        </div>

        <footer className="zone-clear-modal-actions">
          <button ref={cancelRef} type="button" className="btn btn-light" onClick={onClose} disabled={clearing}>Cancel</button>
          <button type="button" className="btn btn-danger" onClick={handleConfirm} disabled={clearing}>
            {clearing ? <><span className="spinner-border spinner-border-sm me-2" />Clearing</> : <><i className="bi bi-trash3 me-2" />{copy.action}</>}
          </button>
        </footer>
      </section>
    </div>
  )
}
