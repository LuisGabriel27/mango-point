import { useState, useEffect, useCallback, useMemo } from 'react'
import Navbar from '../components/Navbar'
import Sidebar from '../components/Sidebar'
import LiveMapTab from '../components/tabs/LiveMapTab'
import OverviewTab from '../components/tabs/OverviewTab'
import CropImpactTab from '../components/tabs/CropImpactTab'
import SurveillanceTab from '../components/tabs/SurveillanceTab'
import api from '../api'
import fallbackTreeGeojsonRaw from '../../public/trees.geojson?raw'

const DEFAULT_ORCHARD_ID = 'default-orchard'
const ALL_ID = '__all_orchards__'

const DEFAULT_MANUAL_WEATHER = {
  temperature_c: 30,
  wind_speed_ms: 2,
  wind_direction_deg: 90,
  rainfall_mm: 0,
  humidity: 75,
}

const fallbackTreeGeojson = JSON.parse(fallbackTreeGeojsonRaw)

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState('live-map')

  // Orchard state
  const [orchards, setOrchards] = useState([])
  const [selectedOrchardId, setSelectedOrchardId] = useState(DEFAULT_ORCHARD_ID)
  const [orchardLoading, setOrchardLoading] = useState(false)

  // Simulation / map state
  const [simData, setSimData] = useState(null)
  const [treeOverrides, setTreeOverrides] = useState({})
  const [playbackFrames, setPlaybackFrames] = useState([])
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0)

  // Monitoring state
  const [monitoringData, setMonitoringData] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  // Alerts
  const [alerts, setAlerts] = useState([])
  const [alertLoading, setAlertLoading] = useState(false)

  // Weather
  const [weather, setWeather] = useState(null)
  const [manualWeather, setManualWeather] = useState(DEFAULT_MANUAL_WEATHER)
  const [weatherOverrideActive, setWeatherOverrideActive] = useState(false)

  // Tree management modal
  const [selectedTree, setSelectedTree] = useState(null)

  // Fallback GeoJSON from static file (mirrors Python app's DEFAULT_ORCHARD)
  const [fallbackGeojson, setFallbackGeojson] = useState(fallbackTreeGeojson)
  useEffect(() => {
    fetch('/trees.geojson')
      .then((r) => {
        if (!r.ok) throw new Error(`Unable to load trees.geojson (${r.status})`)
        return r.json()
      })
      .then((data) => setFallbackGeojson(data))
      .catch(() => setFallbackGeojson(fallbackTreeGeojson))
  }, [])

  // ── Helpers ──────────────────────────────────────────────────────────
  const selectedOrchardRecord = orchards.find((o) => o.orchard_id === selectedOrchardId) ?? null
  const orchardGeojson =
    selectedOrchardId === ALL_ID
      ? { type: 'FeatureCollection', features: orchards.flatMap((o) => (o.geojson ?? fallbackGeojson)?.features ?? []) }
      : (selectedOrchardRecord?.geojson ?? fallbackGeojson)

  const orchardName =
    selectedOrchardId === ALL_ID
      ? 'All registered orchards'
      : selectedOrchardRecord?.name ?? 'Default Orchard'

  // Displayed geojson: current playback frame, or final sim snapshot, or null
  const currentFrame = playbackFrames.length > 0 ? (playbackFrames[currentFrameIdx] ?? null) : null
  const mapGeojson = currentFrame?.risk_geojson ?? simData?.risk_geojson ?? null

  const activeAlertCount = alerts.filter((a) => a.status === 'active').length

  // Build decision support metrics from simulation data
  // (SimulationResponse has no dedicated decision_support field — compute it here)
  const decisionMetrics = useMemo(() => {
    if (!simData?.risk_geojson) return null
    const features = simData.risk_geojson?.features ?? []
    const total = features.length
    if (!total) return null

    const zone1 = features.filter((f) => (f.properties?.risk ?? 0) < 0.2).length
    const zone2 = features.filter((f) => { const r = f.properties?.risk ?? 0; return r >= 0.2 && r < 0.6 }).length
    const zone3 = features.filter((f) => (f.properties?.risk ?? 0) >= 0.6).length

    const z1 = zone1 / total, z2 = zone2 / total, z3 = zone3 / total
    const peak = simData.peak_risk ?? 0
    const nInfested = simData.n_infested_final ?? 0
    const pestReduction = z3 < 0.3 ? 0.45 : z3 < 0.6 ? 0.25 : 0.10
    const savings = total * 180 * pestReduction

    const actions = []
    if (z3 > 0.02) actions.push({
      title: 'Apply targeted treatment to high-risk trees',
      timing: peak >= 0.75 ? 'Immediately (within 24 h)' : 'Within 48 hours',
      priority: peak >= 0.75 ? 'Urgent' : 'High',
      scope_label: `Zone 3 — ${(z3 * 100).toFixed(0)}% of orchard`,
      max_risk: peak,
      recommended_steps: [
        'Mark and bag high-risk trees from the Live Map',
        'Apply pesticide spray per recommended schedule',
        'Monitor treated trees daily for 7 days',
      ],
    })
    if (z2 > 0.05) actions.push({
      title: 'Increase monitoring in moderate-risk zone',
      timing: 'Starting today',
      priority: 'Medium',
      scope_label: `Zone 2 — ${(z2 * 100).toFixed(0)}% of orchard`,
      max_risk: 0.45,
      recommended_steps: [
        'Install or inspect pheromone traps in Zone 2',
        'Visual inspection every 3 days',
        'Log observations in MangoPoint',
      ],
    })
    if (z1 > 0.3) actions.push({
      title: 'Maintain preventive measures in safe zone',
      timing: 'Routine',
      priority: 'Low',
      scope_label: `Zone 1 — ${(z1 * 100).toFixed(0)}% of orchard`,
      max_risk: 0.15,
      recommended_steps: [
        'Continue bagging program for susceptible trees',
        'Sanitation of fallen fruit',
        'Weekly inspection',
      ],
    })

    const summary =
      peak >= 0.75 ? 'Critical risk — immediate field action required to prevent spread.' :
      peak >= 0.5  ? 'High risk — targeted treatment recommended within 48 hours.' :
      peak >= 0.25 ? 'Moderate risk — increase monitoring and prepare treatment resources.' :
                     'Low pest risk — continue current prevention measures.'

    return {
      zones: { zone_1_pct: z1, zone_2_pct: z2, zone_3_pct: z3 },
      economic: { pesticide_reduction: pestReduction, estimated_savings: savings },
      action_plan: actions,
      summary_message: summary,
    }
  }, [simData])

  // ── Data fetchers ─────────────────────────────────────────────────────
  const fetchOrchards = useCallback(async () => {
    setOrchardLoading(true)
    try {
      const res = await api.getOrchards({ active_only: true, include_geojson: true })
      const list = res.data.orchards ?? []
      setOrchards(list)
      if (list.length && !list.find((o) => o.orchard_id === selectedOrchardId)) {
        setSelectedOrchardId(list[0].orchard_id)
      }
    } catch (_) {
      // Backend may be offline; keep existing orchard list
    } finally {
      setOrchardLoading(false)
    }
  }, [selectedOrchardId])

  const fetchAlerts = useCallback(async () => {
    setAlertLoading(true)
    try {
      const res = await api.getAlerts({ limit: 100 })
      setAlerts(res.data.alerts ?? [])
    } catch (_) {
      /* ignore */
    } finally {
      setAlertLoading(false)
    }
  }, [])

  const fetchWeather = useCallback(async () => {
    try {
      const res = await api.getLiveWeather()
      setWeather(res.data)
    } catch (_) { /* ignore */ }
  }, [])

  const fetchMonitoring = useCallback(async () => {
    try {
      const res = await api.getMonitoringMetrics()
      setMonitoringData(res.data)
      setLastUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    } catch (_) { /* ignore */ }
  }, [])

  // ── Initial loads ──────────────────────────────────────────────────────
  useEffect(() => { fetchOrchards() }, [])
  useEffect(() => { fetchAlerts() }, [])
  useEffect(() => { fetchWeather() }, [])
  useEffect(() => { fetchMonitoring() }, [])

  // ── Auto-refresh intervals ────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(fetchWeather, 60_000)
    return () => clearInterval(id)
  }, [fetchWeather])

  useEffect(() => {
    const id = setInterval(() => { fetchAlerts(); fetchMonitoring() }, 30_000)
    return () => clearInterval(id)
  }, [fetchAlerts, fetchMonitoring])

  // ── Simulation complete handler ───────────────────────────────────────
  const handleSimulationComplete = useCallback((data) => {
    setSimData(data)
    const frames = Array.isArray(data.time_series) ? data.time_series : []
    setPlaybackFrames(frames)
    setCurrentFrameIdx(0)
    fetchAlerts()
    fetchMonitoring()
  }, [fetchAlerts, fetchMonitoring])

  // ── Tree management modal ─────────────────────────────────────────────
  const handleTreeClick = useCallback((treeData) => {
    setSelectedTree(treeData)
  }, [])

  const applyTreeStatus = useCallback((treeId, status) => {
    setTreeOverrides((prev) => ({ ...prev, [String(treeId)]: status }))
    setSelectedTree(null)
  }, [])

  return (
    <div className="app-shell">
      <Navbar alertCount={activeAlertCount} activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="viewport-layout">
        {/* ── Main content area (map + tabs) ── */}
        <main className="fullscreen-map-area">
          <div className="ops-pages-shell">
            {/* Tab panels */}
            <div className="ops-tab-body" id="ops-tab-body">
              <div
                id="ops-panel-live-map"
                className="ops-panel"
                style={{ display: activeTab === 'live-map' ? 'block' : 'none' }}
              >
                <LiveMapTab
                  geojson={mapGeojson}
                  baseGeojson={orchardGeojson}
                  alerts={alerts.filter((a) => a.status === 'active')}
                  treeOverrides={treeOverrides}
                  orchardName={orchardName}
                  currentFrame={currentFrame}
                  onTreeClick={handleTreeClick}
                />
              </div>

              <div
                id="ops-panel-overview"
                className="ops-panel ops-panel-scroll"
                style={{ display: activeTab === 'overview' ? 'block' : 'none' }}
              >
                <OverviewTab
                  monitoringData={monitoringData}
                  simData={simData}
                  lastUpdated={lastUpdated}
                  currentFrame={currentFrame}
                  totalTrees={orchardGeojson?.features?.length ?? 0}
                />
              </div>

              <div
                id="ops-panel-impact"
                className="ops-panel ops-panel-scroll"
                style={{ display: activeTab === 'crop-impact' ? 'block' : 'none' }}
              >
                <CropImpactTab monitoringData={monitoringData} simData={simData} />
              </div>

              <div
                id="ops-panel-surveillance"
                className="ops-panel ops-panel-scroll"
                style={{ display: activeTab === 'spread-weather' ? 'block' : 'none' }}
              >
                <SurveillanceTab monitoringData={monitoringData} simData={simData} weather={weather} />
              </div>

              {/* Refresh footer */}
              <div className="ops-refresh-footer">
                <small className="text-muted">
                  <i className="bi bi-arrow-repeat me-1" />
                  Auto-refreshes every 30 seconds | Last: {lastUpdated ?? 'Never'}
                </small>
              </div>
            </div>
          </div>
        </main>

        {/* ── Right sidebar ── */}
        <Sidebar
          orchards={orchards}
          selectedOrchardId={selectedOrchardId}
          onOrchardSelect={setSelectedOrchardId}
          onOrchardRefresh={fetchOrchards}
          orchardLoading={orchardLoading}
          weather={weather}
          manualWeather={manualWeather}
          weatherOverrideActive={weatherOverrideActive}
          onManualWeatherChange={(w) => { setManualWeather(w); setWeatherOverrideActive(true) }}
          onWeatherOverrideToggle={setWeatherOverrideActive}
          orchardGeojson={orchardGeojson}
          treeOverrides={treeOverrides}
          onSimulationComplete={handleSimulationComplete}
          playbackFrames={playbackFrames}
          currentFrameIdx={currentFrameIdx}
          onFrameSeek={setCurrentFrameIdx}
          alerts={alerts}
          alertLoading={alertLoading}
          onAlertRefresh={fetchAlerts}
          decisionMetrics={decisionMetrics}
        />
      </div>

      {/* ── Tree Management Modal ── */}
      {selectedTree && (
        <div
          className="modal fade show d-block"
          tabIndex="-1"
          style={{ background: 'rgba(0,0,0,.5)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedTree(null) }}
        >
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header bg-light border-bottom">
                <h5 className="modal-title">
                  <i className="bi bi-tree-fill me-2" style={{ color: '#22c55e' }} />
                  Tree Management
                </h5>
                <button type="button" className="btn-close" onClick={() => setSelectedTree(null)} />
              </div>
              <div className="modal-body px-4 py-3">
                <div className="mb-4">
                  <p className="mb-1"><strong>Tree #{selectedTree.tree_id}</strong></p>
                  <p className="text-muted small mb-1">
                    Current status: {(selectedTree.status ?? 'healthy').replace(/_/g, ' ')}
                  </p>
                  {selectedTree.risk != null && (
                    <p className="text-muted small mb-0">
                      Risk: {(selectedTree.risk * 100).toFixed(0)}%
                    </p>
                  )}
                </div>
                <hr className="my-2" />
                <div className="d-flex align-items-center mb-2">
                  <i className="bi bi-pencil-square me-2 text-primary" />
                  <strong className="text-primary">Override Status</strong>
                </div>
                <TreeStatusSelect
                  defaultValue={selectedTree.status ?? 'healthy'}
                  onApply={(status) => applyTreeStatus(selectedTree.tree_id, status)}
                  onCancel={() => setSelectedTree(null)}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function TreeStatusSelect({ defaultValue, onApply, onCancel }) {
  const [value, setValue] = useState(defaultValue)

  const OPTIONS = [
    { label: 'Healthy', value: 'healthy' },
    { label: 'Infected', value: 'infected' },
    { label: 'Bagged (reduced risk)', value: 'bagged' },
    { label: 'Dead (removed)', value: 'dead' },
    { label: 'History Infected', value: 'history_infected' },
    { label: 'Suspect (monitoring)', value: 'suspect' },
  ]

  return (
    <>
      <select
        className="form-select mb-3 border-primary"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        style={{ fontSize: '.95rem' }}
      >
        {OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <div className="card bg-light border-0 mb-3">
        <div className="card-body py-2 px-3">
          <div className="d-flex align-items-center">
            <i className="bi bi-info-circle-fill me-2 text-info" />
            <span className="small">Status changes take effect on the next simulation run.</span>
          </div>
          <div className="d-flex align-items-center mt-2">
            <i className="bi bi-shield-check me-2 text-success" />
            <span className="small">
              <strong>Bagged</strong> trees have reduced infection risk;{' '}
              <strong>Dead</strong> trees are immune to pest spread.
            </span>
          </div>
        </div>
      </div>
      <div className="modal-footer bg-light border-top p-2 d-flex gap-2">
        <button type="button" className="btn btn-outline-secondary px-4" onClick={onCancel}>
          <i className="bi bi-x-lg me-1" />Cancel
        </button>
        <button type="button" className="btn btn-success px-4 ms-2" onClick={() => onApply(value)}>
          <i className="bi bi-check-lg me-1" />Apply Changes
        </button>
      </div>
    </>
  )
}
