import { useEffect, useRef, useState } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'
import OverviewDataTable from './OverviewDataTable'

const Plot = createPlotlyComponent(Plotly)
const SERIES = [
  { key: 'simulations', label: 'Completed simulations', color: '#2563eb' },
  { key: 'observations', label: 'Inspection records', color: '#15803d' },
  { key: 'present', label: 'Present findings', color: '#dc2626' },
  { key: 'alerts', label: 'Alerts raised', color: '#b45309' },
]
const TABLE_COLUMNS = [
  { key: 'date', label: 'Date', value: (row) => row.date },
  ...SERIES.map(({ key, label }) => ({ key, label, numeric: true,
    value: (row) => row[key], format: (value) => value.toLocaleString('en-PH') })),
]
const MONTHLY_COLUMNS = [{ ...TABLE_COLUMNS[0], label: 'Month' }, ...TABLE_COLUMNS.slice(1)]
const rowKey = (row) => row.date

export default function OverviewActivityChart({ timeline, monthly }) {
  const containerRef = useRef(null)
  const plotRef = useRef(null)
  const [showTable, setShowTable] = useState(false)
  const maxCount = timeline.reduce((maximum, row) => Math.max(maximum, ...SERIES.map(({ key }) => row[key])), 0)
  useEffect(() => {
    if (!containerRef.current || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => {
      if (plotRef.current) Plotly.Plots.resize(plotRef.current)
    })
    observer.observe(containerRef.current)
    return () => { observer.disconnect(); plotRef.current = null }
  }, [])
  return <div ref={containerRef}>
    <p className="small text-muted mb-1">{monthly ? 'Monthly totals in Philippine time; the current month may be partial.' : 'Daily totals in Philippine time.'} Bars compare record types side by side. Hover for counts; click a legend item to show or hide it.</p>
    <p className="small text-muted mb-2">Present findings are included in inspection records.</p>
    <Plot data={SERIES.map(({ key, label, color }) => ({
      type: 'bar', name: label,
      x: timeline.map((row) => row.date), y: timeline.map((row) => row[key]),
      marker: { color },
      hovertemplate: '<b>%{fullData.name}</b><br>%{y:,} records<extra></extra>',
    }))} layout={{ autosize: true, height: 350, barmode: 'group', bargap: 0.22, bargroupgap: 0.08,
      margin: { l: 42, r: 15, t: 15, b: 105 }, hovermode: 'x unified',
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'Outfit, sans-serif', color: '#475569', size: 12 },
      legend: { orientation: 'h', x: 0, y: -0.18, yanchor: 'top' },
      xaxis: { type: 'date', tickformat: monthly ? '%b %Y' : '%d %b', gridcolor: '#eef2f7' },
      yaxis: { rangemode: 'tozero', tickformat: ',d', dtick: maxCount <= 5 ? 1 : undefined, gridcolor: '#eef2f7', title: 'Records' },
    }} config={{ displayModeBar: false, responsive: true }} style={{ width: '100%', height: 350 }}
      onInitialized={(_, graph) => { plotRef.current = graph }}
      onUpdate={(_, graph) => { plotRef.current = graph }} />
    <button type="button" className="btn btn-sm btn-outline-secondary" aria-expanded={showTable}
      aria-controls="overview-activity-table" onClick={() => setShowTable((value) => !value)}>
      {showTable ? 'Hide data table' : 'View data table'}
    </button>
    <div className="mt-3" id="overview-activity-table" hidden={!showTable}>
      <OverviewDataTable id="overview-timeline" label="Activity counts" rows={timeline}
        columns={monthly ? MONTHLY_COLUMNS : TABLE_COLUMNS} rowKey={rowKey}
        caption={`Activity counts by ${monthly ? 'month' : 'day'}. Present findings are included in inspection records.`} />
    </div>
  </div>
}
