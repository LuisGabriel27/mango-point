import { useEffect, useState } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import CollapsibleCard from '../CollapsibleCard'
import {
  addCustomWeatherPeriod,
  createCecidGateTestPreset,
  createConstantWeatherTimeline,
  customWeatherBlocks,
  localDateTimeValue,
  repeatFirstDayBlocks,
  weatherCoverage,
  WEATHER_VALUE_PRESETS,
} from '../../utils/weatherSchedule'
import { DAYLIGHT_CONDITIONS } from '../../utils/daylightLight'

const CARDINAL = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
const CARDINAL_DEG = { N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315 }

function toCardinal(deg) {
  const number = Number(deg)
  return CARDINAL[Number.isFinite(number) ? ((Math.round(number / 45) % 8) + 8) % 8 : 0]
}

function NumberField({ label, value, onChange, min = 0, max, step = 0.1, suffix }) {
  return (
    <label className="weather-number-field">
      <span>{label}</span>
      <div className="input-group input-group-sm">
        <input
          type="number" className="form-control" value={value}
          min={min} max={max} step={step}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {suffix && <span className="input-group-text">{suffix}</span>}
      </div>
    </label>
  )
}

function PresetField({ label, field, value, onChange, suffix, max, children }) {
  return (
    <div className="weather-preset-field">
      <div className="weather-value-row">
        <NumberField label={label} value={value} onChange={onChange} suffix={suffix} max={max} />
        {children}
      </div>
      <div className="weather-preset-chips" role="group" aria-label={label + ' presets'}>
        {WEATHER_VALUE_PRESETS[field].map((preset) => (
          <button
            type="button" key={preset.label}
            className={'weather-preset-chip' + (Number(value) === preset.value ? ' active' : '')}
            aria-pressed={Number(value) === preset.value}
            aria-label={preset.label + ': ' + preset.value + ' ' + suffix}
            onClick={() => onChange(preset.value)}
          >
            <span>{preset.label}</span>
            <small>{preset.value + ' ' + suffix}</small>
          </button>
        ))}
      </div>
    </div>
  )
}

function WindDirectionField({ value, onChange }) {
  return (
    <label className="weather-number-field weather-wind-direction">
      <span>Wind from</span>
      <select
        className="form-select form-select-sm"
        value={toCardinal(value)}
        onChange={(event) => onChange(CARDINAL_DEG[event.target.value])}
      >
        {CARDINAL.map((direction) => <option key={direction} value={direction}>{direction}</option>)}
      </select>
    </label>
  )
}

export function DaylightConditionField({ block, onChange }) {
  return (
    <div className="weather-preset-field">
      <label className="weather-number-field">
        <span>Daylight light condition</span>
        <select className="form-select form-select-sm" value={block.daylight_condition || ''}
          onChange={(event) => onChange({ daylight_condition: event.target.value || null,
            daylight_condition_basis: event.target.value ? block.daylight_condition_basis || 'assumed' : null })}>
          <option value="">Not specified (radiation needed)</option>
          {Object.entries(DAYLIGHT_CONDITIONS).map(([value, condition]) => (
            <option key={value} value={value}>{condition.label}</option>
          ))}
        </select>
      </label>
      {block.daylight_condition && (
        <label className="weather-number-field mt-2">
          <span>Light condition source</span>
          <select className="form-select form-select-sm" value={block.daylight_condition_basis || 'assumed'}
            onChange={(event) => onChange({ daylight_condition_basis: event.target.value })}>
            <option value="assumed">Assumed scenario</option>
            <option value="observed">Observed locally</option>
          </select>
        </label>
      )}
      <small className="text-muted d-block mt-1">Describes outdoor daylight for this period, separately from cloud percentage. Observed locally means your reported condition. Tree-canopy shade alone does not enable Cecid emergence or movement. Applies during daylight; rain, wind, fruit stage and soil checks still apply.</small>
    </div>
  )
}

function SoilContextEditor({ timeline, onChange }) {
  const context = timeline.manual_soil_context || { preset: 'dry' }
  const update = (patch) => onChange({
    ...timeline,
    manual_soil_context: {
      total_rain_mm: 8, event_duration_hours: 4, hours_since_rain_ended: 6,
      ...context, ...patch,
    },
  })
  return (
    <div className="weather-soil-settings">
      <div className="small fw-semibold mb-2">Starting soil</div>
      <div className="btn-group btn-group-sm w-100 mb-2" role="group" aria-label="Starting soil condition">
        {[['dry', 'Dry'], ['moist', 'Moist now'], ['recently_wet', 'Recently wet'], ['custom', 'Custom']].map(([value, label]) => (
          <button
            type="button" key={value}
            className={'btn ' + (context.preset === value ? 'btn-primary' : 'btn-outline-secondary')}
            aria-pressed={context.preset === value}
            onClick={() => update({ preset: value })}
          >{label}</button>
        ))}
      </div>
      {context.preset === 'dry' && <small className="text-muted">No rainfall in the 72 hours before the simulation.</small>}
      {context.preset === 'moist' && (
        <div>
          <NumberField label="Moisture strength" value={(context.initial_moisture_score ?? 1) * 100}
            max={100} suffix="%" step={1}
            onChange={(value) => update({ initial_moisture_score: Math.max(0, Math.min(1, value / 100)) })} />
          <small className="text-muted">Assumed moist soil at Hour 0 without adding earlier rain. 100% is the model's moisture scale, not a measured soil-water percentage. Moisture decreases over time unless rain adds to it.</small>
        </div>
      )}
      {context.preset === 'recently_wet' && (
        <small className="text-muted">8 mm of rain over 4 hours, ending 6 hours before Hour 0.</small>
      )}
      {context.preset === 'custom' && (
        <div className="weather-soil-grid">
          <NumberField label="Total rain" value={context.total_rain_mm ?? 8} max={500} suffix="mm"
            onChange={(value) => update({ total_rain_mm: value })} />
          <NumberField label="Duration" value={context.event_duration_hours ?? 4} min={1} max={72} suffix="h" step={1}
            onChange={(value) => update({ event_duration_hours: Math.max(1, value) })} />
          <NumberField label="Ended ago" value={context.hours_since_rain_ended ?? 6} max={72} suffix="h" step={1}
            onChange={(value) => update({ hours_since_rain_ended: value })} />
        </div>
      )}
    </div>
  )
}

function WeatherPeriodOverview({ blocks, hours, wholeRun, modal = false }) {
  return (
    <div className={'weather-period-summary-list' + (modal ? ' weather-period-modal-summary-list' : '')}
      role="list" aria-label="Custom weather periods">
      {blocks.length === 0 && (
        <div className="weather-period-overview-empty" role="status">
          <i className="bi bi-cloud-sun" aria-hidden="true" />
          <strong>No weather periods yet</strong>
          <span>Add a period in the setup screen to define the simulation weather.</span>
        </div>
      )}
      {blocks.map((block, index) => (
        <div className="weather-period-summary" key={index} role="listitem">
          <div className="weather-period-summary-header">
            <div className="weather-period-summary-title">
              <span className={'weather-condition ' + (block.rainfall_mm > 0 ? 'rain' : 'dry')}>
                <i className={'bi bi-' + (block.rainfall_mm > 0 ? 'cloud-rain' : 'sun')} />
                {block.rainfall_mm > 0 ? 'Rain' : 'Dry'}
              </span>
              <strong>{wholeRun ? 'Entire simulation' : 'Period ' + (index + 1)}</strong>
            </div>
            <span className="weather-period-summary-range">
              {wholeRun ? `Hour 0–${hours}` : `Hours ${block.start_hour}–${block.end_hour}`}
            </span>
          </div>
          <div className="weather-period-summary-values" aria-label={'Details for weather period ' + (index + 1)}>
            <span className="weather-period-summary-value">
              <i className="bi bi-thermometer-half" aria-hidden="true" />{block.temperature_c ?? '—'}°C
            </span>
            <span className="weather-period-summary-value">
              <i className="bi bi-cloud-rain" aria-hidden="true" />{block.rainfall_mm ?? '—'} mm/h
            </span>
            <span className="weather-period-summary-value">
              <i className="bi bi-wind" aria-hidden="true" />{block.wind_speed_ms ?? '—'} m/s {toCardinal(block.wind_dir_deg)}
            </span>
            <span className="weather-period-summary-value">
              <i className="bi bi-cloud" aria-hidden="true" />{block.cloud_cover_pct ?? 0}% cloud
            </span>
            <span className="weather-period-summary-value">
              <i className="bi bi-brightness-high" aria-hidden="true" />
              {DAYLIGHT_CONDITIONS[block.daylight_condition]?.label || 'Light not specified'}
              {block.daylight_condition && ` (${block.daylight_condition_basis === 'observed' ? 'observed' : 'assumed'})`}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

export function CustomWeatherEditor({
  timeline,
  onChange,
  hours = 48,
  pestType = 'fruitfly',
  onCecidPresetLoad,
  onSimulationHoursChange,
}) {
  const wholeRun = timeline.coverage_mode === 'entire_simulation' && timeline.advanced_blocks?.length === 1
  const blocks = wholeRun || timeline.mode === 'guided'
    ? customWeatherBlocks(timeline, hours)
    : timeline.advanced_blocks || []
  const coverage = weatherCoverage(blocks, hours)
  const rainyPeriodCount = blocks.filter((block) => block.rainfall_mm > 0).length
  const dryPeriodCount = Math.max(0, blocks.length - rainyPeriodCount)
  const [activeIndex, setActiveIndex] = useState(0)
  const [periodsOpen, setPeriodsOpen] = useState(false)
  const [periodsMode, setPeriodsMode] = useState('overview')
  const isCecid = pestType === 'cecid'

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, blocks.length - 1)))
  }, [blocks.length])

  useEffect(() => {
    if (!periodsOpen) return undefined
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setPeriodsOpen(false)
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [periodsOpen])

  const update = (patch) => onChange({ ...timeline, ...patch, enabled: true, mode: 'advanced' })
  const updateBlock = (index, field, value) => update({
    advanced_blocks: blocks.map((block, position) => position === index
      ? { ...block, ...(typeof field === 'object' ? field : { [field]: value }) } : block),
  })

  const changePeriod = (offset) => {
    setActiveIndex((current) => Math.max(0, Math.min(blocks.length - 1, current + offset)))
  }
  const openPeriods = () => {
    setActiveIndex(0)
    setPeriodsMode('overview')
    setPeriodsOpen(true)
  }
  const last = blocks.at(-1)
  const canAdd = !last || last.end_hour < hours || last.end_hour - last.start_hour >= 2
  const removeBlock = (index) => {
    const remaining = blocks.filter((_, position) => position !== index)
    // Keep explicit time ranges; deleting a period must not stretch the remaining weather.
    update({ advanced_blocks: remaining, coverage_mode: 'scheduled' })
    setActiveIndex((current) => Math.min(current, Math.max(0, remaining.length - 1)))
  }
  const repeatDay = () => update({
    advanced_blocks: repeatFirstDayBlocks(blocks, hours),
    coverage_mode: 'scheduled',
  })
  const loadCecidPreset = () => {
    // The gate test is a daily pattern intended to exercise multiple dawn/dusk
    // windows. Keep the seven-day schedule and duration in sync.
    const presetHours = 168
    onSimulationHoursChange?.(presetHours)
    onCecidPresetLoad?.()
    onChange(createCecidGateTestPreset(new Date(), presetHours))
    openPeriods()
  }

  return (
    <div className="custom-weather-editor">
      <div className="weather-start-field">
        <label className="weather-start-label" htmlFor="custom-weather-start">Start date &amp; time</label>
        <DatePicker
          id="custom-weather-start"
          selected={timeline.start_datetime ? new Date(timeline.start_datetime) : null}
          onChange={(date) => update({ start_datetime: date ? localDateTimeValue(date) : '' })}
          showTimeSelect timeFormat="HH:mm" timeIntervals={60}
          dateFormat="MMM d, yyyy h:mm aa"
          placeholderText="Current date & time"
          className="form-control form-control-sm mp-datepicker-input"
          calendarClassName="mp-datepicker" popperPlacement="bottom-start" isClearable
        />
        <small className="text-muted">Guimaras time. Hour 0 begins here.</small>
      </div>

      <div className="weather-periods-toolbar">
        <div>
          <strong>Weather periods</strong>
          <small>{blocks.length} period{blocks.length === 1 ? '' : 's'} · {hours} simulation hours</small>
        </div>
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={openPeriods}>
          <i className="bi bi-pencil-square me-1" />Edit periods
        </button>
      </div>

      <div className="weather-period-general-preview" role="status" aria-label="Weather periods general preview">
        <span className="weather-period-general-preview-icon" aria-hidden="true">
          <i className="bi bi-calendar3-range" />
        </span>
        <div className="weather-period-general-preview-content">
          <strong>{blocks.length ? 'Schedule ready to review' : 'No weather periods configured'}</strong>
          <span>{blocks.length
            ? `${rainyPeriodCount} rainy · ${dryPeriodCount} dry · Hour 0–${hours}`
            : 'Use Edit periods to add a weather period.'}</span>
        </div>
        <i className="bi bi-chevron-right weather-period-general-preview-arrow" aria-hidden="true" />
      </div>

      {periodsOpen && (
        <div className="weather-periods-modal-backdrop" role="presentation" onMouseDown={() => setPeriodsOpen(false)}>
          <div className="weather-periods-modal" role="dialog" aria-modal="true" aria-labelledby="weather-periods-modal-title"
            onMouseDown={(event) => event.stopPropagation()}>
            <div className="weather-periods-modal-header">
              <div>
                <h5 id="weather-periods-modal-title">{periodsMode === 'overview' ? 'Weather period details' : 'Set up weather periods'}</h5>
                <small>{periodsMode === 'overview'
                  ? 'Review the schedule first, then continue to edit each period.'
                  : 'Edit each time range and its weather values. Later periods take priority if ranges overlap.'}</small>
              </div>
              <button type="button" className="btn-close" aria-label="Close weather periods" onClick={() => setPeriodsOpen(false)} />
            </div>
            <div className="weather-periods-modal-body">
      {periodsMode === 'overview' ? (
        <>
          <div className="weather-period-overview-intro">
            <strong>{blocks.length} period{blocks.length === 1 ? '' : 's'} · {hours} simulation hours</strong>
            <span>Check the timing and weather values below before opening the setup controls.</span>
          </div>
          <WeatherPeriodOverview blocks={blocks} hours={hours} wholeRun={wholeRun} modal />
        </>
      ) : (
        <>
      <div className="weather-period-single" role="region" aria-label={`Weather period ${activeIndex + 1} of ${blocks.length}`}>
        {blocks[activeIndex] && (() => {
          const block = blocks[activeIndex]
          const index = activeIndex
          return (
          <section className="cecid-timeline-block weather-period-card" key={index} aria-label={'Weather period ' + (index + 1)}>
            <div className="weather-period-heading">
              <span className={'weather-condition ' + (block.rainfall_mm > 0 ? 'rain' : 'dry')}>
                <i className={'bi bi-' + (block.rainfall_mm > 0 ? 'cloud-rain' : 'sun')} />
                {block.rainfall_mm > 0 ? 'Rain' : 'Dry'}
              </span>
              <strong>{wholeRun ? 'Entire simulation' : 'Period ' + (index + 1)}</strong>
              {blocks.length > 1 && (
                <button type="button" className="btn btn-sm btn-link text-danger p-0 ms-auto"
                  aria-label={'Remove weather period ' + (index + 1)} onClick={() => removeBlock(index)}>
                  <i className="bi bi-trash" />
                </button>
              )}
            </div>

            {wholeRun ? (
              <div className="weather-period-range">
                <span>Hour 0–{hours}</span>
                <button type="button" onClick={() => update({ coverage_mode: 'scheduled', advanced_blocks: blocks })}>
                  Edit hours
                </button>
              </div>
            ) : (
              <div className="weather-period-hours">
                <NumberField label="Start hour" value={block.start_hour} max={hours - 1} step={1} suffix="h"
                  onChange={(value) => updateBlock(index, 'start_hour', value)} />
                <NumberField label="End hour (excluded)" value={block.end_hour} min={1} max={hours} step={1} suffix="h"
                  onChange={(value) => updateBlock(index, 'end_hour', value)} />
              </div>
            )}

            <PresetField label="Temperature" field="temperature_c" value={block.temperature_c}
              suffix="°C" max={50} onChange={(value) => updateBlock(index, 'temperature_c', value)} />
            <PresetField label="Rainfall" field="rainfall_mm" value={block.rainfall_mm}
              suffix="mm/h" max={100} onChange={(value) => updateBlock(index, 'rainfall_mm', value)} />
            <PresetField label="Cloud cover" field="cloud_cover_pct" value={block.cloud_cover_pct ?? 0}
              suffix="%" max={100} onChange={(value) => updateBlock(index, 'cloud_cover_pct', value)} />
            <DaylightConditionField block={block} onChange={(patch) => updateBlock(index, patch)} />
            <PresetField label="Wind strength" field="wind_speed_ms" value={block.wind_speed_ms}
              suffix="m/s" max={30} onChange={(value) => updateBlock(index, 'wind_speed_ms', value)}>
              <WindDirectionField value={block.wind_dir_deg} onChange={(value) => updateBlock(index, 'wind_dir_deg', value)} />
            </PresetField>
            {blocks.length > 1 && (
              <div className="weather-period-navigation weather-period-navigation-in-card" aria-label="Weather period navigation">
                <span className="weather-period-count">Period {activeIndex + 1} of {blocks.length}</span>
                <button type="button" className="btn btn-sm btn-outline-secondary"
                  aria-label="Previous weather period" disabled={activeIndex === 0} onClick={() => changePeriod(-1)}>
                  <i className="bi bi-chevron-left me-1" />Previous
                </button>
                <button type="button" className="btn btn-sm btn-outline-secondary"
                  aria-label="Next weather period" disabled={activeIndex >= blocks.length - 1} onClick={() => changePeriod(1)}>
                  Next<i className="bi bi-chevron-right ms-1" />
                </button>
              </div>
            )}
          </section>
          )
        })()}
      </div>
      <div className="weather-period-actions">
        <button type="button" className="btn btn-sm btn-outline-primary" disabled={!canAdd}
          onClick={() => onChange(addCustomWeatherPeriod(timeline, hours))}>
          <i className="bi bi-plus-lg me-1" />Add period
        </button>
        <button type="button" className="btn btn-sm btn-outline-secondary" disabled={hours <= 24} onClick={repeatDay}
          title="Repeat the first 24 hours until the selected simulation duration">
          <i className="bi bi-repeat me-1" />Repeat first day
        </button>
      </div>
      {!wholeRun && blocks.length === 1 && blocks[0]?.start_hour === 0 && blocks[0]?.end_hour === hours && (
        <button type="button" className="btn btn-sm btn-link px-0"
          onClick={() => update({ coverage_mode: 'entire_simulation' })}>Use for entire simulation</button>
      )}
        </>
      )}

            <div className="weather-periods-modal-footer">
              {periodsMode === 'overview' ? (
                <button type="button" className="btn btn-sm btn-primary" onClick={() => setPeriodsMode('editor')}>
                  <i className="bi bi-pencil-square me-1" />Set up periods
                </button>
              ) : (
                <button type="button" className="btn btn-sm btn-primary" onClick={() => setPeriodsOpen(false)}>Done</button>
              )}
            </div>
          </div>
          </div>
        </div>
      )}

      {coverage.uncovered_hours > 0 && (
        <div className="weather-coverage-note" role="status">
          {coverage.uncovered_hours} hour(s) are uncovered and use default weather. Extend a period or repeat your day.
        </div>
      )}
      {coverage.overlapping_hours > 0 && (
        <div className="weather-coverage-note" role="status">
          {coverage.overlapping_hours} hour(s) overlap. Later periods take priority.
        </div>
      )}

      <details className="weather-cecid-settings">
          <summary>
            <span className="weather-period-general-preview-icon weather-cecid-settings-icon" aria-hidden="true">
              <i className="bi bi-moisture" />
            </span>
            <strong className="weather-cecid-settings-title">Soil &amp; Cecid test preset</strong>
            <small>{isCecid ? (timeline.manual_soil_context?.preset === 'recently_wet' ? 'Recently wet' :
              timeline.manual_soil_context?.preset === 'moist' ? 'Moist at Hour 0' :
              timeline.manual_soil_context?.preset === 'custom' ? 'Custom soil' : 'Dry soil') : 'Available for Cecid Fly'}</small>
            <i className="bi bi-chevron-down weather-cecid-settings-chevron" aria-hidden="true" />
          </summary>
          <SoilContextEditor timeline={timeline} onChange={onChange} />
          <div className="weather-cecid-test" data-testid="cecid-gate-test-preset">
            <div>
              <strong>Dawn + dusk test</strong>
              <small>Seven days of 4 rainy hours, then 20 dry hours, repeated. Loading it selects Cecid Fly and a 7-day simulation.</small>
            </div>
            <button type="button" className="btn btn-sm btn-outline-primary" onClick={loadCecidPreset}>Use preset</button>
          </div>
          <small className="text-muted d-block">
            This preset changes weather only. Soil moisture affects emergence; rain, wind and dawn/dusk or cloudy daylight affect adult movement;
            weed and wind coefficients remain research assumptions for BPI calibration.
          </small>
      </details>
    </div>
  )
}

export default function WeatherCard({
  weather,
  manualWeather,
  weatherOverrideActive,
  onOverrideToggle,
  weatherTimeline,
  onTimelineChange,
  onRetry,
  simulationHours = 48,
  pestType = 'fruitfly',
  onCecidPresetLoad,
  onSimulationHoursChange,
  embedded = false,
}) {
  const [showDetails, setShowDetails] = useState(Boolean(weatherOverrideActive))
  const [retryState, setRetryState] = useState('idle')
  const current = weather?.current
  const hours = Math.max(1, Math.min(168, Number(simulationHours) || 48))
  const timeline = Array.isArray(weatherTimeline?.advanced_blocks) || weatherTimeline?.mode === 'guided'
    ? weatherTimeline
    : createConstantWeatherTimeline(manualWeather, hours)

  useEffect(() => {
    if (weatherOverrideActive) setShowDetails(true)
  }, [weatherOverrideActive])

  useEffect(() => {
    if (current?.source !== 'synthetic') setRetryState('idle')
  }, [current?.source])

  const retryWeather = async () => {
    if (retryState === 'loading' || !onRetry) return
    setRetryState('loading')
    try {
      const succeeded = await onRetry()
      setRetryState(succeeded === false ? 'error' : 'success')
    } catch (_) {
      setRetryState('error')
    }
  }

  const selectCustom = () => {
    onTimelineChange?.({ ...timeline, enabled: true })
    onOverrideToggle?.(true)
    setShowDetails(true)
  }

  return (
    <CollapsibleCard iconName="cloud-sun" title="Weather" embedded={embedded}>
      {current ? (
        <div className="mb-2">
          <div className="d-flex justify-content-between align-items-center mb-1">
            <span className="fw-semibold" style={{ fontSize: '1.1rem' }}>{current.temperature_c?.toFixed(1)}°C</span>
            <span className="text-muted small">{current.source}</span>
          </div>
          <div className="row g-1 small text-muted">
            <div className="col-6"><i className="bi bi-droplet me-1" />Humidity: {current.humidity}%</div>
            <div className="col-6">
              <i className="bi bi-wind me-1" />{current.wind_speed_ms?.toFixed(1)} m/s from {toCardinal(current.wind_direction_deg ?? 0)}
            </div>
            <div className="col-6">
              <i className="bi bi-cloud me-1" />Cloud: {current.cloud_cover_pct != null ? `${current.cloud_cover_pct.toFixed(0)}%` : 'Unavailable'}
            </div>
            <div className="col-6">
              <i className="bi bi-sun me-1" />Solar: {current.shortwave_radiation_wm2 != null ? `${current.shortwave_radiation_wm2.toFixed(0)} W/m²` : 'Unavailable'}
            </div>
            <div className="col-12">Direct sunlight: {current.direct_normal_irradiance_wm2 != null ? `${current.direct_normal_irradiance_wm2.toFixed(0)} W/m²` : 'Unavailable'}</div>
          </div>
          <small className="text-muted">Cloud and sunlight are forecast estimates. Shade beneath trees alone does not enable Cecid activity.</small>
        </div>
      ) : (
        <div className="text-muted small mb-2"><span className="spinner-border spinner-border-sm me-1" />Fetching weather…</div>
      )}
      <small className="text-muted d-block mb-2"><i className="bi bi-arrow-repeat me-1" />Auto-refreshes every 60 s</small>

      <div className="weather-source-switch" role="group" aria-label="Simulation weather source">
        <button type="button" className={'btn btn-sm ' + (!weatherOverrideActive ? 'btn-primary' : 'btn-outline-secondary')}
          aria-pressed={!weatherOverrideActive} onClick={() => onOverrideToggle?.(false)}>
          <i className="bi bi-cloud-sun me-1" />Live Forecast
        </button>
        <button type="button" className={'btn btn-sm ' + (weatherOverrideActive ? 'btn-primary' : 'btn-outline-secondary')}
          aria-pressed={Boolean(weatherOverrideActive)} onClick={selectCustom}>
          <i className="bi bi-sliders me-1" />Custom Weather
        </button>
      </div>

      {current?.source === 'synthetic' && (
        <div className="alert alert-warning py-2 px-2 mt-2 mb-2" style={{ fontSize: '.76rem' }}>
          <div className="fw-semibold"><i className="bi bi-exclamation-triangle-fill me-1" />Synthetic fallback is active</div>
          <div className="mt-1">{weather?.fallback_reason || weather?.provenance?.fallback_reason || 'The live provider did not return usable data.'}</div>
          <button
            type="button"
            className="btn btn-sm btn-outline-dark mt-2 py-0"
            onClick={retryWeather}
            disabled={retryState === 'loading'}
            aria-busy={retryState === 'loading'}
          >
            {retryState === 'loading'
              ? <><span className="spinner-border spinner-border-sm me-1" />Checking Open-Meteo…</>
              : <><i className="bi bi-arrow-clockwise me-1" />Retry Open-Meteo</>}
          </button>
          {retryState === 'error' && (
            <div className="small text-danger mt-2" role="status">
              Open-Meteo is still unavailable. Please try again shortly.
            </div>
          )}
          {retryState === 'success' && (
            <div className="small text-success mt-2" role="status">
              Weather request completed; refreshing the forecast…
            </div>
          )}
        </div>
      )}

      {weatherOverrideActive && (
        <>
          <button type="button" className="sim-expandable-row mt-2 mb-2" aria-expanded={showDetails}
            onClick={() => setShowDetails((value) => !value)}>
            <i className="bi bi-calendar3-range sim-expandable-icon" />
            <span className="sim-expandable-label">Custom weather settings</span>
            <i className={'bi bi-chevron-' + (showDetails ? 'up' : 'down') + ' sim-expandable-chevron'} />
          </button>
          {showDetails && (
            <CustomWeatherEditor
              timeline={timeline} hours={hours} pestType={pestType}
              onCecidPresetLoad={onCecidPresetLoad}
              onSimulationHoursChange={onSimulationHoursChange}
              onChange={(next) => { onTimelineChange?.(next); onOverrideToggle?.(true) }}
            />
          )}
        </>
      )}
    </CollapsibleCard>
  )
}
