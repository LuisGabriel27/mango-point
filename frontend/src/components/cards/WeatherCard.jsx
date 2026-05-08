import { useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'

const CARDINAL = ['N','NE','E','SE','S','SW','W','NW']
function toCardinal(deg) { return CARDINAL[Math.round(deg / 45) % 8] }

function Slider({ id, label, iconName, min, max, step, value, marks, onChange, hint }) {
  return (
    <div className="mb-3">
      <label className="small fw-medium mb-1 d-block" htmlFor={id}>
        <i className={`bi bi-${iconName} me-1`} /> {label}
      </label>
      <input
        id={id} type="range" className="form-range w-100"
        min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <div className="d-flex justify-content-between small text-muted" style={{ marginTop: '-4px' }}>
        {marks.map((m) => <span key={m.label}>{m.label}</span>)}
      </div>
      <div className="text-center small fw-semibold" style={{ color: 'var(--mp-primary)' }}>
        {value}{hint ? ` ${hint}` : ''}
      </div>
    </div>
  )
}

export default function WeatherCard({ weather, manualWeather, weatherOverrideActive, onManualChange, onOverrideToggle }) {
  const [override, setOverride] = useState(weatherOverrideActive ?? false)
  const [timeVarying, setTimeVarying] = useState(false)

  const handleOverrideToggle = (checked) => {
    setOverride(checked)
    onOverrideToggle?.(checked)
  }

  const current = weather?.current

  const setField = (field, val) => onManualChange({ ...manualWeather, [field]: val })

  return (
    <CollapsibleCard iconName="cloud-sun" title="Live Weather">
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
              <i className="bi bi-wind me-1" />{current.wind_speed_ms?.toFixed(1)} m/s {toCardinal(current.wind_direction_deg ?? 0)}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-muted small mb-2">
          <span className="spinner-border spinner-border-sm me-1" />
          Fetching weather…
        </div>
      )}
      <small className="text-muted d-block mb-2">
        <i className="bi bi-arrow-repeat me-1" />Auto-refreshes every 60 s
      </small>

      <hr className="my-2" />

      {/* Manual override toggle */}
      <div className="form-check form-switch mb-1">
        <input
          className="form-check-input" type="checkbox" role="switch"
          id="weather-override-toggle"
          checked={override}
          onChange={(e) => handleOverrideToggle(e.target.checked)}
        />
        <label className="form-check-label fw-medium small" htmlFor="weather-override-toggle">
          Manual Weather Override
        </label>
      </div>
      <small className="text-muted d-block mb-2">
        Override live forecast for scenario testing. Only used when running a simulation.
      </small>

      {override && (
        <div className="pt-2">
          <div className="alert alert-warning py-1 px-2 mb-2" style={{ fontSize: '.78rem' }}>
            <i className="bi bi-flask me-1" /> Scenario mode active — simulation uses these values
          </div>

          <Slider id="manual-temp" label="Temperature (°C)" iconName="thermometer-half"
            min={15} max={45} step={0.5} value={manualWeather.temperature_c ?? 30}
            marks={[{label:'15'},{label:'25'},{label:'35'},{label:'45'}]}
            onChange={(v) => setField('temperature_c', v)} hint="°C"
          />
          <Slider id="manual-wind" label="Wind Speed (m/s)" iconName="wind"
            min={0} max={15} step={0.5} value={manualWeather.wind_speed_ms ?? 2}
            marks={[{label:'0'},{label:'5'},{label:'10'},{label:'15'}]}
            onChange={(v) => setField('wind_speed_ms', v)} hint="m/s"
          />
          <Slider id="manual-wind-dir" label="Wind Direction (° from)" iconName="compass"
            min={0} max={355} step={5} value={manualWeather.wind_direction_deg ?? 90}
            marks={[{label:'N'},{label:'E'},{label:'S'},{label:'W'},{label:'N'}]}
            onChange={(v) => setField('wind_direction_deg', v)} hint="°"
          />
          <Slider id="manual-rain" label="Rainfall (mm/h)" iconName="cloud-rain"
            min={0} max={50} step={1} value={manualWeather.rainfall_mm ?? 0}
            marks={[{label:'0'},{label:'10'},{label:'25'},{label:'50'}]}
            onChange={(v) => setField('rainfall_mm', v)} hint="mm/h"
          />
          <small className="text-muted d-block">
            Rainfall &gt; 5 mm triggers Cecid Fly emergence (requires FRUITLET stage).
          </small>

          <hr className="my-3" />

          <div className="form-check form-switch mb-1">
            <input
              className="form-check-input" type="checkbox" role="switch"
              id="time-varying-toggle"
              checked={timeVarying}
              onChange={(e) => setTimeVarying(e.target.checked)}
            />
            <label className="form-check-label fw-medium small" htmlFor="time-varying-toggle">
              Time-varying schedule (advanced)
            </label>
          </div>
          <small className="text-muted d-block mb-2">
            Vary weather hour-by-hour. Use this to simulate wet → dry transitions for Cecid Fly emergence.
          </small>

          {timeVarying && (
            <div className="alert alert-info py-2 px-2" style={{ fontSize: '.78rem' }}>
              <i className="bi bi-info-circle me-1" />
              Time-varying blocks are configured in the Simulation panel when running.
            </div>
          )}
        </div>
      )}
    </CollapsibleCard>
  )
}
