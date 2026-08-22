import { useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import api from '../../api'

const SEV_BADGE = { critical: 'danger', high: 'warning', medium: 'info', low: 'secondary' }

export function AlertItem({ alert, onUpdate, onApplySuggested }) {
  const [ackNotes] = useState('')
  const [acting, setActing] = useState(false)

  const handleAck = async () => {
    setActing(true)
    try {
      await api.acknowledgeAlert(alert.alert_id, { acknowledged_by: 'dashboard', notes: ackNotes })
      onUpdate()
    } finally { setActing(false) }
  }

  const handleResolve = async () => {
    setActing(true)
    try {
      await api.resolveAlert(alert.alert_id)
      onUpdate()
    } finally { setActing(false) }
  }

  const ts = alert.triggered_at
    ? new Date(alert.triggered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''
  const isWeatherAlert = alert.zone_name?.toLowerCase().includes('weather forecast')

  return (
    <div
      className={`border rounded p-2 mb-2${isWeatherAlert ? ' border-primary border-opacity-50' : ''}`}
      style={{ fontSize: '.8rem' }}
    >
      <div className="d-flex align-items-start justify-content-between gap-1 mb-1">
        <div className="d-flex align-items-center gap-1">
          {isWeatherAlert && <i className="bi bi-cloud-rain-fill text-primary" style={{ fontSize: '.85rem' }} />}
          <span className={`badge bg-${SEV_BADGE[alert.severity] ?? 'secondary'}`}>
            {alert.severity?.toUpperCase()}
          </span>
          {alert.email_sent && (
            <span
              className="badge bg-success-subtle text-success-emphasis border border-success-subtle"
              title="Email delivered to the designated farmers"
            >
              <i className="bi bi-envelope-check me-1" />Emailed
            </span>
          )}
        </div>
        <small className="text-muted">{ts}</small>
      </div>
      <div className="mb-1">{alert.message}</div>
      {alert.recommended_actions?.length > 0 && (
        <ul className="mb-1 ps-3 text-muted" style={{ fontSize: '.75rem' }}>
          {alert.recommended_actions.slice(0, 2).map((action, index) => <li key={index}>{action}</li>)}
        </ul>
      )}
      <div className="d-flex gap-1 flex-wrap mt-1">
        {alert.suggested_simulation_params && onApplySuggested && (
          <button
            type="button"
            className="btn btn-primary btn-sm py-0 fw-semibold"
            onClick={() => onApplySuggested(alert.suggested_simulation_params)}
          >
            <i className="bi bi-play-circle me-1" />Pre-fill Simulation
          </button>
        )}
        {alert.status === 'active' && (
          <button type="button" className="btn btn-outline-secondary btn-sm py-0"
            disabled={acting} onClick={handleAck}>
            Acknowledge
          </button>
        )}
        {alert.status !== 'resolved' && (
          <button type="button" className="btn btn-outline-success btn-sm py-0"
            disabled={acting} onClick={handleResolve}>
            Resolve
          </button>
        )}
      </div>
    </div>
  )
}

export function AlertList({ alerts = [], loading, onRefresh, onApplySuggested }) {
  const active = alerts.filter((alert) => alert.status === 'active')

  if (loading) {
    return <div className="text-muted small"><span className="spinner-border spinner-border-sm me-1" />Loading…</div>
  }
  if (active.length === 0) {
    return (
      <div className="text-muted small">
        <i className="bi bi-check-circle me-1 text-success" />No active alerts
      </div>
    )
  }
  return active.map((alert) => (
    <AlertItem
      key={alert.alert_id}
      alert={alert}
      onUpdate={onRefresh}
      onApplySuggested={onApplySuggested}
    />
  ))
}

export default function AlertPanel({ alerts = [], loading, onRefresh, onApplySuggested }) {
  const active = alerts.filter((alert) => alert.status === 'active')
  const badge = active.length > 0 ? (
    <span className="badge bg-danger rounded-pill ms-1">{active.length}</span>
  ) : null

  return (
    <CollapsibleCard iconName="exclamation-triangle" title="Alerts" headerExtra={badge}>
      <AlertList
        alerts={alerts}
        loading={loading}
        onRefresh={onRefresh}
        onApplySuggested={onApplySuggested}
      />
    </CollapsibleCard>
  )
}
