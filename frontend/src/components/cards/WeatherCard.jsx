import { useEffect, useRef, useState } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import CollapsibleCard from '../CollapsibleCard'
import {
  buildGuidedBlocks,
  createCecidGateTestPreset,
  DEFAULT_GUIDED_PHASES,
  localDateTimeValue,
  localMidnightValue,
  repeatFirstDayBlocks,
} from '../../utils/weatherSchedule'

const CARDINAL = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
const CARDINAL_DEG = { N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315 }
function toCardinal(deg) {
  const numeric = Number(deg)
  return CARDINAL[Number.isFinite(numeric) ? ((Math.round(numeric / 45) % 8) + 8) % 8 : 0]
}

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
  {
    key: 'timeline',
    label: 'Weather timeline',
    icon: 'calendar3-range',
    description: 'Build repeating wet-to-dry periods for Cecid Fly.',
    tag: 'Cecid Fly',
    tagColor: 'primary',
    values: 'timeline',
  },
]

const VISIBLE_SCENARIOS = SCENARIOS.filter((scenario) => (
  scenario.key === 'live' || scenario.key === 'custom' || scenario.key === 'timeline'
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

function NumberField({ label, value, onChange, min, max, step = 0.5, suffix }) {
  return (
    <label className="small d-block">
      <span className="text-muted d-block mb-1">{label}</span>
      <div className="input-group input-group-sm">
        <input
          type="number"
          className="form-control"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {suffix && <span className="input-group-text">{suffix}</span>}
      </div>
    </label>
  )
}

function WindDirectionField({ value, onChange }) {
  const direction = toCardinal(Number(value))
  return (
    <label className="small d-block">
      <span className="text-muted d-block mb-1">Wind from</span>
      <select
        className="form-select form-select-sm px-1"
        style={{ minWidth: 0 }}
        value={direction}
        onChange={(event) => onChange(CARDINAL_DEG[event.target.value])}
      >
        {CARDINAL.map((cardinal) => (
          <option key={cardinal} value={cardinal}>{cardinal}</option>
        ))}
      </select>
    </label>
  )
}

function GuidedTimelineEditor({ timeline, onChange }) {
  const phases = Array.isArray(timeline?.guided_phases) && timeline.guided_phases.length
    ? timeline.guided_phases
    : DEFAULT_GUIDED_PHASES

  const updatePhase = (index, field, value) => {
    const next = phases.map((phase, phaseIndex) => (
      phaseIndex === index ? { ...phase, [field]: value } : phase
    ))
    onChange({ ...timeline, guided_phases: next })
  }

  const resetPreset = () => onChange({
    ...timeline,
    guided_phases: DEFAULT_GUIDED_PHASES.map((phase) => ({ ...phase })),
  })

  return (
    <>
      <div className="alert alert-info py-2 px-2 mb-2" style={{ fontSize: '.76rem' }}>
        <i className="bi bi-info-circle me-1" />
        This phase pattern repeats for the selected simulation duration. Rain builds soil moisture, then dry calm hours allow Cecid Fly emergence at dawn or dusk.
      </div>

      <div className="d-flex align-items-center gap-1 flex-wrap mb-3" aria-label="Repeating weather cycle">
        <span className="small text-muted me-1">Cycle:</span>
        {phases.map((phase, index) => (
          <span key={phase.id ?? index}>
            {index > 0 && <span className="text-muted mx-1">→</span>}
            <span className={`badge ${phase.rainfall_mm > 0 ? 'text-bg-primary' : 'text-bg-success'}`}>
              {phase.rainfall_mm > 0 ? 'RAIN' : 'DRY'} {phase.duration_hours}h
            </span>
          </span>
        ))}
        <span className="small text-muted ms-1">→ repeat</span>
      </div>

      <div className="mb-3">
        <div className="small fw-medium mb-1">
          <i className="bi bi-calendar-event me-1" />Timeline start (Guimaras local time)
        </div>
        <DatePicker
          selected={timeline?.start_datetime ? new Date(timeline.start_datetime) : null}
          onChange={(date) => onChange({ ...timeline, start_datetime: localDateTimeValue(date) || localMidnightValue() })}
          showTimeSelect
          timeFormat="HH:mm"
          timeIntervals={60}
          dateFormat="MMMM d, yyyy h:mm aa"
          placeholderText="Choose local start time…"
          className="form-control form-control-sm mp-datepicker-input"
          calendarClassName="mp-datepicker"
          popperPlacement="bottom-start"
        />
        <small className="text-muted">Start at midnight when you want the first simulated hour to be 00:00.</small>
      </div>

      {phases.map((phase, index) => (
        <div
          className={`border rounded p-2 mb-2 ${phase.rainfall_mm > 0 ? 'border-primary' : 'border-success'}`}
          key={phase.id ?? index}
        >
          <div className="d-flex justify-content-between align-items-center mb-2">
            <div>
              <span className={`badge ${phase.rainfall_mm > 0 ? 'text-bg-primary' : 'text-bg-success'} me-1`}>
                {phase.rainfall_mm > 0 ? 'RAIN' : 'DRY'}
              </span>
              <strong className="small">{index + 1}. {phase.label}</strong>
            </div>
            <span className="small text-muted">{phase.rainfall_mm > 0 ? 'Builds moisture' : 'Gate may open'}</span>
          </div>
          <div className="row g-2">
            <div className="col-6">
              <NumberField
                label="Duration"
                value={phase.duration_hours}
                min={1}
                max={168}
                step={1}
                suffix="h"
                onChange={(value) => updatePhase(index, 'duration_hours', Math.max(1, value || 1))}
              />
            </div>
            <div className="col-6">
              <NumberField
                label={phase.rainfall_mm > 0 ? 'Rain intensity' : 'Rain intensity (dry = 0)'}
                value={phase.rainfall_mm}
                min={0}
                max={100}
                suffix="mm/h"
                onChange={(value) => updatePhase(index, 'rainfall_mm', Math.max(0, value || 0))}
              />
            </div>
            <div className="col-4">
              <NumberField
                label="Temperature"
                value={phase.temperature_c}
                min={0}
                max={50}
                suffix="°C"
                onChange={(value) => updatePhase(index, 'temperature_c', value)}
              />
            </div>
            <div className="col-5">
              <NumberField
                label="Wind"
                value={phase.wind_speed_ms}
                min={0}
                max={30}
                suffix="m/s"
                onChange={(value) => updatePhase(index, 'wind_speed_ms', Math.max(0, value || 0))}
              />
            </div>
            <div className="col-3">
              <WindDirectionField
                value={phase.wind_dir_deg}
                onChange={(value) => updatePhase(index, 'wind_dir_deg', value)}
              />
            </div>
          </div>
        </div>
      ))}

      <button type="button" className="btn btn-sm btn-outline-secondary w-100" onClick={resetPreset}>
        <i className="bi bi-arrow-counterclockwise me-1" />Reset Cecid wet-to-dry preset
      </button>
    </>
  )
}

function AdvancedTimelineEditor({ timeline, onChange }) {
  const blocks = Array.isArray(timeline?.advanced_blocks) ? timeline.advanced_blocks : []
  const blockStripRef = useRef(null)
  const [activeBlockIndex, setActiveBlockIndex] = useState(0)

  useEffect(() => {
    setActiveBlockIndex((current) => Math.min(current, Math.max(0, blocks.length - 1)))
  }, [blocks.length])

  const scrollToBlock = (requestedIndex) => {
    const strip = blockStripRef.current
    if (!strip || blocks.length === 0) return

    const nextIndex = Math.max(0, Math.min(requestedIndex, blocks.length - 1))
    const card = strip.children[nextIndex]
    if (!card) return

    const stripRect = strip.getBoundingClientRect()
    const cardRect = card.getBoundingClientRect()
    strip.scrollTo({
      left: Math.max(0, strip.scrollLeft + cardRect.left - stripRect.left),
      behavior: 'smooth',
    })
    setActiveBlockIndex(nextIndex)
  }

  const handleBlockStripScroll = () => {
    const strip = blockStripRef.current
    if (!strip || blocks.length === 0) return

    const stripLeft = strip.getBoundingClientRect().left
    let closestIndex = 0
    let closestDistance = Number.POSITIVE_INFINITY

    Array.from(strip.children).forEach((card, index) => {
      const distance = Math.abs(card.getBoundingClientRect().left - stripLeft)
      if (distance < closestDistance) {
        closestDistance = distance
        closestIndex = index
      }
    })
    setActiveBlockIndex(closestIndex)
  }

  const handleBlockStripKeyDown = (event) => {
    if (event.target !== event.currentTarget) return
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      scrollToBlock(activeBlockIndex - 1)
    } else if (event.key === 'ArrowRight') {
      event.preventDefault()
      scrollToBlock(activeBlockIndex + 1)
    }
  }

  const updateBlock = (index, field, value) => {
    const next = blocks.map((block, blockIndex) => (
      blockIndex === index ? { ...block, [field]: value } : block
    ))
    onChange({ ...timeline, advanced_blocks: next })
  }

  const conditionFor = (block) => Number(block.rainfall_mm) > 0 ? 'rain' : 'dry'

  const updateCondition = (index, condition) => {
    const block = blocks[index] || {}
    const currentRain = Number(block.rainfall_mm)
    updateBlock(index, 'rainfall_mm', condition === 'rain'
      ? (currentRain > 0 ? currentRain : 2.5)
      : 0)
  }

  const addBlock = () => {
    const previous = blocks.at(-1)
    const start = Math.min(160, Number(previous?.end_hour ?? 0))
    onChange({
      ...timeline,
      advanced_blocks: [
        ...blocks,
        {
          start_hour: start,
          end_hour: Math.min(168, start + 8),
          temperature_c: 28,
          wind_speed_ms: 1.5,
          wind_dir_deg: 90,
          rainfall_mm: 0,
        },
      ],
    })
  }

  const repeatDaily = () => onChange({
    ...timeline,
    advanced_blocks: repeatFirstDayBlocks(blocks, 168),
  })

  const resetStarter = () => onChange({
    ...timeline,
    advanced_blocks: buildGuidedBlocks(DEFAULT_GUIDED_PHASES, 168),
  })

  const loadGateTestPreset = () => onChange(createCecidGateTestPreset())

  return (
    <>
      <div className="alert alert-info py-2 px-2 mb-2" style={{ fontSize: '.76rem' }}>
        <i className="bi bi-info-circle me-1" />
        Build the cycle in order: Rain wets the orchard, then dry periods allow Cecid Fly emergence at dawn or dusk. Start and End are simulation hours; End is excluded.
      </div>

      <div className="border border-primary rounded p-2 mb-3 bg-primary-subtle" data-testid="cecid-gate-test-preset">
        <div className="d-flex justify-content-between align-items-start gap-2">
          <div>
            <div className="small fw-semibold text-primary">
              <i className="bi bi-lightning-charge me-1" />Cecid dawn + dusk test
            </div>
            <small className="d-block text-muted">
              Midnight start, dry soil, 4 hours of rain, then 20 dry calm hours. Repeats daily so both solar windows can become favorable.
            </small>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-primary flex-shrink-0"
            onClick={loadGateTestPreset}
          >
            Load preset
          </button>
        </div>
        <small className="d-block mt-2">
          Before running: select <strong>Cecid Fly</strong>, <strong>Fruitlet</strong>, and at least <strong>48 hours</strong>. Expected favorable times are around 5–7 AM and 5–7 PM Guimaras time.
        </small>
      </div>

      <div className="mb-3">
        <div className="small fw-medium mb-1">
          <i className="bi bi-calendar-event me-1" />Timeline start (Guimaras local time)
        </div>
        <DatePicker
          selected={timeline?.start_datetime ? new Date(timeline.start_datetime) : null}
          onChange={(date) => onChange({ ...timeline, start_datetime: localDateTimeValue(date) || localMidnightValue() })}
          showTimeSelect
          timeFormat="HH:mm"
          timeIntervals={60}
          dateFormat="MMMM d, yyyy h:mm aa"
          placeholderText="Choose local start timeâ€¦"
          className="form-control form-control-sm mp-datepicker-input"
          calendarClassName="mp-datepicker"
          popperPlacement="bottom-start"
        />
        <small className="text-muted d-block mt-1">
          Hour 0 starts at this exact time. For example, a 00:00 start means block 0 begins at midnight; a 01:00 start shifts every gate window one hour later.
        </small>
      </div>

      <SoilContextEditor timeline={timeline} onChange={onChange} />

      <div className="cecid-timeline-sequence mb-3" aria-label="Weather block sequence">
        <span className="small text-muted me-1">Sequence:</span>
        {blocks.map((block, index) => (
          <span key={`${index}-${block.start_hour}-${block.end_hour}`}>
            {index > 0 && <span className="text-muted mx-1">→</span>}
            <span className={`badge ${conditionFor(block) === 'rain' ? 'text-bg-primary' : 'text-bg-success'}`}>
              {conditionFor(block) === 'rain' ? 'RAIN' : 'DRY'} {Math.max(0, Number(block.end_hour) - Number(block.start_hour))}h
            </span>
          </span>
        ))}
        {blocks.length > 0 && <span className="small text-muted ms-1">→ repeat with “Repeat day”</span>}
      </div>

      {blocks.length > 0 && (
        <div className="cecid-timeline-block-nav">
          <small className="text-muted">
            <i className="bi bi-arrows me-1" />Swipe or use arrows
          </small>
          <div className="cecid-timeline-block-nav-controls">
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary cecid-timeline-arrow"
              aria-label="Previous weather block"
              title="Previous weather block"
              disabled={activeBlockIndex === 0}
              onClick={() => scrollToBlock(activeBlockIndex - 1)}
            >
              <i className="bi bi-chevron-left" />
            </button>
            <span className="cecid-timeline-block-count" aria-live="polite">
              {activeBlockIndex + 1} / {blocks.length}
            </span>
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary cecid-timeline-arrow"
              aria-label="Next weather block"
              title="Next weather block"
              disabled={activeBlockIndex === blocks.length - 1}
              onClick={() => scrollToBlock(activeBlockIndex + 1)}
            >
              <i className="bi bi-chevron-right" />
            </button>
          </div>
        </div>
      )}

      <div
        ref={blockStripRef}
        className="cecid-timeline-strip"
        role="region"
        aria-label="Weather timeline blocks"
        tabIndex={blocks.length > 1 ? 0 : -1}
        onScroll={handleBlockStripScroll}
        onKeyDown={handleBlockStripKeyDown}
      >
      {blocks.map((block, index) => (
        <div
          className={`cecid-timeline-block border rounded p-2 ${conditionFor(block) === 'rain' ? 'border-primary' : 'border-success'}`}
          key={`${index}-${block.start_hour}-${block.end_hour}`}
        >
          <div className="d-flex justify-content-between align-items-center mb-2">
            <div>
              <span className={`badge ${conditionFor(block) === 'rain' ? 'text-bg-primary' : 'text-bg-success'} me-1`}>
                {conditionFor(block) === 'rain' ? 'RAIN' : 'DRY'}
              </span>
              <strong className="small">{index + 1}. {conditionFor(block) === 'rain' ? 'Rain period' : 'Dry period'}</strong>
            </div>
            <button
              type="button"
              className="btn btn-sm btn-outline-danger py-0 px-1"
              aria-label={`Remove weather block ${index + 1}`}
              title="Remove block"
              onClick={() => onChange({ ...timeline, advanced_blocks: blocks.filter((_, blockIndex) => blockIndex !== index) })}
            >
              <i className="bi bi-trash" />
            </button>
          </div>
          <div className="row g-2">
            <div className="col-6">
              <NumberField
                label="Start hour"
                value={block.start_hour}
                min={0}
                max={167}
                step={1}
                suffix="h"
                onChange={(value) => updateBlock(index, 'start_hour', value)}
              />
            </div>
            <div className="col-6">
              <NumberField
                label="End hour (not included)"
                value={block.end_hour}
                min={1}
                max={168}
                step={1}
                suffix="h"
                onChange={(value) => updateBlock(index, 'end_hour', value)}
              />
            </div>
            <div className="col-6">
              <label className="small d-block">
                <span className="text-muted d-block mb-1">Condition</span>
                <select
                  className="form-select form-select-sm"
                  value={conditionFor(block)}
                  onChange={(event) => updateCondition(index, event.target.value)}
                >
                  <option value="rain">RAIN — builds moisture</option>
                  <option value="dry">DRY — emergence possible</option>
                </select>
              </label>
            </div>
            <div className="col-6">
              <NumberField
                label={conditionFor(block) === 'rain' ? 'Rain intensity' : 'Rain intensity (dry = 0)'}
                value={block.rainfall_mm}
                min={0}
                max={100}
                suffix="mm/h"
                onChange={(value) => updateBlock(index, 'rainfall_mm', Math.max(0, value || 0))}
              />
            </div>
            <div className="col-4">
              <NumberField
                label="Temperature"
                value={block.temperature_c}
                min={0}
                max={50}
                suffix="°C"
                onChange={(value) => updateBlock(index, 'temperature_c', value)}
              />
            </div>
            <div className="col-5">
              <NumberField
                label="Wind"
                value={block.wind_speed_ms}
                min={0}
                max={30}
                suffix="m/s"
                onChange={(value) => updateBlock(index, 'wind_speed_ms', Math.max(0, value || 0))}
              />
            </div>
            <div className="col-3">
              <WindDirectionField
                value={block.wind_dir_deg}
                onChange={(value) => updateBlock(index, 'wind_dir_deg', value)}
              />
            </div>
          </div>
        </div>
      ))}
      </div>

      <div className="alert alert-light border py-1 px-2 mb-2" style={{ fontSize: '.72rem' }}>
        <i className="bi bi-wind me-1" />For Cecid Fly, 1–5 km/h equals 0.28–1.39 m/s and can gently assist movement downwind. Faster wind progressively lowers survival but never extends the 15 m hourly limit.
      </div>

      <div className="d-flex gap-1">
        <button type="button" className="btn btn-sm btn-outline-primary flex-grow-1" onClick={addBlock}>
          <i className="bi bi-plus-lg me-1" />Add weather block
        </button>
        <button type="button" className="btn btn-sm btn-outline-secondary flex-grow-1" onClick={repeatDaily}>
          <i className="bi bi-repeat me-1" />Repeat day
        </button>
      </div>
      <button type="button" className="btn btn-sm btn-link text-decoration-none px-0" onClick={resetStarter}>
        <i className="bi bi-arrow-counterclockwise me-1" />Reset Rain → Dry starter
      </button>
      <small className="text-muted d-block">Rain intensity is mm/h. Temperature and wind apply throughout each block.</small>
    </>
  )
}

function SoilContextEditor({ timeline, onChange }) {
  const context = timeline?.manual_soil_context || {
    preset: 'recently_wet',
    total_rain_mm: 8,
    event_duration_hours: 4,
    hours_since_rain_ended: 6,
  }
  const setContext = (patch) => onChange({
    ...timeline,
    manual_soil_context: { ...context, ...patch },
  })

  return (
    <div className="border rounded p-2 mb-3 bg-light">
      <div className="small fw-semibold mb-1">
        <i className="bi bi-moisture me-1" />Soil before Hour 0
      </div>
      <div className="btn-group btn-group-sm w-100 mb-2" role="group" aria-label="Starting soil condition">
        {[
          ['dry', 'Dry'],
          ['recently_wet', 'Recently wet'],
          ['custom', 'Custom'],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`btn ${context.preset === value ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => setContext({ preset: value })}
          >
            {label}
          </button>
        ))}
      </div>
      {context.preset === 'recently_wet' && (
        <small className="text-muted d-block">
          Uses 8 mm over 4 hours, ending 6 hours before Hour 0. This supplies the 72-hour soil warm-up without adding hidden rain to the timeline.
        </small>
      )}
      {context.preset === 'dry' && (
        <small className="text-muted d-block">The 72 hours before Hour 0 contain no rain.</small>
      )}
      {context.preset === 'custom' && (
        <div className="row g-2">
          <div className="col-4">
            <NumberField label="Total rain" value={context.total_rain_mm} min={0} max={500} suffix="mm"
              onChange={(value) => setContext({ total_rain_mm: Math.max(0, value || 0) })} />
          </div>
          <div className="col-4">
            <NumberField label="Duration" value={context.event_duration_hours} min={1} max={72} step={1} suffix="h"
              onChange={(value) => setContext({ event_duration_hours: Math.max(1, value || 1) })} />
          </div>
          <div className="col-4">
            <NumberField label="Ended ago" value={context.hours_since_rain_ended} min={0} max={72} step={1} suffix="h"
              onChange={(value) => setContext({ hours_since_rain_ended: Math.max(0, value || 0) })} />
          </div>
        </div>
      )}
    </div>
  )
}

function TimelineEditor({ timeline, onChange }) {
  const safeTimeline = {
    mode: 'advanced',
    ...timeline,
    advanced_blocks: Array.isArray(timeline?.advanced_blocks) && timeline.advanced_blocks.length
      ? timeline.advanced_blocks
      : buildGuidedBlocks(timeline?.guided_phases || DEFAULT_GUIDED_PHASES, 48),
  }
  const update = (next) => onChange({ ...safeTimeline, ...next, mode: 'advanced', enabled: true })

  return (
    <div className="border rounded p-2 mt-1" style={{ fontSize: '.82rem' }}>
      <div className="fw-semibold mb-2"><i className="bi bi-calendar3-range me-1" />Cecid weather timeline</div>
      <AdvancedTimelineEditor timeline={safeTimeline} onChange={update} />
    </div>
  )
}

export default function WeatherCard({
  weather,
  manualWeather,
  weatherOverrideActive,
  onManualChange,
  onOverrideToggle,
  weatherTimeline,
  onTimelineChange,
  onRetry,
}) {
  const [scenarioKey, setScenarioKey] = useState('live')

  const current = weather?.current

  useEffect(() => {
    if (weatherTimeline?.enabled) setScenarioKey('timeline')
    else if (!weatherOverrideActive) setScenarioKey('live')
  }, [weatherTimeline?.enabled, weatherOverrideActive])

  const handleScenarioSelect = (scenario) => {
    setScenarioKey(scenario.key)
    if (scenario.key === 'live') {
      onTimelineChange?.({ ...(weatherTimeline || {}), enabled: false })
      onOverrideToggle?.(false)
    } else if (scenario.values === 'timeline') {
      onTimelineChange?.({ ...(weatherTimeline || {}), enabled: true, mode: 'advanced' })
      onOverrideToggle?.(true)
    } else if (scenario.values && scenario.values !== 'custom') {
      onManualChange(scenario.values)
      onTimelineChange?.({ ...(weatherTimeline || {}), enabled: false })
      onOverrideToggle?.(true)
    } else if (scenario.values === 'custom') {
      onTimelineChange?.({ ...(weatherTimeline || {}), enabled: false })
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
          <strong>{activeScenario.label}</strong> active — simulation uses this instead of the live forecast.
        </div>
      )}
      {current?.source === 'synthetic' && (
        <div className="alert alert-warning py-2 px-2 mb-2" style={{ fontSize: '.76rem' }}>
          <div className="fw-semibold"><i className="bi bi-exclamation-triangle-fill me-1" />Synthetic fallback is active</div>
          <div className="mt-1">{weather?.fallback_reason || weather?.provenance?.fallback_reason || 'The live provider did not return usable data.'}</div>
          <button type="button" className="btn btn-sm btn-outline-dark mt-2 py-0" onClick={onRetry}>
            <i className="bi bi-arrow-clockwise me-1" />Retry Open-Meteo
          </button>
        </div>
      )}

      {scenarioKey === 'timeline' && (
        <TimelineEditor
          timeline={weatherTimeline}
          onChange={(next) => {
            onTimelineChange?.(next)
            onOverrideToggle?.(true)
          }}
        />
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
              onChange={(date) => setField('sim_datetime', localDateTimeValue(date))}
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
            <small className="text-muted d-block mt-1">
              <i className="bi bi-info-circle me-1" />
              Cecid: {((manualWeather?.wind_speed_ms ?? 2) * 3.6).toFixed(1)} km/h. Above 5 km/h progressively reduces survival; wind alone does not hard-close the gate.
            </small>
          </div>
        </div>
      )}
    </CollapsibleCard>
  )
}
