import { useEffect, useMemo, useRef } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'

const Plot = createPlotlyComponent(Plotly)

function useChartResize() {
  const containerRef = useRef(null)
  const plotRef = useRef(null)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return undefined
    const observer = new ResizeObserver(() => {
      if (plotRef.current) Plotly.Plots.resize(plotRef.current)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return {
    containerRef,
    onInitialized: (_, gd) => { plotRef.current = gd },
    onUpdate: (_, gd) => { plotRef.current = gd },
  }
}

const CHART_CONFIG = { displayModeBar: false, responsive: true }
const BASE_LAYOUT = {
  margin: { l: 20, r: 20, t: 34, b: 42 },
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { family: 'Outfit, sans-serif', size: 12, color: '#475569' },
  autosize: true,
  hoverlabel: {
    bgcolor: '#ffffff',
    bordercolor: '#cbd5e1',
    font: { family: 'Outfit, sans-serif', size: 12, color: '#0f172a' },
  },
  colorway: ['#16a34a', '#dc2626', '#f59e0b', '#3b82f6'],
}
const AXIS_BASE = {
  gridcolor: '#eef2f7',
  zerolinecolor: '#e2e8f0',
  linecolor: '#e2e8f0',
  tickfont: { color: '#64748b', size: 11 },
  titlefont: { color: '#334155', size: 12 },
  showspikes: true,
  spikemode: 'across',
  spikethickness: 1,
  spikedash: 'dot',
  spikecolor: '#94a3b8',
}

const YIELD_KG = 45
const PRICE_PHP = 60

export default function CropImpactTab({ monitoringData, simData }) {
  const lossResize = useChartResize()
  const assumptions = useMemo(() => ({
    yieldKg: Number(simData?.impact_assumptions?.yield_per_tree_kg ?? YIELD_KG),
    pricePhp: Number(simData?.impact_assumptions?.farmgate_price_php_per_kg ?? PRICE_PHP),
    lowPct: Number(simData?.impact_assumptions?.damage_low ?? 15),
    basePct: Number(simData?.impact_assumptions?.damage_base ?? 30),
    highPct: Number(simData?.impact_assumptions?.damage_high ?? 45),
  }), [simData])

  const scenarios = useMemo(() => {
    const infested = simData?.n_infested_final ?? monitoringData?.infestation_rate?.infested_trees ?? null
    if (infested == null) return null
    const yieldKg = infested * assumptions.yieldKg
    return [
      { label: 'Low', pct: assumptions.lowPct, color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
      { label: 'Base', pct: assumptions.basePct, color: '#f59e0b', bg: '#fffbeb', border: '#fde68a' },
      { label: 'High', pct: assumptions.highPct, color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
    ].map((s) => ({
      ...s,
      lossPhp: yieldKg * assumptions.pricePhp * (s.pct / 100),
      lossKg: yieldKg * (s.pct / 100),
    }))
  }, [assumptions, monitoringData, simData])

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
          annotations: [{ text: 'Run a simulation to see loss-at-risk trends.', x: 0.5, y: 0.5, xref: 'paper', yref: 'paper', showarrow: false, font: { size: 13, color: '#94a3b8' } }],
          xaxis: { visible: false }, yaxis: { visible: false },
        },
      }
    }
    const xs = lossData.map((d) => d.x)
    const infested = lossData.map((d) => d.infested)
    const low = infested.map((n) => n * assumptions.yieldKg * assumptions.pricePhp * (assumptions.lowPct / 100))
    const base = infested.map((n) => n * assumptions.yieldKg * assumptions.pricePhp * (assumptions.basePct / 100))
    const high = infested.map((n) => n * assumptions.yieldKg * assumptions.pricePhp * (assumptions.highPct / 100))
    const hoverFmt = '<b>%{fullData.name}</b><br>PHP %{y:,.0f}<extra></extra>'
    return {
      data: [
        {
          type: 'scatter', x: xs, y: low, mode: 'lines',
          name: `Low (${assumptions.lowPct}%)`,
          line: { color: '#16a34a', width: 2, shape: 'spline', smoothing: 1.1 },
          fill: 'tozeroy', fillcolor: 'rgba(22,163,74,0.08)',
          hovertemplate: hoverFmt,
        },
        {
          type: 'scatter', x: xs, y: high, mode: 'lines',
          name: `High (${assumptions.highPct}%)`,
          line: { color: '#dc2626', width: 2, shape: 'spline', smoothing: 1.1 },
          fill: 'tonexty', fillcolor: 'rgba(220,38,38,0.10)',
          hovertemplate: hoverFmt,
        },
        {
          type: 'scatter', x: xs, y: base, mode: 'lines',
          name: `Base (${assumptions.basePct}%)`,
          line: { color: '#f59e0b', width: 2.8, shape: 'spline', smoothing: 1.1 },
          marker: { size: 6, color: '#f59e0b', line: { color: '#fff', width: 1.5 } },
          hovertemplate: hoverFmt,
        },
      ],
      layout: {
        ...BASE_LAYOUT,
        height: 260,
        margin: { l: 64, r: 16, t: 40, b: 50 },
        hovermode: 'x unified',
        xaxis: {
          ...AXIS_BASE,
          title: { text: simData?.time_series?.length ? 'Simulation Hour' : 'Time', standoff: 12 },
        },
        yaxis: {
          ...AXIS_BASE,
          title: { text: 'Estimated Loss at Risk (PHP)', standoff: 12 },
          tickformat: '~s',
          automargin: true,
        },
        legend: {
          orientation: 'h', yanchor: 'bottom', y: 1.05, xanchor: 'left', x: 0,
          font: { size: 11, color: '#334155' },
          bgcolor: 'rgba(0,0,0,0)',
        },
      },
    }
  }, [assumptions, lossData, simData])

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
            <div className="card-body p-0">
              <small className="text-muted d-block px-3 pt-2">
                Planning estimate: {assumptions.yieldKg} kg/tree, PHP {assumptions.pricePhp}/kg, damage: {assumptions.lowPct}% / {assumptions.basePct}% / {assumptions.highPct}%
              </small>
              <div ref={lossResize.containerRef} style={{ width: '100%' }}>
                <Plot
                  data={lossFig.data}
                  layout={lossFig.layout}
                  config={CHART_CONFIG}
                  useResizeHandler
                  onInitialized={lossResize.onInitialized}
                  onUpdate={lossResize.onUpdate}
                  style={{ height: 260, width: '100%' }}
                />
              </div>
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
                  <small className="text-muted d-block mb-3">
                    {assumptions.yieldKg} kg/tree - PHP {assumptions.pricePhp}/kg - final infested trees
                  </small>
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
