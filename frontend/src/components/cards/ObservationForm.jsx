import { useCallback, useEffect, useMemo, useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import MpSelect from '../MpSelect'
import api, { apiErrorMessage } from '../../api'

const PRESENCE_OPTIONS = [
  { value: 'present', label: 'Present' },
  { value: 'absent', label: 'Absent' },
  { value: 'not_inspected', label: 'Not inspected' },
]

const METHOD_OPTIONS = [
  { value: 'visual_inspection', label: 'Visual inspection' },
  { value: 'fruit_sampling', label: 'Fruit sampling' },
  { value: 'trap_count', label: 'Trap count' },
  { value: 'other', label: 'Other' },
]

function localDateTimeValue(date = new Date()) {
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

function parseTreeIds(value) {
  return [...new Set(String(value || '')
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean))]
}

function optionalInteger(value) {
  if (value === '' || value == null) return null
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : null
}

function formatObservationTime(value) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value || 'Unknown time'
  return parsed.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export default function ObservationForm({
  orchardId,
  selectedTreeIds = [],
  defaultPest = 'cecid',
  simulationRunId = null,
  forecastRisk = null,
  forecastLeadHours = null,
  observationLon = null,
  observationLat = null,
  embedded = false,
  onSubmitted,
}) {
  const [treeInput, setTreeInput] = useState('')
  const [pest, setPest] = useState(defaultPest)
  const [presence, setPresence] = useState('present')
  const [severity, setSeverity] = useState(0.5)
  const [affectedCount, setAffectedCount] = useState('')
  const [inspectedCount, setInspectedCount] = useState('')
  const [method, setMethod] = useState('visual_inspection')
  const [observer, setObserver] = useState('')
  const [observedAt, setObservedAt] = useState(localDateTimeValue)
  const [notes, setNotes] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [linkForecast, setLinkForecast] = useState(Boolean(simulationRunId))
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [observations, setObservations] = useState([])

  const treeIds = useMemo(() => parseTreeIds(treeInput), [treeInput])
  const affected = optionalInteger(affectedCount)
  const inspected = optionalInteger(inspectedCount)
  const invalidCounts = affected != null && inspected != null && affected > inspected

  useEffect(() => {
    if (!selectedTreeIds?.length) return
    setTreeInput(selectedTreeIds.map(String).join(', '))
  }, [selectedTreeIds])

  useEffect(() => {
    setPest(defaultPest || 'cecid')
  }, [defaultPest])

  useEffect(() => {
    setLinkForecast(Boolean(simulationRunId))
  }, [simulationRunId, selectedTreeIds])

  const loadHistory = useCallback(async () => {
    if (!orchardId) {
      setObservations([])
      return
    }
    setHistoryLoading(true)
    setHistoryError('')
    try {
      const { data } = await api.getObservations({ orchard_id: orchardId, limit: 40 })
      setObservations(Array.isArray(data?.observations) ? data.observations : [])
    } catch (error) {
      setHistoryError(apiErrorMessage(error, 'Unable to load field history.'))
    } finally {
      setHistoryLoading(false)
    }
  }, [orchardId])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!treeIds.length || !orchardId || invalidCounts) return
    setLoading(true)
    setResult(null)
    const common = {
      orchard_id: String(orchardId),
      observed_pest: pest,
      timestamp: new Date(observedAt).toISOString(),
      presence,
      severity: presence === 'present' ? severity : null,
      affected_count: affected,
      inspected_count: inspected,
      method,
      observer_id: observer.trim() || null,
      notes: notes.trim() || null,
      image_url: imageUrl.trim() || null,
      simulation_run_id: linkForecast ? simulationRunId : null,
      forecast_risk: linkForecast && forecastRisk != null ? Number(forecastRisk) : null,
      forecast_lead_hours: (
        linkForecast && Number.isFinite(Number(forecastLeadHours))
          ? Math.max(0, Math.round(Number(forecastLeadHours)))
          : null
      ),
    }
    try {
      if (treeIds.length === 1) {
        await api.submitObservation({
          ...common,
          tree_id: treeIds[0],
          lon: Number.isFinite(Number(observationLon)) ? Number(observationLon) : null,
          lat: Number.isFinite(Number(observationLat)) ? Number(observationLat) : null,
        })
      } else {
        await api.submitObservationsBulk({ ...common, tree_ids: treeIds })
      }
      setResult({
        type: 'success',
        msg: `${treeIds.length} tree${treeIds.length === 1 ? '' : 's'} recorded. The entry was appended to field history.`,
      })
      setNotes('')
      setImageUrl('')
      await loadHistory()
      onSubmitted?.()
    } catch (error) {
      setResult({ type: 'danger', msg: apiErrorMessage(error, 'Observation submission failed.') })
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (observation) => {
    if (!window.confirm(`Delete the field record for tree ${observation.tree_id}? This cannot be undone.`)) return
    try {
      await api.deleteObservation(observation.id)
      await loadHistory()
    } catch (error) {
      setHistoryError(apiErrorMessage(error, 'Unable to delete the field record.'))
    }
  }

  return (
    <CollapsibleCard iconName="clipboard2-check" title="Field Verification" embedded={embedded}>
      <p className="text-muted observation-intro">
        Log what field personnel actually inspected. Records are append-only so forecasts can be compared with later ground truth.
      </p>

      <form onSubmit={handleSubmit}>
        <label className="form-label observation-label" htmlFor="observation-tree-ids">
          Tree ID{treeIds.length > 1 ? 's' : ''}
        </label>
        <input
          id="observation-tree-ids"
          type="text"
          className="form-control form-control-sm"
          placeholder="T05, T06, T07"
          value={treeInput}
          onChange={(event) => setTreeInput(event.target.value)}
        />
        <div className="form-text observation-help">
          Click a tree on the map to prefill it, or separate multiple IDs with commas for a bulk inspection.
        </div>

        <div className="observation-form-grid mt-2">
          <div>
            <label className="form-label observation-label">Pest</label>
            <MpSelect
              small
              value={pest}
              onChange={setPest}
              options={[
                { value: 'cecid', label: 'Cecid Fly' },
                { value: 'fruitfly', label: 'Fruit Fly' },
              ]}
            />
          </div>
          <div>
            <label className="form-label observation-label">Verification</label>
            <MpSelect small value={presence} onChange={setPresence} options={PRESENCE_OPTIONS} />
          </div>
          <div>
            <label className="form-label observation-label">Method</label>
            <MpSelect small value={method} onChange={setMethod} options={METHOD_OPTIONS} />
          </div>
          <div>
            <label className="form-label observation-label" htmlFor="observation-time">Observed at</label>
            <input
              id="observation-time"
              type="datetime-local"
              className="form-control form-control-sm"
              value={observedAt}
              onChange={(event) => setObservedAt(event.target.value)}
              required
            />
          </div>
        </div>

        {presence === 'present' && (
          <div className="mt-2">
            <div className="d-flex justify-content-between align-items-center">
              <label className="form-label observation-label mb-0" htmlFor="observation-severity">Severity</label>
              <strong className="observation-severity-value">{Math.round(severity * 100)}%</strong>
            </div>
            <input
              id="observation-severity"
              type="range"
              className="form-range"
              min={0}
              max={1}
              step={0.05}
              value={severity}
              onChange={(event) => setSeverity(Number(event.target.value))}
            />
          </div>
        )}

        <div className="observation-count-grid">
          <div>
            <label className="form-label observation-label" htmlFor="observation-affected">Affected count</label>
            <input
              id="observation-affected"
              type="number"
              min="0"
              className="form-control form-control-sm"
              value={affectedCount}
              onChange={(event) => setAffectedCount(event.target.value)}
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="form-label observation-label" htmlFor="observation-inspected">Inspected count</label>
            <input
              id="observation-inspected"
              type="number"
              min="0"
              className={`form-control form-control-sm${invalidCounts ? ' is-invalid' : ''}`}
              value={inspectedCount}
              onChange={(event) => setInspectedCount(event.target.value)}
              placeholder="Optional"
            />
          </div>
        </div>
        {invalidCounts && <div className="invalid-feedback d-block">Affected count cannot exceed inspected count.</div>}
        {treeIds.length > 1 && (affected != null || inspected != null) && (
          <div className="form-text observation-help">Counts will be recorded for each selected tree.</div>
        )}

        <label className="form-label observation-label mt-2" htmlFor="observation-observer">Observer</label>
        <input
          id="observation-observer"
          type="text"
          className="form-control form-control-sm"
          placeholder="Name or staff ID (optional)"
          value={observer}
          onChange={(event) => setObserver(event.target.value)}
        />

        <label className="form-label observation-label mt-2" htmlFor="observation-notes">Notes</label>
        <textarea
          id="observation-notes"
          className="form-control form-control-sm"
          rows="2"
          placeholder="Symptoms, sampling details, or treatment notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />

        <label className="form-label observation-label mt-2" htmlFor="observation-image">Photo URL</label>
        <input
          id="observation-image"
          type="url"
          className="form-control form-control-sm"
          placeholder="https://... (optional)"
          value={imageUrl}
          onChange={(event) => setImageUrl(event.target.value)}
        />

        {simulationRunId && (
          <label className="observation-forecast-link mt-2">
            <input
              type="checkbox"
              checked={linkForecast}
              onChange={(event) => setLinkForecast(event.target.checked)}
            />
            <span>
              Link to current forecast <strong>{simulationRunId}</strong>
              {forecastRisk != null && ` (${Math.round(Number(forecastRisk) * 100)}% tree risk)`}
              {Number.isFinite(Number(forecastLeadHours)) && ` · Hour ${Math.round(Number(forecastLeadHours))}`}
            </span>
          </label>
        )}

        <button
          type="submit"
          className="btn btn-success btn-sm w-100 mt-3"
          disabled={loading || !orchardId || !treeIds.length || invalidCounts || !observedAt}
        >
          {loading
            ? <><span className="spinner-border spinner-border-sm me-1" />Recording...</>
            : <><i className="bi bi-clipboard2-check me-1" />Record {treeIds.length || ''} inspection{treeIds.length === 1 ? '' : 's'}</>}
        </button>

        {result && (
          <div className={`alert alert-${result.type} py-2 mt-2 mb-0 observation-result`} role="status">
            {result.msg}
          </div>
        )}
      </form>

      <div className="observation-history-header">
        <div>
          <strong>Recent field history</strong>
          <span>{observations.length} loaded</span>
        </div>
        <button type="button" className="btn btn-sm btn-light" onClick={loadHistory} disabled={historyLoading}>
          <i className={`bi bi-arrow-clockwise${historyLoading ? ' spin' : ''}`} />
          <span className="visually-hidden">Refresh field history</span>
        </button>
      </div>

      {historyError && <div className="alert alert-danger py-2 observation-result">{historyError}</div>}
      {!historyLoading && !observations.length && !historyError && (
        <div className="observation-empty">No field inspections recorded for this orchard yet.</div>
      )}
      <div className="observation-history-list">
        {observations.map((observation) => (
          <article className="observation-history-item" key={observation.id}>
            <div className="observation-history-main">
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <strong>Tree {observation.tree_id}</strong>
                <span className={`observation-presence is-${observation.presence}`}>
                  {String(observation.presence).replace(/_/g, ' ')}
                </span>
                <span className="text-muted">{observation.observed_pest === 'cecid' ? 'Cecid Fly' : 'Fruit Fly'}</span>
              </div>
              <div className="observation-history-meta">
                {formatObservationTime(observation.timestamp)}
                {observation.observer_id && ` · ${observation.observer_id}`}
              </div>
              {(observation.affected_count != null || observation.inspected_count != null) && (
                <div className="observation-history-meta">
                  Count: {observation.affected_count ?? '—'} affected / {observation.inspected_count ?? '—'} inspected
                </div>
              )}
              {observation.simulation_run_id && (
                <div className="observation-history-link">
                  Forecast {observation.simulation_run_id}
                  {observation.forecast_risk != null && ` · ${Math.round(observation.forecast_risk * 100)}% risk`}
                  {observation.forecast_lead_hours != null && ` · ${observation.forecast_lead_hours}h lead`}
                </div>
              )}
            </div>
            <button
              type="button"
              className="btn btn-sm btn-outline-danger observation-delete"
              onClick={() => handleDelete(observation)}
              aria-label={`Delete observation for tree ${observation.tree_id}`}
            >
              <i className="bi bi-trash" />
            </button>
          </article>
        ))}
      </div>
    </CollapsibleCard>
  )
}
