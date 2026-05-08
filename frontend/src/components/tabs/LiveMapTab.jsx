import { useState } from 'react'
import RiskMap from '../RiskMap'

const COMPASS_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 140 140">
  <defs>
    <radialGradient id="face" cx="50%" cy="45%" r="60%"><stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="#edf2f7"/></radialGradient>
    <linearGradient id="needleN" x1="0" y1="1" x2="0" y2="0"><stop offset="0%" stop-color="#d33131"/><stop offset="100%" stop-color="#ff7b7b"/></linearGradient>
    <linearGradient id="needleS" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2f3b46"/><stop offset="100%" stop-color="#5b6a78"/></linearGradient>
    <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000000" flood-opacity="0.28"/></filter>
  </defs>
  <g filter="url(#shadow)"><circle cx="70" cy="70" r="64" fill="url(#face)" stroke="#334155" stroke-width="1.8"/></g>
  <circle cx="70" cy="70" r="55" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.2"/>
  <g stroke="#64748b" stroke-width="1.2" stroke-linecap="round">
    <line x1="70" y1="18" x2="70" y2="28"/><line x1="70" y1="112" x2="70" y2="122"/>
    <line x1="18" y1="70" x2="28" y2="70"/><line x1="112" y1="70" x2="122" y2="70"/>
  </g>
  <g font-family="Segoe UI,sans-serif" font-weight="700" text-anchor="middle">
    <text x="70" y="14" font-size="11" fill="#b91c1c">N</text>
    <text x="70" y="134" font-size="10" fill="#334155">S</text>
    <text x="131" y="74" font-size="10" fill="#334155">E</text>
    <text x="9" y="74" font-size="10" fill="#334155">W</text>
  </g>
  <polygon points="70,24 78,68 70,78 62,68" fill="url(#needleN)" stroke="#991b1b" stroke-width="1"/>
  <polygon points="70,116 78,72 70,62 62,72" fill="url(#needleS)" stroke="#1f2937" stroke-width="1"/>
  <circle cx="70" cy="70" r="7.5" fill="#ffffff" stroke="#334155" stroke-width="1.3"/>
  <circle cx="70" cy="70" r="2.6" fill="#0f172a"/>
  <text x="70" y="88" font-family="Segoe UI,sans-serif" font-size="7.5" fill="#475569" text-anchor="middle" letter-spacing="0.8">TRUE NORTH</text>
</svg>`

const COMPASS_URI = `data:image/svg+xml;utf8,${encodeURIComponent(COMPASS_SVG)}`

const RISK_LEGEND_ENTRIES = [
  { label: 'Critical', color: '#b91c1c' },
  { label: 'Severe',   color: '#ef4444' },
  { label: 'High',     color: '#f97316' },
  { label: 'Moderate', color: '#facc15' },
  { label: 'Low',      color: '#22c55e' },
]

export default function LiveMapTab({
  geojson,
  baseGeojson,
  alerts = [],
  treeOverrides = {},
  orchardName,
  currentFrame,
  onTreeClick,
}) {
  const [showGrid, setShowGrid] = useState(false)

  const titleText = currentFrame != null
    ? `Hour ${currentFrame.hour} — Spread Animation`
    : (orchardName ?? null)

  const showLegend = geojson != null

  return (
    <div className="operations-map-panel">
      <div className="operations-map-stage" style={{ position: 'relative' }}>
        <button
          type="button"
          className="btn btn-light btn-sm map-overlay-btn"
          onClick={() => setShowGrid((g) => !g)}
        >
          <i className="bi bi-grid-3x3-gap me-1" />
          {showGrid ? 'Hide Grid' : 'Show Grid'}
        </button>

        {titleText && (
          <div className="map-animation-title">{titleText}</div>
        )}

        <div className="map-card">
          <RiskMap
            geojson={geojson}
            baseGeojson={baseGeojson}
            alerts={alerts}
            treeOverrides={treeOverrides}
            showGridOverlay={showGrid}
            onTreeClick={onTreeClick}
          />
        </div>

        {showLegend && (
          <div className="map-risk-legend">
            <div className="map-risk-legend-title">Risk Level</div>
            {RISK_LEGEND_ENTRIES.map((entry) => (
              <div key={entry.label} className="map-risk-legend-item">
                <div className="map-risk-legend-swatch" style={{ background: entry.color }} />
                {entry.label}
              </div>
            ))}
          </div>
        )}

        <img src={COMPASS_URI} alt="Compass - True North" className="map-compass" />
      </div>
    </div>
  )
}
