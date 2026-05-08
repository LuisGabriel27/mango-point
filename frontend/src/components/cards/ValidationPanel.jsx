import { useState, useEffect } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'
import api, { apiErrorMessage } from '../../api'

const Plot = createPlotlyComponent(Plotly)
const CHART_CONFIG = { displayModeBar: false, responsive: true }
const BASE_LAYOUT = { margin: { l: 20, r: 20, t: 40, b: 40 }, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', height: 320, font: { family: 'Outfit, sans-serif', size: 12 } }

const SEV_BADGE = { Low: 'success', Medium: 'warning', High: 'danger' }

function pct(v) { return v != null ? `${(v * 100).toFixed(1)}%` : '—' }

export default function ValidationPanel() {
  const [summary, setSummary] = useState(null)
  const [cases, setCases] = useState([])
  const [pestFilter, setPestFilter] = useState(['cecid', 'fruitfly'])
  const [yearFilter, setYearFilter] = useState([2022, 2023, 2024, 2025])
  const [maxCases, setMaxCases] = useState(12)
  const [hours, setHours] = useState(48)
  const [mcRuns, setMcRuns] = useState(20)
  const [running, setRunning] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [results, setResults] = useState(null)
  const [loadingSummary, setLoadingSummary] = useState(true)

  useEffect(() => {
    Promise.all([api.getHistoricalData(), api.getValidationCases()])
      .then(([sumRes, casRes]) => {
        setSummary(sumRes.data)
        setCases(casRes.data.cases ?? [])
      })
      .catch(() => {})
      .finally(() => setLoadingSummary(false))
  }, [])

  const toggleFilter = (arr, setArr, val) => {
    setArr(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val])
  }

  const handleRun = async () => {
    setRunning(true)
    setFeedback({ type: 'info', msg: 'Running historical validation…' })
    try {
      const res = await api.runValidation({
        max_cases: maxCases,
        pest_types: pestFilter,
        years: yearFilter,
        hours,
        monte_carlo_runs: mcRuns,
        seed: null,
      })
      setResults(res.data)
      setFeedback({ type: 'success', msg: `Validation complete — ${res.data.summary?.total_cases ?? 0} cases processed.` })
    } catch (err) {
      setFeedback({ type: 'danger', msg: apiErrorMessage(err, 'Validation failed.') })
    } finally {
      setRunning(false)
    }
  }

  const metricFig = results ? (() => {
    const s = results.summary ?? {}
    const cls = results.classification_metrics ?? {}
    const reg = results.regression_metrics ?? {}
    const rows = [
      ['Overall Accuracy', s.overall_accuracy_pct ?? 0],
      ['Precision', (cls.precision ?? 0) * 100],
      ['Recall', (cls.recall ?? 0) * 100],
      ['F1-Score', (cls.f1_score ?? 0) * 100],
      ['Specificity', (cls.specificity ?? 0) * 100],
      ['R-squared', (reg.r_squared ?? 0) * 100],
    ]
    return {
      data: [{
        type: 'bar',
        x: rows.map((r) => r[0]),
        y: rows.map((r) => r[1]),
        text: rows.map((r) => `${r[1].toFixed(1)}%`),
        textposition: 'outside',
        marker: { color: ['#2e7d32','#558b2f','#ef6c00','#1565c0','#6a1b9a','#455a64'] },
        hovertemplate: '%{x}: %{y:.1f}%<extra></extra>',
      }],
      layout: {
        ...BASE_LAYOUT,
        showlegend: false,
        yaxis_title: 'Score (%)',
        yaxis: { gridcolor: '#ececec' },
      },
    }
  })() : null

  const confMatrix = results?.classification_metrics?.confusion_matrix ?? results?.confusion_matrix ?? {}

  return (
    <div>
      {/* Dataset summary */}
      <div className="card shadow-sm border-0 mb-3">
        <div className="card-header py-2">
          <div className="d-flex align-items-center">
            <i className="bi bi-database me-2" />
            <span className="fw-semibold">Historical Dataset</span>
          </div>
        </div>
        <div className="card-body">
          {loadingSummary ? (
            <div className="text-muted small"><span className="spinner-border spinner-border-sm me-1" />Loading…</div>
          ) : summary ? (
            <>
              <p className="text-muted small mb-3">
                Source: BPI Guimaras pest monitoring records.
              </p>
              <div className="row g-2 mb-2">
                {[
                  ['Historical Records', summary.n_records],
                  ['Data Period', summary.year_range],
                  ['Fruit Fly Cases', summary.fruit_fly_relevant_records],
                  ['Cecid Fly Cases', summary.cecid_fly_relevant_records],
                ].map(([label, val]) => (
                  <div key={label} className="col-6">
                    <div className="card border-0 bg-light h-100">
                      <div className="card-body py-2">
                        <small className="text-muted d-block">{label}</small>
                        <h5 className="mb-0 fw-bold">{val ?? '—'}</h5>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mb-2">
                <small className="text-muted me-2">Years covered:</small>
                {(summary.years ?? []).map((y) => (
                  <span key={y} className="badge bg-secondary rounded-pill me-1">{y}</span>
                ))}
              </div>
              {/* Case preview */}
              {cases.length > 0 && (
                <div className="table-responsive" style={{ maxHeight: 220, overflowY: 'auto' }}>
                  <table className="table table-sm table-hover mb-0">
                    <thead className="table-light">
                      <tr><th>Case ID</th><th>Date</th><th>Pest</th><th>Stage</th><th>Level</th></tr>
                    </thead>
                    <tbody>
                      {cases.slice(0, 6).map((c) => (
                        <tr key={c.case_id}>
                          <td className="fw-semibold">{c.case_id}</td>
                          <td>{c.date}</td>
                          <td>{c.pest_type === 'cecid' ? 'Cecid Fly' : 'Fruit Fly'}</td>
                          <td>{(c.orchard_stage ?? '').replace(/^\w/, (x) => x.toUpperCase())}</td>
                          <td>
                            <span className={`badge bg-${SEV_BADGE[c.actual_level] ?? 'secondary'}`}>
                              {c.actual_level}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <div className="alert alert-warning py-2 mb-0">Historical validation metadata is unavailable.</div>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="card shadow-sm border-0 mb-3">
        <div className="card-header py-2">
          <div className="d-flex align-items-center">
            <i className="bi bi-sliders2 me-2" />
            <span className="fw-semibold">Validation Controls</span>
          </div>
        </div>
        <div className="card-body">
          <p className="text-muted small mb-3">
            Historical validation compares MangoPoint simulations against archived BPI Guimaras monitoring records.
          </p>

          <label className="fw-medium mb-1 d-block small"><i className="bi bi-bug me-1" />Pest filter</label>
          <div className="d-flex gap-2 mb-3">
            {[['cecid','Cecid Fly (Gall Midge)'],['fruitfly','Fruit Fly (Bactrocera)']].map(([v, l]) => (
              <div key={v} className="form-check">
                <input className="form-check-input" type="checkbox" id={`pest-${v}`}
                  checked={pestFilter.includes(v)}
                  onChange={() => toggleFilter(pestFilter, setPestFilter, v)} />
                <label className="form-check-label small" htmlFor={`pest-${v}`}>{l}</label>
              </div>
            ))}
          </div>

          <label className="fw-medium mb-1 d-block small"><i className="bi bi-calendar3 me-1" />Years</label>
          <div className="d-flex gap-2 flex-wrap mb-3">
            {[2022,2023,2024,2025].map((y) => (
              <div key={y} className="form-check">
                <input className="form-check-input" type="checkbox" id={`year-${y}`}
                  checked={yearFilter.includes(y)}
                  onChange={() => toggleFilter(yearFilter, setYearFilter, y)} />
                <label className="form-check-label small" htmlFor={`year-${y}`}>{y}</label>
              </div>
            ))}
          </div>

          <div className="row g-2 mb-3">
            <div className="col-6">
              <label className="fw-medium mb-1 d-block small"><i className="bi bi-collection me-1" />Max cases</label>
              <input type="number" className="form-control" min={1} max={20} step={1}
                value={maxCases} onChange={(e) => setMaxCases(+e.target.value)} />
            </div>
            <div className="col-6">
              <label className="fw-medium mb-1 d-block small"><i className="bi bi-clock-history me-1" />Simulation hours</label>
              <input type="number" className="form-control" min={24} max={168} step={24}
                value={hours} onChange={(e) => setHours(+e.target.value)} />
            </div>
          </div>
          <div className="row g-2 mb-3">
            <div className="col-6">
              <label className="fw-medium mb-1 d-block small"><i className="bi bi-shuffle me-1" />Monte Carlo runs</label>
              <input type="number" className="form-control" min={10} max={100} step={5}
                value={mcRuns} onChange={(e) => setMcRuns(+e.target.value)} />
            </div>
          </div>

          <button type="button" className="btn btn-success w-100 mb-2" disabled={running} onClick={handleRun}>
            {running ? <><span className="spinner-border spinner-border-sm me-1" />Running validation…</> : <><i className="bi bi-play-circle me-2" />Run Historical Validation</>}
          </button>

          {feedback && (
            <div className={`alert alert-${feedback.type} py-2`} style={{ fontSize: '.83rem' }}>{feedback.msg}</div>
          )}
        </div>
      </div>

      {/* Results */}
      {results && (
        <>
          {metricFig && (
            <div className="card shadow-sm border-0 mb-3">
              <div className="card-header py-2"><span className="fw-semibold">Validation Metrics</span></div>
              <div className="card-body py-1">
                <Plot data={metricFig.data} layout={metricFig.layout} config={CHART_CONFIG} useResizeHandler style={{ height: 320, width: '100%' }} />
              </div>
            </div>
          )}

          {/* Results table */}
          {results.results?.length > 0 && (
            <div className="card shadow-sm border-0 mb-3">
              <div className="card-header py-2"><span className="fw-semibold">Case Results</span></div>
              <div className="card-body py-1">
                <div className="table-responsive" style={{ maxHeight: 420, overflowY: 'auto' }}>
                  <table className="table table-sm table-hover mb-0">
                    <thead className="table-light">
                      <tr><th>Case</th><th>Date</th><th>Pest</th><th>Actual</th><th>Predicted</th><th>Risk</th><th>Match</th></tr>
                    </thead>
                    <tbody>
                      {results.results.map((r) => (
                        <tr key={r.case_id}>
                          <td className="fw-semibold">{r.case_id}</td>
                          <td>{r.date}</td>
                          <td>{r.pest_type === 'cecid' ? 'Cecid' : 'Fruit'}</td>
                          <td><span className={`badge bg-${SEV_BADGE[r.actual_level] ?? 'secondary'}`}>{r.actual_level}</span></td>
                          <td><span className={`badge bg-${SEV_BADGE[r.predicted_level] ?? 'secondary'}`}>{r.predicted_level}</span></td>
                          <td>{pct(r.predicted_risk)}</td>
                          <td><span className={`badge bg-${r.match ? 'success' : 'danger'} rounded-pill`}>{r.match ? 'Match' : 'Mismatch'}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Confusion matrix */}
          {Object.keys(confMatrix).length > 0 && (
            <div className="card shadow-sm border-0 mb-3">
              <div className="card-header py-2"><span className="fw-semibold">Confusion Matrix</span></div>
              <div className="card-body py-2">
                <div className="row g-2 mb-2">
                  {[
                    { label: 'True Positives', key: 'true_positives', color: 'success', note: 'Detected high-risk periods.' },
                    { label: 'False Positives', key: 'false_positives', color: 'warning', note: 'Alerts raised incorrectly.' },
                    { label: 'False Negatives', key: 'false_negatives', color: 'danger', note: 'Missed outbreaks — critical.' },
                    { label: 'True Negatives', key: 'true_negatives', color: 'secondary', note: 'Low-risk periods correctly recognized.' },
                  ].map(({ label, key, color, note }) => (
                    <div key={key} className="col-6">
                      <div className="card border-0 bg-light h-100">
                        <div className="card-body py-2">
                          <small className={`text-${color} text-uppercase fw-semibold d-block mb-1`}>{label}</small>
                          <h5 className="mb-1 fw-bold">{confMatrix[key] ?? 0}</h5>
                          <p className="text-muted small mb-0">{note}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <small className="text-danger">
                  False negatives are especially critical because they represent missed outbreaks that could delay intervention decisions.
                </small>
              </div>
            </div>
          )}

          {/* Interpretation */}
          <div className="card shadow-sm border-0 mb-3">
            <div className="card-header py-2">
              <div className="d-flex align-items-center"><i className="bi bi-journal-check me-2" /><span className="fw-semibold">Validation Interpretation</span></div>
            </div>
            <div className="card-body">
              <ul className="small mb-0 ps-3">
                <li>Reliability: accuracy and F1-score summarize how consistently the model agrees with documented pest activity.</li>
                <li>Early warning confidence: recall highlights how often higher-risk periods are detected before they are missed.</li>
                <li>Reduced false alarms: precision and specificity indicate whether interventions are recommended selectively.</li>
                <li>Evidence-based forecasting: historical agreement supports decision-support use.</li>
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
