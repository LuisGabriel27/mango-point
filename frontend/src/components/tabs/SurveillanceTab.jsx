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

function emptyFig(msg, height = 260) {
  return {
    data: [],
    layout: {
      ...BASE_LAYOUT, height,
      annotations: [{ text: msg, x: 0.5, y: 0.5, xref: 'paper', yref: 'paper', showarrow: false, font: { size: 13, color: '#94a3b8' } }],
      xaxis: { visible: false }, yaxis: { visible: false },
    },
  }
}

export default function SurveillanceTab({ monitoringData, simData, weather }) {
  const spreadResize = useChartResize()
  const envResize = useChartResize()
  const spreadFig = useMemo(() => {
    // Prefer simulation time_series; fall back to monitoring pest_trend from DB
    const cumulativeTrace = (xs, ys, name) => ({
      type: 'scatter', x: xs, y: ys, mode: 'lines',
      name,
      line: { color: '#ef4444', width: 2.6, shape: 'spline', smoothing: 1.1 },
      fill: 'tozeroy', fillcolor: 'rgba(239,68,68,0.10)',
      hovertemplate: '<b>%{fullData.name}</b><br>%{y:,} trees<extra></extra>',
    })
    const dailyTrace = (xs, ys, name) => ({
      type: 'bar', x: xs, y: ys, name,
      marker: { color: 'rgba(249,115,22,0.55)', line: { color: 'rgba(249,115,22,0.85)', width: 0.5 } },
      yaxis: 'y2',
      hovertemplate: '<b>%{fullData.name}</b><br>%{y:,}<extra></extra>',
    })
    const legendBase = {
      orientation: 'h', yanchor: 'bottom', y: 1.05, xanchor: 'left', x: 0,
      font: { size: 11, color: '#334155' },
      bgcolor: 'rgba(0,0,0,0)',
    }

    if (simData?.time_series?.length) {
      const xs = simData.time_series.map((f) => `Hour ${f.hour}`)
      const cumulative = simData.time_series.map((f) => f.n_infested ?? 0)
      const daily = simData.time_series.map((f) => f.n_new ?? 0)
      return {
        data: [
          cumulativeTrace(xs, cumulative, 'Cumulative infested'),
          dailyTrace(xs, daily, 'New per step'),
        ],
        layout: {
          ...BASE_LAYOUT,
          height: 260,
          margin: { l: 64, r: 56, t: 40, b: 70 },
          hovermode: 'x unified',
          bargap: 0.35,
          xaxis: {
            ...AXIS_BASE,
            title: { text: 'Simulation hour', standoff: 18 },
            tickangle: -30,
            automargin: true,
          },
          yaxis: {
            ...AXIS_BASE,
            title: { text: 'Cumulative infested trees', standoff: 12 },
            automargin: true,
          },
          yaxis2: {
            ...AXIS_BASE,
            title: { text: 'New per step', standoff: 12 },
            overlaying: 'y',
            side: 'right',
            gridcolor: 'rgba(0,0,0,0)',
            showspikes: false,
            automargin: true,
          },
          legend: legendBase,
        },
      }
    }

    const trend = monitoringData?.pest_trend ?? []
    if (!trend.length) return emptyFig('Run a simulation to see infestation spread over time.')
    const xs = trend.map((d) => d.timestamp ?? d.date ?? d.x ?? '')
    const cumulative = trend.map((d) => d.infested_trees ?? d.infested ?? 0)
    const daily = cumulative.map((v, i) => i === 0 ? v : Math.max(0, v - cumulative[i - 1]))
    return {
      data: [
        cumulativeTrace(xs, cumulative, 'Cumulative'),
        dailyTrace(xs, daily, 'Daily New'),
      ],
      layout: {
        ...BASE_LAYOUT,
        height: 260,
        margin: { l: 64, r: 56, t: 40, b: 60 },
        hovermode: 'x unified',
        bargap: 0.35,
        xaxis: {
          ...AXIS_BASE,
          title: { text: 'Time', standoff: 14 },
          automargin: true,
        },
        yaxis: {
          ...AXIS_BASE,
          title: { text: 'Cumulative Infested Trees', standoff: 12 },
          automargin: true,
        },
        yaxis2: {
          ...AXIS_BASE,
          title: { text: 'Daily New Infested', standoff: 12 },
          overlaying: 'y',
          side: 'right',
          gridcolor: 'rgba(0,0,0,0)',
          showspikes: false,
          automargin: true,
        },
        legend: legendBase,
      },
    }
  }, [monitoringData, simData])

  // Weather line chart: use simulation time_series weather or monitoring environment trends
  const envFig = useMemo(() => {
    // If we have simulation weather data, use it
    const tempTrace = (xs, ys) => ({
      type: 'scatter', x: xs, y: ys, mode: 'lines',
      name: 'Temp °C',
      line: { color: '#f59e0b', width: 2.4, shape: 'spline', smoothing: 1.1 },
      fill: 'tozeroy', fillcolor: 'rgba(245,158,11,0.10)',
      hovertemplate: '<b>Temp</b><br>%{y:.1f} °C<extra></extra>',
    })
    const secondaryTrace = (xs, ys, name, unit) => ({
      type: 'scatter', x: xs, y: ys, mode: 'lines',
      name,
      line: { color: '#3b82f6', width: 2.2, shape: 'spline', smoothing: 1.1, dash: 'dot' },
      yaxis: 'y2',
      hovertemplate: `<b>${name}</b><br>%{y:.1f} ${unit}<extra></extra>`,
    })
    const legendBase = {
      orientation: 'h', yanchor: 'bottom', y: 1.06, xanchor: 'left', x: 0,
      font: { size: 11, color: '#334155' },
      bgcolor: 'rgba(0,0,0,0)',
    }

    if (simData?.time_series?.length && simData.time_series[0]?.weather) {
      const frames = simData.time_series.filter((f) => f.weather)
      const xs = frames.map((f) => f.datetime ?? `Hour ${f.hour}`)
      const temps = frames.map((f) => f.weather.temperature_c ?? f.weather.temp_c)
      const winds = frames.map((f) => f.weather.wind_speed_ms ?? f.weather.wind_ms)
      return {
        data: [
          tempTrace(xs, temps),
          secondaryTrace(xs, winds, 'Wind m/s', 'm/s'),
        ],
        layout: {
          ...BASE_LAYOUT,
          height: 220,
          margin: { l: 56, r: 52, t: 40, b: 60 },
          hovermode: 'x unified',
          xaxis: {
            ...AXIS_BASE,
            tickangle: -30,
            automargin: true,
          },
          yaxis: {
            ...AXIS_BASE,
            title: { text: 'Temp (°C)', standoff: 10 },
            automargin: true,
          },
          yaxis2: {
            ...AXIS_BASE,
            title: { text: 'Wind (m/s)', standoff: 10 },
            overlaying: 'y',
            side: 'right',
            gridcolor: 'rgba(0,0,0,0)',
            showspikes: false,
            automargin: true,
          },
          legend: legendBase,
        },
      }
    }

    const env = monitoringData?.environment?.trends ?? monitoringData?.environment?.trend ?? []
    if (!env.length) return emptyFig('Environmental trend data unavailable.', 220)
    const xs = env.map((e) => e.timestamp ?? e.date ?? '')
    return {
      data: [
        tempTrace(xs, env.map((e) => e.temperature_c ?? e.temperature)),
        secondaryTrace(xs, env.map((e) => e.humidity), 'Humidity %', '%'),
      ],
      layout: {
        ...BASE_LAYOUT,
        height: 220,
        margin: { l: 60, r: 60, t: 40, b: 60 },
        hovermode: 'x unified',
        xaxis: { ...AXIS_BASE, automargin: true },
        yaxis: {
          ...AXIS_BASE,
          title: { text: 'Temp (°C)', standoff: 10 },
          automargin: true,
        },
        yaxis2: {
          ...AXIS_BASE,
          title: { text: 'Humidity (%)', standoff: 10 },
          overlaying: 'y',
          side: 'right',
          gridcolor: 'rgba(0,0,0,0)',
          showspikes: false,
          automargin: true,
        },
        legend: legendBase,
      },
    }
  }, [monitoringData, simData])

  const current = simData?.time_series?.[0]?.weather ?? simData?.weather_data?.[0] ?? weather?.current

  return (
    <div className="p-3">
      <div className="d-flex flex-column gap-3">
        <div className="card shadow-sm border-0 monitoring-module-chart-card">
          <div className="card-header py-2">
            <div className="d-flex align-items-center justify-content-between">
              <div className="d-flex align-items-center">
                <i className="bi bi-graph-up-arrow me-2" />
                <span className="fw-semibold">Infestation Spread Over Time</span>
              </div>
              {simData?.time_series?.length > 0 && (
                <small className="text-success">
                  <i className="bi bi-check-circle me-1" />From simulation
                </small>
              )}
            </div>
          </div>
          <div className="card-body p-0">
            <div ref={spreadResize.containerRef} style={{ width: '100%' }}>
              <Plot
                data={spreadFig.data}
                layout={spreadFig.layout}
                config={CHART_CONFIG}
                useResizeHandler
                onInitialized={spreadResize.onInitialized}
                onUpdate={spreadResize.onUpdate}
                style={{ height: 260, width: '100%' }}
              />
            </div>
          </div>
        </div>

        <div className="card shadow-sm border-0 monitoring-module-chart-card">
          <div className="card-header py-2">
            <div className="d-flex align-items-center">
              <i className="bi bi-cloud-sun me-2" />
              <span className="fw-semibold">Weather During Simulation</span>
            </div>
          </div>
          <div className="card-body p-0">
            {current && (
              <div className="d-flex gap-3 small text-muted mb-2 px-3 pt-2">
                <span><i className="bi bi-thermometer-half me-1" />{current.temperature_c?.toFixed(1)}°C</span>
                <span><i className="bi bi-droplet me-1" />{current.humidity}%</span>
                <span><i className="bi bi-wind me-1" />{current.wind_speed_ms?.toFixed(1)} m/s</span>
              </div>
            )}
            <div ref={envResize.containerRef} style={{ width: '100%' }}>
              <Plot
                data={envFig.data}
                layout={envFig.layout}
                config={CHART_CONFIG}
                useResizeHandler
                onInitialized={envResize.onInitialized}
                onUpdate={envResize.onUpdate}
                style={{ height: 220, width: '100%' }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
