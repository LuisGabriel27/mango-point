import { useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import api from '../../api'

const SEV_BADGE = { critical: 'danger', high: 'warning', medium: 'info', low: 'secondary' }

function AlertItem({ alert, onUpdate }) {
  const [ackNotes, setAckNotes] = useState('')
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

  return (
    <div className="border rounded p-2 mb-2" style={{ fontSize: '.8rem' }}>
      <div className="d-flex align-items-start justify-content-between gap-1 mb-1">
        <span className={`badge bg-${SEV_BADGE[alert.severity] ?? 'secondary'}`}>
          {alert.severity?.toUpperCase()}
        </span>
        <small className="text-muted">{ts}</small>
      </div>
      <div className="mb-1">{alert.message}</div>
      {alert.recommended_actions?.length > 0 && (
        <ul className="mb-1 ps-3 text-muted" style={{ fontSize: '.75rem' }}>
          {alert.recommended_actions.slice(0, 2).map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      )}
      <div className="d-flex gap-1 flex-wrap mt-1">
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

export default function AlertPanel({ alerts = [], loading, onRefresh }) {
  const active = alerts.filter((a) => a.status === 'active')

  const badge = active.length > 0 ? (
    <span className="badge bg-danger rounded-pill ms-1">{active.length}</span>
  ) : null

  return (
    <CollapsibleCard
      iconName="exclamation-triangle"
      title="Alerts"
      headerExtra={badge}
    >
      {loading ? (
        <div className="text-muted small"><span className="spinner-border spinner-border-sm me-1" />Loading…</div>
      ) : active.length === 0 ? (
        <div className="text-muted small">
          <i className="bi bi-check-circle me-1 text-success" />No active alerts
        </div>
      ) : (
        active.map((a) => (
          <AlertItem key={a.alert_id} alert={a} onUpdate={onRefresh} />
        ))
      )}
      <small className="text-muted d-block mt-2">
        <i className="bi bi-arrow-repeat me-1" />Auto-refreshes every 30 s
      </small>
    </CollapsibleCard>
  )
}
