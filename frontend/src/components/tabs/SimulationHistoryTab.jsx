import { useCallback, useEffect, useState } from 'react'
import api, { apiErrorMessage } from '../../api'
import MpSelect from '../MpSelect'
import {
  getSimulationRunFromHistory,
  listSimulationRunsFromHistory,
  saveSimulationRunToHistory,
} from '../../utils/simulationHistoryStore'

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

function currentMonthValue() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
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
  orchardId,
  orchardName,
  refreshKey = 0,
  onLoadRun,
  onUseTemplate,
}) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingRunId, setLoadingRunId] = useState(null)
  const [exportingRunId, setExportingRunId] = useState(null)
  const [exportingHistory, setExportingHistory] = useState(false)
  const [exportScope, setExportScope] = useState('orchard')
  const [exportPeriod, setExportPeriod] = useState('all')
  const [exportMonth, setExportMonth] = useState(currentMonthValue)
  const [status, setStatus] = useState(null)

  const fetchRuns = useCallback(async () => {
    setLoading(true)
    setStatus(null)
    let cachedRuns = []

    try {
      cachedRuns = await listSimulationRunsFromHistory({ orchardId, limit: 50 })
      if (cachedRuns.length) setRuns(cachedRuns)
    } catch (_) {
      cachedRuns = []
    }

    try {
      const params = { limit: 50 }
      if (orchardId) params.orchard_id = orchardId
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
  }, [orchardId])

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
      const params = { period: exportPeriod, limit: 5000 }
      if (exportScope === 'orchard' && orchardId) params.orchard_id = orchardId
      if (exportPeriod === 'month') {
        const [year, month] = exportMonth.split('-').map(Number)
        params.year = year
        params.month = month
      }
      const res = await api.exportSimulationRuns(params)
      const fallback = `mangopoint_simulation_history_${exportPeriod}.xlsx`
      downloadBlob(res.data, filenameFromDisposition(res.headers['content-disposition'], fallback))
      setStatus({ type: 'success', msg: 'History export downloaded.' })
    } catch (err) {
      setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not export simulation history.') })
    } finally {
      setExportingHistory(false)
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
                {orchardName || 'Active orchard'} — saved runs, parameters, weather &amp; playback
              </div>
            </div>
            <div className="d-flex flex-wrap align-items-center justify-content-end gap-2">
              <div style={{ width: 138 }}>
                <MpSelect
                  small
                  className="mb-0"
                  value={exportScope}
                  onChange={setExportScope}
                  options={[
                    { value: 'orchard', label: 'Active orchard' },
                    { value: 'all', label: 'All orchards' },
                  ]}
                />
              </div>
              <div style={{ width: 118 }}>
                <MpSelect
                  small
                  className="mb-0"
                  value={exportPeriod}
                  onChange={setExportPeriod}
                  options={[
                    { value: 'all', label: 'All dates' },
                    { value: 'month', label: 'By month' },
                  ]}
                />
              </div>
              {exportPeriod === 'month' && (
                <input
                  type="month"
                  className="form-control form-control-sm"
                  style={{ width: 130 }}
                  value={exportMonth}
                  onChange={(e) => setExportMonth(e.target.value)}
                />
              )}
              <button
                type="button"
                className="btn btn-success btn-sm"
                onClick={handleExportHistory}
                disabled={exportingHistory || (exportPeriod === 'month' && !exportMonth)}
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
              <table className="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Date</th>
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
                  {runs.map((run) => {
                    const busy = loadingRunId === run.run_id
                    const exporting = exportingRunId === run.run_id
                    return (
                      <tr key={run.run_id}>
                        <td>
                          <div className="fw-medium">{formatDate(run.started_at)}</div>
                          <div className="text-muted" style={{ fontSize: '.72rem' }}>{run.run_id}</div>
                        </td>
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
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-muted small py-4 text-center">
              No saved simulations for this orchard yet. Run a simulation first, then it will appear here.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
