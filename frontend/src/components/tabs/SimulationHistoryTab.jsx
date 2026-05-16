import { useCallback, useEffect, useState } from 'react'
import api, { apiErrorMessage } from '../../api'

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
    try {
      const params = { limit: 50 }
      if (orchardId) params.orchard_id = orchardId
      const res = await api.getSimulationRuns(params)
      setRuns(res.data?.runs ?? [])
    } catch (err) {
      setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not load simulation history.') })
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
      return res.data
    } catch (err) {
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
        <div className="card-header py-3">
          <div className="d-flex flex-wrap align-items-center justify-content-between gap-2">
            <div>
              <div className="fw-semibold">
                <i className="bi bi-clock-history me-2" />
                Simulation History
              </div>
              <div className="text-muted small">
                {orchardName || 'Active orchard'} - saved runs, parameters, weather, playback, and results
              </div>
            </div>
            <div className="d-flex flex-wrap align-items-center justify-content-end gap-2">
              <select
                className="form-select form-select-sm"
                style={{ width: 130 }}
                value={exportScope}
                onChange={(e) => setExportScope(e.target.value)}
              >
                <option value="orchard">Active orchard</option>
                <option value="all">All orchards</option>
              </select>
              <select
                className="form-select form-select-sm"
                style={{ width: 110 }}
                value={exportPeriod}
                onChange={(e) => setExportPeriod(e.target.value)}
              >
                <option value="all">All dates</option>
                <option value="month">By month</option>
              </select>
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
