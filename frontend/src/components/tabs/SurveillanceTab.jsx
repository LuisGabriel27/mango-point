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

function emptyFig(msg, height = 260) {
  return {
    data: [],
    layout: {
      ...BASE_LAYOUT, height,
      annotations: [{ text: msg, x: 0.5, y: 0.5, xref: 'paper', yref: 'paper', showarrow: false, font: { size: 13, color: '#7c7c7c' } }],
      xaxis: { visible: false }, yaxis: { visible: false },
    },
  }
}

export default function SurveillanceTab({ monitoringData, simData, weather }) {
  const spreadFig = useMemo(() => {
    // Prefer simulation time_series; fall back to monitoring pest_trend from DB
    if (simData?.time_series?.length) {
      const xs = simData.time_series.map((f) => `Hour ${f.hour}`)
      const cumulative = simData.time_series.map((f) => f.n_infested ?? 0)
      const daily = simData.time_series.map((f) => f.n_new ?? 0)
      return {
        data: [
          { type: 'scatter', x: xs, y: cumulative, mode: 'lines', name: 'Cumulative infested', line: { color: '#ef4444', width: 2 } },
          { type: 'bar', x: xs, y: daily, name: 'New per step', marker: { color: 'rgba(251,146,60,0.5)' }, yaxis: 'y2' },
        ],
        layout: {
          ...BASE_LAYOUT,
          height: 260,
          // Roomier margins so the two y-axis titles and rotated hour labels
          // no longer overlap with the tick numbers.
          margin: { l: 70, r: 60, t: 34, b: 70 },
          xaxis: {
            title: { text: 'Simulation hour', standoff: 18 },
            gridcolor: '#eee',
            tickangle: -30,
            automargin: true,
          },
          yaxis: {
            title: { text: 'Cumulative infested trees', standoff: 12 },
            gridcolor: '#eee',
            automargin: true,
          },
          yaxis2: {
            title: { text: 'New per step', standoff: 12 },
            overlaying: 'y',
            side: 'right',
            gridcolor: '#eee',
            automargin: true,
          },
          legend: { orientation: 'h', yanchor: 'bottom', y: 1.03, xanchor: 'left', x: 0 },
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
        { type: 'scatter', x: xs, y: cumulative, mode: 'lines', name: 'Cumulative', line: { color: '#ef4444', width: 2 } },
        { type: 'bar', x: xs, y: daily, name: 'Daily New', marker: { color: 'rgba(251,146,60,0.5)' }, yaxis: 'y2' },
      ],
      layout: {
        ...BASE_LAYOUT,
        height: 260,
        margin: { l: 70, r: 60, t: 34, b: 60 },
        xaxis: {
          title: { text: 'Time', standoff: 14 },
          gridcolor: '#eee',
          automargin: true,
        },
        yaxis: {
          title: { text: 'Cumulative Infested Trees', standoff: 12 },
          gridcolor: '#eee',
          automargin: true,
        },
        yaxis2: {
          title: { text: 'Daily New Infested', standoff: 12 },
          overlaying: 'y',
          side: 'right',
          gridcolor: '#eee',
          automargin: true,
        },
        legend: { orientation: 'h', yanchor: 'bottom', y: 1.03, xanchor: 'left', x: 0 },
      },
    }
  }, [monitoringData, simData])

  // Weather line chart: use simulation time_series weather or monitoring environment trends
  const envFig = useMemo(() => {
    // If we have simulation weather data, use it
    if (simData?.time_series?.length && simData.time_series[0]?.weather) {
      const frames = simData.time_series.filter((f) => f.weather)
      const xs = frames.map((f) => f.datetime ?? `Hour ${f.hour}`)
      const temps = frames.map((f) => f.weather.temperature_c ?? f.weather.temp_c)
      const winds = frames.map((f) => f.weather.wind_speed_ms ?? f.weather.wind_ms)
      return {
        data: [
          { type: 'scatter', x: xs, y: temps, mode: 'lines', name: 'Temp °C', line: { color: '#f59e0b', width: 2 } },
          { type: 'scatter', x: xs, y: winds, mode: 'lines', name: 'Wind m/s', line: { color: '#3b82f6', width: 2, dash: 'dot' }, yaxis: 'y2' },
        ],
        layout: {
          ...BASE_LAYOUT,
          height: 200,
          // Two-line datetimes (e.g. "12:00 / May 11, 2026") and the right-side
          // axis title need extra room — bumped from { l:20, r:40, b:30 }.
          margin: { l: 60, r: 60, t: 30, b: 60 },
          xaxis: { gridcolor: '#eee', tickangle: -30, automargin: true },
          yaxis: {
            title: { text: 'Temp (°C)', standoff: 10 },
            gridcolor: '#eee',
            automargin: true,
          },
          yaxis2: {
            title: { text: 'Wind (m/s)', standoff: 10 },
            overlaying: 'y',
            side: 'right',
            automargin: true,
          },
          legend: { orientation: 'h', yanchor: 'bottom', y: 1.03, xanchor: 'left', x: 0 },
        },
      }
    }

    const env = monitoringData?.environment?.trends ?? monitoringData?.environment?.trend ?? []
    if (!env.length) return emptyFig('Environmental trend data unavailable.', 200)
    const xs = env.map((e) => e.timestamp ?? e.date ?? '')
    return {
      data: [
        { type: 'scatter', x: xs, y: env.map((e) => e.temperature_c ?? e.temperature), mode: 'lines', name: 'Temp °C', line: { color: '#f59e0b', width: 2 } },
        { type: 'scatter', x: xs, y: env.map((e) => e.humidity), mode: 'lines', name: 'Humidity %', line: { color: '#3b82f6', width: 2 }, yaxis: 'y2' },
      ],
      layout: {
        ...BASE_LAYOUT,
        height: 200,
        margin: { l: 60, r: 60, t: 30, b: 60 },
        xaxis: { gridcolor: '#eee', automargin: true },
        yaxis: {
          title: { text: 'Temp (°C)', standoff: 10 },
          gridcolor: '#eee',
          automargin: true,
        },
        yaxis2: {
          title: { text: 'Humidity (%)', standoff: 10 },
          overlaying: 'y',
          side: 'right',
          automargin: true,
        },
        legend: { orientation: 'h', yanchor: 'bottom', y: 1.03, xanchor: 'left', x: 0 },
      },
    }
  }, [monitoringData, simData])

  const current = weather?.current

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
          <div className="card-body py-1">
            <Plot
              data={spreadFig.data}
              layout={spreadFig.layout}
              config={CHART_CONFIG}
              useResizeHandler
              style={{ height: 260, width: '100%' }}
            />
          </div>
        </div>

        <div className="card shadow-sm border-0 monitoring-module-chart-card">
          <div className="card-header py-2">
            <div className="d-flex align-items-center">
              <i className="bi bi-cloud-sun me-2" />
              <span className="fw-semibold">Weather During Simulation</span>
            </div>
          </div>
          <div className="card-body py-1">
            {current && (
              <div className="d-flex gap-3 small text-muted mb-2 px-1">
                <span><i className="bi bi-thermometer-half me-1" />{current.temperature_c?.toFixed(1)}°C</span>
                <span><i className="bi bi-droplet me-1" />{current.humidity}%</span>
                <span><i className="bi bi-wind me-1" />{current.wind_speed_ms?.toFixed(1)} m/s</span>
              </div>
            )}
            <Plot
              data={envFig.data}
              layout={envFig.layout}
              config={CHART_CONFIG}
              useResizeHandler
              style={{ height: 200, width: '100%' }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
