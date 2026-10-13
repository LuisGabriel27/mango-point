import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import SettingsModal from './SettingsModal'
import WorkflowTutorial from './tutorial/WorkflowTutorial'
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
  alertError = '',
  activeTab,
  onTabChange,
  onAlertRefresh,
  onApplySuggested,
  onControlsOpen,
  tutorialProps,
}) {
  const { user, logout } = useAuth()
  const [bellOpen, setBellOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const bellRef = useRef(null)
  const tutorialPanel = tutorialProps?.presentation?.navbarPanel
  const bellDisplayed = bellOpen || tutorialPanel === 'notifications'
  const settingsDisplayed = settingsOpen || tutorialPanel === 'settings'

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
      <nav className="main-navbar" inert={tutorialProps?.presentation ? "" : undefined}>
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
        {tutorialProps && <WorkflowTutorial user={user} {...tutorialProps} />}
        {user && (
          <div className="navbar-user d-none d-lg-flex">
            <span className="navbar-username">{user.full_name || user.username}</span>
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
          data-tour="settings"
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
            className={`navbar-bell-btn${bellDisplayed ? ' is-open' : ''}`}
            onClick={() => {
              if (!bellOpen) onAlertRefresh?.()
              setBellOpen((open) => !open)
            }}
            data-tour="alerts"
            aria-label="Notifications"
            aria-expanded={bellDisplayed}
          >
            <i className="bi bi-bell-fill" />
            {active.length > 0 && <span className="navbar-bell-badge">{active.length}</span>}
          </button>

          {bellDisplayed && (
            <div
              className={`navbar-bell-dropdown${tutorialPanel === 'notifications' ? ' is-tutorial-target' : ''}`}
              data-tour="notification-list"
            >
              <div className="navbar-bell-header">
                <span><i className="bi bi-bell-fill me-1" />Alerts</span>
                <div className="d-flex align-items-center gap-2">
                  <span className="navbar-bell-count">{active.length} active</span>
                  <button type="button" className="btn btn-sm btn-outline-light py-0 px-1" aria-label="Refresh notifications" onClick={onAlertRefresh} disabled={alertLoading}>
                    <i className={`bi ${alertLoading ? 'bi-hourglass-split' : 'bi-arrow-clockwise'}`} aria-hidden="true" />
                  </button>
                </div>
              </div>
              <div className="navbar-bell-list navbar-alert-action-list">
                <AlertList
                  alerts={alerts}
                  loading={alertLoading}
                  error={alertError}
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
      {settingsDisplayed && <SettingsModal
        key={tutorialPanel === 'settings' ? tutorialProps?.presentation?.settingsTab : 'manual'}
        tutorialTab={tutorialPanel === 'settings' ? tutorialProps?.presentation?.settingsTab : null}
        onClose={() => { if (tutorialPanel !== 'settings') setSettingsOpen(false) }}
      />}
    </>
  )
}
