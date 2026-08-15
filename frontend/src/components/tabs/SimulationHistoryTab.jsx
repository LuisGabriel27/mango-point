import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import api, { apiErrorMessage } from '../../api'
import MpSelect from '../MpSelect'
import {
  getSimulationRunFromHistory,
  listSimulationRunsFromHistory,
  saveSimulationRunToHistory,
} from '../../utils/simulationHistoryStore'

const DEFAULT_ORCHARD_ID = 'default-orchard'
const DEFAULT_ORCHARD_LABEL = 'Default Orchard (BPI)'
const ALL_ORCHARDS = 'all'

const HISTORY_GROUP_OPTIONS = [
  { value: 'all', label: 'All dates' },
  { value: 'day', label: 'By day' },
  { value: 'week', label: 'By week' },
  { value: 'month', label: 'By month' },
]

function formatDate(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function percent(value) {
  if (value == null || Number.isNaN(Number(value))) return '--'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function pestLabel(value) {
  const v = String(value ?? '').toLowerCase()
  if (v === 'fruitfly') return 'Fruit Fly'
  if (v === 'cecid') return 'Cecid Fly'
  return value || '--'
}

function modeLabel(value) {
  const v = String(value ?? '').toLowerCase()
  if (v === 'tree_graph') return 'Tree Graph'
  if (v === 'grid') return 'Grid (CA)'
  return value || '--'
}

function filenameFromDisposition(header, fallback) {
  const match = /filename="?([^"]+)"?/i.exec(header || '')
  return match?.[1] || fallback
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function runTime(value) {
  const time = new Date(value ?? 0).getTime()
  return Number.isFinite(time) ? time : 0
}

function validRunDate(run) {
  if (!run?.started_at) return null
  const date = new Date(run.started_at)
  return Number.isNaN(date.getTime()) ? null : date
}

function startOfWeek(date) {
  const result = new Date(date)
  result.setHours(0, 0, 0, 0)
  const daysSinceMonday = (result.getDay() + 6) % 7
  result.setDate(result.getDate() - daysSinceMonday)
  return result
}

function historyGroupForRun(run, grouping) {
  const date = validRunDate(run)
  if (!date) return { key: 'unknown', label: 'Unknown date' }

  if (grouping === 'day') {
    return {
      key: `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`,
      label: date.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }),
    }
  }

  if (grouping === 'week') {
    const weekStart = startOfWeek(date)
    return {
      key: weekStart.toISOString().slice(0, 10),
      label: `Week of ${weekStart.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}`,
    }
  }

  return {
    key: `${date.getFullYear()}-${date.getMonth()}`,
    label: date.toLocaleDateString([], { year: 'numeric', month: 'long' }),
  }
}

function groupRuns(runs, grouping) {
  if (grouping === 'all') return [{ key: 'all', label: null, runs }]

  const groups = new Map()
  runs.forEach((run) => {
    const group = historyGroupForRun(run, grouping)
    if (!groups.has(group.key)) groups.set(group.key, { ...group, runs: [] })
    groups.get(group.key).runs.push(run)
  })
  return [...groups.values()]
}

function mergeRuns(apiRuns = [], cachedRuns = []) {
  const byId = new Map()

  for (const run of cachedRuns) {
    if (run?.run_id) byId.set(run.run_id, run)
  }

  for (const run of apiRuns) {
    if (!run?.run_id) continue
    const cached = byId.get(run.run_id)
    byId.set(run.run_id, {
      ...cached,
      ...run,
      cached_locally: Boolean(cached?.cached_locally),
    })
  }

  return [...byId.values()].sort((a, b) => (
    runTime(b.started_at || b.local_saved_at) - runTime(a.started_at || a.local_saved_at)
  ))
}

export default function SimulationHistoryTab({
  orchards = [],
  refreshKey = 0,
  onLoadRun,
  onUseTemplate,
}) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingRunId, setLoadingRunId] = useState(null)
  const [exportingRunId, setExportingRunId] = useState(null)
  const [exportingHistory, setExportingHistory] = useState(false)
  const [syncingToSupabase, setSyncingToSupabase] = useState(false)
  const [historyOrchardId, setHistoryOrchardId] = useState(ALL_ORCHARDS)
  const [historyGrouping, setHistoryGrouping] = useState('all')
  const [status, setStatus] = useState(null)

  const historyOrchardOptions = useMemo(() => {
    const options = [
      { value: ALL_ORCHARDS, label: 'All orchards' },
      { value: DEFAULT_ORCHARD_ID, label: DEFAULT_ORCHARD_LABEL },
    ]
    const seen = new Set(options.map((option) => option.value))
    orchards.forEach((orchard) => {
      const value = orchard?.orchard_id
      if (!value || seen.has(value)) return
      seen.add(value)
      options.push({ value, label: orchard.name || value })
    })
    return options
  }, [orchards])

  const selectedHistoryOrchardName = useMemo(
    () => historyOrchardOptions.find((option) => option.value === historyOrchardId)?.label
      ?? historyOrchardId,
    [historyOrchardId, historyOrchardOptions],
  )

  const groupedRuns = useMemo(
    () => groupRuns(runs, historyGrouping),
    [runs, historyGrouping],
  )

  const orchardLabel = (runOrchardId) => {
    if (runOrchardId === DEFAULT_ORCHARD_ID) return DEFAULT_ORCHARD_LABEL
    return historyOrchardOptions.find((option) => option.value === runOrchardId)?.label
      ?? runOrchardId
      ?? '--'
  }

  const fetchRuns = useCallback(async () => {
    setLoading(true)
    setStatus(null)
    setRuns([])
    let cachedRuns = []
    const selectedOrchardId = historyOrchardId === ALL_ORCHARDS ? undefined : historyOrchardId

    try {
      cachedRuns = await listSimulationRunsFromHistory({ orchardId: selectedOrchardId, limit: 1000 })
      if (cachedRuns.length) setRuns(cachedRuns)
    } catch (_) {
      cachedRuns = []
    }

    try {
      const params = { limit: 1000 }
      if (selectedOrchardId) params.orchard_id = selectedOrchardId
      const res = await api.getSimulationRuns(params)
      setRuns(mergeRuns(res.data?.runs ?? [], cachedRuns))
    } catch (err) {
      if (cachedRuns.length) {
        setStatus({
          type: 'warning',
          msg: `${apiErrorMessage(err, 'Could not load server history.')} Showing saved browser history.`,
        })
      } else {
        setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not load simulation history.') })
      }
    } finally {
      setLoading(false)
    }
  }, [historyOrchardId])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns, refreshKey])

  const fetchRunDetails = async (runId) => {
    setLoadingRunId(runId)
    setStatus(null)
    try {
      const res = await api.getSimulationRun(runId)
      saveSimulationRunToHistory(res.data).catch(() => {})
      return res.data
    } catch (err) {
      const cached = await getSimulationRunFromHistory(runId)
      if (cached) {
        setStatus({ type: 'warning', msg: 'Loaded this simulation from saved browser history.' })
        return cached
      }
      setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not load saved simulation.') })
      return null
    } finally {
      setLoadingRunId(null)
    }
  }

  const handleLoad = async (runId) => {
    const data = await fetchRunDetails(runId)
    if (!data) return
    onLoadRun?.(data)
    setStatus({ type: 'success', msg: 'Saved simulation loaded into the dashboard.' })
  }

  const handleTemplate = async (runId) => {
    const data = await fetchRunDetails(runId)
    if (!data) return
    onUseTemplate?.(data.request_payload ?? data.input_parameters ?? {})
    setStatus({ type: 'success', msg: 'Saved parameters copied into the simulation controls.' })
  }

  const handleExportHistory = async () => {
    setExportingHistory(true)
    setStatus(null)
    try {
      const params = { period: 'all', limit: 5000 }
      if (historyOrchardId !== ALL_ORCHARDS) params.orchard_id = historyOrchardId
      const res = await api.exportSimulationRuns(params)
      const fallback = 'mangopoint_simulation_history.xlsx'
      downloadBlob(res.data, filenameFromDisposition(res.headers['content-disposition'], fallback))
      setStatus({ type: 'success', msg: 'History export downloaded.' })
    } catch (err) {
      setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not export simulation history.') })
    } finally {
      setExportingHistory(false)
    }
  }

  const handleSyncToSupabase = async () => {
    setSyncingToSupabase(true)
    setStatus(null)
    try {
      const res = await api.runSupabaseSync()
      const result = res.data ?? {}
      const processed = Number(result.processed ?? 0)
      const succeeded = Number(result.succeeded ?? 0)
      const skipped = Number(result.skipped ?? 0)
      const failed = Number(result.failed ?? 0)
      const pending = Number(result.pending_events ?? 0)

      if (result.message && processed === 0) {
        setStatus({
          type: result.configured ? 'warning' : 'danger',
          msg: result.message,
        })
        return
      }

      const details = [
        `${succeeded} pushed`,
        skipped ? `${skipped} skipped` : null,
        failed ? `${failed} failed` : null,
        `${pending} pending`,
      ].filter(Boolean).join(' · ')

      setStatus({
        type: failed ? 'warning' : 'success',
        msg: `Supabase sync complete (${details}).`,
      })
    } catch (err) {
      setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not sync with Supabase.') })
    } finally {
      setSyncingToSupabase(false)
    }
  }

  const handleExportRun = async (runId) => {
    setExportingRunId(runId)
    setStatus(null)
    try {
      const res = await api.exportSimulationRun(runId)
      downloadBlob(res.data, filenameFromDisposition(res.headers['content-disposition'], `mangopoint_simulation_${runId}.xlsx`))
      setStatus({ type: 'success', msg: 'Simulation export downloaded.' })
    } catch (err) {
      setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not export saved simulation.') })
    } finally {
      setExportingRunId(null)
    }
  }

  return (
    <div className="p-3">
      <div className="card shadow-sm border-0 monitoring-module-chart-card">
        <div className="card-header">
          <div className="d-flex flex-wrap align-items-center justify-content-between gap-2">
            <div>
              <div className="fw-bold" style={{ fontSize: '.88rem' }}>
                <i className="bi bi-clock-history me-2" style={{ color: 'var(--mp-primary)' }} />
                Simulation History
              </div>
              <div className="text-muted" style={{ fontSize: '.75rem', marginTop: '.1rem' }}>
                {selectedHistoryOrchardName} — saved runs, parameters, weather &amp; playback
              </div>
            </div>
            <div className="d-flex flex-wrap align-items-center justify-content-end gap-2">
              <div style={{ width: 180 }}>
                <MpSelect
                  small
                  className="mb-0"
                  value={historyOrchardId}
                  onChange={setHistoryOrchardId}
                  options={historyOrchardOptions}
                />
              </div>
              <div style={{ width: 130 }}>
                <MpSelect
                  small
                  className="mb-0"
                  value={historyGrouping}
                  onChange={setHistoryGrouping}
                  options={HISTORY_GROUP_OPTIONS}
                />
              </div>
              <button
                type="button"
                className="btn btn-success btn-sm"
                onClick={handleExportHistory}
                disabled={exportingHistory}
              >
                {exportingHistory ? <span className="spinner-border spinner-border-sm me-1" /> : <i className="bi bi-file-earmark-excel me-1" />}
                Export History
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={fetchRuns}
                disabled={loading}
              >
                {loading ? <span className="spinner-border spinner-border-sm me-1" /> : <i className="bi bi-arrow-clockwise me-1" />}
                Refresh
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleSyncToSupabase}
                disabled={syncingToSupabase}
                title="Push pending local database changes to Supabase"
              >
                {syncingToSupabase ? <span className="spinner-border spinner-border-sm me-1" /> : <i className="bi bi-cloud-arrow-up me-1" />}
                {syncingToSupabase ? 'Syncing…' : 'Sync to Supabase'}
              </button>
            </div>
          </div>
        </div>

        <div className="card-body">
          {status && (
            <div className={`alert alert-${status.type} py-2 mb-3`} style={{ fontSize: '.86rem' }}>
              {status.msg}
            </div>
          )}

          {loading && !runs.length ? (
            <div className="text-muted small py-4 text-center">Loading saved simulations...</div>
          ) : runs.length ? (
            <div className="table-responsive">
              <table className="table table-sm align-middle mb-0 simulation-history-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Orchard</th>
                    <th>Pest</th>
                    <th>Model</th>
                    <th className="text-end">Duration</th>
                    <th className="text-end">Peak Risk</th>
                    <th className="text-end">Infested</th>
                    <th>Weather</th>
                    <th className="text-end">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {groupedRuns.map((group) => (
                    <Fragment key={group.key}>
                      {group.label && (
                        <tr key={`${group.key}-header`} className="history-group-row">
                          <th colSpan="9" className="text-muted bg-light" style={{ fontSize: '.78rem' }}>
                            <i className="bi bi-calendar3 me-1" />
                            {group.label}
                            <span className="fw-normal ms-2">{group.runs.length} run{group.runs.length === 1 ? '' : 's'}</span>
                          </th>
                        </tr>
                      )}
                      {group.runs.map((run) => {
                        const busy = loadingRunId === run.run_id
                        const exporting = exportingRunId === run.run_id
                        return (
                          <tr key={run.run_id}>
                            <td>
                              <div className="fw-medium">{formatDate(run.started_at)}</div>
                              <div className="text-muted" style={{ fontSize: '.72rem' }}>{run.run_id}</div>
                            </td>
                            <td>{orchardLabel(run.orchard_id)}</td>
                            <td>{pestLabel(run.pest_type)}</td>
                            <td>
                              <span className="badge bg-light text-dark border">{modeLabel(run.simulation_mode)}</span>
                            </td>
                            <td className="text-end">{run.hours ?? '--'} h</td>
                            <td className="text-end">{percent(run.peak_risk)}</td>
                            <td className="text-end">{run.n_infested_final ?? '--'}</td>
                            <td className="text-capitalize">{run.weather_source ?? '--'}</td>
                            <td>
                              <div className="d-flex justify-content-end gap-2">
                                <button
                                  type="button"
                                  className="btn btn-success btn-sm"
                                  disabled={busy}
                                  onClick={() => handleLoad(run.run_id)}
                                >
                                  {busy ? <span className="spinner-border spinner-border-sm me-1" /> : <i className="bi bi-box-arrow-in-down me-1" />}
                                  Load Result
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-outline-secondary btn-sm"
                                  disabled={busy}
                                  onClick={() => handleTemplate(run.run_id)}
                                >
                                  <i className="bi bi-sliders me-1" />
                                  Use as Template
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-outline-success btn-sm"
                                  disabled={exporting}
                                  onClick={() => handleExportRun(run.run_id)}
                                >
                                  {exporting ? <span className="spinner-border spinner-border-sm me-1" /> : <i className="bi bi-file-earmark-excel me-1" />}
                                  Export
                                </button>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-muted small py-4 text-center">
              No saved simulations for {selectedHistoryOrchardName.toLowerCase()} yet. Run a simulation first, then it will appear here.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
