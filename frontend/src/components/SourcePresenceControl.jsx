import { useId } from 'react'
import HelpTooltip from './HelpTooltip'
import { isUncertainSourceStatus, sourceProbability } from '../utils/sourcePresence.js'

export default function SourcePresenceControl({ status, value = null, onChange, className = '' }) {
  const id = useId()
  if (status !== 'infected' && !isUncertainSourceStatus(status)) return null
  const probability = sourceProbability(value)
  if (status === 'infected') {
    return (
      <div className={`source-presence-control ${className}`}>
        <div className="control-label-row">
          <strong className="small">Source presence: 100% (confirmed)</strong>
          <HelpTooltip label="Confirmed source presence">Infected starts as a known current source in every run.</HelpTooltip>
        </div>
      </div>
    )
  }
  return (
    <div className={`source-presence-control ${className}`}>
      <div className="control-label-row small fw-semibold mb-1">
        <label htmlFor={`${id}-mode`}>Assumed source presence</label>
        <HelpTooltip label="Assumed source presence">Chance this source is present in each run; separate from predicted infestation risk.</HelpTooltip>
      </div>
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
    </div>
  )
}
