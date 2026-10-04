import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api, { apiErrorMessage } from '../api'
import AuthLayout from '../components/AuthLayout'

export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const response = await api.requestPasswordReset({ email })
      navigate(`/reset-password?challenge=${encodeURIComponent(response.data.challenge_id)}`, {
        state: { email, message: response.data.message },
      })
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to send a reset code. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      eyebrow="Account Recovery"
      title="Reset your password"
      description="Enter the recovery email saved on your MangoPoint account."
      footer={<Link className="auth-back-link" to="/login"><i className="bi bi-arrow-left" aria-hidden="true" /> Back to login</Link>}
    >
      <form onSubmit={handleSubmit}>
        {error && <div className="alert alert-warning auth-alert" role="alert"><i className="bi bi-exclamation-circle" aria-hidden="true" /><span>{error}</span></div>}
        <label className="form-label fw-semibold" htmlFor="recovery-email">Account recovery email</label>
        <input id="recovery-email" type="email" className="form-control mb-2" placeholder="you@example.com" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoFocus />
        <p className="auth-password-hint mb-3">Use the email saved under Settings → Account.</p>
        <button type="submit" className="btn btn-success w-100 login-submit-btn" disabled={loading}>
          {loading ? <><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />Sending code…</> : <><i className="bi bi-envelope me-2" aria-hidden="true" />Send reset code</>}
        </button>
      </form>
    </AuthLayout>
  )
}
