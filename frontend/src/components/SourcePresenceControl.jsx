import { useId } from 'react'
import { isUncertainSourceStatus, sourceProbability } from '../utils/sourcePresence.js'

export default function SourcePresenceControl({ status, value = null, onChange, className = '' }) {
  const id = useId()
  if (status !== 'infected' && !isUncertainSourceStatus(status)) return null
  const probability = sourceProbability(value)
  if (status === 'infected') {
    return (
      <div className={`source-presence-control ${className}`}>
        <strong className="small">Source presence: 100% (confirmed)</strong>
        <small className="text-muted d-block">Infected starts as a known current source in every run.</small>
      </div>
    )
  }
  return (
    <div className={`source-presence-control ${className}`}>
      <label className="small fw-semibold d-block mb-1" htmlFor={`${id}-mode`}>Assumed source presence</label>
      <select id={`${id}-mode`} className="form-select form-select-sm mb-2"
        value={probability == null ? 'default' : 'custom'}
        onChange={(event) => onChange?.(event.target.value === 'default' ? null : 0.5)}>
        <option value="default">Use scenario default</option>
        <option value="custom">Set a percentage</option>
      </select>
      {probability != null && (
        <>
          <label className="small d-flex justify-content-between" htmlFor={`${id}-probability`}>
            <span>{status === 'history_infected' ? 'Reservoir present' : 'Current infestation present'}</span>
            <strong>{Math.round(probability * 100)}%</strong>
          </label>
          <input id={`${id}-probability`} className="form-range mb-0" type="range"
            min="0" max="100" step="5" value={Math.round(probability * 100)}
            onChange={(event) => onChange?.(Number(event.target.value) / 100)} />
        </>
      )}
      <small className="text-muted d-block">Chance this source is present in each run; separate from predicted infestation risk.</small>
    </div>
  )
}
