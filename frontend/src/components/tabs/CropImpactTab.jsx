import { useMemo } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'

const Plot = createPlotlyComponent(Plotly)

const CHART_CONFIG = { displayModeBar: false, responsive: true }
const BASE_LAYOUT = {
  margin: { l: 20, r: 20, t: 34, b: 42 },
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { family: 'Outfit, sans-serif', size: 12 },
  autosize: true,
}

const YIELD_KG = 45
const PRICE_PHP = 60

export default function CropImpactTab({ monitoringData, simData }) {
  const scenarios = useMemo(() => {
    const infested = simData?.n_infested_final ?? monitoringData?.infestation_rate?.infested_trees ?? null
    if (infested == null) return null
    const yieldKg = infested * YIELD_KG
    return [
      { label: 'Low', pct: 15, color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
      { label: 'Base', pct: 30, color: '#f59e0b', bg: '#fffbeb', border: '#fde68a' },
      { label: 'High', pct: 45, color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
    ].map((s) => ({
      ...s,
      lossPhp: yieldKg * PRICE_PHP * (s.pct / 100),
      lossKg: yieldKg * (s.pct / 100),
    }))
  }, [monitoringData, simData])

  const lossData = useMemo(() => {
    // Prefer simulation time_series over DB pest_trend
    if (simData?.time_series?.length) {
      return simData.time_series.map((frame) => ({
        x: frame.datetime ?? `Hour ${frame.hour}`,
        infested: frame.n_infested ?? 0,
      }))
    }
    if (!monitoringData?.pest_trend?.length) return []
    return monitoringData.pest_trend.map((pt) => ({
      x: pt.timestamp ?? pt.date ?? pt.x,
      infested: pt.infested_trees ?? pt.infested ?? 0,
    }))
  }, [monitoringData, simData])


  const lossFig = useMemo(() => {
    if (!lossData.length) {
      return {
        data: [],
        layout: {
          ...BASE_LAYOUT, height: 260,
          annotations: [{ text: 'Run a simulation to see loss-at-risk trends.', x: 0.5, y: 0.5, xref: 'paper', yref: 'paper', showarrow: false, font: { size: 14, color: '#7c7c7c' } }],
          xaxis: { visible: false }, yaxis: { visible: false },
        },
      }
    }
    const xs = lossData.map((d) => d.x)
    const infested = lossData.map((d) => d.infested)
    const YIELD = 45, PRICE = 60
    const low = infested.map((n) => n * YIELD * PRICE * 0.15)
    const base = infested.map((n) => n * YIELD * PRICE * 0.30)
    const high = infested.map((n) => n * YIELD * PRICE * 0.45)
    return {
      data: [
        { type: 'scatter', x: xs, y: low, mode: 'lines', name: 'Low (15%)', line: { color: '#16a34a', width: 1.8 } },
        { type: 'scatter', x: xs, y: high, mode: 'lines', name: 'High (45%)', line: { color: '#dc2626', width: 1.8 }, fill: 'tonexty', fillcolor: 'rgba(220,38,38,0.10)' },
        { type: 'scatter', x: xs, y: base, mode: 'lines+markers', name: 'Base (30%)', line: { color: '#f59e0b', width: 2.4 }, marker: { size: 5 } },
      ],
      layout: {
        ...BASE_LAYOUT, height: 260,
        xaxis: { title: simData?.time_series?.length ? 'Simulation Hour' : 'Time', gridcolor: '#eee' },
        yaxis: { title: 'Estimated Loss at Risk (PHP)', gridcolor: '#eee', tickprefix: 'PHP ' },
        legend: { orientation: 'h', yanchor: 'bottom', y: 1.03, xanchor: 'left', x: 0 },
      },
    }
  }, [lossData, simData])

  return (
    <div className="p-3">
      <div className="row g-3">
        <div className="col-12">
          <div className="card shadow-sm border-0 monitoring-module-chart-card">
            <div className="card-header py-2">
              <div className="d-flex align-items-center">
                <i className="bi bi-cash-coin me-2" />
                <span className="fw-semibold">Estimated Loss at Risk (Scenario)</span>
              </div>
            </div>
            <div className="card-body py-1">
              <small className="text-muted d-block px-2 pt-1">
                Planning estimate: 45 kg/tree, PHP 60/kg, damage: 15% / 30% / 45%
              </small>
              <Plot
                data={lossFig.data}
                layout={lossFig.layout}
                config={CHART_CONFIG}
                useResizeHandler
                style={{ height: 260, width: '100%' }}
              />
            </div>
          </div>
        </div>

        <div className="col-12">
          <div className="card shadow-sm border-0 monitoring-module-chart-card">
            <div className="card-header py-2">
              <div className="d-flex align-items-center">
                <i className="bi bi-table me-2" />
                <span className="fw-semibold">Damage Scenario Breakdown</span>
              </div>
            </div>
            <div className="card-body px-3 py-3">
              {scenarios ? (
                <>
                  <small className="text-muted d-block mb-3">{YIELD_KG} kg/tree · PHP {PRICE_PHP}/kg · final infested trees</small>
                  <div className="row g-2">
                    {scenarios.map((s) => (
                      <div key={s.label} className="col-12 col-md-4">
                        <div className="rounded p-3" style={{ background: s.bg, border: `1px solid ${s.border}` }}>
                          <div className="fw-semibold small mb-2" style={{ color: s.color }}>{s.label} — {s.pct}% damage</div>
                          <div className="d-flex justify-content-between align-items-end">
                            <div>
                              <div className="fw-bold" style={{ fontSize: '1.1rem' }}>PHP {s.lossPhp.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                              <div className="text-muted" style={{ fontSize: '0.72rem' }}>revenue loss</div>
                            </div>
                            <div className="text-end">
                              <div className="fw-bold" style={{ fontSize: '1.1rem' }}>{s.lossKg.toLocaleString(undefined, { maximumFractionDigits: 0 })} kg</div>
                              <div className="text-muted" style={{ fontSize: '0.72rem' }}>yield lost</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="text-muted small py-1">
                  <i className="bi bi-info-circle me-1" />Run a simulation to see scenario breakdown.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
