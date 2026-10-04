import { useCallback, useEffect, useRef, useState } from 'react'
import api, { apiErrorMessage } from '../api'

export default function AlertRecipientSettings() {
  const nameInputRef = useRef(null)
  const emailInputRef = useRef(null)
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
    loadRecipients()
  }, [loadRecipients])

  const clearForm = () => {
    setEditingId(null)
    setName('')
    setEmail('')
  }

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
      const payload = { email: normalizedEmail, name: name.trim() || null }
      const response = editingId === null
        ? await api.addAlertEmailRecipient(payload)
        : await api.updateAlertEmailRecipient(editingId, payload)
      setRecipients((current) => editingId === null
        ? [...current.filter((item) => item.recipient_id !== response.data.recipient_id), response.data]
        : current.map((item) => (
            item.recipient_id === response.data.recipient_id ? response.data : item
          )))
      const wasEditing = editingId !== null
      clearForm()
      setNotice(wasEditing
        ? `${response.data.email} was updated.`
        : `${response.data.email} will receive future alert emails.`)
      emailInputRef.current?.focus()
    } catch (requestError) {
      setError(apiErrorMessage(
        requestError,
        editingId === null ? 'Could not add this recipient.' : 'Could not update this recipient.',
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
    clearForm()
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
      if (editingId === recipient.recipient_id) clearForm()
      setNotice(`${recipient.email} was permanently deleted.`)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not delete this recipient.'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="settings-panel-section" aria-labelledby="notification-email-settings-title">
      <div className="settings-section-heading">
        <span className="settings-section-icon"><i className="bi bi-envelope-at" /></span>
        <div>
          <h3 id="notification-email-settings-title">Notification email recipients</h3>
          <p>Add the people who should receive new MangoPoint risk alerts away from the dashboard.</p>
        </div>
      </div>

      <form className="alert-recipient-form" onSubmit={handleSubmit}>
        <div className="alert-recipient-fields">
          <div>
            <label htmlFor="settings-recipient-name">Name <span>(optional)</span></label>
            <input
              ref={nameInputRef}
              id="settings-recipient-name"
              className="form-control form-control-sm"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={200}
              placeholder="e.g. Juan Dela Cruz"
              disabled={busy}
            />
          </div>
          <div>
            <label htmlFor="settings-recipient-email">Email address</label>
            <input
              ref={emailInputRef}
              id="settings-recipient-email"
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
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={handleCancelEdit} disabled={busy}>
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
        <span>{activeCount} active{pausedCount > 0 ? ` · ${pausedCount} paused` : ''}</span>
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
          <div className={`alert-recipient-row${recipient.is_active ? '' : ' is-paused'}`} key={recipient.recipient_id}>
            <span className="alert-recipient-avatar" aria-hidden="true">
              {(recipient.name || recipient.email).slice(0, 1).toUpperCase()}
            </span>
            <span className="alert-recipient-details">
              <strong className={recipient.name ? '' : 'is-missing-name'}>{recipient.name || 'Name not provided'}</strong>
              <span>{recipient.email}</span>
              <small>{recipient.is_active ? 'Receiving alerts' : 'Paused — no alerts sent'}</small>
            </span>
            <span className="alert-recipient-actions">
              <button type="button" className="alert-recipient-action is-edit" onClick={() => handleEdit(recipient)} disabled={busy} aria-label={`Edit ${recipient.name || recipient.email}`}>
                <i className="bi bi-pencil" /><span>Edit</span>
              </button>
              <button type="button" className={`alert-recipient-action ${recipient.is_active ? 'is-pause' : 'is-resume'}`} onClick={() => handleToggleActive(recipient)} disabled={busy} aria-label={`${recipient.is_active ? 'Pause' : 'Resume'} alerts for ${recipient.name || recipient.email}`}>
                {updatingId === recipient.recipient_id
                  ? <span className="spinner-border spinner-border-sm" />
                  : <i className={`bi ${recipient.is_active ? 'bi-pause-fill' : 'bi-play-fill'}`} />}
                <span>{recipient.is_active ? 'Pause' : 'Resume'}</span>
              </button>
              <button type="button" className="alert-recipient-action is-delete" onClick={() => handleDelete(recipient)} disabled={busy} aria-label={`Permanently delete ${recipient.name || recipient.email}`}>
                {deletingId === recipient.recipient_id
                  ? <span className="spinner-border spinner-border-sm" />
                  : <i className="bi bi-trash3" />}
                <span>Delete</span>
              </button>
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
