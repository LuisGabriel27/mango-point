import { useState } from 'react'
import SourcePresenceControl from './SourcePresenceControl'
import { isUncertainSourceStatus } from '../utils/sourcePresence.js'

const OPTIONS = [
  { label: 'Healthy', value: 'healthy' },
  { label: 'Infected', value: 'infected' },
  { label: 'Bagged (reduced risk)', value: 'bagged' },
  { label: 'Dead (removed)', value: 'dead' },
  { label: 'History Infected', value: 'history_infected' },
  { label: 'Suspect (monitoring)', value: 'suspect' },
]

export default function TreeStatusSelect({ defaultValue, defaultSourceProbability = null, onApply, onCancel }) {
  const [value, setValue] = useState(defaultValue || 'healthy')
  const [probability, setProbability] = useState(defaultSourceProbability)
  return (
    <>
      <select aria-label="Tree status" className="form-select mb-3 border-primary" value={value}
        onChange={(event) => setValue(event.target.value)}>
        {OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      <SourcePresenceControl status={value} value={probability} onChange={setProbability} className="mb-3" />
      <div className="card bg-light border-0 mb-3">
        <div className="card-body py-2 px-3 small">
          <p className="mb-2"><strong>History Infected</strong> may contain a latent soil or adult reservoir;
            fruit starts uninfested. <strong>Suspect</strong> may start with a current infestation.
            <strong> Infected</strong> is a known current source.</p>
          <p className="mb-2">A percentage here overrides the zone setting for this tree.
            Use scenario default to follow the defaults under Model.</p>
          <p className="mb-0"><strong>Bagged</strong> receives 30% of incoming pressure (70% reduction).
            <strong> Dead</strong> is excluded from spread. Changes apply to the next simulation run.</p>
        </div>
      </div>
      <div className="modal-footer bg-light border-top p-2 d-flex gap-2">
        <button type="button" className="btn btn-outline-secondary px-4" onClick={onCancel}>Cancel</button>
        <button type="button" className="btn btn-success px-4 ms-2"
          onClick={() => onApply(value, isUncertainSourceStatus(value) ? probability : null)}>Apply Changes</button>
      </div>
    </>
  )
}
