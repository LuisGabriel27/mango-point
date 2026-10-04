import { useEffect, useMemo, useRef, useState } from 'react'
import api, { apiErrorMessage } from '../api'
import { useAuth } from '../context/AuthContext'
import AlertRecipientSettings from './AlertRecipientSettings'

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export default function SettingsModal({ onClose }) {
  const { user, updateUser } = useAuth()
  const dialogRef = useRef(null)
  const previousFocusRef = useRef(null)
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const tabs = useMemo(() => [
    { id: 'account', label: 'Account', icon: 'person-gear' },
    ...(isAdmin ? [{ id: 'notifications', label: 'Notification emails', icon: 'envelope-at' }] : []),
  ], [isAdmin])
  const [activeTab, setActiveTab] = useState('account')
  const [fullName, setFullName] = useState(user?.full_name || '')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileError, setProfileError] = useState('')
  const [profileNotice, setProfileNotice] = useState('')
  const [recoveryEmail, setRecoveryEmail] = useState(user?.email || '')
  const [emailPassword, setEmailPassword] = useState('')
  const [emailSaving, setEmailSaving] = useState(false)
  const [emailError, setEmailError] = useState('')
  const [emailNotice, setEmailNotice] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [passwordNotice, setPasswordNotice] = useState('')
  const busy = profileSaving || emailSaving || passwordSaving

  useEffect(() => {
    previousFocusRef.current = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialogRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      previousFocusRef.current?.focus?.()
    }
  }, [])

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !busy) {
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
  }, [busy, onClose])

  const handleProfileSubmit = async (event) => {
    event.preventDefault()
    const normalizedName = fullName.trim()
    if (!normalizedName) {
      setProfileError('Name cannot be empty.')
      return
    }
    setProfileSaving(true)
    setProfileError('')
    setProfileNotice('')
    try {
      const response = await api.updateProfile({ full_name: normalizedName })
      const updated = response.data.user ?? response.data
      updateUser(updated)
      setFullName(updated.full_name)
      setProfileNotice('Your name was updated.')
    } catch (requestError) {
      setProfileError(apiErrorMessage(requestError, 'Could not update your name.'))
    } finally {
      setProfileSaving(false)
    }
  }

  const handlePasswordSubmit = async (event) => {
    event.preventDefault()
    setPasswordError('')
    setPasswordNotice('')
    if (newPassword.length < 8) {
      setPasswordError('New password must contain at least 8 characters.')
      return
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('New password and confirmation do not match.')
      return
    }
    if (currentPassword === newPassword) {
      setPasswordError('New password must be different from the current password.')
      return
    }

    setPasswordSaving(true)
    try {
      const response = await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPasswordNotice(response.data.message || 'Password updated successfully.')
    } catch (requestError) {
      setPasswordError(apiErrorMessage(requestError, 'Could not update your password.'))
    } finally {
      setPasswordSaving(false)
    }
  }

  const handleEmailSubmit = async (event) => {
    event.preventDefault()
    setEmailError('')
    setEmailNotice('')
    setEmailSaving(true)
    try {
      const response = await api.updateAccountEmail({
        email: recoveryEmail.trim(),
        current_password: emailPassword,
      })
      const updated = response.data.user ?? response.data
      updateUser(updated)
      setRecoveryEmail(updated.email)
      setEmailPassword('')
      setEmailNotice('Your login and recovery email was updated.')
    } catch (requestError) {
      setEmailError(apiErrorMessage(requestError, 'Could not update your recovery email.'))
    } finally {
      setEmailSaving(false)
    }
  }

  return (
    <div
      className="orchard-modal-backdrop settings-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose()
      }}
    >
      <section
        ref={dialogRef}
        className="orchard-modal-dialog settings-modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-modal-title"
        tabIndex={-1}
      >
        <header className="orchard-modal-header settings-modal-header">
          <div>
            <div className="orchard-modal-eyebrow">MangoPoint preferences</div>
            <h2 id="settings-modal-title" className="orchard-modal-title">Settings</h2>
          </div>
          <button type="button" className="btn-close" aria-label="Close settings" onClick={onClose} disabled={busy} />
        </header>

        <div className="settings-modal-layout">
          <nav className="settings-modal-nav" aria-label="Settings sections">
            <div className="settings-account-summary">
              <span className="settings-account-avatar">{(user?.full_name || user?.username || 'U').slice(0, 1).toUpperCase()}</span>
              <span><strong>{user?.full_name || user?.username}</strong><small>{user?.email}</small></span>
            </div>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`settings-nav-item${activeTab === tab.id ? ' active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
                aria-current={activeTab === tab.id ? 'page' : undefined}
              >
                <i className={`bi bi-${tab.icon}`} />{tab.label}
              </button>
            ))}
          </nav>

          <div className="settings-modal-content">
            {activeTab === 'account' && (
              <div className="settings-account-panels">
                <section className="settings-panel-section" aria-labelledby="profile-settings-title">
                  <div className="settings-section-heading">
                    <span className="settings-section-icon"><i className="bi bi-person" /></span>
                    <div><h3 id="profile-settings-title">Profile</h3><p>Update the name displayed in MangoPoint.</p></div>
                  </div>
                  <form className="settings-form" onSubmit={handleProfileSubmit}>
                    <label htmlFor="settings-full-name">Full name</label>
                    <input
                      id="settings-full-name"
                      className="form-control"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                      maxLength={200}
                      autoComplete="name"
                      disabled={profileSaving}
                      required
                    />
                    <div className="settings-readonly-row">
                      <span><small>Username</small><strong>{user?.username}</strong></span>
                      <span><small>Role</small><strong>{user?.role}</strong></span>
                    </div>
                    <div className="settings-form-feedback" aria-live="polite">
                      {profileError && <div className="alert alert-danger py-2 mb-0">{profileError}</div>}
                      {!profileError && profileNotice && <div className="alert alert-success py-2 mb-0">{profileNotice}</div>}
                    </div>
                    <div className="settings-form-actions">
                      <button type="submit" className="btn btn-success btn-sm" disabled={profileSaving || fullName.trim() === user?.full_name}>
                        {profileSaving && <span className="spinner-border spinner-border-sm me-1" />}Save name
                      </button>
                    </div>
                  </form>
                </section>

                <section className="settings-panel-section" aria-labelledby="email-settings-title">
                  <div className="settings-section-heading">
                    <span className="settings-section-icon"><i className="bi bi-envelope-check" /></span>
                    <div><h3 id="email-settings-title">Login and recovery email</h3><p>Brevo sends password reset codes to this address.</p></div>
                  </div>
                  <form className="settings-form" onSubmit={handleEmailSubmit}>
                    <div className="settings-password-grid">
                      <div>
                        <label htmlFor="settings-recovery-email">Email address</label>
                        <input id="settings-recovery-email" type="email" className="form-control" value={recoveryEmail} onChange={(event) => setRecoveryEmail(event.target.value)} autoComplete="email" maxLength={255} disabled={emailSaving} required />
                      </div>
                      <div>
                        <label htmlFor="settings-email-password">Current password</label>
                        <input id="settings-email-password" type="password" className="form-control" value={emailPassword} onChange={(event) => setEmailPassword(event.target.value)} autoComplete="current-password" disabled={emailSaving} required />
                      </div>
                    </div>
                    <div className="settings-form-feedback" aria-live="polite">
                      {emailError && <div className="alert alert-danger py-2 mb-0">{emailError}</div>}
                      {!emailError && emailNotice && <div className="alert alert-success py-2 mb-0">{emailNotice}</div>}
                    </div>
                    <div className="settings-form-actions">
                      <button type="submit" className="btn btn-success btn-sm" disabled={emailSaving || !emailPassword || recoveryEmail.trim().toLowerCase() === user?.email?.toLowerCase()}>
                        {emailSaving && <span className="spinner-border spinner-border-sm me-1" />}Save recovery email
                      </button>
                    </div>
                  </form>
                </section>

                <section className="settings-panel-section" aria-labelledby="password-settings-title">
                  <div className="settings-section-heading">
                    <span className="settings-section-icon"><i className="bi bi-shield-lock" /></span>
                    <div><h3 id="password-settings-title">Password</h3><p>Confirm your current password before choosing a replacement.</p></div>
                  </div>
                  <form className="settings-form" onSubmit={handlePasswordSubmit}>
                    <div className="settings-password-grid">
                      <div className="settings-field-wide">
                        <label htmlFor="settings-current-password">Current password</label>
                        <input id="settings-current-password" type="password" className="form-control" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" disabled={passwordSaving} required />
                      </div>
                      <div>
                        <label htmlFor="settings-new-password">New password</label>
                        <input id="settings-new-password" type="password" className="form-control" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={8} maxLength={256} autoComplete="new-password" disabled={passwordSaving} required />
                      </div>
                      <div>
                        <label htmlFor="settings-confirm-password">Confirm new password</label>
                        <input id="settings-confirm-password" type="password" className="form-control" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={8} maxLength={256} autoComplete="new-password" disabled={passwordSaving} required />
                      </div>
                    </div>
                    <small className="text-muted">Use at least 8 characters.</small>
                    <div className="settings-form-feedback" aria-live="polite">
                      {passwordError && <div className="alert alert-danger py-2 mb-0">{passwordError}</div>}
                      {!passwordError && passwordNotice && <div className="alert alert-success py-2 mb-0">{passwordNotice}</div>}
                    </div>
                    <div className="settings-form-actions">
                      <button type="submit" className="btn btn-success btn-sm" disabled={passwordSaving}>
                        {passwordSaving && <span className="spinner-border spinner-border-sm me-1" />}Change password
                      </button>
                    </div>
                  </form>
                </section>
              </div>
            )}
            {activeTab === 'notifications' && isAdmin && <AlertRecipientSettings />}
          </div>
        </div>
      </section>
    </div>
  )
}
