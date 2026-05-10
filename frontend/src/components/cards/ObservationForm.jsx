import { useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import MpSelect from '../MpSelect'
import api, { apiErrorMessage } from '../../api'

export default function ObservationForm() {
  const [treeId, setTreeId] = useState('')
  const [pest, setPest] = useState('cecid')
  const [severity, setSeverity] = useState(0.5)
  const [observer, setObserver] = useState('')
  const [notes, setNotes] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    setLoading(true)
    setResult(null)
    try {
      const body = {
        tree_id: parseInt(treeId) || treeId,
        observed_pest: pest,
        timestamp: new Date().toISOString(),
        severity,
        observer_id: observer,
        notes,
      }
      await api.submitObservation(body)
      setResult({ type: 'success', msg: 'Observation submitted successfully.' })
      setTreeId(''); setObserver(''); setNotes('')
    } catch (err) {
      setResult({ type: 'danger', msg: apiErrorMessage(err, 'Submission failed.') })
    } finally {
      setLoading(false)
    }
  }

  return (
    <CollapsibleCard iconName="clipboard2-data" title="Field Observation">
      <label className="fw-medium mb-1 d-block small"><i className="bi bi-tree me-1" />Tree ID</label>
      <input type="text" className="form-control mb-2" placeholder="e.g. 5 or T05"
        value={treeId} onChange={(e) => setTreeId(e.target.value)} />

      <label className="fw-medium mb-1 d-block small"><i className="bi bi-bug me-1" />Pest observed</label>
      <MpSelect
        value={pest}
        onChange={setPest}
        options={[
          { value: 'cecid', label: 'Cecid Fly' },
          { value: 'fruitfly', label: 'Fruit Fly' },
        ]}
        className="mb-2"
      />

      <label className="fw-medium mb-1 d-block small"><i className="bi bi-speedometer2 me-1" />Severity (0–1)</label>
      <input type="range" className="form-range w-100 mb-1" min={0} max={1} step={0.1}
        value={severity} onChange={(e) => setSeverity(Number(e.target.value))} />
      <div className="text-center small fw-semibold mb-2" style={{ color: 'var(--mp-primary)' }}>{severity.toFixed(1)}</div>

      <label className="fw-medium mb-1 d-block small"><i className="bi bi-person me-1" />Observer ID</label>
      <input type="text" className="form-control mb-2" placeholder="Your name / ID"
        value={observer} onChange={(e) => setObserver(e.target.value)} />

      <label className="fw-medium mb-1 d-block small"><i className="bi bi-journal-text me-1" />Notes</label>
      <textarea className="form-control mb-2" placeholder="Optional notes…" style={{ height: 60 }}
        value={notes} onChange={(e) => setNotes(e.target.value)} />

      <button type="button" className="btn btn-outline-primary w-100" disabled={loading || !treeId} onClick={handleSubmit}>
        {loading ? <><span className="spinner-border spinner-border-sm me-1" />Submitting…</> : <><i className="bi bi-send me-2" />Submit Observation</>}
      </button>

      {result && (
        <div className={`alert alert-${result.type} py-2 mt-2`} style={{ fontSize: '.83rem' }}>{result.msg}</div>
      )}
    </CollapsibleCard>
  )
}
