import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'

const TABS = [
  { id: 'live-map', label: 'Live Map' },
  { id: 'overview', label: 'Overview' },
  { id: 'crop-impact', label: 'Crop Impact' },
  { id: 'spread-weather', label: 'Spread & Weather' },
  { id: 'history', label: 'History' },
]

const SEV_COLOR = { critical: '#dc2626', high: '#d97706', medium: '#2563eb', low: '#6b7280' }
const SEV_ICON  = { critical: 'exclamation-octagon-fill', high: 'exclamation-triangle-fill', medium: 'info-circle-fill', low: 'bell-fill' }

export default function Navbar({ alertCount = 0, alerts = [], activeTab, onTabChange }) {
  const { user, logout } = useAuth()
  const [clock, setClock] = useState('')
  const [bellOpen, setBellOpen] = useState(false)
  const bellRef = useRef(null)

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const handler = (e) => {
      if (bellRef.current && !bellRef.current.contains(e.target)) setBellOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const active = alerts.filter((a) => a.status === 'active')

  return (
    <nav className="main-navbar">
      <a className="navbar-brand" href="/">
        <img src="/mangopoint.png" className="navbar-logo" alt="MangoPoint" />
        <span>MangoPoint</span>
      </a>

      <div className="navbar-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`navbar-tab${activeTab === t.id ? ' active' : ''}`}
            onClick={() => onTabChange?.(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="navbar-controls">
        <span className="navbar-clock d-none d-md-inline">{clock}</span>
        {user && (
          <div className="navbar-user d-none d-lg-flex">
            <span className="navbar-username">{user.full_name || user.username}</span>
            <span className="navbar-userrole">{user.role?.toUpperCase()}</span>
          </div>
        )}

        {/* Notification bell */}
        <div className="navbar-bell-wrap" ref={bellRef}>
          <button
            type="button"
            className={`navbar-bell-btn${bellOpen ? ' is-open' : ''}`}
            onClick={() => setBellOpen((o) => !o)}
            aria-label="Notifications"
          >
            <i className="bi bi-bell-fill" />
            {active.length > 0 && (
              <span className="navbar-bell-badge">{active.length}</span>
            )}
          </button>

          {bellOpen && (
            <div className="navbar-bell-dropdown">
              <div className="navbar-bell-header">
                <span><i className="bi bi-bell-fill me-1" />Alerts</span>
                <span className="navbar-bell-count">{active.length} active</span>
              </div>
              <div className="navbar-bell-list">
                {active.length === 0 ? (
                  <div className="navbar-bell-empty">
                    <i className="bi bi-check-circle-fill text-success me-1" />
                    No active alerts
                  </div>
                ) : (
                  active.map((a) => {
                    const ts = a.triggered_at
                      ? new Date(a.triggered_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                      : ''
                    return (
                      <div key={a.alert_id} className="navbar-bell-item">
                        <div className="navbar-bell-item-top">
                          <i
                            className={`bi bi-${SEV_ICON[a.severity] ?? 'bell-fill'} me-1`}
                            style={{ color: SEV_COLOR[a.severity] ?? '#6b7280' }}
                          />
                          <span className="navbar-bell-sev" style={{ color: SEV_COLOR[a.severity] ?? '#6b7280' }}>
                            {a.severity?.toUpperCase()}
                          </span>
                          <span className="navbar-bell-ts">{ts}</span>
                        </div>
                        <div className="navbar-bell-msg">{a.message}</div>
                        {a.zone_name && (
                          <div className="navbar-bell-zone">
                            <i className="bi bi-geo-alt me-1" />{a.zone_name}
                          </div>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          )}
        </div>

        <button type="button" className="navbar-logout-btn" onClick={logout}>
          <i className="bi bi-box-arrow-right me-1" />Logout
        </button>
      </div>
    </nav>
  )
}
