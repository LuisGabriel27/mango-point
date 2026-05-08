import { useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import api, { apiErrorMessage } from '../../api'

const STAGE_OPTIONS = [
  { label: 'Dormant', value: 'dormant' },
  { label: 'Flowering', value: 'flowering' },
  { label: 'Fruitlet', value: 'fruitlet' },
  { label: 'Mature', value: 'mature' },
]

const DIR_OPTIONS = [
  { label: '↖  NW — North-West', value: 'NW' },
  { label: '↑   N  — North', value: 'N' },
  { label: '↗  NE — North-East', value: 'NE' },
  { label: '←  W  — West', value: 'W' },
  { label: '→  E  — East', value: 'E' },
  { label: '↙  SW — South-West', value: 'SW' },
  { label: '↓   S  — South', value: 'S' },
  { label: '↘  SE — South-East', value: 'SE' },
]

const DEFAULTS = {
  yield_per_tree_kg: 45,
  farmgate_price_php_per_kg: 60,
  damage_low: 15,
  damage_base: 30,
  damage_high: 45,
  pesticide_cost_per_ha: 0,
}

function manualWeatherPayload(weather) {
  if (!weather) return null

  return {
    temperature_c: Number(weather.temperature_c ?? 30),
    wind_speed_ms: Number(weather.wind_speed_ms ?? 2),
    wind_dir_deg: Number(weather.wind_dir_deg ?? weather.wind_direction_deg ?? 90),
    rainfall_mm: Number(weather.rainfall_mm ?? 0),
  }
}

function SectionLabel({ iconName, text }) {
  return (
    <div className="section-label">
      <i className={`bi bi-${iconName} me-1`} />
      <span>{text}</span>
    </div>
  )
}

function Slider({ id, label, iconName, min, max, step, value, marks, onChange }) {
  return (
    <div className="mb-2">
      <label className="small fw-medium mb-1 d-block" htmlFor={id}>
        {iconName && <i className={`bi bi-${iconName} me-1`} />}{label}
      </label>
      <input
        id={id} type="range" className="form-range w-100"
        min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <div className="d-flex justify-content-between small text-muted">
        {marks.map((m) => <span key={m.label}>{m.label}</span>)}
      </div>
      <div className="text-center small fw-semibold" style={{ color: 'var(--mp-primary)' }}>{value}</div>
    </div>
  )
}

export default function SimulationCard({
  orchardGeojson,
  orchardId,
  treeOverrides,
  onSimulationComplete,
  manualWeather,
  weatherOverrideActive,
}) {
  const [simMode, setSimMode] = useState('grid')
  const [pestType, setPestType] = useState('fruitfly')
  const [orchardStage, setOrchardStage] = useState('mature')
  const [quadrantMode, setQuadrantMode] = useState(false)
  const [quadrantStages, setQuadrantStages] = useState({ nw: 'flowering', ne: 'fruitlet', sw: 'mature', se: 'dormant' })
  const [daysFlowering, setDaysFlowering] = useState(60)
  const [neighborThreat, setNeighborThreat] = useState(0)
  const [neighborDir, setNeighborDir] = useState('N')
  const [treatmentEnabled, setTreatmentEnabled] = useState(false)
  const [treatmentType, setTreatmentType] = useState('targeted_spray')
  const [treatmentEfficacy, setTreatmentEfficacy] = useState(0.65)
  const [simHours, setSimHours] = useState('48')
  const [showImpact, setShowImpact] = useState(false)
  const [impact, setImpact] = useState(DEFAULTS)
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState(null)

  const setImpactField = (k, v) => setImpact((p) => ({ ...p, [k]: v }))
  const setQStage = (q, v) => setQuadrantStages((p) => ({ ...p, [q]: v }))

  const handleRun = async () => {
    setRunning(true)
    setStatus({ type: 'info', msg: 'Simulation in progress…' })
    try {
      const parsedHours = Number.parseInt(simHours, 10)
      const body = {
        pest_type: pestType,
        orchard_id: orchardId,
        orchard_geojson: orchardGeojson,
        hours: Number.isFinite(parsedHours) ? parsedHours : 48,
        bagged_tree_ids: [],
        initial_infestation: [],
        treatment_applications: treatmentEnabled
          ? [{
              treatment_type: treatmentType,
              coverage: 'whole_orchard',
              efficacy: treatmentEfficacy,
              source_reduction: treatmentEfficacy,
              label: 'React treatment scenario',
            }]
          : [],
        random_seed: null,
        risk_threshold: 0.7,
        orchard_stage: orchardStage,
        days_since_flowering: daysFlowering,
        neighbor_threat: neighborThreat,
        simulation_mode: simMode,
        include_time_series: true,
      }

      if (neighborThreat > 0 && neighborDir) {
        body.neighbor_direction = neighborDir
      }

      if (quadrantMode) {
        body.quadrant_stages = quadrantStages
      }

      if (weatherOverrideActive) {
        body.manual_weather = manualWeatherPayload(manualWeather)
      }

      if (treeOverrides && Object.keys(treeOverrides).length > 0) {
        body.tree_overrides = treeOverrides
      }

      const res = await api.runSimulation(body)
      const peakPct = res.data.peak_risk != null ? `${(res.data.peak_risk * 100).toFixed(0)}%` : '—'
      const nInfested = res.data.n_infested_final ?? 0
      setStatus({ type: 'success', msg: `Done — peak risk: ${peakPct}, ${nInfested} infested` })
      onSimulationComplete?.(res.data)
    } catch (err) {
      const msg = apiErrorMessage(err, 'Simulation failed.')
      setStatus({ type: 'danger', msg })
    } finally {
      setRunning(false)
    }
  }

  return (
    <CollapsibleCard iconName="cpu" title="Simulation">
      <SectionLabel iconName="diagram-3" text="Spread Model" />
      <select className="form-select mb-1" value={simMode} onChange={(e) => setSimMode(e.target.value)}>
        <option value="grid">Grid - Cellular Automata (baseline)</option>
        <option value="tree_graph">Tree Graph - Crown-aware model</option>
      </select>
      {simMode === 'tree_graph' && (
        <div className="alert alert-info py-1 px-2 mt-1 mb-0" style={{ fontSize: '.78rem' }}>
          <i className="bi bi-info-circle me-1" />
          Tree Graph uses crown-to-crown distances. Supply <code>crown_radius_m</code> in GeoJSON properties or set a global fallback.
        </div>
      )}

      <SectionLabel iconName="bug" text="Pest & Phenology" />
      <div className="row g-2 mb-1">
        <div className="col-6">
          <label className="small fw-medium mb-1 d-block"><i className="bi bi-bug me-1" />Pest</label>
          <select className="form-select form-select-sm" value={pestType} onChange={(e) => setPestType(e.target.value)}>
            <option value="cecid">Cecid Fly</option>
            <option value="fruitfly">Fruit Fly</option>
          </select>
        </div>
        <div className="col-6">
          <label className="small fw-medium mb-1 d-block"><i className="bi bi-flower1 me-1" />Stage</label>
          <select className="form-select form-select-sm" value={orchardStage} onChange={(e) => setOrchardStage(e.target.value)}>
            {STAGE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </div>
      <small className="text-muted d-block mb-2">Fruitlet activates Cecid Fly · Mature activates Fruit Fly</small>

      <div className="form-check form-switch mb-1">
        <input className="form-check-input" type="checkbox" role="switch" id="quadrant-mode"
          checked={quadrantMode} onChange={(e) => setQuadrantMode(e.target.checked)} />
        <label className="form-check-label small" htmlFor="quadrant-mode">
          Use different stages per orchard quadrant (NW / NE / SW / SE)
        </label>
      </div>
      {quadrantMode && (
        <div className="mb-2">
          <small className="text-muted d-block mb-2">Each quadrant has a dominant stage; 70% of trees follow it.</small>
          <div className="row g-2">
            {['nw','ne','sw','se'].map((q) => (
              <div className="col-6" key={q}>
                <label className="small fw-medium mb-1 d-block">{q.toUpperCase()}</label>
                <select className="form-select form-select-sm" value={quadrantStages[q]}
                  onChange={(e) => setQStage(q, e.target.value)}>
                  {STAGE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            ))}
          </div>
        </div>
      )}

      <Slider id="days-flowering" label="Days Since Flowering" iconName="calendar-event"
        min={0} max={120} step={5} value={daysFlowering}
        marks={[{label:'0d'},{label:'30d'},{label:'60d'},{label:'90d'},{label:'120d'}]}
        onChange={setDaysFlowering}
      />
      <small className="text-muted d-block mb-0">Higher = riper fruit = stronger Fruit Fly attraction.</small>

      <SectionLabel iconName="exclamation-triangle" text="Neighbor Pressure" />
      <Slider id="neighbor-threat" label="Threat Level" iconName="bar-chart-steps"
        min={0} max={1} step={0.1} value={neighborThreat}
        marks={[{label:'None'},{label:'Low'},{label:'Med'},{label:'High'},{label:'Max'}]}
        onChange={setNeighborThreat}
      />
      {neighborThreat > 0 && (
        <div className="mb-1">
          <label className="small fw-medium mb-1 d-block"><i className="bi bi-compass me-1" />Neighbor Direction</label>
          <select className="form-select mb-1" value={neighborDir} onChange={(e) => setNeighborDir(e.target.value)}>
            {DIR_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      )}
      <small className="text-muted d-block mb-0">Pressure from unmanaged orchards (historical ~2× higher CPTD).</small>

      <SectionLabel iconName="shield-plus" text="Treatment Scenario" />
      <div className="form-check form-switch mb-1">
        <input className="form-check-input" type="checkbox" role="switch" id="treatment-enabled"
          checked={treatmentEnabled} onChange={(e) => setTreatmentEnabled(e.target.checked)} />
        <label className="form-check-label fw-medium small" htmlFor="treatment-enabled">
          Include orchard treatment in forecast
        </label>
      </div>
      {treatmentEnabled && (
        <div>
          <label className="small fw-medium mb-1 d-block"><i className="bi bi-capsule me-1" />Treatment type</label>
          <select className="form-select form-select-sm mb-2" value={treatmentType} onChange={(e) => setTreatmentType(e.target.value)}>
            <option value="protective_spray">Protective spray</option>
            <option value="targeted_spray">Targeted spray</option>
            <option value="sanitation">Sanitation</option>
            <option value="combined">Combined action</option>
          </select>
          <Slider id="treatment-efficacy" label="Effectiveness" iconName="activity"
            min={0} max={0.95} step={0.05} value={treatmentEfficacy}
            marks={[{label:'0%'},{label:'50%'},{label:'95%'}]}
            onChange={setTreatmentEfficacy}
          />
        </div>
      )}

      <SectionLabel iconName="clock-history" text="Forecast Duration" />
      <select className="form-select mb-0" value={simHours} onChange={(e) => setSimHours(e.target.value)}>
        <option value="24">24 h - Short-range</option>
        <option value="48">48 h - Standard</option>
        <option value="72">72 h - Extended</option>
        <option value="168">168 h - 7-day outlook</option>
      </select>

      {/* Impact assumptions */}
      <div className="mt-3 mb-1">
        <button type="button" className="btn btn-link btn-sm px-0 text-muted fw-medium"
          onClick={() => setShowImpact((v) => !v)}>
          <i className={`bi bi-chevron-${showImpact ? 'up' : 'down'} me-1`} />Impact Assumptions
        </button>
      </div>
      {showImpact && (
        <div>
          <div className="row g-2 mb-2">
            <div className="col-6">
              <label className="small mb-1">Yield (kg/tree)</label>
              <input type="number" className="form-control form-control-sm" min={0} step={1}
                value={impact.yield_per_tree_kg} onChange={(e) => setImpactField('yield_per_tree_kg', +e.target.value)} />
            </div>
            <div className="col-6">
              <label className="small mb-1">Farmgate (PHP/kg)</label>
              <input type="number" className="form-control form-control-sm" min={0} step={1}
                value={impact.farmgate_price_php_per_kg} onChange={(e) => setImpactField('farmgate_price_php_per_kg', +e.target.value)} />
            </div>
          </div>
          <div className="row g-2 mb-2">
            {['damage_low','damage_base','damage_high'].map((k, i) => (
              <div className="col-4" key={k}>
                <label className="small mb-1">{['Low %','Base %','High %'][i]}</label>
                <input type="number" className="form-control form-control-sm" min={0} max={100} step={1}
                  value={impact[k]} onChange={(e) => setImpactField(k, +e.target.value)} />
              </div>
            ))}
          </div>
          <label className="small fw-medium mb-1 d-block">
            <i className="bi bi-cash-stack me-1" />Pesticide cost (PHP/ha)
          </label>
          <input type="number" className="form-control form-control-sm mb-1" min={0} step={50}
            value={impact.pesticide_cost_per_ha} onChange={(e) => setImpactField('pesticide_cost_per_ha', +e.target.value)} />
          <small className="text-muted d-block">Updates Crop Impact and Economic Impact estimates.</small>
        </div>
      )}

      <hr className="mt-3 mb-2" />
      <button id="run-sim-btn" type="button" className="btn btn-success w-100 fw-semibold"
        onClick={handleRun} disabled={running || !orchardGeojson}>
        {running
          ? <><span className="spinner-border spinner-border-sm me-2" />Running…</>
          : <><i className="bi bi-play-circle-fill me-2" />Run Simulation</>}
      </button>

      {status && (
        <div className={`alert alert-${status.type} py-2 mt-2`} style={{ fontSize: '.83rem' }}>
          {status.msg}
        </div>
      )}
    </CollapsibleCard>
  )
}
