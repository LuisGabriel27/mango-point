import { useState, useEffect, useMemo } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import api, { apiErrorMessage } from '../../api'
import {
  buildGuidedBlocks,
  normalizeAdvancedBlocks,
  summarizeWeatherBlocks,
} from '../../utils/weatherSchedule'

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

// Sensitivity presets — maps plain-language choice to biological gate params
const SENSITIVITY_PRESETS = {
  cautious: {
    label: 'Cautious',
    icon: 'shield-check',
    description: 'Pest spreads only under strong trigger conditions. Use when recent scouting shows low activity.',
    cecid_rainfall_threshold_mm: 8.0,
    cecid_base_dispersal_prob: 0.08,
    fruit_fly_temp_threshold_c: 28.0,
    fruit_fly_base_dispersal_prob: 0.05,
  },
  standard: {
    label: 'Standard',
    icon: 'bullseye',
    description: 'Based on 2022–2025 BPI orchard data. Best default for most situations.',
    cecid_rainfall_threshold_mm: null,
    cecid_base_dispersal_prob: null,
    fruit_fly_temp_threshold_c: null,
    fruit_fly_base_dispersal_prob: null,
  },
  sensitive: {
    label: 'Sensitive',
    icon: 'exclamation-triangle',
    description: 'Pest spreads under mild conditions. Use for early-season monitoring or when activity is already high.',
    cecid_rainfall_threshold_mm: 2.0,
    cecid_base_dispersal_prob: 0.18,
    fruit_fly_temp_threshold_c: 22.0,
    fruit_fly_base_dispersal_prob: 0.13,
  },
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

function treatmentApplicationPayload(type, efficacy) {
  if (type === 'protective_spray') {
    return [{
      treatment_type: type,
      coverage: 'whole_orchard',
      efficacy,
      source_reduction: 0,
      label: 'Protective spray scenario',
    }]
  }

  if (type === 'sanitation') {
    return [{
      treatment_type: type,
      coverage: 'targeted',
      efficacy: 0,
      source_reduction: efficacy,
      label: 'Sanitation source-reduction scenario',
    }]
  }

  if (type === 'combined') {
    return [{
      treatment_type: type,
      coverage: 'whole_orchard',
      efficacy,
      source_reduction: efficacy,
      label: 'Combined treatment scenario',
    }]
  }

  return [{
    treatment_type: type,
    coverage: 'targeted',
    efficacy,
    source_reduction: efficacy,
    label: 'Targeted source-tree treatment scenario',
  }]
}

function SectionLabel({ iconName, text }) {
  return (
    <div className="section-label">
      <i className={`bi bi-${iconName} me-1`} />
      <span>{text}</span>
    </div>
  )
}

function BtnGroup({ options, value, onChange, small = false }) {
  return (
    <div className={`sim-btn-group${small ? ' sim-btn-group-sm' : ''}`}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`sim-btn-group-item${value === o.value ? ' active' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.icon && <i className={`bi bi-${o.icon} me-1`} />}
          {o.label}
        </button>
      ))}
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

function CecidTimelineResult({ diagnostics }) {
  if (!Array.isArray(diagnostics) || !diagnostics.length) return null

  const favorableHours = diagnostics.filter((entry) => entry.status === 'favorable' || entry.favorable)
  const limitedHours = diagnostics.filter((entry) => entry.status === 'limited')
  const reachableHours = diagnostics.filter((entry) => Number(entry.reachable_tree_count ?? 0) > 0)
  const maxRelays = Math.max(0, ...diagnostics.map((entry) => Number(entry.active_relay_count ?? 0)))
  return (
    <div className="border rounded p-2 mt-2" style={{ fontSize: '.78rem' }}>
      <div className="d-flex align-items-center justify-content-between mb-1">
        <strong><i className="bi bi-activity me-1" />Cecid gate timeline</strong>
        <span className={`badge ${favorableHours.length ? 'text-bg-success' : 'text-bg-secondary'}`}>
          {favorableHours.length} favorable hour{favorableHours.length === 1 ? '' : 's'}
        </span>
      </div>
      <div className="small text-muted mb-2">
        {favorableHours.length
          ? <>Favorable hours: {favorableHours.map((entry) => `${entry.step} (${String(entry.hour_of_day).padStart(2, '0')}:00)`).join(', ')}</>
          : 'No hour reached favorable Cecid suitability in this run.'}
        {limitedHours.length > 0 && <> Â· {limitedHours.length} twilight hour{limitedHours.length === 1 ? '' : 's'} limited by weather</>}
        {reachableHours.length > 0 && <> Â· trees reachable in {reachableHours.length} hour{reachableHours.length === 1 ? '' : 's'}</>}
        {maxRelays > 0 && <> Â· up to {maxRelays} active weed relay{maxRelays === 1 ? '' : 's'}</>}
      </div>
      <details>
        <summary className="text-primary" style={{ cursor: 'pointer' }}>Show hourly gate details</summary>
        <div className="table-responsive mt-1" style={{ maxHeight: 220 }}>
          <table className="table table-sm mb-0" style={{ fontSize: '.7rem' }}>
            <thead>
              <tr><th>Hour</th><th>Local</th><th>Rain</th><th>Soil</th><th>Wind</th><th>Sources / cohorts / relays</th><th>Trees</th><th>Neighbor</th><th>Score</th><th>Status</th></tr>
            </thead>
            <tbody>
              {diagnostics.map((entry) => (
                <tr key={`${entry.step}-${entry.datetime}`}>
                  <td>{entry.step}</td>
                  <td>{String(entry.hour_of_day).padStart(2, '0')}:00</td>
                  <td>{Number(entry.rainfall_mm).toFixed(1)} mm/h</td>
                  <td>{Number(entry.soil_wetness_mm ?? 0).toFixed(1)} mm</td>
                  <td title={`Downwind ${Math.round(Number(entry.downwind_bearing_deg ?? 0))}°; edge direction factor ${Number(entry.directional_factor_min ?? 1).toFixed(2)}–${Number(entry.directional_factor_max ?? 1).toFixed(2)}`}>
                    {Number(entry.wind_speed_ms ?? 0).toFixed(1)} m/s
                    <br />{Number(entry.wind_speed_kmh ?? 0).toFixed(1)} km/h
                  </td>
                  <td title={JSON.stringify(entry.active_relay_density_counts ?? {})}>
                    {Number(entry.active_source_count ?? 0)} / {Number(entry.active_cohort_count ?? 0)} / {Number(entry.active_relay_count ?? 0)}
                  </td>
                  <td>{Number(entry.reachable_tree_count ?? 0)}</td>
                  <td>{Number(entry.neighbor_contribution ?? 0).toFixed(3)}</td>
                  <td>{Math.round(Number(entry.suitability_score ?? 0) * 100)}%</td>
                  <td title={[...(entry.hard_reasons || []), ...(entry.limiting_factors || [])].join('; ')}>
                    {entry.status || (entry.gate_open ? 'Favorable' : 'Closed')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}

export default function SimulationCard({
  orchardGeojson,
  orchardId,
  treeOverrides,
  treeStageOverrides,
  phenologyZones,
  cecidWeedZones,
  legacyCecidEmergenceZones,
  onPestTypeChange,
  onClearTreeStageOverrides,
  onSimulationComplete,
  manualWeather,
  weatherOverrideActive,
  weatherTimeline,
  orchardCoordinates,
  suggestedParams,
  onClearSuggested,
  loadedParams,
}) {
  const [simMode, setSimMode] = useState('grid')
  const [pestType, setPestType] = useState('fruitfly')
  const [orchardStage, setOrchardStage] = useState('mature')
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
  const [prefixRain, setPrefixRain] = useState(null)
  const [gateDiagnostics, setGateDiagnostics] = useState([])

  useEffect(() => {
    onPestTypeChange?.(pestType)
  }, [onPestTypeChange, pestType])

  // Calibration overrides
  const [showCalibration, setShowCalibration] = useState(false)
  const [useObsSeeds, setUseObsSeeds] = useState(false)
  const [obsLookbackDays, setObsLookbackDays] = useState(30)
  const [sensitivity, setSensitivity] = useState('standard')

  const timelineActive = Boolean(weatherOverrideActive && weatherTimeline?.enabled)
  const timelineHours = Number.parseInt(simHours, 10)
  const safeTimelineHours = Number.isFinite(timelineHours) ? timelineHours : 48
  const timelineBlocks = useMemo(() => {
    if (!timelineActive) return []
    return weatherTimeline?.mode === 'advanced'
      ? normalizeAdvancedBlocks(weatherTimeline?.advanced_blocks, safeTimelineHours)
      : buildGuidedBlocks(weatherTimeline?.guided_phases, safeTimelineHours)
  }, [safeTimelineHours, timelineActive, weatherTimeline?.advanced_blocks, weatherTimeline?.guided_phases, weatherTimeline?.mode])
  const timelinePayloadBlocks = timelineBlocks.length
    ? timelineBlocks
    : [{
      start_hour: 0,
      end_hour: safeTimelineHours,
      temperature_c: 30,
      wind_speed_ms: 2,
      wind_dir_deg: 90,
      rainfall_mm: 0,
    }]
  const timelineSummary = useMemo(() => {
    if (!timelineActive) return null
    const threshold = SENSITIVITY_PRESETS[sensitivity]?.cecid_rainfall_threshold_mm ?? 5
    return summarizeWeatherBlocks(
      timelineBlocks,
      safeTimelineHours,
      weatherTimeline?.start_datetime,
      threshold,
      {
        manual_soil_context: weatherTimeline?.manual_soil_context,
        manual_weather_prefix_rain: Array.isArray(prefixRain) ? prefixRain : null,
        latitude: orchardCoordinates?.lat,
        longitude: orchardCoordinates?.lon,
      },
    )
  }, [
    orchardCoordinates?.lat,
    orchardCoordinates?.lon,
    prefixRain,
    safeTimelineHours,
    sensitivity,
    timelineActive,
    timelineBlocks,
    weatherTimeline?.manual_soil_context,
    weatherTimeline?.start_datetime,
  ])

  // Apply suggested params from a weather forecast alert
  useEffect(() => {
    if (!suggestedParams) return
    if (suggestedParams.pest_type) setPestType(suggestedParams.pest_type)
    if (suggestedParams.orchard_stage) setOrchardStage(suggestedParams.orchard_stage)
    if (suggestedParams.hours) setSimHours(String(suggestedParams.hours))
    if (suggestedParams.days_since_flowering != null) setDaysFlowering(suggestedParams.days_since_flowering)
    if (suggestedParams.neighbor_threat != null) setNeighborThreat(suggestedParams.neighbor_threat)
    setPrefixRain(suggestedParams.manual_weather_prefix_rain ?? null)
  }, [suggestedParams])

  useEffect(() => {
    if (!loadedParams || !Object.keys(loadedParams).length) return

    const normalizePest = (value) => {
      const v = String(value ?? '').toLowerCase()
      if (v.includes('fruit')) return 'fruitfly'
      if (v.includes('cecid')) return 'cecid'
      return value || 'fruitfly'
    }
    const firstTreatment = Array.isArray(loadedParams.treatment_applications)
      ? loadedParams.treatment_applications[0]
      : null
    const dashboardState = loadedParams.dashboard_state ?? {}

    if (loadedParams.simulation_mode) setSimMode(loadedParams.simulation_mode)
    if (loadedParams.pest_type) setPestType(normalizePest(loadedParams.pest_type))
    if (loadedParams.orchard_stage) setOrchardStage(loadedParams.orchard_stage)
    if (loadedParams.days_since_flowering != null) setDaysFlowering(Number(loadedParams.days_since_flowering))
    if (loadedParams.neighbor_threat != null) setNeighborThreat(Number(loadedParams.neighbor_threat))
    if (loadedParams.neighbor_direction) setNeighborDir(loadedParams.neighbor_direction)
    if (loadedParams.hours != null) setSimHours(String(loadedParams.hours))
    if (loadedParams.manual_weather_prefix_rain != null) setPrefixRain(loadedParams.manual_weather_prefix_rain)

    setTreatmentEnabled(Boolean(firstTreatment))
    if (firstTreatment?.treatment_type) setTreatmentType(firstTreatment.treatment_type)
    if (firstTreatment) {
      const restoredEfficacy = firstTreatment.treatment_type === 'sanitation'
        ? firstTreatment.source_reduction
        : (firstTreatment.efficacy ?? firstTreatment.source_reduction)
      setTreatmentEfficacy(Number(restoredEfficacy ?? 0.65))
    }

    if (loadedParams.impact_assumptions) {
      setImpact({ ...DEFAULTS, ...loadedParams.impact_assumptions })
    }

    setUseObsSeeds(Boolean(loadedParams.use_observations_as_seeds))
    if (loadedParams.observations_lookback_days != null) {
      setObsLookbackDays(Number(loadedParams.observations_lookback_days))
    }
    if (dashboardState.sensitivity) setSensitivity(dashboardState.sensitivity)

    setStatus({ type: 'info', msg: 'Loaded saved simulation parameters into the controls.' })
  }, [loadedParams])

  const setImpactField = (k, v) => setImpact((p) => ({ ...p, [k]: v }))

  const handleRun = async () => {
    setRunning(true)
    setGateDiagnostics([])
    setStatus({ type: 'info', msg: 'Simulation in progress…' })
    try {
      const parsedHours = Number.parseInt(simHours, 10)
      const requestedHours = Number.isFinite(parsedHours) ? parsedHours : 48
      const body = {
        pest_type: pestType,
        orchard_id: orchardId,
        orchard_geojson: orchardGeojson,
        hours: requestedHours,
        bagged_tree_ids: [],
        initial_infestation: [],
        treatment_applications: treatmentEnabled
          ? treatmentApplicationPayload(treatmentType, treatmentEfficacy)
          : [],
        random_seed: null,
        risk_threshold: 0.7,
        orchard_stage: orchardStage,
        days_since_flowering: daysFlowering,
        neighbor_threat: neighborThreat,
        simulation_mode: simMode,
        include_time_series: true,
        impact_assumptions: impact,
        dashboard_state: {
          sensitivity,
          treatment_enabled: treatmentEnabled,
          treatment_type: treatmentType,
          treatment_efficacy: treatmentEfficacy,
          use_observations_as_seeds: useObsSeeds,
          observations_lookback_days: obsLookbackDays,
          weather_override_active: weatherOverrideActive,
          weather_timeline: timelineActive ? weatherTimeline : null,
          impact_assumptions: impact,
          phenology_zones: phenologyZones ?? [],
          cecid_weed_zones: cecidWeedZones ?? [],
          cecid_emergence_zones: legacyCecidEmergenceZones ?? [],
        },
      }
      if (pestType === 'cecid') {
        body.cecid_weed_zones = (cecidWeedZones ?? []).map((zone) => ({
          id: zone.id,
          label: zone.label,
          density: zone.density,
          coordinates: zone.coordinates,
        }))
        if (legacyCecidEmergenceZones?.length) {
          body.cecid_emergence_zones = legacyCecidEmergenceZones.map((zone) => ({
            id: zone.id,
            label: zone.label,
            pressure: zone.pressure,
            coordinates: zone.coordinates,
          }))
        }
      }
      if (pestType === 'cecid') body.debug_gates = true

      if (neighborThreat > 0 && neighborDir) {
        body.neighbor_direction = neighborDir
      }

      if (treeStageOverrides && Object.keys(treeStageOverrides).length > 0) {
        body.tree_stage_overrides = treeStageOverrides
      }

      if (weatherOverrideActive) {
        if (timelineActive) {
          body.manual_weather_blocks = timelinePayloadBlocks
          if (weatherTimeline?.manual_soil_context) {
            body.manual_soil_context = weatherTimeline.manual_soil_context
          }
          if (weatherTimeline?.start_datetime) {
            body.manual_weather_start = weatherTimeline.start_datetime
          }
        } else {
          body.manual_weather = manualWeatherPayload(manualWeather)
          if (manualWeather?.sim_datetime) {
            body.manual_weather_start = manualWeather.sim_datetime
          }
        }
      }

      if (Array.isArray(prefixRain) && prefixRain.length > 0) {
        body.manual_weather_prefix_rain = prefixRain
      } else if (timelineActive && Number(prefixRain) > 0) {
        body.manual_soil_context = {
          preset: 'custom',
          total_rain_mm: Number(prefixRain),
          event_duration_hours: 1,
          hours_since_rain_ended: 1,
        }
      }

      if (treeOverrides && Object.keys(treeOverrides).length > 0) {
        body.tree_overrides = treeOverrides
      }

      // Calibration overrides
      if (useObsSeeds) {
        body.use_observations_as_seeds = true
        body.observations_lookback_days = obsLookbackDays
      }
      const preset = SENSITIVITY_PRESETS[sensitivity]
      if (preset) {
        if (preset.cecid_rainfall_threshold_mm != null) body.cecid_rainfall_threshold_mm = preset.cecid_rainfall_threshold_mm
        if (preset.cecid_base_dispersal_prob != null) body.cecid_base_dispersal_prob = preset.cecid_base_dispersal_prob
        if (preset.fruit_fly_temp_threshold_c != null) body.fruit_fly_temp_threshold_c = preset.fruit_fly_temp_threshold_c
        if (preset.fruit_fly_base_dispersal_prob != null) body.fruit_fly_base_dispersal_prob = preset.fruit_fly_base_dispersal_prob
      }

      const res = await api.runSimulation(body)
      setGateDiagnostics(res.data.gate_diagnostics ?? [])
      const peakPct = res.data.peak_risk != null ? `${(res.data.peak_risk * 100).toFixed(0)}%` : '—'
      const nInfested = res.data.n_infested_final ?? 0
      const weatherSrc = timelineActive
        ? 'weather timeline'
        : weatherOverrideActive ? 'manual weather' : 'live forecast'
      const seedNote = useObsSeeds ? 'field observations' : 'auto seed'
      const sensitivityLabel = SENSITIVITY_PRESETS[sensitivity]?.label ?? 'Standard'
      setStatus({
        type: 'success',
        msg: `Done — peak risk: ${peakPct}, ${nInfested} infested · ${seedNote} · ${sensitivityLabel} · ${weatherSrc}`,
      })
      onSimulationComplete?.({
        ...res.data,
        impact_assumptions: impact,
        request_payload: body,
        input_parameters: body,
      })
    } catch (err) {
      const msg = apiErrorMessage(err, 'Simulation failed.')
      setStatus({ type: 'danger', msg })
    } finally {
      setRunning(false)
    }
  }

  const handleClearSuggested = () => {
    setPrefixRain(null)
    onClearSuggested?.()
  }

  return (
    <CollapsibleCard iconName="cpu" title="Simulation">
      {suggestedParams?._rain_summary && (
        <div
          className="alert alert-primary py-2 px-2 mb-2 d-flex align-items-start gap-2"
          style={{ fontSize: '.78rem' }}
        >
          <i className="bi bi-cloud-rain-fill flex-shrink-0 mt-1" />
          <span className="flex-grow-1">{suggestedParams._rain_summary}</span>
          <button
            type="button"
            className="btn-close flex-shrink-0"
            style={{ fontSize: '.6rem' }}
            onClick={handleClearSuggested}
          />
        </div>
      )}
      <SectionLabel iconName="diagram-3" text="Spread Model" />
      <BtnGroup
        value={simMode}
        onChange={setSimMode}
        options={[
          { value: 'grid', label: 'Grid (CA)', icon: 'grid' },
          { value: 'tree_graph', label: 'Tree Graph', icon: 'diagram-3' },
        ]}
      />
      {simMode === 'tree_graph' && (
        <div className="alert alert-info py-1 px-2 mt-1 mb-0" style={{ fontSize: '.78rem' }}>
          <i className="bi bi-info-circle me-1" />
          Tree Graph uses crown-to-crown distances. Supply <code>crown_radius_m</code> in GeoJSON properties or set a global fallback.
        </div>
      )}

      <SectionLabel iconName="bug" text="Pest & Phenology" />
      <label className="small fw-medium mb-1 d-block"><i className="bi bi-bug me-1" />Pest</label>
      <BtnGroup
        value={pestType}
        onChange={setPestType}
        options={[
          { value: 'cecid', label: 'Cecid Fly', icon: 'droplet' },
          { value: 'fruitfly', label: 'Fruit Fly', icon: 'bug' },
        ]}
      />
      <label className="small fw-medium mb-1 d-block mt-2"><i className="bi bi-flower1 me-1" />Orchard Stage</label>
      <BtnGroup
        value={orchardStage}
        onChange={setOrchardStage}
        options={STAGE_OPTIONS}
        small
      />
      <small className="text-muted d-block mb-2 mt-1">Fruitlet activates Cecid Fly · Mature activates Fruit Fly</small>

      {treeStageOverrides && Object.keys(treeStageOverrides).length > 0 && (
        <div className="alert alert-success py-1 px-2 mb-2 d-flex align-items-center gap-2" style={{ fontSize: '.78rem' }}>
          <span className="flex-grow-1">
            <i className="bi bi-map me-1" />
            {Object.keys(treeStageOverrides).length} tree(s) use map-assigned stage zones.
          </span>
          <button type="button" className="btn btn-sm btn-outline-success py-0 px-2" onClick={onClearTreeStageOverrides}>
            Clear
          </button>
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
          <div className="sim-btn-group sim-btn-group-sm">
            {DIR_OPTIONS.map((o) => (
              <button key={o.value} type="button"
                className={`sim-btn-group-item${neighborDir === o.value ? ' active' : ''}`}
                onClick={() => setNeighborDir(o.value)}>
                {o.value}
              </button>
            ))}
          </div>
        </div>
      )}
      <small className="text-muted d-block mb-0">
        {pestType === 'cecid'
          ? 'Adds risk only when a live soil-source cohort can reach a fruitlet tree during an eligible dawn/dusk hour.'
          : 'Pressure from unmanaged orchards (historical ~2× higher CPTD).'}
      </small>

      <SectionLabel iconName="shield-plus" text="Treatment Scenario" />
      <label className="sim-toggle-row mb-1" htmlFor="treatment-enabled">
        <div className="sim-toggle-body">
          <i className="bi bi-shield-plus sim-toggle-icon" />
          <span className="sim-toggle-label">Include orchard treatment</span>
        </div>
        <input className="form-check-input flex-shrink-0" type="checkbox" role="switch" id="treatment-enabled"
          checked={treatmentEnabled} onChange={(e) => setTreatmentEnabled(e.target.checked)} />
      </label>
      {treatmentEnabled && (
        <div>
          <label className="small fw-medium mb-1 d-block"><i className="bi bi-capsule me-1" />Treatment type</label>
          <BtnGroup
            value={treatmentType}
            onChange={setTreatmentType}
            small
            options={[
              { value: 'protective_spray', label: 'Protective' },
              { value: 'targeted_spray', label: 'Targeted' },
              { value: 'sanitation', label: 'Sanitation' },
              { value: 'combined', label: 'Combined' },
            ]}
          />
          <Slider id="treatment-efficacy" label="Effectiveness" iconName="activity"
            min={0} max={0.95} step={0.05} value={treatmentEfficacy}
            marks={[{label:'0%'},{label:'50%'},{label:'95%'}]}
            onChange={setTreatmentEfficacy}
          />
          {(treatmentType === 'targeted_spray' || treatmentType === 'sanitation') && (
            <small className="text-muted d-block mb-2">
              Applies to detected or seeded source trees unless specific targets are selected later.
            </small>
          )}
        </div>
      )}

      <SectionLabel iconName="clock-history" text="Forecast Duration" />
      <BtnGroup
        value={simHours}
        onChange={setSimHours}
        options={[
          { value: '24', label: '24 h' },
          { value: '48', label: '48 h' },
          { value: '72', label: '72 h' },
          { value: '168', label: '7 day' },
        ]}
      />

      {timelineActive && timelineSummary && pestType === 'cecid' && (
        <div className={`alert ${timelineSummary.favorable_hours > 0 && orchardStage === 'fruitlet' ? 'alert-success' : 'alert-warning'} py-2 px-2 mt-2 mb-0`} style={{ fontSize: '.76rem' }}>
          <div className="fw-semibold mb-1"><i className="bi bi-activity me-1" />Cecid timeline checks</div>
          <ul className="mb-0 ps-3">
            {orchardStage !== 'fruitlet' && <li>Cecid Fly requires the Fruitlet orchard stage.</li>}
            {!timelineSummary.reaches_rain_threshold && <li>Decayed soil wetness never reaches the selected {SENSITIVITY_PRESETS[sensitivity]?.cecid_rainfall_threshold_mm ?? 5} mm sensitivity scale.</li>}
            {!timelineSummary.has_dry_crepuscular_window && <li>No dry solar dawn or dusk window is scheduled.</li>}
            {timelineSummary.favorable_hours === 0 && timelineSummary.limited_hours > 0 && <li>Twilight windows exist, but rain, soil moisture, or wind keeps suitability below 25%.</li>}
            {orchardStage === 'fruitlet' && timelineSummary.favorable_hours > 0 && (
              <li>{timelineSummary.favorable_hours} hour(s) are favorable; moderate wind or drizzle reduces probability instead of hard-closing the model.</li>
            )}
            {timelineSummary.covered_hours < timelineSummary.hours && <li>Uncovered hours use default dry weather.</li>}
          </ul>
        </div>
      )}

      {/* Impact assumptions */}
      <button
        type="button"
        className="sim-expandable-row mt-3"
        onClick={() => setShowImpact((v) => !v)}
      >
        <i className="bi bi-cash-stack sim-expandable-icon" />
        <span className="sim-expandable-label">Crop Impact Assumptions</span>
        <i className={`bi bi-chevron-${showImpact ? 'up' : 'down'} sim-expandable-chevron`} />
      </button>
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

      {/* Calibration panel */}
      <button
        type="button"
        className="sim-expandable-row"
        onClick={() => setShowCalibration((v) => !v)}
      >
        <i className="bi bi-sliders sim-expandable-icon" />
        <span className="sim-expandable-label">Accuracy Settings</span>
        <i className={`bi bi-chevron-${showCalibration ? 'up' : 'down'} sim-expandable-chevron`} />
      </button>
      {showCalibration && (
        <div className="border rounded p-2 mb-2" style={{ fontSize: '.82rem' }}>

          {/* Observation seeding */}
          <label className="sim-toggle-row mb-1" htmlFor="obs-seeds">
            <div className="sim-toggle-body">
              <i className="bi bi-geo-alt sim-toggle-icon" />
              <span className="sim-toggle-label">Start from field observations</span>
            </div>
            <input className="form-check-input flex-shrink-0" type="checkbox" role="switch" id="obs-seeds"
              checked={useObsSeeds} onChange={(e) => setUseObsSeeds(e.target.checked)} />
          </label>
          <small className="text-muted d-block mb-2">
            Uses scout reports as the starting point instead of a random guess.
          </small>
          {useObsSeeds && (
            <div className="mb-3 ms-1">
              <label className="small mb-1 d-block">Include observations from the last:</label>
              <div className="d-flex gap-2 flex-wrap">
                {[7, 14, 30, 60].map((d) => (
                  <button
                    key={d} type="button"
                    className={`btn btn-sm py-0 ${obsLookbackDays === d ? 'btn-primary' : 'btn-outline-secondary'}`}
                    onClick={() => setObsLookbackDays(d)}
                  >
                    {d === 7 ? '1 week' : d === 14 ? '2 weeks' : d === 30 ? '1 month' : '2 months'}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Sensitivity preset */}
          <div className="fw-medium small mb-1">
            <i className="bi bi-activity me-1" />How cautious should the forecast be?
          </div>
          <div className="d-flex flex-column gap-1 mb-2">
            {Object.entries(SENSITIVITY_PRESETS).map(([key, preset]) => (
              <button
                key={key} type="button"
                className={`btn btn-sm text-start py-1 px-2 ${sensitivity === key ? 'btn-primary' : 'btn-outline-secondary'}`}
                onClick={() => setSensitivity(key)}
              >
                <i className={`bi bi-${preset.icon} me-1`} />
                <strong>{preset.label}</strong>
                <span className="ms-1 fw-normal" style={{ fontSize: '.75rem', opacity: 0.85 }}>— {preset.description}</span>
              </button>
            ))}
          </div>

          {treeOverrides && Object.values(treeOverrides).filter(v => v === 'infected').length > 0 && (
            <div className="text-muted" style={{ fontSize: '.76rem' }}>
              <i className="bi bi-exclamation-circle me-1 text-danger" />
              {Object.values(treeOverrides).filter(v => v === 'infected').length} tree(s) marked infected on map will also be used.
            </div>
          )}
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
      {pestType === 'cecid' && (
        <CecidTimelineResult diagnostics={gateDiagnostics} />
      )}
    </CollapsibleCard>
  )
}
