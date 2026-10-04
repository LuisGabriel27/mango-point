import CollapsibleCard from '../CollapsibleCard'

const ZONE_COLORS = {
  zone_1: '#22c55e',
  zone_2: '#facc15',
  zone_3: '#ef4444',
}

function pct(v) { return v != null ? `${(v * 100).toFixed(1)}%` : '—' }
function php(v) {
  if (v == null) return '—'
  if (v >= 1_000_000) return `PHP ${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `PHP ${(v / 1_000).toFixed(0)}K`
  return `PHP ${v.toFixed(0)}`
}

function priorityColor(p) {
  const k = (p ?? '').toLowerCase()
  if (k === 'urgent') return 'danger'
  if (k === 'high') return 'warning'
  if (k === 'medium') return 'info'
  return 'success'
}

function count(v) {
  const value = Number(v)
  if (!Number.isFinite(value)) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

export default function DecisionSupportCard({ metrics, defaultOpen = true, embedded = false }) {
  if (!metrics) {
    return (
      <CollapsibleCard
        iconName="clipboard2-pulse"
        title="Decision Support"
        defaultOpen={defaultOpen}
        embedded={embedded}
        cardClass="decision-support-card"
      >
        <div className="text-muted small">
          <i className="bi bi-info-circle me-1" />Run a simulation to generate decision support metrics.
        </div>
      </CollapsibleCard>
    )
  }

  const zones = metrics.zones ?? {}
  const economic = metrics.economic ?? {}
  const actions = metrics.action_plan ?? []
  const cecid = metrics.cecid ?? null
  const uncertainty = cecid?.uncertainty ?? null

  return (
    <CollapsibleCard
      iconName="clipboard2-pulse"
      title="Decision Support"
      defaultOpen={defaultOpen}
      embedded={embedded}
      cardClass="decision-support-card"
      cardStyle={{ boxShadow: 'inset 3px 0 0 var(--mp-primary), var(--mp-shadow-card)' }}
    >
      {cecid && (
        <>
          <div className="alert alert-info py-2 mb-2" style={{ fontSize: '.79rem' }}>
            <div className="fw-semibold mb-1">
              <i className="bi bi-bug me-1" />Cecid result interpretation
            </div>
            <div className="d-flex justify-content-between gap-2">
              <span>Established on eligible fruitlet trees</span>
              <strong>
                {count(cecid.establishedTreeCount)} / {count(cecid.eligibleTreeCount)}
                {cecid.establishedEligibleRate != null ? ` (${pct(cecid.establishedEligibleRate)})` : ''}
              </strong>
            </div>
            <div className="d-flex justify-content-between gap-2">
              <span>Maximum reachable in an eligible hour</span>
              <strong>{count(cecid.reachableTreeCount)}</strong>
            </div>
            <div className="d-flex justify-content-between gap-2">
              <span>Soil sources / emergence events</span>
              <strong>{count(cecid.sourceCount)} / {count(cecid.cohortEventCount)}</strong>
            </div>
            {cecid.externalNeighborTreeCount > 0 && (
              <div className="d-flex justify-content-between gap-2">
                <span>Trees exposed to external pressure</span>
                <strong>{count(cecid.externalNeighborTreeCount)}</strong>
              </div>
            )}
            {Number(uncertainty?.runs) > 1 && (
              <div className="mt-2 pt-2 border-top border-info-subtle">
                <div className="d-flex justify-content-between gap-2">
                  <span>{count(uncertainty.runs)}-run scenario range</span>
                  <strong>{count(uncertainty.minimum)}–{count(uncertainty.maximum)} trees</strong>
                </div>
                <div className="text-muted">
                  Median {count(uncertainty.median)}. This reflects unknown source placement and random establishment; it is not a calibrated confidence interval.
                </div>
              </div>
            )}
            <div className="text-muted mt-1">
              Reachable means exposed to adult pressure, not automatically infested. Zone percentages below use all {count(cecid.orchardTreeCount)} orchard trees.
            </div>
          </div>
          <hr className="my-2" />
        </>
      )}

      {/* Thresholds */}
      <div className="mb-2">
        <small className="text-muted">
          <i className="bi bi-sliders2 me-1" />
          Thresholds: &lt;20% (Safe) | ≥60% (Critical)
        </small>
      </div>
      <hr className="my-2" />

      {/* Zone classification */}
      <small className="d-block mb-2">
        <i className="bi bi-layers me-1" /><strong>Zone Classification</strong>
      </small>
      {[
        { key: 'zone_1', label: 'Zone 1: No Action', valueKey: 'zone_1_pct' },
        { key: 'zone_2', label: 'Zone 2: Monitor', valueKey: 'zone_2_pct' },
        { key: 'zone_3', label: 'Zone 3: Targeted Action', valueKey: 'zone_3_pct' },
      ].map(({ key, label, valueKey }) => (
        <div key={key} className="d-flex justify-content-between align-items-center py-1">
          <div className="d-flex align-items-center">
            <span style={{
              display: 'inline-block', width: 16, height: 16,
              backgroundColor: ZONE_COLORS[key], marginRight: 8,
              borderRadius: 3, border: key === 'zone_3' ? '2px solid #7f1d1d' : '2px solid transparent',
            }} />
            <span className="fw-medium" style={{ fontSize: '.82rem' }}>{label}</span>
          </div>
          <span className="fw-bold" style={{ fontSize: '.82rem' }}>{pct(zones[valueKey])}</span>
        </div>
      ))}

      <hr className="my-2" />

      {/* Economic impact */}
      <small className="d-block mb-2">
        <i className="bi bi-piggy-bank me-1" /><strong>Economic Impact</strong>
      </small>
      {metrics.economic ? (
        <>
          <div className="d-flex justify-content-between align-items-center py-1">
            <span className="text-muted small"><i className="bi bi-graph-down-arrow me-1" />Projected Loss at Risk</span>
            <span className="fw-semibold text-danger">{php(economic.projected_loss)}</span>
          </div>
          <div className="d-flex justify-content-between align-items-center py-1">
            <span className="text-muted small"><i className="bi bi-piggy-bank me-1" />Potential Savings</span>
            <span className="fw-bold text-success">{php(economic.estimated_savings)}</span>
          </div>
          <div className="d-flex justify-content-between align-items-center py-1">
            <span className="text-muted small"><i className="bi bi-cash-coin me-1" />Remaining Loss</span>
            <span className="fw-semibold">{php(economic.remaining_loss)}</span>
          </div>
          <div className="d-flex justify-content-between align-items-center py-1">
            <span className="text-muted small"><i className="bi bi-arrows-collapse me-1" />Pesticide Use Avoided</span>
            <span className="badge bg-success">{pct(economic.pesticide_reduction)}</span>
          </div>
          <small className="text-muted d-block mt-2">
            Assumes the recommendations prevent {pct(economic.recommendation_effectiveness)} of the projected base-scenario damage. Treatment and labor costs are not subtracted.
          </small>
        </>
      ) : (
        <div className="text-muted small">Economic inputs were not recorded for this result.</div>
      )}

      {/* Summary message */}
      {metrics.summary_message && (
        <div className="alert alert-info py-2 mt-2" style={{ fontSize: '.83rem' }}>
          {metrics.summary_message}
        </div>
      )}

      <hr className="my-2" />

      {/* Action plan */}
      <small className="d-block mb-2">
        <i className="bi bi-list-check me-1" /><strong>Action Plan</strong>
      </small>
      {actions.length === 0 ? (
        <div className="text-muted small">No action plan generated for the latest map.</div>
      ) : (
        <div>
          {actions.map((item, i) => (
            <div key={i} className="decision-action-item py-2">
              <div className="d-flex justify-content-between align-items-start gap-2">
                <div className="flex-grow-1 pe-2">
                  <span className="fw-semibold">{item.title}</span>
                  <small className="text-muted d-block">
                    <i className="bi bi-clock me-1" />{item.timing}
                  </small>
                </div>
                <span className={`badge bg-${priorityColor(item.priority)} decision-action-priority`}>
                  {item.priority || 'Routine'}
                </span>
              </div>
              <small className="text-muted d-block mt-1">
                <i className="bi bi-geo-alt me-1" />
                {item.scope_label} | Peak risk {((item.max_risk ?? 0) * 100).toFixed(0)}%
              </small>
              {item.recommended_steps?.slice(0, 3).length > 0 && (
                <ul className="decision-action-steps small mb-1 mt-2">
                  {item.recommended_steps.slice(0, 3).map((s, j) => <li key={j}>{s}</li>)}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      <small className="text-muted d-block mt-2">
        <i className="bi bi-info-circle me-1" />Updates automatically after each simulation
      </small>
    </CollapsibleCard>
  )
}
