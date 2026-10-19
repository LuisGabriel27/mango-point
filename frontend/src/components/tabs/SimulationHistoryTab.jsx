import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import api, { apiErrorMessage } from '../../api'
import MpSelect from '../MpSelect'
import ConfirmationModal from '../ConfirmationModal'
import {
  getSimulationRunFromHistory,
  saveSimulationRunToHistory,
  setSimulationHistoryDeleted,
} from '../../utils/simulationHistoryStore'
import { mergeHistoryRuns as mergeRuns, syncSimulationHistory } from '../../utils/simulationHistorySync'
import {
  HISTORY_PERIOD_ALL_HISTORY,
  HISTORY_PERIOD_MONTH,
  filterRunsByHistoryPeriod,
  historyPage,
  historyMonthKey,
  historyMonthLabel,
} from '../../utils/historyPeriod'

const DEFAULT_ORCHARD_ID = 'default-orchard'
const DEFAULT_ORCHARD_LABEL = 'Default Orchard (BPI)'
const ALL_ORCHARDS = 'all'
const HISTORY_PAGE_SIZE = 10

const HISTORY_GROUP_OPTIONS = [
  { value: 'all', label: 'No grouping' },
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

export default function SimulationHistoryTab({
  orchards = [],
  refreshKey = 0,
  onLoadRun,
  onUseTemplate,
  onPrintRun,
  onRunVisibilityChange,
}) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(false)
  const [offlineCache, setOfflineCache] = useState({ phase: 'checking' })
  const [loadingRunId, setLoadingRunId] = useState(null)
  const [syncingToSupabase, setSyncingToSupabase] = useState(false)
  const [historyOrchardId, setHistoryOrchardId] = useState(ALL_ORCHARDS)
  const [historyPeriod, setHistoryPeriod] = useState(HISTORY_PERIOD_MONTH)
  const [historyMonth, setHistoryMonth] = useState(() => historyMonthKey())
  const [historyGrouping, setHistoryGrouping] = useState('all')
  const [requestedPage, setRequestedPage] = useState(0)
  const [status, setStatus] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [lastDeleted, setLastDeleted] = useState(null)
  const [restoring, setRestoring] = useState(false)
  const fetchVersion = useRef(0)
  const cacheController = useRef(null)
  const mutationInFlight = useRef(false)
  const currentMonthKey = useMemo(() => historyMonthKey(), [])
  const selectedMonthLabel = useMemo(() => historyMonthLabel(historyMonth), [historyMonth])

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

  const displayedRuns = useMemo(
    () => filterRunsByHistoryPeriod(runs.filter((run) => (
      historyOrchardId === ALL_ORCHARDS || run.orchard_id === historyOrchardId
    )), historyPeriod, historyMonth),
    [historyMonth, historyOrchardId, historyPeriod, runs],
  )
  const completedRuns = runs.filter((run) => run.status === 'completed')
  const offlineReadyCount = completedRuns.filter((run) => run.cached_locally).length

  const historyView = useMemo(
    () => historyPage(displayedRuns, requestedPage, HISTORY_PAGE_SIZE),
    [displayedRuns, requestedPage],
  )

  const groupedRuns = useMemo(
    () => groupRuns(historyView.runs, historyGrouping),
    [historyGrouping, historyView.runs],
  )
  const showPagination = displayedRuns.length > HISTORY_PAGE_SIZE

  useEffect(() => {
    if (requestedPage !== historyView.page) setRequestedPage(historyView.page)
  }, [historyView.page, requestedPage])

  useEffect(() => {
    setRequestedPage(0)
  }, [historyGrouping, historyMonth, historyOrchardId, historyPeriod])

  const orchardLabel = (runOrchardId) => {
    if (runOrchardId === DEFAULT_ORCHARD_ID) return DEFAULT_ORCHARD_LABEL
    return historyOrchardOptions.find((option) => option.value === runOrchardId)?.label
      ?? runOrchardId
      ?? '--'
  }

  const fetchRuns = useCallback(async ({ preserveStatus = false } = {}) => {
    cacheController.current?.abort()
    const controller = new AbortController()
    cacheController.current = controller
    const version = ++fetchVersion.current
    setRequestedPage(0)
    setLoading(true)
    if (!preserveStatus) setStatus(null)
    setRuns([])
    setOfflineCache({ phase: 'checking' })
    let lastRuns = []
    try {
      await syncSimulationHistory({ api, signal: controller.signal, onUpdate: (snapshot) => {
        if (version !== fetchVersion.current) return
        lastRuns = snapshot.runs
        setRuns(snapshot.runs)
        setOfflineCache(snapshot)
        setLoading(snapshot.phase === 'checking')
      } })
    } catch (err) {
      if (controller.signal.aborted || version !== fetchVersion.current) return
      if ([401, 403].includes(err?.response?.status)) {
        setRuns([])
        setOfflineCache({ phase: 'unavailable' })
        setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Please sign in again.') })
        return
      }
      const cachedRuns = lastRuns.filter((run) => run.cached_locally)
      setRuns(cachedRuns)
      setOfflineCache({ phase: 'unavailable' })
      if (cachedRuns.length) {
        setStatus({
          type: 'warning',
          msg: `${apiErrorMessage(err, 'Could not load server history.')} Showing saved browser history.`,
        })
      } else {
        setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not load simulation history.') })
      }
    } finally {
      if (version === fetchVersion.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchRuns()
    return () => { fetchVersion.current++; cacheController.current?.abort() }
  }, [fetchRuns, refreshKey])

  useEffect(() => {
    const resume = () => { if (!mutationInFlight.current) fetchRuns() }
    window.addEventListener('online', resume)
    return () => window.removeEventListener('online', resume)
  }, [fetchRuns])

  const fetchRunDetails = async (runId) => {
    setLoadingRunId(runId)
    setStatus(null)
    try {
      const res = await api.getSimulationRun(runId, { timeout: 20000 })
      saveSimulationRunToHistory(res.data).catch(() => {})
      return res.data
    } catch (err) {
      // An authoritative missing/deleted run must never fall back to old output.
      if ([404, 410].includes(err?.response?.status)) {
        await setSimulationHistoryDeleted([runId], true).catch(() => {})
        setRuns((current) => current.filter((run) => run.run_id !== runId))
        setStatus({ type: 'warning', msg: 'This saved simulation is no longer available in History.' })
        return null
      }
      if ([401, 403].includes(err?.response?.status)) {
        setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Please sign in again.') })
        return null
      }
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
    const template = data.request_payload ?? data.input_parameters ?? {}
    onUseTemplate?.(template)
    const modelVersion = template?.dashboard_state?.simulation_model_version
    setStatus(modelVersion
      ? { type: 'success', msg: 'Saved parameters, original random seed, and model version copied into the controls.' }
      : {
          type: 'warning',
          msg: 'Legacy parameters and original random seed copied. This run predates model-version tracking, so a rerun may not match its historical result.',
        })
  }

  const handlePrint = async (runId) => {
    const data = await fetchRunDetails(runId)
    if (data) onPrintRun?.(data)
  }

  const handleDelete = async () => {
    if (!deleteTarget || mutationInFlight.current) return
    mutationInFlight.current = true
    setDeleting(true)
    setDeleteError('')
    try {
      await api.deleteSimulationRun(deleteTarget.run_id)
      cacheController.current?.abort()
      fetchVersion.current++
      setLoading(false)
      setOfflineCache({ phase: 'partial' })
      let cacheUpdated = true
      try { await setSimulationHistoryDeleted([deleteTarget.run_id], true) }
      catch (_) { cacheUpdated = false }
      setRuns((current) => current.filter((run) => run.run_id !== deleteTarget.run_id))
      setLastDeleted(deleteTarget)
      setDeleteTarget(null)
      setStatus({ type: cacheUpdated ? 'success' : 'warning',
        msg: cacheUpdated ? 'Simulation removed from History. Its stored data and linked observations are preserved.'
          : 'Simulation deleted on the server. Browser storage could not be updated; reconnect before using cached History.' })
      onRunVisibilityChange?.(deleteTarget.run_id, true)
      fetchRuns({ preserveStatus: true })
    } catch (err) {
      setDeleteError(apiErrorMessage(err, 'Could not delete this simulation. Please try again.'))
    } finally { mutationInFlight.current = false; setDeleting(false) }
  }

  const handleUndo = async () => {
    if (!lastDeleted || mutationInFlight.current) return
    mutationInFlight.current = true
    setRestoring(true)
    try {
      await api.restoreSimulationRun(lastDeleted.run_id)
      cacheController.current?.abort()
      fetchVersion.current++
      setLoading(false)
      await setSimulationHistoryDeleted([lastDeleted.run_id], false).catch(() => {})
      setRuns((current) => mergeRuns([lastDeleted], current))
      onRunVisibilityChange?.(lastDeleted.run_id, false)
      setLastDeleted(null)
      setStatus({ type: 'success', msg: 'Simulation restored to History.' })
      fetchRuns({ preserveStatus: true })
    } catch (err) {
      setStatus({ type: 'danger', msg: apiErrorMessage(err, 'Could not restore this simulation. Please try again.') })
    } finally { mutationInFlight.current = false; setRestoring(false) }
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

  return (
    <div className="p-3">
      <div className="card shadow-sm border-0 monitoring-module-chart-card">
        <div className="card-header" data-tour="history-heading">
          <div className="d-flex flex-wrap align-items-center justify-content-between gap-2">
            <div>
              <div className="fw-bold" style={{ fontSize: '.88rem' }}>
                <i className="bi bi-clock-history me-2" style={{ color: 'var(--mp-primary)' }} />
                Simulation History
              </div>
              <div className="text-muted" style={{ fontSize: '.75rem', marginTop: '.1rem' }}>
                {selectedHistoryOrchardName} — {historyPeriod === HISTORY_PERIOD_ALL_HISTORY ? 'all saved runs' : selectedMonthLabel}
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
              <div className="history-period-filter">
                <label className={`history-month-picker${historyPeriod === HISTORY_PERIOD_MONTH ? ' active' : ''}`}>
                  <i className="bi bi-calendar3" aria-hidden="true" />
                  <span className="visually-hidden">History month and year</span>
                  <input
                    type="month"
                    value={historyMonth}
                    max={currentMonthKey}
                    aria-label="History month and year"
                    onFocus={() => setHistoryPeriod(HISTORY_PERIOD_MONTH)}
                    onChange={(event) => {
                      if (!event.target.value) return
                      setHistoryMonth(event.target.value)
                      setHistoryPeriod(HISTORY_PERIOD_MONTH)
                    }}
                  />
                </label>
                <button
                  type="button"
                  className={`btn btn-sm ${historyPeriod === HISTORY_PERIOD_ALL_HISTORY ? 'btn-success' : 'btn-outline-secondary'}`}
                  aria-pressed={historyPeriod === HISTORY_PERIOD_ALL_HISTORY}
                  onClick={() => setHistoryPeriod(HISTORY_PERIOD_ALL_HISTORY)}
                >
                  All history
                </button>
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
          <div className="small text-muted mb-3" role="status" aria-live="polite" data-testid="history-offline-status">
            {offlineCache.phase === 'checking' ? 'Checking saved results for offline use...'
              : offlineCache.phase === 'downloading'
                ? `Preparing results for offline use: ${offlineReadyCount} of ${completedRuns.length} ready across all orchards.`
                : offlineCache.phase === 'unavailable'
                  ? `${offlineReadyCount} results available offline in this browser. Reconnect and refresh to check for more saved results.`
                  : `${offlineReadyCount} of ${completedRuns.length} results available offline in this browser across all orchards.`}
            {offlineCache.phase === 'partial' && (
              <span> Some results could not be prepared. {offlineCache.error ? apiErrorMessage(offlineCache.error) : ''} Use Refresh to retry.</span>
            )}
          </div>
          {status && (
            <div className={`alert alert-${status.type} py-2 mb-3`} style={{ fontSize: '.86rem' }}>
              {status.msg}
              {lastDeleted && <button type="button" className="btn btn-link btn-sm py-0 ms-2"
                disabled={restoring} onClick={handleUndo}>{restoring ? 'Restoring…' : 'Undo delete'}</button>}
            </div>
          )}

          {loading && !runs.length ? (
            <div className="text-muted small py-4 text-center">Loading saved simulations...</div>
          ) : displayedRuns.length ? (
            <>
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
                    <th className="text-center history-actions-column">Actions</th>
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
                            <span className="fw-normal ms-2">
                              {group.runs.length} run{group.runs.length === 1 ? '' : 's'}{showPagination ? ' on this page' : ''}
                            </span>
                          </th>
                        </tr>
                      )}
                      {group.runs.map((run) => {
                        const busy = loadingRunId === run.run_id
                        return (
                          <tr key={run.run_id}>
                            <td>
                              <div className="fw-medium">{formatDate(run.started_at)}</div>
                              <div className="text-muted" style={{ fontSize: '.72rem' }}>{run.run_id}</div>
                              <div className={`small ${run.cached_locally ? 'text-success' : 'text-muted'}`}>
                                {run.cached_locally ? 'Available offline' : 'Online only'}
                              </div>
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
                            <td className="history-actions-column">
                              <div className="history-run-actions">
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
                                {onPrintRun && (
                                  <button type="button" className="btn btn-outline-success btn-sm" disabled={busy} onClick={() => handlePrint(run.run_id)}>
                                    <i className="bi bi-printer me-1" />Print report
                                  </button>
                                )}
                                <button type="button" className="btn btn-outline-danger btn-sm"
                                  aria-label={`Delete simulation ${run.run_id}`}
                                  disabled={loading || Boolean(loadingRunId) || deleting || restoring || !run.server_saved}
                                  title={run.server_saved ? 'Delete this saved simulation' : 'Connect to the API and refresh History to delete this run.'}
                                  onClick={() => { setDeleteTarget(run); setDeleteError('') }}>
                                  <i className="bi bi-trash3 me-1" aria-hidden="true" />Delete
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
            {showPagination && (
              <div className="history-pagination-footer overview-table-footer mt-3 pt-2">
                <span className="small text-muted" role="status">
                  Showing {historyView.first.toLocaleString('en-PH')}&ndash;{historyView.last.toLocaleString('en-PH')} of {historyView.total.toLocaleString('en-PH')} simulations
                </span>
                <nav aria-label="Simulation history pages" className="overview-table-pagination">
                  <span className="small text-muted">
                    Page {(historyView.page + 1).toLocaleString('en-PH')} of {historyView.pageCount.toLocaleString('en-PH')}
                  </span>
                  <div className="btn-group btn-group-sm">
                    <button type="button" className="btn btn-outline-secondary" disabled={historyView.page === 0}
                      onClick={() => setRequestedPage(0)} aria-label="First simulation history page">First</button>
                    <button type="button" className="btn btn-outline-secondary" disabled={historyView.page === 0}
                      onClick={() => setRequestedPage(historyView.page - 1)} aria-label="Previous simulation history page">Previous</button>
                    <button type="button" className="btn btn-outline-secondary" disabled={historyView.page >= historyView.pageCount - 1}
                      onClick={() => setRequestedPage(historyView.page + 1)} aria-label="Next simulation history page">Next</button>
                    <button type="button" className="btn btn-outline-secondary" disabled={historyView.page >= historyView.pageCount - 1}
                      onClick={() => setRequestedPage(historyView.pageCount - 1)} aria-label="Last simulation history page">Last</button>
                  </div>
                </nav>
              </div>
            )}
            </>
          ) : (
            <div className="text-muted small py-4 text-center">
              {historyPeriod === HISTORY_PERIOD_MONTH
                ? `No simulations saved in ${selectedMonthLabel} for ${selectedHistoryOrchardName.toLowerCase()}. Choose another month or select All history.`
                : `No saved simulations for ${selectedHistoryOrchardName.toLowerCase()} yet. Run a simulation first, then it will appear here.`}
            </div>
          )}
        </div>
      </div>
      {deleteTarget && <ConfirmationModal title="Delete saved simulation?" confirmLabel="Delete simulation" danger showIcon={false}
        closeLabel="Close simulation deletion confirmation" busy={deleting} error={deleteError}
        onClose={() => { if (!deleting) setDeleteTarget(null) }} onConfirm={handleDelete}>
        <p>Remove this simulation from shared History? Its stored data and linked field observations will be kept. You can undo this deletion.</p>
        <p className="mt-2"><strong>{orchardLabel(deleteTarget.orchard_id)}</strong><br />
          {pestLabel(deleteTarget.pest_type)} · {modeLabel(deleteTarget.simulation_mode)} · {deleteTarget.hours} h<br />
          {formatDate(deleteTarget.started_at)}<br />
          <span className="small text-break">{deleteTarget.run_id}</span></p>
      </ConfirmationModal>}
    </div>
  )
}
