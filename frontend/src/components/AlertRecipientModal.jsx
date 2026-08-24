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
  const nameInputRef = useRef(null)
  const emailInputRef = useRef(null)
  const previousFocusRef = useRef(null)
  const [recipients, setRecipients] = useState([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [updatingId, setUpdatingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const busy = saving || updatingId !== null || deletingId !== null
  const activeCount = recipients.filter((recipient) => recipient.is_active).length
  const pausedCount = recipients.length - activeCount

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
    if (recipients.some((recipient) => (
      recipient.recipient_id !== editingId
      && recipient.email.toLowerCase() === normalizedEmail
    ))) {
      setError('That email address is already assigned to another recipient.')
      return
    }

    setSaving(true)
    setError('')
    setNotice('')
    try {
      const payload = {
        email: normalizedEmail,
        name: name.trim() || null,
      }
      const response = editingId === null
        ? await api.addAlertEmailRecipient(payload)
        : await api.updateAlertEmailRecipient(editingId, payload)
      setRecipients((current) => editingId === null
        ? [
            ...current.filter((item) => item.recipient_id !== response.data.recipient_id),
            response.data,
          ]
        : current.map((item) => (
            item.recipient_id === response.data.recipient_id ? response.data : item
          )))
      const wasEditing = editingId !== null
      setEditingId(null)
      setName('')
      setEmail('')
      setNotice(wasEditing
        ? `${response.data.email} was updated.`
        : `${response.data.email} will receive future alert emails.`)
      emailInputRef.current?.focus()
    } catch (requestError) {
      setError(apiErrorMessage(
        requestError,
        editingId === null
          ? 'Could not add this recipient.'
          : 'Could not update this recipient.',
      ))
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = (recipient) => {
    setEditingId(recipient.recipient_id)
    setName(recipient.name || '')
    setEmail(recipient.email)
    setError('')
    setNotice('')
    requestAnimationFrame(() => nameInputRef.current?.focus())
  }

  const handleCancelEdit = () => {
    setEditingId(null)
    setName('')
    setEmail('')
    setError('')
    setNotice('')
    emailInputRef.current?.focus()
  }

  const handleToggleActive = async (recipient) => {
    const nextActive = !recipient.is_active
    setUpdatingId(recipient.recipient_id)
    setError('')
    setNotice('')
    try {
      const response = await api.updateAlertEmailRecipient(recipient.recipient_id, {
        is_active: nextActive,
      })
      setRecipients((current) => current.map((item) => (
        item.recipient_id === recipient.recipient_id ? response.data : item
      )))
      setNotice(nextActive
        ? `${recipient.email} will receive future alert emails again.`
        : `${recipient.email} is paused and will not receive new alert emails.`)
    } catch (requestError) {
      setError(apiErrorMessage(
        requestError,
        nextActive ? 'Could not resume this recipient.' : 'Could not pause this recipient.',
      ))
    } finally {
      setUpdatingId(null)
    }
  }

  const handleDelete = async (recipient) => {
    const label = recipient.name || recipient.email
    if (!window.confirm(
      `Permanently delete ${label}? This removes the recipient and cannot be undone.`,
    )) return

    setDeletingId(recipient.recipient_id)
    setError('')
    setNotice('')
    try {
      await api.removeAlertEmailRecipient(recipient.recipient_id)
      setRecipients((current) => current.filter(
        (item) => item.recipient_id !== recipient.recipient_id,
      ))
      if (editingId === recipient.recipient_id) {
        setEditingId(null)
        setName('')
        setEmail('')
      }
      setNotice(`${recipient.email} was permanently deleted.`)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not delete this recipient.'))
    } finally {
      setDeletingId(null)
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
                  ref={nameInputRef}
                  id="alert-recipient-name"
                  className="form-control form-control-sm"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  placeholder="e.g. Juan Dela Cruz"
                  disabled={busy}
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
                  disabled={busy}
                  required
                />
              </div>
            </div>
            <div className="alert-recipient-form-actions">
              {editingId !== null && (
                <button
                  type="button"
                  className="btn btn-outline-secondary btn-sm"
                  onClick={handleCancelEdit}
                  disabled={busy}
                >
                  Cancel
                </button>
              )}
              <button type="submit" className="btn btn-success btn-sm" disabled={busy}>
                {saving
                  ? <><span className="spinner-border spinner-border-sm me-1" />Saving</>
                  : editingId !== null
                    ? <><i className="bi bi-check2 me-1" />Save changes</>
                    : <><i className="bi bi-person-plus-fill me-1" />Add recipient</>}
              </button>
            </div>
          </form>

          <div className="alert-recipient-feedback" aria-live="polite">
            {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}
            {!error && notice && <div className="alert alert-success py-2 mb-0">{notice}</div>}
          </div>

          <div className="alert-recipient-list-heading">
            <span>Alert recipients</span>
            <span>
              {activeCount} active{pausedCount > 0 ? ` · ${pausedCount} paused` : ''}
            </span>
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
              <div
                className={`alert-recipient-row${recipient.is_active ? '' : ' is-paused'}`}
                key={recipient.recipient_id}
              >
                <span className="alert-recipient-avatar" aria-hidden="true">
                  {(recipient.name || recipient.email).slice(0, 1).toUpperCase()}
                </span>
                <span className="alert-recipient-details">
                  <strong className={recipient.name ? '' : 'is-missing-name'}>
                    {recipient.name || 'Name not provided'}
                  </strong>
                  <span>{recipient.email}</span>
                  <small>{recipient.is_active ? 'Receiving alerts' : 'Paused — no alerts sent'}</small>
                </span>
                <span className="alert-recipient-actions">
                  <button
                    type="button"
                    className="alert-recipient-action is-edit"
                    onClick={() => handleEdit(recipient)}
                    disabled={busy}
                    aria-label={`Edit ${recipient.name || recipient.email}`}
                  >
                    <i className="bi bi-pencil" />
                    <span>Edit</span>
                  </button>
                  <button
                    type="button"
                    className={`alert-recipient-action ${recipient.is_active ? 'is-pause' : 'is-resume'}`}
                    onClick={() => handleToggleActive(recipient)}
                    disabled={busy}
                    aria-label={`${recipient.is_active ? 'Pause' : 'Resume'} alerts for ${recipient.name || recipient.email}`}
                  >
                    {updatingId === recipient.recipient_id
                      ? <span className="spinner-border spinner-border-sm" />
                      : <i className={`bi ${recipient.is_active ? 'bi-pause-fill' : 'bi-play-fill'}`} />}
                    <span>{recipient.is_active ? 'Pause' : 'Resume'}</span>
                  </button>
                  <button
                    type="button"
                    className="alert-recipient-action is-delete"
                    onClick={() => handleDelete(recipient)}
                    disabled={busy}
                    aria-label={`Permanently delete ${recipient.name || recipient.email}`}
                  >
                    {deletingId === recipient.recipient_id
                      ? <span className="spinner-border spinner-border-sm" />
                      : <i className="bi bi-trash3" />}
                    <span>Delete</span>
                  </button>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
