import { useState } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import CollapsibleCard from '../CollapsibleCard'

const CARDINAL = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
const CARDINAL_DEG = { N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315 }
function toCardinal(deg) { return CARDINAL[Math.round((deg ?? 0) / 45) % 8] }

// Plain-language weather scenarios — values sent to the simulation engine
const SCENARIOS = [
  {
    key: 'live',
    label: 'Live Forecast',
    icon: 'cloud-sun',
    description: 'Use real weather from the forecast API.',
    values: null, // means: don't override
  },
  {
    key: 'after_rain',
    label: 'After Rain',
    icon: 'cloud-drizzle',
    description: 'Rain just stopped — prime Cecid Fly emergence window.',
    tag: 'Cecid Fly',
    tagColor: 'primary',
    values: { temperature_c: 26, wind_speed_ms: 1.5, wind_direction_deg: 90, rainfall_mm: 0 },
  },
  {
    key: 'custom',
    label: 'Custom',
    icon: 'sliders',
    description: 'Set exact values manually.',
    values: 'custom',
  },
]

const VISIBLE_SCENARIOS = SCENARIOS.filter((scenario) => (
  scenario.key === 'live' || scenario.key === 'custom'
))

function WindCompass({ value, onChange }) {
  const current = toCardinal(value)
  return (
    <div className="mb-3">
      <div className="small fw-medium mb-1">
        <i className="bi bi-compass me-1" />Wind coming from
      </div>
      <div className="d-grid gap-1" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        {CARDINAL.map((dir) => (
          <button
            key={dir} type="button"
            className={`btn btn-sm py-0 ${current === dir ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => onChange(CARDINAL_DEG[dir])}
          >
            {dir}
          </button>
        ))}
      </div>
    </div>
  )
}

function RainPicker({ value, onChange }) {
  const levels = [
    { label: 'None', val: 0, hint: 'Dry' },
    { label: 'Light', val: 3, hint: '3 mm/h' },
    { label: 'Moderate', val: 8, hint: '8 mm/h' },
    { label: 'Heavy', val: 20, hint: '20 mm/h' },
  ]
  const active = levels.reduce((best, l) => Math.abs(l.val - value) < Math.abs(best.val - value) ? l : best, levels[0])
  return (
    <div className="mb-3">
      <div className="small fw-medium mb-1">
        <i className="bi bi-cloud-rain me-1" />Rainfall
      </div>
      <div className="d-flex gap-1 flex-wrap">
        {levels.map((l) => (
          <button
            key={l.label} type="button"
            className={`btn btn-sm py-0 ${active.val === l.val ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => onChange(l.val)}
          >
            {l.label}
            <span className="ms-1 text-muted" style={{ fontSize: '.72rem' }}>({l.hint})</span>
          </button>
        ))}
      </div>
      {value >= 5 && (
        <small className="text-primary d-block mt-1">
          <i className="bi bi-info-circle me-1" />Enough to trigger Cecid Fly (needs Fruitlet stage)
        </small>
      )}
    </div>
  )
}

function TempPicker({ value, onChange }) {
  const levels = [
    { label: 'Cool', val: 22, hint: '22°C' },
    { label: 'Warm', val: 27, hint: '27°C' },
    { label: 'Hot', val: 33, hint: '33°C' },
    { label: 'Very hot', val: 38, hint: '38°C' },
  ]
  const active = levels.reduce((best, l) => Math.abs(l.val - value) < Math.abs(best.val - value) ? l : best, levels[0])
  return (
    <div className="mb-3">
      <div className="small fw-medium mb-1">
        <i className="bi bi-thermometer-half me-1" />Temperature
      </div>
      <div className="d-flex gap-1 flex-wrap">
        {levels.map((l) => (
          <button
            key={l.label} type="button"
            className={`btn btn-sm py-0 ${active.val === l.val ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => onChange(l.val)}
          >
            {l.label}
            <span className="ms-1 text-muted" style={{ fontSize: '.72rem' }}>({l.hint})</span>
          </button>
        ))}
      </div>
      {value < 25 && (
        <small className="text-muted d-block mt-1">
          <i className="bi bi-info-circle me-1" />Below 25°C — Fruit Fly gate will stay closed
        </small>
      )}
    </div>
  )
}

export default function WeatherCard({ weather, manualWeather, weatherOverrideActive, onManualChange, onOverrideToggle }) {
  const [scenarioKey, setScenarioKey] = useState('live')

  const current = weather?.current

  const handleScenarioSelect = (scenario) => {
    setScenarioKey(scenario.key)
    if (scenario.key === 'live') {
      onOverrideToggle?.(false)
    } else if (scenario.values && scenario.values !== 'custom') {
      onManualChange(scenario.values)
      onOverrideToggle?.(true)
    } else if (scenario.values === 'custom') {
      onOverrideToggle?.(true)
    }
  }

  const setField = (field, val) => onManualChange({ ...manualWeather, [field]: val })

  const activeScenario = VISIBLE_SCENARIOS.find((s) => s.key === scenarioKey) ?? VISIBLE_SCENARIOS[0]
  const isOverrideOn = scenarioKey !== 'live'

  return (
    <CollapsibleCard iconName="cloud-sun" title="Weather">
      {/* Live weather display */}
      {current ? (
        <div className="mb-2">
          <div className="d-flex justify-content-between align-items-center mb-1">
            <span className="fw-semibold" style={{ fontSize: '1.1rem' }}>
              {current.temperature_c?.toFixed(1)}°C
            </span>
            <span className="text-muted small">{current.source}</span>
          </div>
          <div className="row g-1 small text-muted">
            <div className="col-6">
              <i className="bi bi-droplet me-1" />Humidity: {current.humidity}%
            </div>
            <div className="col-6">
              <i className="bi bi-wind me-1" />{current.wind_speed_ms?.toFixed(1)} m/s from {toCardinal(current.wind_direction_deg ?? 0)}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-muted small mb-2">
          <span className="spinner-border spinner-border-sm me-1" />Fetching weather…
        </div>
      )}
      <small className="text-muted d-block mb-2">
        <i className="bi bi-arrow-repeat me-1" />Auto-refreshes every 60 s
      </small>

      <hr className="my-2" />

      {/* Scenario selector */}
      <div className="small fw-medium mb-2">
        <i className="bi bi-flask me-1" />Test a weather scenario
      </div>
      <div className="d-flex flex-column gap-1 mb-2">
        {VISIBLE_SCENARIOS.map((s) => (
          <button
            key={s.key} type="button"
            className={`btn btn-sm text-start py-1 px-2 ${scenarioKey === s.key ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => handleScenarioSelect(s)}
          >
            <i className={`bi bi-${s.icon} me-1`} />
            <strong>{s.label}</strong>
            {s.tag && (
              <span className={`badge bg-${s.tagColor} ms-1`} style={{ fontSize: '.65rem' }}>{s.tag}</span>
            )}
            <span className="ms-1 fw-normal" style={{ fontSize: '.75rem', opacity: 0.85 }}>— {s.description}</span>
          </button>
        ))}
      </div>

      {/* Active scenario banner */}
      {isOverrideOn && (
        <div className="alert alert-warning py-1 px-2 mb-2" style={{ fontSize: '.78rem' }}>
          <i className="bi bi-flask me-1" />
          <strong>{activeScenario.label}</strong> scenario active — simulation uses these values instead of the live forecast.
        </div>
      )}

      {/* Custom controls — only shown in Custom mode */}
      {scenarioKey === 'custom' && (
        <div className="border rounded p-2 mt-1" style={{ fontSize: '.82rem' }}>

          {/* Date & time */}
          <div className="mb-3">
            <div className="small fw-medium mb-1">
              <i className="bi bi-calendar-event me-1" />Simulation date &amp; time
            </div>
            <DatePicker
              selected={manualWeather?.sim_datetime ? new Date(manualWeather.sim_datetime) : null}
              onChange={(date) => setField('sim_datetime', date ? date.toISOString() : '')}
              showTimeSelect
              timeFormat="HH:mm"
              timeIntervals={30}
              dateFormat="MMMM d, yyyy h:mm aa"
              placeholderText="Select date and time…"
              className="form-control form-control-sm mp-datepicker-input"
              calendarClassName="mp-datepicker"
              popperPlacement="bottom-start"
              isClearable
            />
            <small className="text-muted">Leave blank to use the current date and time.</small>
          </div>

          {/* Temperature */}
          <TempPicker value={manualWeather?.temperature_c ?? 30} onChange={(v) => setField('temperature_c', v)} />
          <div className="input-group input-group-sm mb-3" style={{ maxWidth: 140 }}>
            <input
              type="number" className="form-control" placeholder="Exact °C"
              value={manualWeather?.temperature_c ?? ''}
              min={0} max={50} step={0.1}
              onChange={(e) => setField('temperature_c', parseFloat(e.target.value))}
            />
            <span className="input-group-text">°C</span>
          </div>

          {/* Rainfall */}
          <RainPicker value={manualWeather?.rainfall_mm ?? 0} onChange={(v) => setField('rainfall_mm', v)} />
          <div className="input-group input-group-sm mb-3" style={{ maxWidth: 140 }}>
            <input
              type="number" className="form-control" placeholder="Exact mm/h"
              value={manualWeather?.rainfall_mm ?? ''}
              min={0} max={100} step={0.5}
              onChange={(e) => setField('rainfall_mm', parseFloat(e.target.value))}
            />
            <span className="input-group-text">mm/h</span>
          </div>

          {/* Wind direction */}
          <WindCompass value={manualWeather?.wind_direction_deg ?? 90} onChange={(v) => setField('wind_direction_deg', v)} />

          {/* Wind strength */}
          <div className="mb-1">
            <div className="small fw-medium mb-1">
              <i className="bi bi-wind me-1" />Wind strength
            </div>
            <div className="d-flex gap-1 flex-wrap mb-1">
              {[{l:'Calm',v:1},{l:'Light',v:3},{l:'Moderate',v:6},{l:'Strong',v:10}].map(({l,v}) => {
                const cur = manualWeather?.wind_speed_ms ?? 2
                const isActive = Math.abs(cur - v) < 2
                return (
                  <button key={l} type="button"
                    className={`btn btn-sm py-0 ${isActive ? 'btn-primary' : 'btn-outline-secondary'}`}
                    onClick={() => setField('wind_speed_ms', v)}>
                    {l}
                  </button>
                )
              })}
            </div>
            <div className="input-group input-group-sm" style={{ maxWidth: 140 }}>
              <input
                type="number" className="form-control" placeholder="Exact m/s"
                value={manualWeather?.wind_speed_ms ?? ''}
                min={0} max={30} step={0.5}
                onChange={(e) => setField('wind_speed_ms', parseFloat(e.target.value))}
              />
              <span className="input-group-text">m/s</span>
            </div>
            {(manualWeather?.wind_speed_ms ?? 2) >= 6 && (
              <small className="text-muted d-block mt-1">
                <i className="bi bi-info-circle me-1" />Strong wind closes the Cecid Fly gate
              </small>
            )}
          </div>
        </div>
      )}
    </CollapsibleCard>
  )
}
