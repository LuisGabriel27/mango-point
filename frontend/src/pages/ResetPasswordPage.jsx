import { useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import api, { apiErrorMessage } from '../api'
import AuthLayout from '../components/AuthLayout'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const challengeId = searchParams.get('challenge') || ''
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    if (password !== confirmation) {
      setError('The passwords do not match.')
      return
    }
    setLoading(true)
    try {
      const response = await api.resetPassword({
        challenge_id: challengeId,
        code,
        new_password: password,
      })
      setMessage(response.data.message)
      setCode('')
      setPassword('')
      setConfirmation('')
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to reset your password. Request a new code and try again.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      eyebrow="Secure Password Reset"
      title={message ? 'Password updated' : 'Enter your reset code'}
      description={message ? 'Your MangoPoint account is ready to use.' : 'Enter the six-digit code from your email and choose a new password.'}
      footer={<Link className="auth-back-link" to="/login"><i className="bi bi-arrow-left" aria-hidden="true" /> Back to login</Link>}
    >
      {message ? (
        <div className="auth-success" role="status">
          <span className="auth-success-icon"><i className="bi bi-check2" aria-hidden="true" /></span>
          <h2>Reset complete</h2>
          <p>{message}</p>
          <Link to="/login" className="btn btn-success w-100 login-submit-btn">Continue to login</Link>
        </div>
      ) : !challengeId ? (
        <div className="alert alert-warning auth-alert" role="alert">
          <i className="bi bi-link-45deg" aria-hidden="true" />
          <span>This reset request is incomplete. Request a new code from the login page.</span>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          {error && <div className="alert alert-warning auth-alert" role="alert"><i className="bi bi-exclamation-circle" aria-hidden="true" /><span>{error}</span></div>}
          {location.state?.message && <div className="auth-code-notice"><i className="bi bi-envelope-check" aria-hidden="true" /><span>{location.state.message}</span></div>}
          <label className="form-label fw-semibold" htmlFor="reset-code">Six-digit reset code</label>
          <input
            id="reset-code"
            type="text"
            className="form-control auth-code-input mb-3"
            placeholder="000000"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength="6"
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
            required
            autoFocus
          />
          <label className="form-label fw-semibold" htmlFor="new-password">New password</label>
          <div className="auth-password-wrap mb-3">
            <input id="new-password" type={showPassword ? 'text' : 'password'} className="form-control" placeholder="At least 8 characters" autoComplete="new-password" minLength="8" value={password} onChange={(event) => setPassword(event.target.value)} required />
            <button type="button" className="auth-password-toggle" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? 'Hide passwords' : 'Show passwords'}>
              <i className={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true" />
            </button>
          </div>
          <label className="form-label fw-semibold" htmlFor="confirm-password">Confirm new password</label>
          <input id="confirm-password" type={showPassword ? 'text' : 'password'} className="form-control mb-2" placeholder="Enter it again" autoComplete="new-password" minLength="8" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required />
          <p className="auth-password-hint">The code expires after 10 minutes and allows five attempts.</p>
          <button type="submit" className="btn btn-success w-100 login-submit-btn" disabled={loading}>
            {loading ? <><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />Updating password…</> : <><i className="bi bi-shield-check me-2" aria-hidden="true" />Reset password</>}
          </button>
        </form>
      )}
    </AuthLayout>
  )
}
