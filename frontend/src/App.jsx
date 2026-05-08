import { Component } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: '2rem', fontFamily: 'monospace', background: '#fff1f2', minHeight: '100vh' }}>
          <h2 style={{ color: '#b91c1c' }}>MangoPoint — Render Error</h2>
          <p style={{ color: '#374151' }}>
            An unexpected error occurred. Open the browser console (F12) for details.
          </p>
          <pre style={{ background: '#fff', border: '1px solid #fca5a5', padding: '1rem', borderRadius: 8, color: '#b91c1c', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {this.state.error?.message}
            {'\n'}
            {this.state.error?.stack}
          </pre>
          <button
            style={{ marginTop: '1rem', padding: '.5rem 1.5rem', background: '#1B4332', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700 }}
            onClick={() => { this.setState({ error: null }); window.location.reload() }}
          >
            Reload page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function RequireAuth({ children }) {
  const { token, loading } = useAuth()

  if (loading) {
    return (
      <div className="d-flex align-items-center justify-content-center" style={{ minHeight: '100vh', background: '#F8F7F4' }}>
        <div className="text-center">
          <div className="spinner-border text-success mb-3" role="status" />
          <h5 className="fw-semibold" style={{ fontFamily: 'Manrope,sans-serif', color: '#1B4332' }}>
            Restoring session
          </h5>
          <p className="text-muted">Validating your MangoPoint access token.</p>
        </div>
      </div>
    )
  }

  return token ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/*"
              element={
                <RequireAuth>
                  <ErrorBoundary>
                    <DashboardPage />
                  </ErrorBoundary>
                </RequireAuth>
              }
            />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  )
}
