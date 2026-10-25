import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { apiErrorMessage } from '../api'
import AuthLayout from '../components/AuthLayout'
import LoginTerms from '../components/LoginTerms'
import SignInCodeInput from '../components/SignInCodeInput'
import ConfirmationModal from '../components/ConfirmationModal'

const emptyCode = () => Array(6).fill('')

export default function LoginPage() {
  const { login, verifyLogin, resendLogin, cancelLogin, sessionNotice } = useAuth()
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState(emptyCode)
  const [resendAt, setResendAt] = useState(0)
  const [now, setNow] = useState(Date.now())
  const [notice, setNotice] = useState('')
  const [sessionLimit, setSessionLimit] = useState(null)
  const [recoveryOpen, setRecoveryOpen] = useState(false)
  const requestInFlight = useRef(false)
  const loginForm = useRef(null)
  const codeInput = useRef(null)
  const recoveryButton = useRef(null)
  const wasRecoveryOpen = useRef(false)

  useEffect(() => () => cancelLogin(), [cancelLogin])
  useEffect(() => {
    if (!challenge) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [challenge])
  useEffect(() => {
    if (challenge && !loading) codeInput.current?.focus()
  }, [challenge, error, loading])
  useEffect(() => {
    if (wasRecoveryOpen.current && !recoveryOpen && !challenge) recoveryButton.current?.focus()
    wasRecoveryOpen.current = recoveryOpen
  }, [recoveryOpen, challenge])

  const acceptChallenge = (next) => {
    setRecoveryOpen(false)
    setChallenge(next)
    setCode(emptyCode())
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

  const startAgain = () => {
    if (loading) return
    cancelLogin()
    setChallenge(null)
    setCode(emptyCode())
    setSessionLimit(null)
    setRecoveryOpen(false)
    setError(null)
    setNotice('')
  }

  const closeRecovery = () => {
    if (loading) return
    setRecoveryOpen(false)
    setError(null)
  }

  const submit = async (verificationCode = code.join(''), recoverSessions = false) => {
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
        acceptChallenge(await login(identifier, password, { recoverSessions, authTarget: sessionLimit?.authTarget }))
      }
    } catch (err) {
      const status = err?.response?.status
      if (status === 409) {
        setSessionLimit({ authTarget: err.config?.authTarget || challenge?.authTarget })
        if (challenge) { cancelLogin(); setChallenge(null); setCode(emptyCode()); setPassword('') }
        else setRecoveryOpen(true)
        setError(recoverSessions ? 'Recovery is unavailable. Please contact your administrator.'
          : challenge ? 'Two sessions are active. Enter your password to recover access.' : null)
      }
      else if (status === 401 && !challenge) setError('Check your username or email and password, then try again.')
      else if (status === 404) setError('Sign-in verification is unavailable. Ask the administrator to update the API.')
      else setError(apiErrorMessage(err, 'Unable to connect to MangoPoint.'))
      if (challenge && status === 400) setCode(emptyCode())
    } finally {
      requestInFlight.current = false
      setLoading(false)
    }
  }

  const updateCode = (nextCode) => {
    setCode(nextCode)
    const completed = nextCode.join('')
    if (!challenge?.session_recovery && completed.length === 6 && completed !== code.join('')) void submit(completed)
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
      {error && !recoveryOpen && (
        <div id="login-error" className="alert alert-warning auth-alert" role="alert">
          <i className="bi bi-exclamation-circle" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <form ref={loginForm} key={challenge ? 'verification' : 'password'} onSubmit={(event) => { event.preventDefault(); void submit() }} className="login-form" aria-busy={loading}>
        {challenge ? (
          <>
            {challenge.session_recovery && <div className="alert alert-info auth-alert" role="status">
              Confirming this code signs out all other MangoPoint sessions for this account and signs you in here. Unsaved work in those sessions may be lost.
            </div>}
            <div className="login-field login-verification-field">
              <label id="login-code-label" className="form-label" htmlFor="login-code-1">Please enter the authentication code</label>
              <SignInCodeInput ref={codeInput} value={code} onChange={updateCode}
                disabled={loading || expired} error={error} />
              <div className="login-code-resend">
                <span>Didn't get the code?</span>{' '}
                <button type="button" className="btn btn-link p-0 auth-inline-link" onClick={handleResend}
                  disabled={loading || resendSeconds > 0 || expired}>
                  {resendSeconds ? `Resend code in ${resendSeconds}s` : 'Resend code'}
                </button>
              </div>
              <p id="login-code-help" className="auth-password-hint" role={expired ? 'status' : undefined}>
                {expired ? 'This code has expired. Choose Start again to sign in.'
                  : challenge.session_recovery ? 'Enter all six digits, then confirm below. Never share your code.'
                    : 'Enter all six digits to sign in automatically. Never share your code.'}
              </p>
            </div>
            {loading && <div className="login-code-progress" role="status">
              <span className="spinner-border spinner-border-sm" aria-hidden="true" />Verifying…
            </div>}
            {challenge.session_recovery && <button type="submit" className="btn btn-success w-100 login-submit-btn"
              disabled={loading || expired || code.join('').length !== 6}>Sign out other sessions and sign in</button>}
            {!challenge.session_recovery && error && code.join('').length === 6 && !expired && <div className="login-code-actions">
              <button type="submit" className="btn btn-link p-0 auth-inline-link" disabled={loading}>Verify and sign in</button>
            </div>}
            <button type="button" className="btn btn-link p-0 auth-inline-link" onClick={startAgain} disabled={loading}>Start again</button>
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
            onChange={(event) => { setIdentifier(event.target.value); setSessionLimit(null) }}
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
        </div>

        <button type="submit" className="btn btn-success w-100 login-submit-btn" disabled={loading}>
          {loading ? (
            <><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />Signing in…</>
          ) : (
            <>Sign in<i className="bi bi-arrow-right" aria-hidden="true" /></>
          )}
        </button>
        <div className="auth-forgot-row">
          <Link className="auth-inline-link" to="/forgot-password">Forgot password?</Link>
          <button ref={recoveryButton} type="button" className="btn btn-link p-0 auth-inline-link"
            aria-haspopup="dialog" disabled={loading}
            onClick={() => {
              if (!loginForm.current?.reportValidity()) return
              setError(null)
              setRecoveryOpen(true)
            }}>Recover account access</button>
        </div>
          </>
        )}
      </form>
      <LoginTerms />
      {recoveryOpen && <ConfirmationModal title={sessionLimit ? 'Two sessions are active' : 'Recover account access'} confirmLabel="Email a recovery code"
        onConfirm={() => void submit('', true)} onClose={closeRecovery} busy={loading} error={error || ''}
        showIcon={false} closeLabel="Close session recovery" className="session-recovery-backdrop">
        <p>Verify your email to sign out other sessions and sign in here.</p>
      </ConfirmationModal>}
    </AuthLayout>
  )
}
