function KpiCard({ iconName, iconColor, title, value, detail }) {
  return (
    <div className="col-12 col-md-4">
      <div className="card shadow-sm border-0 h-100 monitoring-kpi-card">
        <div className="card-body p-3">
          <div className="d-flex align-items-start gap-3">
            <div className="monitoring-kpi-icon">
              <i className={`bi bi-${iconName} ${iconColor} fs-4`} />
            </div>
            <div className="flex-grow-1">
              <p className="monitoring-kpi-label text-muted mb-1">{title}</p>
              <h3 className="monitoring-kpi-value mb-1 fw-bold">{value ?? '—'}</h3>
              <div className="monitoring-kpi-detail">{detail}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function riskBadge(score) {
  if (score == null) return <span className="badge bg-secondary">—</span>
  const v = score * 100
  if (v >= 70) return <span className="badge bg-danger">Critical</span>
  if (v >= 50) return <span className="badge bg-warning text-dark">High</span>
  if (v >= 30) return <span className="badge bg-info text-dark">Moderate</span>
  return <span className="badge bg-success">Low</span>
}

export default function OverviewTab({ monitoringData, simData, totalTrees: totalTreesProp = 0 }) {
  const m = monitoringData ?? {}

  // Simulation data takes priority over monitoring DB data
  const infestedFinal = simData?.n_infested_final ?? null
  // totalTrees: prefer the real geojson count passed from parent (works without DB trees),
  // fall back to what the monitoring API returns from the DB tree table
  const totalTrees = totalTreesProp > 0 ? totalTreesProp : (m.infestation_rate?.total_trees ?? 0)

  // Infestation rate: compute from sim result if available
  const infestRateVal = infestedFinal != null && totalTrees > 0
    ? infestedFinal / totalTrees
    : (m.infestation_rate?.rate ?? null)
  const infestRate = infestRateVal != null ? `${(infestRateVal * 100).toFixed(1)}%` : '—'
  const infestRatePct = infestRateVal != null ? `${(infestRateVal * 100).toFixed(1)}%` : '0%'

  // Risk score: prefer simulation peak_risk, fallback to monitoring risk_index
  const riskScoreVal = simData?.peak_risk ?? m.risk_index?.score ?? null
  const riskScore = riskScoreVal != null ? `${(riskScoreVal * 100).toFixed(1)}%` : '—'

  const infestedTrees = infestedFinal ?? m.infestation_rate?.infested_trees ?? 0
  const activeAlerts = m.alert_summary?.active ?? 0

  const lossBase = infestedFinal != null
    ? `PHP ${((infestedFinal * 45 * 60 * 0.30) / 1000).toFixed(0)}K (est.)`
    : '—'

  // Susceptible stage: prefer sim metadata stage_breakdown, fallback to monitoring phenology
  const susceptible = (() => {
    const sb = simData?.metadata?.stage_breakdown
    if (sb && Object.keys(sb).length) {
      const total = Object.values(sb).reduce((s, v) => s + (v ?? 0), 0)
      const sus = (sb.fruitlet ?? 0) + (sb.mature ?? 0)
      return total > 0 ? `${Math.round((sus / total) * 100)}%` : '—'
    }
    const rows = Array.isArray(m.phenology) ? m.phenology : []
    if (!rows.length) return '—'
    const total = rows.reduce((s, r) => s + (r.count ?? 0), 0)
    const sus = rows
      .filter((r) => ['fruitlet', 'mature'].includes(r.stage))
      .reduce((s, r) => s + (r.count ?? 0), 0)
    return total > 0 ? `${Math.round((sus / total) * 100)}%` : '—'
  })()

  // Simulation peak hour (from last time series frame)
  const peakHour = simData?.time_series?.length
    ? simData.time_series[simData.time_series.length - 1]?.hour ?? null
    : null

  return (
    <div className="row g-3 p-3">
      <KpiCard
        iconName="virus" iconColor="text-danger"
        title="Infestation rate"
        value={infestRate}
        detail={
          <div className="mt-2">
            <div className="progress" style={{ height: 6 }}>
              <div className="progress-bar bg-danger" style={{ width: infestRatePct }} />
            </div>
            {infestedFinal != null && (
              <small className="text-muted">{infestedFinal} of {totalTrees || '?'} trees</small>
            )}
          </div>
        }
      />
      <KpiCard
        iconName="speedometer2" iconColor="text-warning"
        title="Peak risk score"
        value={riskScore}
        detail={
          <div className="mt-2 monitoring-risk-badge">
            {riskBadge(riskScoreVal)}
            {simData?.peak_risk != null && (
              <small className="text-muted d-block mt-1">from simulation</small>
            )}
          </div>
        }
      />
      <KpiCard
        iconName="tree-fill" iconColor="text-danger"
        title="Infested trees"
        value={infestedTrees}
        detail={
          <small className="text-muted">
            {infestedFinal != null
              ? `after ${peakHour != null ? `${peakHour}h` : 'simulation'}`
              : 'from monitoring data'}
          </small>
        }
      />
      <KpiCard
        iconName="bell-fill" iconColor="text-danger"
        title="Active alerts"
        value={activeAlerts}
        detail={
          m.alert_summary ? (
            <small className="text-muted">
              {m.alert_summary.by_severity?.critical ?? 0} critical · {m.alert_summary.by_severity?.high ?? 0} high
            </small>
          ) : null
        }
      />
      <KpiCard
        iconName="cash-coin" iconColor="text-success"
        title="Estimated loss at risk"
        value={lossBase}
        detail={<small className="text-muted">base scenario (30% damage rate)</small>}
      />
      <KpiCard
        iconName="flower1" iconColor="text-primary"
        title="Susceptible stage exposure"
        value={susceptible}
        detail={<small className="text-muted">fruitlet + mature trees</small>}
      />

      {simData && (
        <div className="col-12">
          <div className="card border-0 shadow-sm">
            <div className="card-body p-3">
              <div className="d-flex flex-wrap gap-3 small">
                <span><i className="bi bi-cpu me-1 text-primary" /><strong>Mode:</strong> {simData.metadata?.simulation_mode ?? simData.simulation_mode ?? '—'}</span>
                <span><i className="bi bi-bug me-1 text-danger" /><strong>Pest:</strong> {simData.pest_type ?? '—'}</span>
                <span><i className="bi bi-clock me-1" /><strong>Duration:</strong> {simData.hours ?? '—'} h</span>
                <span><i className="bi bi-grid me-1" /><strong>Cells at risk:</strong> {simData.cells_at_risk ?? '—'}</span>
                <span><i className="bi bi-flower1 me-1 text-success" /><strong>Stage:</strong> {simData.metadata?.orchard_stage ?? '—'}</span>
                {simData.metadata?.neighbor_threat > 0 && (
                  <span><i className="bi bi-exclamation-triangle me-1 text-warning" /><strong>Neighbor pressure:</strong> {simData.metadata.neighbor_threat}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
