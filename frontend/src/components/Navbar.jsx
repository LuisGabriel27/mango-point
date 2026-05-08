import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'

const TABS = [
  { id: 'live-map', label: 'Live Map' },
  { id: 'overview', label: 'Overview' },
  { id: 'crop-impact', label: 'Crop Impact' },
  { id: 'spread-weather', label: 'Spread & Weather' },
]

export default function Navbar({ alertCount = 0, activeTab, onTabChange }) {
  const { user, logout } = useAuth()
  const [clock, setClock] = useState('')

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setClock(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <nav className="main-navbar">
      <a className="navbar-brand" href="/">
        <img src="https://img.icons8.com/color/48/mango.png" height="24" alt="" />
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
        {alertCount > 0 && (
          <span className="navbar-alert-badge">
            <i className="bi bi-exclamation-triangle-fill" />
            {alertCount} alert{alertCount !== 1 ? 's' : ''}
          </span>
        )}
        <span className="navbar-clock d-none d-md-inline">{clock}</span>
        {user && (
          <div className="navbar-user d-none d-lg-flex">
            <span className="navbar-username">{user.full_name || user.username}</span>
            <span className="navbar-userrole">{user.role?.toUpperCase()}</span>
          </div>
        )}
        <button type="button" className="navbar-logout-btn" onClick={logout}>
          <i className="bi bi-box-arrow-right me-1" />Logout
        </button>
      </div>
    </nav>
  )
}
