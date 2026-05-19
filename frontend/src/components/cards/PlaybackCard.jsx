import { useState, useEffect, useRef } from 'react'
import CollapsibleCard from '../CollapsibleCard'

export default function PlaybackCard({ frames = [], currentFrameIdx = 0, onFrameSeek, defaultOpen = false, autoOpenSignal = 0 }) {
  const [playing, setPlaying] = useState(false)
  const intervalRef = useRef(null)
  const disabled = frames.length === 0
  const max = Math.max(0, frames.length - 1)
  const frame = frames[currentFrameIdx] ?? null

  // Auto-advance
  useEffect(() => {
    clearInterval(intervalRef.current)
    if (!playing || disabled) return
    intervalRef.current = setInterval(() => {
      onFrameSeek?.((prev) => {
        const next = typeof prev === 'number' ? prev : currentFrameIdx
        return next >= max ? 0 : next + 1
      })
    }, 800)
    return () => clearInterval(intervalRef.current)
  }, [playing, disabled, max, onFrameSeek])

  // Stop at end
  useEffect(() => {
    if (currentFrameIdx >= max && playing) setPlaying(false)
  }, [currentFrameIdx, max, playing])

  // Tick labels every 8 hours + first + last
  const tickSet = new Set()
  frames.forEach((f, i) => {
    if (i === 0 || i === max || f.hour % 8 === 0) tickSet.add(i)
  })
  const ticks = [...tickSet].map((i) => ({ i, label: `${frames[i].hour}h` }))

  const weather = frame?.weather ?? {}
  const temp = weather.temperature_c ?? weather.temp_c
  const wind = weather.wind_speed_ms ?? weather.wind_ms

  return (
    <CollapsibleCard iconName="film" title="Playback" defaultOpen={defaultOpen} openOverride={autoOpenSignal}>
      {disabled ? (
        <div className="text-muted small">Run a simulation to enable playback.</div>
      ) : (
        <>
          {/* Slider */}
          <input type="range" className="form-range w-100" min={0} max={max} step={1}
            value={currentFrameIdx}
            onChange={(e) => { setPlaying(false); onFrameSeek?.(Number(e.target.value)) }} />

          {/* Tick labels */}
          <div className="d-flex justify-content-between" style={{ fontSize: '.68rem', color: '#6b7280', marginTop: '-4px', marginBottom: '4px' }}>
            {ticks.map(({ i, label }) => <span key={i}>{label}</span>)}
          </div>

          {/* Controls */}
          <div className="d-flex justify-content-center gap-2 mt-1">
            <button type="button" className="btn btn-outline-secondary btn-sm"
              disabled={currentFrameIdx === 0}
              onClick={() => { setPlaying(false); onFrameSeek?.(Math.max(0, currentFrameIdx - 1)) }}>
              <i className="bi bi-skip-backward-fill" />
            </button>
            <button type="button" className={`btn btn-${playing ? 'warning' : 'success'} btn-sm px-3`}
              onClick={() => setPlaying((p) => !p)}>
              <i className={`bi bi-${playing ? 'pause-fill' : 'play-fill'} me-1`} />
              {playing ? 'Pause' : 'Play'}
            </button>
            <button type="button" className="btn btn-outline-secondary btn-sm"
              disabled={currentFrameIdx >= max}
              onClick={() => { setPlaying(false); onFrameSeek?.(Math.min(max, currentFrameIdx + 1)) }}>
              <i className="bi bi-skip-forward-fill" />
            </button>
          </div>

          {/* Frame stats */}
          {frame && (
            <div className="d-flex flex-wrap gap-2 mt-2 small" style={{ fontSize: '.76rem' }}>
              <span className="badge bg-secondary">Hour {frame.hour}</span>
              <span><i className="bi bi-bug me-1 text-danger" />Infested: {frame.n_infested}</span>
              <span><i className="bi bi-plus-circle me-1 text-warning" />New: {frame.n_new}</span>
              {temp != null && <span><i className="bi bi-thermometer-half me-1" />{Number(temp).toFixed(1)}°C</span>}
              {wind != null && <span><i className="bi bi-wind me-1" />{Number(wind).toFixed(1)} m/s</span>}
            </div>
          )}
        </>
      )}
    </CollapsibleCard>
  )
}
