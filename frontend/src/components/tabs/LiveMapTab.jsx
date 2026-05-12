import { useState } from 'react'
import RiskMap from '../RiskMap'

const COMPASS_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 140 140">
  <defs>
    <!-- Brass bezel gradient -->
    <radialGradient id="bezel" cx="50%" cy="50%" r="50%">
      <stop offset="80%"  stop-color="#3a4452"/>
      <stop offset="92%"  stop-color="#1f2733"/>
      <stop offset="100%" stop-color="#10151c"/>
    </radialGradient>
    <!-- Ivory face -->
    <radialGradient id="face" cx="50%" cy="42%" r="62%">
      <stop offset="0%"  stop-color="#fefcf6"/>
      <stop offset="60%" stop-color="#f3eedf"/>
      <stop offset="100%" stop-color="#e3dcc6"/>
    </radialGradient>
    <linearGradient id="needleN" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%"  stop-color="#b91c1c"/>
      <stop offset="100%" stop-color="#ff5252"/>
    </linearGradient>
    <linearGradient id="needleS" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"  stop-color="#1f2933"/>
      <stop offset="100%" stop-color="#475569"/>
    </linearGradient>
    <filter id="bezelShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="2.4" flood-color="#000" flood-opacity="0.45"/>
    </filter>
  </defs>

  <!-- Outer brass bezel with inner highlight ring -->
  <g filter="url(#bezelShadow)">
    <circle cx="70" cy="70" r="66" fill="url(#bezel)"/>
    <circle cx="70" cy="70" r="63.5" fill="none" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
  </g>

  <!-- Ivory face -->
  <circle cx="70" cy="70" r="58" fill="url(#face)" stroke="#5b6573" stroke-width="0.8"/>

  <!-- 16-point tick ring (long for cardinals, short for everything else) -->
  <g stroke="#3a4452" stroke-linecap="round">
    <!-- Cardinals -->
    <g stroke-width="1.6">
      <line x1="70" y1="14"  x2="70" y2="26"/>
      <line x1="70" y1="114" x2="70" y2="126"/>
      <line x1="14" y1="70"  x2="26" y2="70"/>
      <line x1="114" y1="70" x2="126" y2="70"/>
    </g>
    <!-- Intercardinals (45°) -->
    <g stroke-width="1.1">
      <line x1="32"  y1="32"  x2="40"  y2="40"/>
      <line x1="108" y1="32"  x2="100" y2="40"/>
      <line x1="32"  y1="108" x2="40"  y2="100"/>
      <line x1="108" y1="108" x2="100" y2="100"/>
    </g>
    <!-- Half-cardinals (22.5°) -->
    <g stroke-width="0.7" opacity="0.7">
      <line x1="92"  y1="17"  x2="89"  y2="27"/>
      <line x1="48"  y1="17"  x2="51"  y2="27"/>
      <line x1="123" y1="48"  x2="113" y2="51"/>
      <line x1="123" y1="92"  x2="113" y2="89"/>
      <line x1="92"  y1="123" x2="89"  y2="113"/>
      <line x1="48"  y1="123" x2="51"  y2="113"/>
      <line x1="17"  y1="48"  x2="27"  y2="51"/>
      <line x1="17"  y1="92"  x2="27"  y2="89"/>
    </g>
  </g>

  <!-- Cardinal letters -->
  <g font-family="'Manrope','Segoe UI',sans-serif" text-anchor="middle">
    <text x="70" y="40"  font-size="12" font-weight="800" fill="#b91c1c">N</text>
    <text x="70" y="106" font-size="10" font-weight="700" fill="#334155">S</text>
    <text x="105" y="74" font-size="10" font-weight="700" fill="#334155">E</text>
    <text x="35"  y="74" font-size="10" font-weight="700" fill="#334155">W</text>
  </g>

  <!-- Compass-rose needle (sharp diamond) -->
  <g>
    <polygon points="70,22 76,70 70,68 64,70" fill="url(#needleN)" stroke="#7f1d1d" stroke-width="0.7" stroke-linejoin="round"/>
    <polygon points="70,118 76,70 70,72 64,70" fill="url(#needleS)" stroke="#0f172a" stroke-width="0.7" stroke-linejoin="round"/>
  </g>

  <!-- Center pin with metallic highlight -->
  <circle cx="70" cy="70" r="6.5" fill="#1f2933" stroke="#7c8290" stroke-width="1"/>
  <circle cx="68.5" cy="68.5" r="1.5" fill="#e2e8f0" opacity="0.9"/>

  <!-- Subtle "TRUE NORTH" engraved label -->
  <text x="70" y="92" font-family="'Manrope','Segoe UI',sans-serif" font-size="6.5"
        fill="#475569" text-anchor="middle" letter-spacing="1.6" font-weight="700">
    TRUE NORTH
  </text>
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
  stageOverrides = {},
  stageZones = [],
  stageZoneDrawing = false,
  stageZoneStage = 'mature',
  stageZoneDraft = [],
  stageOptions = [],
  onStageZoneStageChange,
  onStageZoneStart,
  onStageZoneCancel,
  onStageZoneFinish,
  onStageZoneClear,
  onStageZoneMapClick,
  orchardName,
  orthophotoOverlay = null,
  viewportKey = 'default',
  fitToOrthophoto = true,
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

        <div className="map-stage-zone-tools">
          <button
            type="button"
            className={`btn btn-sm ${stageZoneDrawing ? 'btn-success' : 'btn-light'}`}
            onClick={stageZoneDrawing ? onStageZoneCancel : onStageZoneStart}
          >
            <i className="bi bi-bounding-box me-1" />
            {stageZoneDrawing ? 'Cancel Zone' : 'Stage Zone'}
          </button>
          {stageZoneDrawing && (
            <>
              <select
                className="form-select form-select-sm map-stage-zone-select"
                value={stageZoneStage}
                onChange={(e) => onStageZoneStageChange?.(e.target.value)}
              >
                {stageOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-sm btn-success"
                disabled={stageZoneDraft.length < 3}
                onClick={onStageZoneFinish}
              >
                Save
              </button>
            </>
          )}
          {!stageZoneDrawing && stageZones.length > 0 && (
            <button type="button" className="btn btn-sm btn-light" onClick={onStageZoneClear}>
              Clear Stages
            </button>
          )}
        </div>

        {titleText && (
          <div className="map-animation-title">{titleText}</div>
        )}

        <div className="map-card">
          <RiskMap
            geojson={geojson}
            baseGeojson={baseGeojson}
            alerts={alerts}
            treeOverrides={treeOverrides}
            stageOverrides={stageOverrides}
            stageZones={stageZones}
            stageZoneDrawing={stageZoneDrawing}
            stageZoneDraft={stageZoneDraft}
            onStageZoneMapClick={onStageZoneMapClick}
            orthophotoOverlay={orthophotoOverlay}
            viewportKey={viewportKey}
            fitToOrthophoto={fitToOrthophoto}
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
