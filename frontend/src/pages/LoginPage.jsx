import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { apiErrorMessage } from '../api'
import AuthLayout from '../components/AuthLayout'
import LoginTerms from '../components/LoginTerms'

export default function LoginPage() {
  const { login, verifyLogin, resendLogin, cancelLogin, sessionNotice } = useAuth()
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')
  const [resendAt, setResendAt] = useState(0)
  const [now, setNow] = useState(Date.now())
  const [notice, setNotice] = useState('')
  const requestInFlight = useRef(false)
  const codeInput = useRef(null)

  useEffect(() => () => cancelLogin(), [cancelLogin])
  useEffect(() => {
    if (!challenge) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [challenge])
  useEffect(() => {
    if (challenge && error && !loading) codeInput.current?.focus()
  }, [challenge, error, loading])

  const acceptChallenge = (next) => {
    setChallenge(next)
    setCode('')
    setPassword('')
    setNow(Date.now())
    setResendAt(Date.now() + next.resend_after_seconds * 1000)
  }
  const resendSeconds = Math.max(0, Math.ceil((resendAt - now) / 1000))
  const expired = challenge && Date.parse(challenge.expires_at) <= now

  const handleResend = async () => {
    if (requestInFlight.current || loading || resendSeconds || expired) return
    requestInFlight.current = true
    setLoading(true)
    setError(null)
    setNotice('')
    try {
      acceptChallenge(await resendLogin(challenge))
      setNotice('A new code was sent. Use the latest email.')
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to resend your sign-in code.'))
      if (err?.response?.status === 429) {
        setResendAt(Date.now() + Number(err.response.headers['retry-after'] || 60) * 1000)
      }
    } finally { requestInFlight.current = false; setLoading(false) }
  }

  const submit = async (verificationCode = code) => {
    if (requestInFlight.current || loading) return
    if (challenge && (!/^[0-9]{6}$/.test(verificationCode) || Date.parse(challenge.expires_at) <= Date.now())) return
    requestInFlight.current = true
    setError(null)
    setNotice('')
    setLoading(true)
    try {
      if (challenge) {
        await verifyLogin(challenge, verificationCode)
        navigate('/')
      } else {
        acceptChallenge(await login(identifier, password))
      }
    } catch (err) {
      const status = err?.response?.status
      if (status === 401 && !challenge) setError('Check your username or email and password, then try again.')
      else if (status === 404) setError('Sign-in verification is unavailable. Ask the administrator to update the API.')
      else setError(apiErrorMessage(err, 'Unable to connect to MangoPoint.'))
    } finally {
      requestInFlight.current = false
      setLoading(false)
    }
  }

  const updateCode = (value) => {
    const nextCode = value.replace(/\D/g, '').slice(0, 6)
    setCode(nextCode)
    if (nextCode.length === 6 && nextCode !== code) void submit(nextCode)
  }

  return (
    <AuthLayout
      compact
      eyebrow="Account access"
      title={challenge ? 'Check your email' : 'Welcome back'}
      description={challenge ? `Enter the six-digit sign-in code sent to ${challenge.masked_email}.` : 'Sign in to your orchard workspace to continue.'}
      footer={<span className="login-access-note"><i className="bi bi-lock" aria-hidden="true" />Access for authorized orchard personnel</span>}
    >
      {sessionNotice && <div className="alert alert-info auth-alert" role="status">{sessionNotice}</div>}
      {notice && <div className="alert alert-info auth-alert" role="status">{notice}</div>}
      {error && (
        <div id="login-error" className="alert alert-warning auth-alert" role="alert">
          <i className="bi bi-exclamation-circle" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <form key={challenge ? 'verification' : 'password'} onSubmit={(event) => { event.preventDefault(); void submit() }} className="login-form" aria-busy={loading}>
        {challenge ? (
          <>
            <div className="login-field">
              <label className="form-label" htmlFor="login-code">Email verification code</label>
              <input ref={codeInput} id="login-code" type="text" className="form-control" inputMode="numeric"
                autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6}
                value={code} onChange={(event) => updateCode(event.target.value)}
                onPaste={(event) => { event.preventDefault(); updateCode(event.clipboardData.getData('text')) }}
                aria-describedby="login-code-help" required autoFocus disabled={loading || expired} />
              <p id="login-code-help" className="auth-password-hint mt-2" role={expired ? 'status' : undefined}>
                {expired ? 'This code has expired. Start again to request a new code.' : 'Enter all six digits to sign in automatically. Never share your code.'}
              </p>
            </div>
            <button type="submit" className="btn btn-success w-100 login-submit-btn" disabled={loading || expired || code.length !== 6}>
              {loading ? 'Verifying…' : 'Verify and sign in'}
            </button>
            <div className="d-flex flex-wrap gap-3 justify-content-between mt-3">
              <button type="button" className="btn btn-link p-0 auth-inline-link" onClick={handleResend}
                disabled={loading || resendSeconds > 0 || expired}>
                {resendSeconds ? `Resend code in ${resendSeconds}s` : 'Resend code'}
              </button>
              <button type="button" className="btn btn-link p-0 auth-inline-link" disabled={loading}
                onClick={() => { cancelLogin(); setChallenge(null); setCode(''); setError(null); setNotice('') }}>
                Start again
              </button>
            </div>
          </>
        ) : (
          <>
        <div className="login-field">
          <label className="form-label" htmlFor="login-identifier">Username or email</label>
          <input
            id="login-identifier"
            type="text"
            className="form-control"
            placeholder="Enter your username or email"
            autoComplete="username"
            maxLength={254}
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
              maxLength={256}
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
        <p className="auth-password-hint mt-3 mb-0">We’ll email a verification code after checking your password. Internet access is required.</p>
          </>
        )}
      </form>
      <LoginTerms />
    </AuthLayout>
  )
}
