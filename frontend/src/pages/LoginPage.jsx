import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { apiErrorMessage } from '../api'
import AuthLayout from '../components/AuthLayout'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (loading) return
    setError(null)
    setLoading(true)
    try {
      await login(identifier, password)
      navigate('/')
    } catch (err) {
      const status = err?.response?.status
      if (status === 401) setError('Check your username or email and password, then try again.')
      else if (status === 503 || status === 404) setError('Sign-in is temporarily unavailable. Please try again shortly.')
      else setError(apiErrorMessage(err, 'Unable to connect to MangoPoint.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      compact
      eyebrow="Account access"
      title="Welcome back"
      description="Sign in to your orchard workspace to continue."
      footer={<span className="login-access-note"><i className="bi bi-lock" aria-hidden="true" />Access for authorized orchard personnel</span>}
    >
      {error && (
        <div id="login-error" className="alert alert-warning auth-alert" role="alert">
          <i className="bi bi-exclamation-circle" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="login-form" aria-busy={loading}>
        <div className="login-field">
          <label className="form-label" htmlFor="login-identifier">Username or email</label>
          <input
            id="login-identifier"
            type="text"
            className="form-control"
            placeholder="Enter your username or email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            aria-describedby={error ? 'login-error' : undefined}
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            required
            autoFocus
          />
        </div>

        <div className="login-field">
          <label className="form-label" htmlFor="login-password">Password</label>
          <div className="auth-password-wrap">
            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              className="form-control"
              placeholder="Enter your password"
              autoComplete="current-password"
              aria-describedby={error ? 'login-error' : undefined}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button
              type="button"
              className="auth-password-toggle"
              onClick={() => setShowPassword((visible) => !visible)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
              aria-controls="login-password"
            >
              <i className={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true" />
            </button>
          </div>
          <div className="auth-forgot-row">
            <Link className="auth-inline-link" to="/forgot-password">Forgot password?</Link>
          </div>
        </div>

        <button type="submit" className="btn btn-success w-100 login-submit-btn" disabled={loading}>
          {loading ? (
            <><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />Signing in…</>
          ) : (
            <>Sign in<i className="bi bi-arrow-right" aria-hidden="true" /></>
          )}
        </button>
      </form>
    </AuthLayout>
  )
}
