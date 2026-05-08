import { useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import api, { apiErrorMessage } from '../../api'

export default function EvaluationPanel() {
  const [threshold, setThreshold] = useState(0.5)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleEvaluate = async () => {
    setLoading(true)
    setResult(null)
    try {
      const res = await api.evaluate({ risk_threshold: threshold })
      setResult({ ok: true, data: res.data })
    } catch (err) {
      setResult({ ok: false, msg: apiErrorMessage(err, 'Evaluation failed.') })
    } finally {
      setLoading(false)
    }
  }

  const d = result?.data

  return (
    <CollapsibleCard iconName="graph-up" title="Live Evaluation">
      <p className="text-muted small mb-2">
        Live evaluation reviews the latest simulation run against operational observation data.
        It is separate from the historical validation evidence shown above.
      </p>

      <label className="fw-medium mb-1 d-block small"><i className="bi bi-sliders me-1" />Risk threshold</label>
      <input type="number" className="form-control mb-2" min={0} max={1} step={0.05}
        value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />

      <button type="button" className="btn btn-outline-info w-100 mb-2" disabled={loading} onClick={handleEvaluate}>
        {loading
          ? <><span className="spinner-border spinner-border-sm me-1" />Evaluating…</>
          : <><i className="bi bi-bar-chart-line me-2" />Evaluate Latest Simulation Run</>}
      </button>

      {result && !result.ok && (
        <div className="alert alert-danger py-2" style={{ fontSize: '.83rem' }}>{result.msg}</div>
      )}

      {d && (
        <div>
          <table className="table table-sm table-borderless mb-0">
            <tbody>
              {[
                ['Precision', d.precision],
                ['Recall', d.recall],
                ['F1-Score', d.f1_score],
                ['Spatial Overlap', d.spatial_overlap_percentage != null ? `${d.spatial_overlap_percentage.toFixed(1)}%` : null],
              ].map(([k, v]) => (
                <tr key={k}>
                  <td className="text-muted">{k}</td>
                  <td className="fw-semibold text-end">{v != null ? (typeof v === 'number' && v <= 1 ? `${(v * 100).toFixed(1)}%` : v) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {d.confusion_matrix && (
            <div className="mt-2">
              <small className="text-muted d-block mb-1">Confusion Matrix</small>
              <div className="row g-1 text-center" style={{ fontSize: '.75rem' }}>
                {[
                  { label: 'TP', color: 'success', v: d.confusion_matrix.true_positives },
                  { label: 'FP', color: 'warning', v: d.confusion_matrix.false_positives },
                  { label: 'FN', color: 'danger', v: d.confusion_matrix.false_negatives },
                  { label: 'TN', color: 'secondary', v: d.confusion_matrix.true_negatives },
                ].map(({ label, color, v }) => (
                  <div key={label} className="col-6">
                    <div className={`p-1 rounded bg-${color} bg-opacity-10 border border-${color} border-opacity-25`}>
                      <div className={`text-${color} fw-bold`}>{label}</div>
                      <div className="fw-bold">{v ?? 0}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </CollapsibleCard>
  )
}
