import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import SettingsModal from './SettingsModal'
import { AlertList } from './cards/AlertPanel'

const TABS = [
  { id: 'live-map', label: 'Live Map' },
  { id: 'overview', label: 'Overview' },
  { id: 'crop-impact', label: 'Crop Impact' },
  { id: 'spread-weather', label: 'Spread & Weather' },
  { id: 'history', label: 'History' },
]

export default function Navbar({
  alerts = [],
  alertLoading = false,
  activeTab,
  onTabChange,
  onAlertRefresh,
  onApplySuggested,
  onControlsOpen,
}) {
  const { user, logout } = useAuth()
  const [clock, setClock] = useState('')
  const [bellOpen, setBellOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
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
    const handler = (event) => {
      if (bellRef.current && !bellRef.current.contains(event.target)) setBellOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const active = alerts.filter((alert) => alert.status === 'active')
  const handleApplySuggested = (params) => {
    onApplySuggested?.(params)
    setBellOpen(false)
  }

  return (
    <>
      <nav className="main-navbar">
      <a className="navbar-brand" href="/">
        <img src="/brand/mangopoint-logo-v2.png" className="navbar-logo" alt="" width="40" height="40" />
        <span>MangoPoint</span>
      </a>

      <div className="navbar-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`navbar-tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => onTabChange?.(tab.id)}
          >
            {tab.label}
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

        <button
          type="button"
          className="navbar-controls-btn"
          onClick={onControlsOpen}
          aria-label="Open simulation workspace"
          title="Open controls"
        >
          <i className="bi bi-sliders2" />
          <span>Controls</span>
        </button>

        <button
          type="button"
          className="navbar-settings-btn"
          onClick={() => {
            setBellOpen(false)
            setSettingsOpen(true)
          }}
          aria-label="Open settings"
          title="Settings"
        >
          <i className="bi bi-gear-fill" />
        </button>

        <div className="navbar-bell-wrap" ref={bellRef}>
          <button
            type="button"
            className={`navbar-bell-btn${bellOpen ? ' is-open' : ''}`}
            onClick={() => setBellOpen((open) => !open)}
            aria-label="Notifications"
            aria-expanded={bellOpen}
          >
            <i className="bi bi-bell-fill" />
            {active.length > 0 && <span className="navbar-bell-badge">{active.length}</span>}
          </button>

          {bellOpen && (
            <div className="navbar-bell-dropdown">
              <div className="navbar-bell-header">
                <span><i className="bi bi-bell-fill me-1" />Alerts</span>
                <span className="navbar-bell-count">{active.length} active</span>
              </div>
              <div className="navbar-bell-list navbar-alert-action-list">
                <AlertList
                  alerts={alerts}
                  loading={alertLoading}
                  onRefresh={onAlertRefresh}
                  onApplySuggested={handleApplySuggested}
                />
              </div>
            </div>
          )}
        </div>

        <button type="button" className="navbar-logout-btn" onClick={logout}>
          <i className="bi bi-box-arrow-right me-1" />Logout
        </button>
      </div>
      </nav>
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </>
  )
}
