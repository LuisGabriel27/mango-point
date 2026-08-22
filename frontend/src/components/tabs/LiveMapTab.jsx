import { useEffect, useState } from 'react'
import RiskMap from '../RiskMap'
import MpSelect from '../MpSelect'

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

const TREE_STATE_LEGEND_ENTRIES = [
  { label: 'Healthy', color: '#22c55e' },
  { label: 'Infected', color: '#ef4444' },
  { label: 'Bagged', color: '#3b82f6' },
  { label: 'Dead', color: '#424242' },
  { label: 'Historical', color: '#ff9800' },
  { label: 'Suspect', color: '#9c27b0' },
]

const ZONE_TYPE_OPTIONS = [
  { value: 'stage', label: 'Stage' },
  { value: 'status', label: 'Status' },
  { value: 'cecid', label: 'Weed Habitat' },
]

const CECID_DENSITY_OPTIONS = [
  { value: 'sparse', label: 'Sparse (0.60×)' },
  { value: 'moderate', label: 'Moderate (0.80×)' },
  { value: 'dense', label: 'Dense (1.00×)' },
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
  onStageZoneUndoPoint,
  onStageZoneMapClick,
  statusZones = [],
  statusZoneDrawing = false,
  statusZoneStatus = 'infected',
  statusZoneDraft = [],
  statusOptions = [],
  onStatusZoneStatusChange,
  onStatusZoneStart,
  onStatusZoneCancel,
  onStatusZoneFinish,
  onStatusZoneUndoPoint,
  onStatusZoneMapClick,
  cecidWeedZones = [],
  legacyCecidEmergenceZones = [],
  cecidZoneDrawing = false,
  cecidZoneDensity = 'moderate',
  cecidZoneLabel = 'Weed habitat',
  cecidZoneDraft = [],
  cecidZoneSaveState = 'idle',
  cecidZoneSaveError = '',
  onCecidZoneDensityChange,
  onCecidZoneLabelChange,
  onCecidZoneStart,
  onCecidZoneCancel,
  onCecidZoneFinish,
  onCecidZoneUndoPoint,
  onCecidZoneMapClick,
  onCecidZoneUpdate,
  onCecidZoneRedraw,
  onCecidZoneDelete,
  onCecidZoneClear,
  onCecidZoneRetry,
  selectedPestType = 'fruitfly',
  zoneHistory = [],
  onZoneUndoLast,
  onZoneClearAll,
  orchardName,
  orthophotoOverlay = null,
  viewportKey = 'default',
  fitToOrthophoto = true,
  currentFrame,
  onTreeClick,
}) {
  const [showGrid, setShowGrid] = useState(false)
  const [showWeedManager, setShowWeedManager] = useState(false)
  const [zoneEditorType, setZoneEditorType] = useState('stage')
  const [zoneVisibility, setZoneVisibility] = useState({
    stage: true,
    status: true,
    cecid: selectedPestType === 'cecid',
  })

  useEffect(() => {
    setZoneVisibility((current) => ({
      ...current,
      cecid: selectedPestType === 'cecid',
    }))
  }, [selectedPestType])

  const drawingByType = {
    stage: stageZoneDrawing,
    status: statusZoneDrawing,
    cecid: cecidZoneDrawing,
  }
  const draftByType = {
    stage: stageZoneDraft,
    status: statusZoneDraft,
    cecid: cecidZoneDraft,
  }
  const activeDrawing = Boolean(drawingByType[zoneEditorType])
  const activeDraft = draftByType[zoneEditorType] || []
  const cancelAllDrawings = () => {
    onStageZoneCancel?.()
    onStatusZoneCancel?.()
    onCecidZoneCancel?.()
  }
  const handleZoneTypeChange = (value) => {
    cancelAllDrawings()
    setZoneEditorType(value)
  }
  const handleZoneDrawToggle = () => {
    if (activeDrawing) {
      cancelAllDrawings()
      return
    }
    if (zoneEditorType === 'stage') onStageZoneStart?.()
    else if (zoneEditorType === 'status') onStatusZoneStart?.()
    else onCecidZoneStart?.()
  }
  const handleZoneUndoPoint = () => {
    if (zoneEditorType === 'stage') onStageZoneUndoPoint?.()
    else if (zoneEditorType === 'status') onStatusZoneUndoPoint?.()
    else onCecidZoneUndoPoint?.()
  }
  const handleZoneFinish = () => {
    if (zoneEditorType === 'stage') onStageZoneFinish?.()
    else if (zoneEditorType === 'status') onStatusZoneFinish?.()
    else onCecidZoneFinish?.()
  }

  const titleText = currentFrame != null
    ? `Hour ${currentFrame.hour} — Spread Animation`
    : (orchardName ?? null)

  const showLegend = geojson != null

  return (
    <div className="operations-map-panel">
      <div className="operations-map-stage" style={{ position: 'relative' }}>
        <div className="map-top-controls" role="toolbar" aria-label="Map controls">
        <button
          type="button"
          className="btn btn-light btn-sm map-overlay-btn"
          onClick={() => setShowGrid((g) => !g)}
        >
          <i className="bi bi-grid-3x3-gap me-1" />
          {showGrid ? 'Hide Grid' : 'Show Grid'}
        </button>

        <div className="map-zone-tools map-zone-editor" role="group" aria-label="Zone editor">
          <span className="map-zone-editor-label">
            <i className="bi bi-bounding-box-circles" />
            Zone Editor
          </span>
          <div className="map-zone-type-wrap">
            <MpSelect
              small
              className="map-zone-type-select"
              value={zoneEditorType}
              onChange={handleZoneTypeChange}
              options={ZONE_TYPE_OPTIONS}
            />
          </div>
          <button
            type="button"
            className={`btn btn-sm ${activeDrawing ? 'btn-success' : 'btn-light'}`}
            onClick={handleZoneDrawToggle}
          >
            <i className="bi bi-bounding-box me-1" />
            {activeDrawing ? 'Cancel' : 'Draw Zone'}
          </button>

          {activeDrawing && (
            <>
              {zoneEditorType === 'stage' && (
                <div style={{ flexShrink: 0, width: 118 }}>
                  <MpSelect small value={stageZoneStage} onChange={onStageZoneStageChange} options={stageOptions} />
                </div>
              )}
              {zoneEditorType === 'status' && (
                <div style={{ flexShrink: 0, width: 148 }}>
                  <MpSelect small value={statusZoneStatus} onChange={onStatusZoneStatusChange} options={statusOptions} />
                </div>
              )}
              {zoneEditorType === 'cecid' && (
                <>
                  <input
                    className="form-control form-control-sm map-cecid-zone-label"
                    value={cecidZoneLabel}
                    aria-label="Weed habitat label"
                    onChange={(event) => onCecidZoneLabelChange?.(event.target.value)}
                    placeholder="Weed habitat label"
                  />
                  <div style={{ flexShrink: 0, width: 130 }}>
                    <MpSelect
                      small
                      value={cecidZoneDensity}
                      onChange={onCecidZoneDensityChange}
                      options={CECID_DENSITY_OPTIONS}
                    />
                  </div>
                  <span className="map-cecid-assumption" title="Weed relay coefficients require BPI field calibration">
                    Research shelter/relay assumption. Weeds never create flies or another generation.
                  </span>
                </>
              )}
              <button
                type="button"
                className="btn btn-sm btn-light"
                disabled={activeDraft.length === 0}
                onClick={handleZoneUndoPoint}
              >
                <i className="bi bi-arrow-counterclockwise me-1" />
                Undo Point
              </button>
              <button
                type="button"
                className="btn btn-sm btn-success"
                disabled={activeDraft.length < 3}
                onClick={handleZoneFinish}
              >
                Save
              </button>
            </>
          )}

          {!activeDrawing && (
            <>
              <span className="map-zone-divider" />
              {ZONE_TYPE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`btn btn-sm ${zoneVisibility[option.value] ? 'btn-light' : 'btn-outline-secondary'}`}
                  onClick={() => setZoneVisibility((current) => ({
                    ...current,
                    [option.value]: !current[option.value],
                  }))}
                  title={`Toggle ${option.label} zones`}
                >
                  <i className={`bi ${zoneVisibility[option.value] ? 'bi-eye' : 'bi-eye-slash'} me-1`} />
                  {option.value === 'cecid' ? 'Weeds' : option.label}
                </button>
              ))}
              {zoneEditorType === 'cecid' && (
                <button
                  type="button"
                  className={`btn btn-sm ${showWeedManager ? 'btn-success' : 'btn-light'}`}
                  onClick={() => setShowWeedManager((current) => !current)}
                >
                  <i className="bi bi-list-ul me-1" />
                  {cecidWeedZones.length} habitat{cecidWeedZones.length === 1 ? '' : 's'}
                </button>
              )}
            </>
          )}

          {!activeDrawing && cecidZoneSaveState !== 'idle' && (
            <span
              className={`badge ${cecidZoneSaveState === 'error' ? 'text-bg-danger' : cecidZoneSaveState === 'saved' ? 'text-bg-success' : 'text-bg-light text-dark'}`}
              title={cecidZoneSaveError || 'Weed habitat persistence status'}
            >
              {cecidZoneSaveState === 'saving' && <span className="spinner-border spinner-border-sm me-1" />}
              {cecidZoneSaveState === 'saving' ? 'Saving' : cecidZoneSaveState === 'saved' ? 'Saved' : 'Save error'}
            </span>
          )}
          {!activeDrawing && cecidZoneSaveState === 'error' && (
            <button type="button" className="btn btn-sm btn-warning" onClick={onCecidZoneRetry}>
              Retry
            </button>
          )}

          {!activeDrawing && zoneHistory.length > 0 && (
            <>
              <span className="map-zone-divider" />
              <button type="button" className="btn btn-sm btn-light" onClick={onZoneUndoLast}>
                <i className="bi bi-arrow-counterclockwise me-1" />
                Undo Zone
              </button>
              <button type="button" className="btn btn-sm btn-light" onClick={onZoneClearAll}>
                Clear All
              </button>
            </>
          )}
        </div>
        </div>

        {showWeedManager && zoneEditorType === 'cecid' && !activeDrawing && (
          <div className="map-weed-zone-manager">
            <div className="d-flex align-items-center justify-content-between gap-2 mb-2">
              <div>
                <div className="fw-bold small"><i className="bi bi-flower2 me-1" />Weed habitats</div>
                <div className="text-muted" style={{ fontSize: '.68rem' }}>
                  Persistent orchard shelter and one-hop relay assumptions.
                </div>
              </div>
              {cecidWeedZones.length > 0 && (
                <button type="button" className="btn btn-sm btn-outline-danger" onClick={onCecidZoneClear}>
                  Clear all
                </button>
              )}
            </div>
            {cecidWeedZones.length === 0 ? (
              <div className="text-muted small">No weed habitats saved. Use Draw Zone to add one.</div>
            ) : (
              <div className="d-flex flex-column gap-2">
                {cecidWeedZones.map((zone) => (
                  <div className="border rounded p-2" key={`${zone.id}-${zone.label}`}>
                    <div className="d-flex gap-2 align-items-center">
                      <input
                        className="form-control form-control-sm"
                        defaultValue={zone.label}
                        aria-label={`Label for ${zone.label}`}
                        onBlur={(event) => {
                          const label = event.target.value.trim() || zone.label
                          if (label !== zone.label) onCecidZoneUpdate?.(zone.id, { label })
                        }}
                      />
                      <div style={{ width: 132, flexShrink: 0 }}>
                        <MpSelect
                          small
                          value={zone.density}
                          onChange={(density) => onCecidZoneUpdate?.(zone.id, { density })}
                          options={CECID_DENSITY_OPTIONS}
                        />
                      </div>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-success"
                        title={`Redraw ${zone.label}`}
                        onClick={() => onCecidZoneRedraw?.(zone.id)}
                      >
                        <i className="bi bi-pencil" />
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        title={`Delete ${zone.label}`}
                        onClick={() => onCecidZoneDelete?.(zone.id)}
                      >
                        <i className="bi bi-trash" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {legacyCecidEmergenceZones.length > 0 && (
              <div className="alert alert-secondary py-1 px-2 mt-2 mb-0" style={{ fontSize: '.69rem' }}>
                {legacyCecidEmergenceZones.length} legacy emergence zone{legacyCecidEmergenceZones.length === 1 ? '' : 's'} shown read-only for historical replay. They are not converted to weeds.
              </div>
            )}
            {cecidZoneSaveState === 'error' && (
              <div className="text-danger mt-2" style={{ fontSize: '.69rem' }}>{cecidZoneSaveError}</div>
            )}
          </div>
        )}

        {/* Zone tools — Stage Zone + Status Zone side by side */}
        {false && (
        <div className="map-zone-tools">
          {/* Legacy separate controls retained only for source compatibility. */}
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
              <div style={{ flexShrink: 0, width: 118 }}>
                <MpSelect
                  small
                  className="map-stage-zone-select"
                  value={stageZoneStage}
                  onChange={(val) => onStageZoneStageChange?.(val)}
                  options={stageOptions}
                />
              </div>
              <button
                type="button"
                className="btn btn-sm btn-light"
                disabled={stageZoneDraft.length === 0}
                onClick={onStageZoneUndoPoint}
                title="Remove the last point"
              >
                <i className="bi bi-arrow-counterclockwise me-1" />
                Undo Point
              </button>
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

          {/* Divider between zone buttons */}
          {!stageZoneDrawing && !statusZoneDrawing && (
            <span className="map-zone-divider" />
          )}

          {/* Status Zone */}
          <button
            type="button"
            className={`btn btn-sm ${statusZoneDrawing ? 'btn-success' : 'btn-light'}`}
            onClick={statusZoneDrawing ? onStatusZoneCancel : onStatusZoneStart}
          >
            <i className="bi bi-pencil-square me-1" />
            {statusZoneDrawing ? 'Cancel Zone' : 'Status Zone'}
          </button>
          {statusZoneDrawing && (
            <>
              <div style={{ flexShrink: 0, width: 160 }}>
                <MpSelect
                  small
                  className="map-status-zone-select"
                  value={statusZoneStatus}
                  onChange={(val) => onStatusZoneStatusChange?.(val)}
                  options={statusOptions}
                />
              </div>
              <button
                type="button"
                className="btn btn-sm btn-light"
                disabled={statusZoneDraft.length === 0}
                onClick={onStatusZoneUndoPoint}
                title="Remove the last point"
              >
                <i className="bi bi-arrow-counterclockwise me-1" />
                Undo Point
              </button>
              <button
                type="button"
                className="btn btn-sm btn-success"
                disabled={statusZoneDraft.length < 3}
                onClick={onStatusZoneFinish}
              >
                Save
              </button>
            </>
          )}

          {/* Universal Undo / Clear — shown when zones exist and not drawing */}
          {!stageZoneDrawing && !statusZoneDrawing && zoneHistory.length > 0 && (
            <>
              <span className="map-zone-divider" />
              <button
                type="button"
                className="btn btn-sm btn-light"
                onClick={onZoneUndoLast}
                title="Undo the most recent zone (stage or status)"
              >
                <i className="bi bi-arrow-counterclockwise me-1" />
                Undo Zone
              </button>
              <button type="button" className="btn btn-sm btn-light" onClick={onZoneClearAll}>
                Clear All
              </button>
            </>
          )}
        </div>
        )}

        {titleText && (
          <div className="map-animation-title">{titleText}</div>
        )}

        <div className="map-card">
          <RiskMap
            key={viewportKey}
            geojson={geojson}
            baseGeojson={baseGeojson}
            alerts={alerts}
            treeOverrides={treeOverrides}
            stageOverrides={stageOverrides}
            stageZones={stageZones}
            stageZoneDrawing={stageZoneDrawing}
            stageZoneDraft={stageZoneDraft}
            onStageZoneMapClick={onStageZoneMapClick}
            statusZones={statusZones}
            statusZoneDrawing={statusZoneDrawing}
            statusZoneDraft={statusZoneDraft}
            onStatusZoneMapClick={onStatusZoneMapClick}
            cecidWeedZones={cecidWeedZones}
            legacyCecidEmergenceZones={legacyCecidEmergenceZones}
            cecidZoneDrawing={cecidZoneDrawing}
            cecidZoneDraft={cecidZoneDraft}
            onCecidZoneMapClick={onCecidZoneMapClick}
            zoneVisibility={zoneVisibility}
            orthophotoOverlay={orthophotoOverlay}
            viewportKey={viewportKey}
            fitToOrthophoto={fitToOrthophoto}
            showGridOverlay={showGrid}
            onTreeClick={onTreeClick}
          />
        </div>

        {showLegend && (
          <div className="map-risk-legend">
            <div className="map-risk-legend-title">Map legend</div>
            <div className="map-risk-legend-columns">
              <div>
                <div className="map-risk-legend-group-title">Risk level</div>
                {RISK_LEGEND_ENTRIES.map((entry) => (
                  <div key={entry.label} className="map-risk-legend-item">
                    <div className="map-risk-legend-swatch" style={{ background: entry.color }} />
                    {entry.label}
                  </div>
                ))}
              </div>
              <div>
                <div className="map-risk-legend-group-title">Tree state</div>
                {TREE_STATE_LEGEND_ENTRIES.map((entry) => (
                  <div key={entry.label} className="map-risk-legend-item">
                    <div className="map-risk-legend-swatch is-tree-state" style={{ background: entry.color }} />
                    {entry.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <img src={COMPASS_URI} alt="Compass - True North" className="map-compass" />
      </div>
    </div>
  )
}
