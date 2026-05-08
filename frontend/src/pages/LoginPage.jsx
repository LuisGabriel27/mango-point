import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { apiErrorMessage } from '../api'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(identifier, password)
      navigate('/')
    } catch (err) {
      const status = err?.response?.status
      if (status === 401) setError('Invalid credentials. Check your username and password.')
      else if (status === 503) setError('Database is offline. Try the default admin credentials.')
      else if (status === 404) setError('Authentication endpoint not found. Is the backend running?')
      else setError(apiErrorMessage(err, 'Unable to connect to the API.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container-fluid px-3 auth-shell">
      <div className="login-shell">
        <div className="login-orb login-orb-a" />
        <div className="login-orb login-orb-b" />
        <div className="row align-items-center justify-content-center g-4 login-grid">
          {/* Hero panel */}
          <div className="col-12 col-lg-6 mb-4 mb-lg-0">
            <div className="login-hero-panel">
              <span className="badge login-badge mb-3">Secure Access</span>
              <h1 className="login-hero-title">MangoPoint</h1>
              <p className="login-hero-copy">
                Sign in to unlock the existing simulation, monitoring, GIS, and validation tools.
              </p>
              <div className="login-feature-list">
                <div className="login-feature">
                  <i className="bi bi-shield-lock me-2 text-success" />
                  <span>Protected FastAPI routes</span>
                </div>
                <div className="login-feature">
                  <i className="bi bi-map me-2 text-success" />
                  <span>GIS and monitoring dashboards</span>
                </div>
                <div className="login-feature">
                  <i className="bi bi-cpu me-2 text-success" />
                  <span>Simulation and validation workflows</span>
                </div>
              </div>
            </div>
          </div>

          {/* Login card */}
          <div className="col-12 col-lg-5">
            <div className="card login-card border-0 shadow-lg">
              <div className="card-body p-4 p-lg-5">
                <div className="login-card-kicker">Dashboard Login</div>
                <h2 className="login-card-title mb-1">Welcome back</h2>
                <p className="text-muted mb-4">
                  Use your MangoPoint username or email and password.
                </p>

                {error && (
                  <div className="alert alert-warning py-2 mb-3" role="alert">
                    {error}
                  </div>
                )}

                <form onSubmit={handleSubmit}>
                  <label className="form-label fw-semibold" htmlFor="login-identifier">
                    Username or Email
                  </label>
                  <input
                    id="login-identifier"
                    type="text"
                    className="form-control mb-3"
                    placeholder="admin or admin@example.com"
                    autoComplete="username"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    required
                  />

                  <label className="form-label fw-semibold" htmlFor="login-password">
                    Password
                  </label>
                  <input
                    id="login-password"
                    type="password"
                    className="form-control mb-3"
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />

                  <div className="login-processing mb-2">
                    {loading && (
                      <div className="d-flex align-items-center gap-2 text-muted small">
                        <div className="spinner-border spinner-border-sm" role="status" />
                        Verifying credentials…
                      </div>
                    )}
                  </div>

                  <button
                    type="submit"
                    className="btn btn-success w-100 login-submit-btn"
                    disabled={loading}
                  >
                    <i className="bi bi-box-arrow-in-right me-2" />
                    {loading ? 'Signing in…' : 'Login'}
                  </button>
                </form>

                <small className="text-muted d-block mt-3">
                  Replace the default development admin password after first login.
                </small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
