import { useEffect, useMemo, useState } from 'react'
import RiskMap from '../RiskMap'
import MpSelect from '../MpSelect'
import ZoneManager from '../ZoneManager'
import ZoneClearConfirmationModal from '../ZoneClearConfirmationModal'
import { buildZoneInventory, ZONE_TYPE_OPTIONS, zoneInventoryCounts } from '../../utils/zoneInventory'
import { zoneClearSummary } from '../../utils/zoneManagerModel'

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

const CECID_LIKELIHOOD_LEGEND_ENTRIES = [
  { label: '75–100% of runs', color: '#b91c1c' },
  { label: '50–74% of runs', color: '#ef4444' },
  { label: '25–49% of runs', color: '#f59e0b' },
  { label: '10–24% of runs', color: '#facc15' },
  { label: '0–9% of runs', color: '#22c55e' },
]

const CECID_TREE_STATE_LEGEND_ENTRIES = [
  { label: 'Fruitlet eligible', color: '#22c55e' },
  { label: 'Fruit infestation established', color: '#ef4444' },
  { label: 'Not eligible stage', color: '#6b7280' },
  { label: 'Soil source (S)', color: '#78350f' },
  { label: 'Bagged', color: '#3b82f6' },
]

const DRAW_MODE_OPTIONS = [
  { value: 'polygon', label: 'Point polygon' },
  { value: 'lasso', label: 'Freehand lasso' },
]

const EDIT_SCOPE_OPTIONS = [
  { value: 'scenario', label: 'Scenario only' },
  { value: 'orchard', label: 'Apply to orchard' },
]

const CECID_DENSITY_OPTIONS = [
  { value: 'sparse', label: 'Sparse (0.60×)' },
  { value: 'moderate', label: 'Moderate (0.80×)' },
  { value: 'dense', label: 'Dense (1.00×)' },
]

export default function LiveMapTab({
  geojson,
  baseGeojson,
  treePoints = null,
  alerts = [],
  treeOverrides = {},
  stageOverrides = {},
  stageZones = [],
  stageZoneDrawing = false,
  stageZoneStage = 'mature',
  stageZoneDraft = [],
  stageZoneSelectedCount = 0,
  stageOptions = [],
  onStageZoneStageChange,
  onStageZoneStart,
  onStageZoneCancel,
  onStageZoneFinish,
  onStageZoneUndoPoint,
  onStageZoneMapClick,
  onStageZoneDraftChange,
  onStageZoneDelete,
  onStageZoneClear,
  statusZones = [],
  statusZoneDrawing = false,
  statusZoneStatus = 'infected',
  statusZoneDraft = [],
  statusZoneSelectedCount = 0,
  statusOptions = [],
  onStatusZoneStatusChange,
  onStatusZoneStart,
  onStatusZoneCancel,
  onStatusZoneFinish,
  onStatusZoneUndoPoint,
  onStatusZoneMapClick,
  onStatusZoneDraftChange,
  onStatusZoneDelete,
  onStatusZoneClear,
  treeEditScope = 'scenario',
  treeEditSaveState = 'idle',
  treeEditSaveError = '',
  onTreeEditScopeChange,
  managementZones = [],
  managementZoneDrawing = false,
  managementZoneLabel = 'Zone 1',
  managementZoneDraft = [],
  managementZoneSelectedCount = 0,
  managementZoneSaveState = 'idle',
  managementZoneSaveError = '',
  onManagementZoneLabelChange,
  onManagementZoneStart,
  onManagementZoneCancel,
  onManagementZoneFinish,
  onManagementZoneUndoPoint,
  onManagementZoneMapClick,
  onManagementZoneDraftChange,
  onManagementZoneUpdate,
  onManagementZoneRedraw,
  onManagementZoneDelete,
  onManagementZoneClear,
  onManagementZoneRetry,
  cecidWeedZones = [],
  legacyCecidEmergenceZones = [],
  cecidZoneDrawing = false,
  cecidZoneDensity = 'moderate',
  cecidZoneLabel = 'Weed habitat',
  cecidZoneDraft = [],
  cecidZoneSelectedCount = 0,
  cecidZoneSaveState = 'idle',
  cecidZoneSaveError = '',
  onCecidZoneDensityChange,
  onCecidZoneLabelChange,
  onCecidZoneStart,
  onCecidZoneCancel,
  onCecidZoneFinish,
  onCecidZoneUndoPoint,
  onCecidZoneMapClick,
  onCecidZoneDraftChange,
  onCecidZoneUpdate,
  onCecidZoneRedraw,
  onCecidZoneDelete,
  onCecidZoneClear,
  onCecidZoneRetry,
  selectedPestType = 'fruitfly',
  resultPestType = selectedPestType,
  zoneHistory = [],
  onZoneUndoLast,
  onZoneClearAll,
  orchardName,
  orthophotoOverlay = null,
  viewportKey = 'default',
  fitToOrthophoto = true,
  currentFrame,
  cecidMapMode = 'representative',
  cecidEnsembleRuns = 0,
  onCecidMapModeChange,
  onTreeClick,
  onPrintReport,
}) {
  const [showGrid, setShowGrid] = useState(false)
  const [showZoneManager, setShowZoneManager] = useState(false)
  const [zoneEditorOpen, setZoneEditorOpen] = useState(false)
  const [layersOpen, setLayersOpen] = useState(false)
  const [legendOpen, setLegendOpen] = useState(false)
  const [clearAllModalOpen, setClearAllModalOpen] = useState(false)
  const [zoneListFilter, setZoneListFilter] = useState('all')
  const [zoneEditorType, setZoneEditorType] = useState('stage')
  const [drawMode, setDrawMode] = useState('polygon')
  const [zoneVisibility, setZoneVisibility] = useState({
    stage: true,
    status: true,
    management: true,
    cecid: selectedPestType === 'cecid',
  })
  const zoneEntries = useMemo(() => buildZoneInventory({
    stageZones, statusZones, managementZones, cecidWeedZones,
    legacyCecidEmergenceZones, treePoints, stageOptions, statusOptions,
  }), [stageZones, statusZones, managementZones, cecidWeedZones,
    legacyCecidEmergenceZones, treePoints, stageOptions, statusOptions])
  const zoneCounts = zoneInventoryCounts(zoneEntries)
  const clearAllSummary = useMemo(() => zoneClearSummary(zoneEntries), [zoneEntries])

  useEffect(() => {
    setZoneVisibility((current) => ({
      ...current,
      cecid: selectedPestType === 'cecid',
    }))
  }, [selectedPestType])

  const drawingByType = {
    stage: stageZoneDrawing,
    status: statusZoneDrawing,
    management: managementZoneDrawing,
    cecid: cecidZoneDrawing,
  }
  const draftByType = {
    stage: stageZoneDraft,
    status: statusZoneDraft,
    management: managementZoneDraft,
    cecid: cecidZoneDraft,
  }
  const selectedCountByType = {
    stage: stageZoneSelectedCount,
    status: statusZoneSelectedCount,
    management: managementZoneSelectedCount,
    cecid: cecidZoneSelectedCount,
  }
  const activeDrawing = Boolean(drawingByType[zoneEditorType])
  const activeDraft = draftByType[zoneEditorType] || []
  const cancelAllDrawings = () => {
    onStageZoneCancel?.()
    onStatusZoneCancel?.()
    onManagementZoneCancel?.()
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
    setLayersOpen(false)
    setShowZoneManager(false)
    if (zoneEditorType === 'stage') onStageZoneStart?.()
    else if (zoneEditorType === 'status') onStatusZoneStart?.()
    else if (zoneEditorType === 'management') onManagementZoneStart?.()
    else onCecidZoneStart?.()
  }
  const handleZoneUndoPoint = () => {
    if (zoneEditorType === 'stage') onStageZoneUndoPoint?.()
    else if (zoneEditorType === 'status') onStatusZoneUndoPoint?.()
    else if (zoneEditorType === 'management') onManagementZoneUndoPoint?.()
    else onCecidZoneUndoPoint?.()
  }
  const handleZoneFinish = () => {
    if (zoneEditorType === 'stage') onStageZoneFinish?.()
    else if (zoneEditorType === 'status') onStatusZoneFinish?.()
    else if (zoneEditorType === 'management') onManagementZoneFinish?.()
    else onCecidZoneFinish?.()
  }
  const closeZoneEditor = () => {
    cancelAllDrawings()
    setZoneEditorOpen(false)
  }
  const openZoneManager = () => {
    cancelAllDrawings()
    setZoneEditorOpen(false)
    setLayersOpen(false)
    setZoneListFilter('all')
    setShowZoneManager(true)
  }

  const titleText = resultPestType === 'cecid'
    && cecidMapMode === 'likelihood'
    && cecidEnsembleRuns > 1
    ? `Cecid infestation likelihood — ${cecidEnsembleRuns} runs`
    : currentFrame != null
      ? `Hour ${currentFrame.hour} — Representative realization`
      : (orchardName ?? null)

  const showLegend = geojson != null
  const riskLegendEntries = resultPestType === 'cecid' && cecidMapMode === 'likelihood'
    ? CECID_LIKELIHOOD_LEGEND_ENTRIES
    : RISK_LEGEND_ENTRIES
  const treeStateLegendEntries = resultPestType === 'cecid'
    ? CECID_TREE_STATE_LEGEND_ENTRIES
    : TREE_STATE_LEGEND_ENTRIES

  return (
    <div className="operations-map-panel">
      <div className="operations-map-stage" style={{ position: 'relative' }}>
        <div className="map-command-bar" role="toolbar" aria-label="Map controls">
          {onPrintReport && (
            <button type="button" className="map-command-btn" onClick={onPrintReport} title="Print or export this simulation result">
              <i className="bi bi-printer" /><span>Report</span>
            </button>
          )}
          <button
            type="button"
            className={`map-command-btn${showGrid ? ' active' : ''}`}
            aria-pressed={showGrid}
            onClick={() => setShowGrid((current) => !current)}
            title="Show or hide the orchard grid"
          >
            <i className="bi bi-grid-3x3-gap" /><span>Grid</span>
          </button>
          <button
            type="button"
            className={`map-command-btn${zoneEditorOpen ? ' active' : ''}`}
            aria-expanded={zoneEditorOpen}
            aria-controls="map-zone-editor-panel"
            onClick={() => {
              setLayersOpen(false)
              setShowZoneManager(false)
              if (zoneEditorOpen) closeZoneEditor()
              else setZoneEditorOpen(true)
            }}
          >
            <i className="bi bi-bounding-box-circles" /><span>Zones</span>
            {zoneEntries.length > 0 && <span className="map-command-count">{zoneEntries.length}</span>}
          </button>
          <button
            type="button"
            className={`map-command-btn${layersOpen ? ' active' : ''}`}
            aria-expanded={layersOpen}
            aria-controls="map-layers-popover"
            disabled={activeDrawing}
            onClick={() => {
              setShowZoneManager(false)
              if (zoneEditorOpen) closeZoneEditor()
              setLayersOpen((current) => !current)
            }}
          >
            <i className="bi bi-layers" /><span>Layers</span>
          </button>

          {resultPestType === 'cecid' && cecidEnsembleRuns > 1 && (
            <div className="map-result-mode" role="group" aria-label="Cecid result map mode">
              <button
                type="button"
                className={`btn btn-sm ${cecidMapMode === 'likelihood' ? 'btn-success' : 'btn-light'}`}
                onClick={() => onCecidMapModeChange?.('likelihood')}
                title="How often each tree established infestation across repeated runs"
              >
                Likelihood
              </button>
              <button
                type="button"
                className={`btn btn-sm ${cecidMapMode === 'representative' ? 'btn-success' : 'btn-light'}`}
                onClick={() => onCecidMapModeChange?.('representative')}
                title="The exact seeded run used by playback"
              >
                One run
              </button>
            </div>
          )}
        </div>

        {layersOpen && !activeDrawing && (
          <section id="map-layers-popover" className="map-layers-popover" aria-label="Zone layer visibility">
            <header>
              <div><strong>Map layers</strong><small>Choose which boundaries appear.</small></div>
              <button type="button" className="btn btn-sm btn-light" aria-label="Close map layers" onClick={() => setLayersOpen(false)}>
                <i className="bi bi-x-lg" />
              </button>
            </header>
            <div className="map-layer-list">
              {ZONE_TYPE_OPTIONS.map((option) => {
                const label = option.value === 'cecid' ? 'Weed habitats'
                  : option.value === 'management' ? 'Management areas'
                    : `${option.label} zones`
                return (
                  <button
                    key={option.value}
                    type="button"
                    className="map-layer-row"
                    role="switch"
                    aria-checked={zoneVisibility[option.value]}
                    onClick={() => setZoneVisibility((current) => ({
                      ...current,
                      [option.value]: !current[option.value],
                    }))}
                  >
                    <span><i className={`bi ${zoneVisibility[option.value] ? 'bi-eye' : 'bi-eye-slash'}`} />{label}</span>
                    <span className="map-layer-meta">{zoneCounts[option.value]} <span className={`map-layer-switch${zoneVisibility[option.value] ? ' active' : ''}`} /></span>
                  </button>
                )
              })}
            </div>
          </section>
        )}

        {zoneEditorOpen && (
          <section
            id="map-zone-editor-panel"
            className={`map-zone-editor-panel${activeDrawing ? ' is-drawing' : ''}`}
            aria-label={activeDrawing ? 'Active zone drawing controls' : 'Zone editor'}
          >
            <header className="map-zone-editor-panel-header">
              <div>
                <strong><i className="bi bi-bounding-box-circles" />Zone editor</strong>
                <small>{activeDrawing ? 'Draw the boundary on the map, then apply it.' : 'Choose a zone type and its settings.'}</small>
              </div>
              <div className="map-zone-editor-header-actions">
                <button type="button" className="btn btn-sm btn-light" onClick={openZoneManager}>
                  <i className="bi bi-list-ul me-1" />Manage<span className="d-none d-sm-inline"> zones</span>
                </button>
                {!activeDrawing && zoneHistory.length > 0 && (
                  <button type="button" className="btn btn-sm btn-light" onClick={onZoneUndoLast} title="Undo the most recently created zone">
                    <i className="bi bi-arrow-counterclockwise me-1" />Undo
                  </button>
                )}
                <button type="button" className="btn btn-sm btn-light" aria-label="Close zone editor" onClick={closeZoneEditor}>
                  <i className="bi bi-x-lg" />
                </button>
              </div>
            </header>

            <div className="map-zone-editor-fields">
              <label className="map-zone-editor-field">
                <span>Zone type</span>
                <MpSelect small value={zoneEditorType} onChange={handleZoneTypeChange} options={ZONE_TYPE_OPTIONS} />
              </label>
              {zoneEditorType === 'stage' && (
                <label className="map-zone-editor-field">
                  <span>Tree stage</span>
                  <MpSelect small value={stageZoneStage} onChange={onStageZoneStageChange} options={stageOptions} />
                </label>
              )}
              {zoneEditorType === 'status' && (
                <label className="map-zone-editor-field">
                  <span>Tree status</span>
                  <MpSelect small value={statusZoneStatus} onChange={onStatusZoneStatusChange} options={statusOptions} />
                </label>
              )}
              {(zoneEditorType === 'stage' || zoneEditorType === 'status') && (
                <label className="map-zone-editor-field">
                  <span>Save behavior</span>
                  <MpSelect small value={treeEditScope} onChange={onTreeEditScopeChange} options={EDIT_SCOPE_OPTIONS} />
                </label>
              )}
              {zoneEditorType === 'management' && (
                <label className="map-zone-editor-field">
                  <span>Area name</span>
                  <input className="form-control form-control-sm" value={managementZoneLabel} onChange={(event) => onManagementZoneLabelChange?.(event.target.value)} placeholder="Zone label" />
                </label>
              )}
              {zoneEditorType === 'cecid' && (
                <>
                  <label className="map-zone-editor-field">
                    <span>Habitat name</span>
                    <input className="form-control form-control-sm" value={cecidZoneLabel} onChange={(event) => onCecidZoneLabelChange?.(event.target.value)} placeholder="Weed habitat label" />
                  </label>
                  <label className="map-zone-editor-field">
                    <span>Density</span>
                    <MpSelect small value={cecidZoneDensity} onChange={onCecidZoneDensityChange} options={CECID_DENSITY_OPTIONS} />
                  </label>
                </>
              )}
              <label className="map-zone-editor-field">
                <span>Drawing method</span>
                <MpSelect small value={drawMode} onChange={setDrawMode} options={DRAW_MODE_OPTIONS} />
              </label>
            </div>

            {zoneEditorType === 'cecid' && (
              <p className="map-zone-editor-note"><i className="bi bi-info-circle" />Weed habitats represent a research shelter/relay assumption and do not create flies.</p>
            )}

            <footer className="map-zone-editor-footer">
              <div className="map-zone-editor-status" aria-live="polite">
                {activeDrawing ? (
                  <><strong>{selectedCountByType[zoneEditorType] || 0}</strong> trees selected · {drawMode === 'lasso' ? 'Drag around the area' : 'Add at least 3 boundary points'}</>
                ) : zoneEntries.length > 0 ? `${zoneEntries.length} saved or scenario zone${zoneEntries.length === 1 ? '' : 's'}` : 'No zones created yet'}
              </div>
              <div className="map-zone-editor-actions">
                {!activeDrawing ? (
                  <button type="button" className="btn btn-sm btn-success" onClick={handleZoneDrawToggle}>
                    <i className="bi bi-pencil-square me-1" />Start drawing
                  </button>
                ) : (
                  <>
                    <button type="button" className="btn btn-sm btn-light" disabled={activeDraft.length === 0} onClick={handleZoneUndoPoint}>
                      <i className="bi bi-arrow-counterclockwise me-1" />Undo point
                    </button>
                    <button type="button" className="btn btn-sm btn-outline-secondary" onClick={handleZoneDrawToggle}>Cancel</button>
                    <button
                      type="button"
                      className="btn btn-sm btn-success"
                      disabled={activeDraft.length < 3 || (zoneEditorType !== 'cecid' && !selectedCountByType[zoneEditorType])}
                      onClick={handleZoneFinish}
                    >
                      {zoneEditorType === 'stage' || zoneEditorType === 'status' ? 'Apply zone' : 'Save zone'}
                    </button>
                  </>
                )}
              </div>
            </footer>

            {!activeDrawing && (zoneEditorType === 'stage' || zoneEditorType === 'status') && treeEditSaveState !== 'idle' && (
              <div className={`map-zone-save-message ${treeEditSaveState}`} role="status">
                {treeEditSaveState === 'saving' ? 'Saving orchard changes…' : treeEditSaveState === 'saved' ? 'Orchard changes saved.' : treeEditSaveError || 'Tree changes could not be saved.'}
              </div>
            )}
            {!activeDrawing && zoneEditorType === 'management' && managementZoneSaveState !== 'idle' && (
              <div className={`map-zone-save-message ${managementZoneSaveState}`} role="status">
                {managementZoneSaveState === 'saving' ? 'Saving management area…' : managementZoneSaveState === 'saved' ? 'Management area saved.' : managementZoneSaveError || 'Management area could not be saved.'}
                {managementZoneSaveState === 'error' && <button type="button" className="btn btn-sm btn-warning ms-2" onClick={onManagementZoneRetry}>Retry</button>}
              </div>
            )}
            {!activeDrawing && zoneEditorType === 'cecid' && cecidZoneSaveState !== 'idle' && (
              <div className={`map-zone-save-message ${cecidZoneSaveState}`} role="status">
                {cecidZoneSaveState === 'saving' ? 'Saving weed habitat…' : cecidZoneSaveState === 'saved' ? 'Weed habitat saved.' : cecidZoneSaveError || 'Weed habitat could not be saved.'}
                {cecidZoneSaveState === 'error' && <button type="button" className="btn btn-sm btn-warning ms-2" onClick={onCecidZoneRetry}>Retry</button>}
              </div>
            )}
          </section>
        )}

        {false && (
        <div className="map-top-controls" role="toolbar" aria-label="Legacy map controls">
        {onPrintReport && (
          <button type="button" className="btn btn-light btn-sm map-overlay-btn" onClick={onPrintReport}>
            <i className="bi bi-printer me-1" />Print report
          </button>
        )}
        <button
          type="button"
          className="btn btn-light btn-sm map-overlay-btn"
          onClick={() => setShowGrid((g) => !g)}
        >
          <i className="bi bi-grid-3x3-gap me-1" />
          {showGrid ? 'Hide Grid' : 'Show Grid'}
        </button>

        {resultPestType === 'cecid' && cecidEnsembleRuns > 1 && (
          <div className="map-result-mode" role="group" aria-label="Cecid result map mode">
            <button
              type="button"
              className={`btn btn-sm ${cecidMapMode === 'likelihood' ? 'btn-success' : 'btn-light'}`}
              onClick={() => onCecidMapModeChange?.('likelihood')}
              title="How often each tree established infestation across repeated runs"
            >
              Likelihood
            </button>
            <button
              type="button"
              className={`btn btn-sm ${cecidMapMode === 'representative' ? 'btn-success' : 'btn-light'}`}
              onClick={() => onCecidMapModeChange?.('representative')}
              title="The exact seeded run used by playback"
            >
              One run
            </button>
          </div>
        )}

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
              <div style={{ flexShrink: 0, width: 126 }}>
                <MpSelect small value={drawMode} onChange={setDrawMode} options={DRAW_MODE_OPTIONS} />
              </div>
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
              {(zoneEditorType === 'stage' || zoneEditorType === 'status') && (
                <div style={{ flexShrink: 0, width: 132 }}>
                  <MpSelect
                    small
                    value={treeEditScope}
                    onChange={onTreeEditScopeChange}
                    options={EDIT_SCOPE_OPTIONS}
                  />
                </div>
              )}
              {zoneEditorType === 'management' && (
                <input
                  className="form-control form-control-sm map-cecid-zone-label"
                  value={managementZoneLabel}
                  aria-label="Management zone label"
                  onChange={(event) => onManagementZoneLabelChange?.(event.target.value)}
                  placeholder="Zone label"
                />
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
              <span className="badge text-bg-light map-zone-selection-count">
                {selectedCountByType[zoneEditorType] || 0} tree{selectedCountByType[zoneEditorType] === 1 ? '' : 's'} selected
              </span>
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
                disabled={activeDraft.length < 3 || (zoneEditorType !== 'cecid' && !selectedCountByType[zoneEditorType])}
                onClick={handleZoneFinish}
              >
                {zoneEditorType === 'stage' || zoneEditorType === 'status' ? 'Apply' : 'Save'}
              </button>
              <span className="map-zone-draw-hint">
                {drawMode === 'lasso' ? 'Hold and drag around trees' : 'Click 3+ boundary points'}
              </span>
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
                  aria-pressed={zoneVisibility[option.value]}
                  onClick={() => setZoneVisibility((current) => ({
                    ...current,
                    [option.value]: !current[option.value],
                  }))}
                  title={`Toggle ${option.label} zones`}
                >
                  <i className={`bi ${zoneVisibility[option.value] ? 'bi-eye' : 'bi-eye-slash'} me-1`} />
                  {option.value === 'cecid' ? 'Weeds' : option.value === 'management' ? 'Areas' : option.label}
                  {' '}({zoneCounts[option.value]})
                </button>
              ))}
              <button
                type="button"
                className={`btn btn-sm ${showZoneManager ? 'btn-success' : 'btn-light'}`}
                aria-expanded={showZoneManager}
                aria-controls="map-zone-manager"
                onClick={() => {
                  if (!showZoneManager) setZoneListFilter('all')
                  setShowZoneManager((current) => !current)
                }}
              >
                <i className="bi bi-list-ul me-1" />
                {zoneEntries.length} zone{zoneEntries.length === 1 ? '' : 's'}
              </button>
            </>
          )}

          {!activeDrawing && (zoneEditorType === 'stage' || zoneEditorType === 'status') && treeEditSaveState !== 'idle' && (
            <span
              className={`badge ${treeEditSaveState === 'error' ? 'text-bg-danger' : treeEditSaveState === 'saved' ? 'text-bg-success' : 'text-bg-light text-dark'}`}
              title={treeEditSaveError || 'Selected-tree persistence status'}
            >
              {treeEditSaveState === 'saving' && <span className="spinner-border spinner-border-sm me-1" />}
              {treeEditSaveState === 'saving' ? 'Saving trees' : treeEditSaveState === 'saved' ? 'Trees saved' : 'Tree save error'}
            </span>
          )}

          {!activeDrawing && zoneEditorType === 'management' && managementZoneSaveState !== 'idle' && (
            <span
              className={`badge ${managementZoneSaveState === 'error' ? 'text-bg-danger' : managementZoneSaveState === 'saved' ? 'text-bg-success' : 'text-bg-light text-dark'}`}
              title={managementZoneSaveError || 'Management-zone persistence status'}
            >
              {managementZoneSaveState === 'saving' && <span className="spinner-border spinner-border-sm me-1" />}
              {managementZoneSaveState === 'saving' ? 'Saving' : managementZoneSaveState === 'saved' ? 'Saved' : 'Save error'}
            </span>
          )}
          {!activeDrawing && zoneEditorType === 'management' && managementZoneSaveState === 'error' && (
            <button type="button" className="btn btn-sm btn-warning" onClick={onManagementZoneRetry}>Retry</button>
          )}

          {!activeDrawing && zoneEditorType === 'cecid' && cecidZoneSaveState !== 'idle' && (
            <span
              className={`badge ${cecidZoneSaveState === 'error' ? 'text-bg-danger' : cecidZoneSaveState === 'saved' ? 'text-bg-success' : 'text-bg-light text-dark'}`}
              title={cecidZoneSaveError || 'Weed habitat persistence status'}
            >
              {cecidZoneSaveState === 'saving' && <span className="spinner-border spinner-border-sm me-1" />}
              {cecidZoneSaveState === 'saving' ? 'Saving' : cecidZoneSaveState === 'saved' ? 'Saved' : 'Save error'}
            </span>
          )}
          {!activeDrawing && zoneEditorType === 'cecid' && cecidZoneSaveState === 'error' && (
            <button type="button" className="btn btn-sm btn-warning" onClick={onCecidZoneRetry}>
              Retry
            </button>
          )}

          {!activeDrawing && zoneEntries.length > 0 && (
            <>
              <span className="map-zone-divider" />
              {zoneHistory.length > 0 && (
                <button type="button" className="btn btn-sm btn-light" onClick={onZoneUndoLast}>
                  <i className="bi bi-arrow-counterclockwise me-1" />
                  Undo Zone
                </button>
              )}
              <button type="button" className="btn btn-sm btn-light" onClick={onZoneClearAll}>
                Clear All
              </button>
            </>
          )}
        </div>
        </div>
        )}

        {showZoneManager && !activeDrawing && (
          <ZoneManager
            entries={zoneEntries}
            filter={zoneListFilter}
            onFilterChange={setZoneListFilter}
            zoneVisibility={zoneVisibility}
            densityOptions={CECID_DENSITY_OPTIONS}
            onClearAll={() => setClearAllModalOpen(true)}
            onClose={() => setShowZoneManager(false)}
            stageActions={{
              onDelete: onStageZoneDelete,
              onClear: onStageZoneClear,
            }}
            statusActions={{
              onDelete: onStatusZoneDelete,
              onClear: onStatusZoneClear,
            }}
            managementActions={{
              onUpdate: onManagementZoneUpdate,
              onRedraw: (zoneId) => {
                handleZoneTypeChange('management')
                setShowZoneManager(false)
                setZoneEditorOpen(true)
                onManagementZoneRedraw?.(zoneId)
              },
              onDelete: onManagementZoneDelete,
              onClear: onManagementZoneClear,
              onRetry: onManagementZoneRetry,
              error: managementZoneSaveState === 'error' ? managementZoneSaveError : '',
            }}
            weedActions={{
              onUpdate: onCecidZoneUpdate,
              onRedraw: (zoneId) => {
                handleZoneTypeChange('cecid')
                setShowZoneManager(false)
                setZoneEditorOpen(true)
                onCecidZoneRedraw?.(zoneId)
              },
              onDelete: onCecidZoneDelete,
              onClear: onCecidZoneClear,
              onRetry: onCecidZoneRetry,
              error: cecidZoneSaveState === 'error' ? cecidZoneSaveError : '',
            }}
          />
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
            onStageZoneDraftChange={onStageZoneDraftChange}
            statusZones={statusZones}
            statusZoneDrawing={statusZoneDrawing}
            statusZoneDraft={statusZoneDraft}
            onStatusZoneMapClick={onStatusZoneMapClick}
            onStatusZoneDraftChange={onStatusZoneDraftChange}
            managementZones={managementZones}
            managementZoneDrawing={managementZoneDrawing}
            managementZoneDraft={managementZoneDraft}
            onManagementZoneMapClick={onManagementZoneMapClick}
            onManagementZoneDraftChange={onManagementZoneDraftChange}
            cecidWeedZones={cecidWeedZones}
            legacyCecidEmergenceZones={legacyCecidEmergenceZones}
            cecidZoneDrawing={cecidZoneDrawing}
            cecidZoneDraft={cecidZoneDraft}
            onCecidZoneMapClick={onCecidZoneMapClick}
            onCecidZoneDraftChange={onCecidZoneDraftChange}
            zoneDrawMode={drawMode}
            zoneVisibility={zoneVisibility}
            orthophotoOverlay={orthophotoOverlay}
            viewportKey={viewportKey}
            fitToOrthophoto={fitToOrthophoto}
            showGridOverlay={showGrid}
            pestType={resultPestType}
            cecidMapMode={cecidMapMode}
            onTreeClick={onTreeClick}
          />
        </div>

        {showLegend && (
          <section className={`map-risk-legend${legendOpen ? ' is-open' : ' is-collapsed'}`} aria-label="Map legend">
            <button
              type="button"
              className="map-legend-toggle"
              aria-expanded={legendOpen}
              onClick={() => setLegendOpen((current) => !current)}
            >
              <span><i className="bi bi-palette" />Legend</span>
              {!legendOpen && (
                <span className="map-legend-preview" aria-hidden="true">
                  {riskLegendEntries.map((entry) => (
                    <span key={entry.label} style={{ background: entry.color }} />
                  ))}
                </span>
              )}
              <i className={`bi bi-chevron-${legendOpen ? 'down' : 'up'}`} />
            </button>
            {legendOpen && (
              <div className="map-risk-legend-content">
                <div className="map-risk-legend-columns">
                  <div>
                    <div className="map-risk-legend-group-title">
                      {resultPestType === 'cecid' && cecidMapMode === 'likelihood'
                        ? 'Across runs'
                        : 'Risk level'}
                    </div>
                    {riskLegendEntries.map((entry) => (
                      <div key={entry.label} className="map-risk-legend-item">
                        <div className="map-risk-legend-swatch" style={{ background: entry.color }} />
                        {entry.label}
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="map-risk-legend-group-title">Tree state</div>
                    {treeStateLegendEntries.map((entry) => (
                      <div key={entry.label} className="map-risk-legend-item">
                        <div className="map-risk-legend-swatch is-tree-state" style={{ background: entry.color }} />
                        {entry.label}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        <img src={COMPASS_URI} alt="Compass - True North" className="map-compass" />

        {clearAllModalOpen && (
          <ZoneClearConfirmationModal
            zoneCount={clearAllSummary.total}
            persistentCount={clearAllSummary.persistent}
            scenarioCount={clearAllSummary.scenario}
            onConfirm={async () => {
              await onZoneClearAll?.()
              setShowZoneManager(false)
              setZoneEditorOpen(false)
            }}
            onClose={() => setClearAllModalOpen(false)}
          />
        )}
      </div>
    </div>
  )
}
