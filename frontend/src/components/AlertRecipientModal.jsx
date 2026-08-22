import { useCallback, useEffect, useRef, useState } from 'react'
import api, { apiErrorMessage } from '../api'

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export default function AlertRecipientModal({ onClose }) {
  const dialogRef = useRef(null)
  const emailInputRef = useRef(null)
  const previousFocusRef = useRef(null)
  const [recipients, setRecipients] = useState([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [removingId, setRemovingId] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const busy = saving || removingId !== null

  const loadRecipients = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.getAlertEmailRecipients()
      setRecipients(response.data ?? [])
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not load alert recipients.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    previousFocusRef.current = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    loadRecipients().finally(() => emailInputRef.current?.focus())

    return () => {
      document.body.style.overflow = previousOverflow
      previousFocusRef.current?.focus?.()
    }
  }, [loadRecipients])

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !busy) {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return

      const focusable = [...dialogRef.current.querySelectorAll(FOCUSABLE_SELECTOR)]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
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
  }, [busy, onClose])

  const handleSubmit = async (event) => {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    if (recipients.some((recipient) => recipient.email.toLowerCase() === normalizedEmail)) {
      setError('That email address is already receiving alerts.')
      return
    }

    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = await api.addAlertEmailRecipient({
        email: normalizedEmail,
        name: name.trim() || null,
      })
      setRecipients((current) => [
        ...current.filter((item) => item.recipient_id !== response.data.recipient_id),
        response.data,
      ])
      setName('')
      setEmail('')
      setNotice(`${response.data.email} will receive future alert emails.`)
      emailInputRef.current?.focus()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not add this recipient.'))
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (recipient) => {
    const label = recipient.name || recipient.email
    if (!window.confirm(`Stop sending future alert emails to ${label}?`)) return

    setRemovingId(recipient.recipient_id)
    setError('')
    setNotice('')
    try {
      await api.removeAlertEmailRecipient(recipient.recipient_id)
      setRecipients((current) => current.filter(
        (item) => item.recipient_id !== recipient.recipient_id,
      ))
      setNotice(`${recipient.email} was removed from alert recipients.`)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not remove this recipient.'))
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <div
      className="orchard-modal-backdrop alert-recipient-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose()
      }}
    >
      <div
        ref={dialogRef}
        className="orchard-modal-dialog alert-recipient-modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="alert-recipient-modal-title"
        aria-describedby="alert-recipient-modal-description"
      >
        <div className="orchard-modal-header alert-recipient-modal-header">
          <div>
            <div className="orchard-modal-eyebrow">Notification delivery</div>
            <h2 id="alert-recipient-modal-title" className="orchard-modal-title">
              Alert email recipients
            </h2>
          </div>
          <button
            type="button"
            className="btn-close"
            aria-label="Close alert email recipients dialog"
            onClick={onClose}
            disabled={busy}
          />
        </div>

        <div className="alert-recipient-modal-body">
          <p id="alert-recipient-modal-description" className="alert-recipient-intro">
            Assign farmers or other significant people who should receive every new
            MangoPoint risk alert, even when they are away from the dashboard.
          </p>

          <form className="alert-recipient-form" onSubmit={handleSubmit}>
            <div className="alert-recipient-fields">
              <div>
                <label htmlFor="alert-recipient-name">Name <span>(optional)</span></label>
                <input
                  id="alert-recipient-name"
                  className="form-control form-control-sm"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  placeholder="e.g. Juan Dela Cruz"
                  disabled={saving}
                />
              </div>
              <div>
                <label htmlFor="alert-recipient-email">Email address</label>
                <input
                  ref={emailInputRef}
                  id="alert-recipient-email"
                  type="email"
                  className="form-control form-control-sm"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  maxLength={254}
                  autoComplete="email"
                  placeholder="farmer@example.com"
                  disabled={saving}
                  required
                />
              </div>
            </div>
            <button type="submit" className="btn btn-success btn-sm" disabled={saving}>
              {saving
                ? <><span className="spinner-border spinner-border-sm me-1" />Adding</>
                : <><i className="bi bi-person-plus-fill me-1" />Add recipient</>}
            </button>
          </form>

          <div className="alert-recipient-feedback" aria-live="polite">
            {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}
            {!error && notice && <div className="alert alert-success py-2 mb-0">{notice}</div>}
          </div>

          <div className="alert-recipient-list-heading">
            <span>Currently receiving alerts</span>
            <span>{recipients.length}</span>
          </div>

          <div className="alert-recipient-list">
            {loading && (
              <div className="alert-recipient-empty">
                <span className="spinner-border spinner-border-sm me-2" />Loading recipients…
              </div>
            )}
            {!loading && recipients.length === 0 && (
              <div className="alert-recipient-empty">
                <i className="bi bi-envelope-plus" />
                <span>No recipients assigned yet.</span>
              </div>
            )}
            {!loading && recipients.map((recipient) => (
              <div className="alert-recipient-row" key={recipient.recipient_id}>
                <span className="alert-recipient-avatar" aria-hidden="true">
                  {(recipient.name || recipient.email).slice(0, 1).toUpperCase()}
                </span>
                <span className="alert-recipient-details">
                  {recipient.name && <strong>{recipient.name}</strong>}
                  <span>{recipient.email}</span>
                </span>
                <button
                  type="button"
                  className="alert-recipient-remove"
                  onClick={() => handleRemove(recipient)}
                  disabled={removingId === recipient.recipient_id}
                  aria-label={`Remove ${recipient.name || recipient.email}`}
                  title="Stop email alerts"
                >
                  {removingId === recipient.recipient_id
                    ? <span className="spinner-border spinner-border-sm" />
                    : <i className="bi bi-trash3" />}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
