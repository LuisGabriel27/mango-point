import { useEffect, useRef } from 'react'
import OrchardSwitcher from './cards/OrchardSwitcher'
import WeatherCard from './cards/WeatherCard'
import SimulationCard from './cards/SimulationCard'
import PlaybackCard from './cards/PlaybackCard'
import DecisionSupportCard from './cards/DecisionSupportCard'
import {
  DEFAULT_SIDEBAR_WORKFLOW,
  nextSidebarWorkflowId,
  sidebarWorkflowForEvent,
  SIDEBAR_WORKFLOWS,
} from '../utils/sidebarWorkspace'

export default function Sidebar({
  orchards,
  selectedOrchardId,
  onOrchardSelect,
  onOrchardRefresh,
  onOrchardUpload,
  orchardLoading,
  weather,
  manualWeather,
  weatherOverrideActive,
  weatherTimeline,
  onManualWeatherChange,
  onWeatherOverrideToggle,
  onWeatherTimelineChange,
  onWeatherRetry,
  orchardCoordinates,
  orchardGeojson,
  treeOverrides,
  treeStageOverrides,
  phenologyZones,
  cecidWeedZones,
  legacyCecidEmergenceZones,
  onPestTypeChange,
  onClearTreeStageOverrides,
  onSimulationComplete,
  simulationTemplate,
  playbackFrames,
  currentFrameIdx,
  onFrameSeek,
  decisionMetrics,
  suggestedSimParams,
  onClearSuggestedSimParams,
  activeWorkflow = DEFAULT_SIDEBAR_WORKFLOW,
  onWorkflowChange,
  collapsed = false,
  onCollapsedChange,
  mobileOpen = false,
  onMobileOpenChange,
  defaultTreeCount = 0,
}) {
  const asideRef = useRef(null)
  const closeButtonRef = useRef(null)
  const tabRefs = useRef([])

  useEffect(() => {
    if (!mobileOpen) return undefined
    const isOverlay = typeof window.matchMedia !== 'function'
      || window.matchMedia('(max-width: 991.98px)').matches
    if (!isOverlay) return undefined

    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.requestAnimationFrame(() => closeButtonRef.current?.focus())

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onMobileOpenChange?.(false)
        return
      }
      if (event.key !== 'Tab' || !asideRef.current) return
      const focusable = [...asideRef.current.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )].filter((element) => element.offsetParent !== null)
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
      previousFocus?.focus?.()
    }
  }, [mobileOpen, onMobileOpenChange])

  const selectedOrchard = orchards?.find((orchard) => orchard.orchard_id === selectedOrchardId)
  const orchardLabel = selectedOrchard?.name
    || (selectedOrchardId === 'default-orchard' ? 'Default Orchard (BPI)' : 'Select an orchard')
  const currentWeather = weather?.current
  const weatherLabel = weatherOverrideActive
    ? (weatherTimeline?.enabled ? 'Timeline weather' : 'Weather override')
    : currentWeather?.temperature_c != null
      ? `${Number(currentWeather.temperature_c).toFixed(1)}°C live`
      : 'Weather loading'

  const selectWorkflow = (workflow, { reveal = false } = {}) => {
    onWorkflowChange?.(workflow)
    if (reveal) onCollapsedChange?.(false)
  }

  const handleTabKeyDown = (event) => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const nextWorkflow = nextSidebarWorkflowId(activeWorkflow, event.key)
    const nextIndex = SIDEBAR_WORKFLOWS.findIndex(({ id }) => id === nextWorkflow)
    selectWorkflow(nextWorkflow)
    tabRefs.current[nextIndex]?.focus()
  }

  const handleSimulationComplete = (data) => {
    onSimulationComplete?.(data)
    selectWorkflow(sidebarWorkflowForEvent('simulation-success', activeWorkflow), { reveal: true })
  }

  return (
    <>
      <button
        type="button"
        className={`sidebar-backdrop${mobileOpen ? ' is-visible' : ''}`}
        aria-label="Close simulation workspace"
        onClick={() => onMobileOpenChange?.(false)}
        tabIndex={mobileOpen ? 0 : -1}
      />
      <aside
        ref={asideRef}
        className={`floating-right-sidebar${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' is-mobile-open' : ''}`}
        id="right-sidebar"
        aria-label="Simulation workspace"
      >
        <div className="sidebar-collapsed-rail" aria-label="Workspace shortcuts">
          <button
            type="button"
            className="sidebar-rail-expand"
            onClick={() => onCollapsedChange?.(false)}
            aria-label="Expand simulation workspace"
            title="Expand workspace"
          >
            <i className="bi bi-layout-sidebar-inset-reverse" />
          </button>
          {SIDEBAR_WORKFLOWS.map((workflow) => (
            <button
              key={workflow.id}
              type="button"
              className={`sidebar-rail-tab${activeWorkflow === workflow.id ? ' active' : ''}`}
              onClick={() => selectWorkflow(workflow.id, { reveal: true })}
              aria-label={`Open ${workflow.label}`}
              title={workflow.label}
            >
              <i className={`bi bi-${workflow.icon}`} />
              {workflow.id === 'results' && playbackFrames.length > 0 && <span className="sidebar-result-dot" />}
            </button>
          ))}
        </div>

        <div className="sidebar-workspace">
          <header className="sidebar-workspace-header">
            <div className="sidebar-workspace-heading">
              <span className="sidebar-workspace-eyebrow">Workspace</span>
              <strong>Simulation controls</strong>
            </div>
            <div className="sidebar-workspace-actions">
              <button
                type="button"
                className="sidebar-header-btn sidebar-desktop-collapse"
                onClick={() => onCollapsedChange?.(true)}
                aria-label="Collapse simulation workspace"
                title="Collapse workspace"
              >
                <i className="bi bi-layout-sidebar-inset" />
              </button>
              <button
                ref={closeButtonRef}
                type="button"
                className="sidebar-header-btn sidebar-mobile-close"
                onClick={() => onMobileOpenChange?.(false)}
                aria-label="Close simulation workspace"
              >
                <i className="bi bi-x-lg" />
              </button>
            </div>
          </header>

          <button
            type="button"
            className="sidebar-context-summary"
            onClick={() => selectWorkflow('setup')}
            title="Open setup"
          >
            <span><i className="bi bi-geo-alt-fill" />{orchardLabel}</span>
            <span><i className="bi bi-cloud-sun" />{weatherLabel}</span>
          </button>

          <div className="sidebar-workflow-tabs" role="tablist" aria-label="Simulation workflow">
            {SIDEBAR_WORKFLOWS.map((workflow, index) => (
              <button
                key={workflow.id}
                ref={(element) => { tabRefs.current[index] = element }}
                type="button"
                id={`sidebar-tab-${workflow.id}`}
                className={`sidebar-workflow-tab${activeWorkflow === workflow.id ? ' active' : ''}`}
                role="tab"
                aria-selected={activeWorkflow === workflow.id}
                aria-controls={`sidebar-panel-${workflow.id}`}
                tabIndex={activeWorkflow === workflow.id ? 0 : -1}
                onClick={() => selectWorkflow(workflow.id)}
                onKeyDown={handleTabKeyDown}
              >
                <i className={`bi bi-${workflow.icon}`} />
                <span>{workflow.label}</span>
                {workflow.id === 'results' && playbackFrames.length > 0 && <span className="sidebar-result-dot" />}
              </button>
            ))}
          </div>

          <div className="sidebar-workflow-panels">
            <div
              id="sidebar-panel-setup"
              className="sidebar-workflow-panel"
              role="tabpanel"
              aria-labelledby="sidebar-tab-setup"
              hidden={activeWorkflow !== 'setup'}
            >
              <OrchardSwitcher
                orchards={orchards}
                selectedId={selectedOrchardId}
                onSelect={onOrchardSelect}
                onRefresh={onOrchardRefresh}
                onUpload={onOrchardUpload}
                loading={orchardLoading}
                defaultTreeCount={defaultTreeCount}
                embedded
              />
              <WeatherCard
                weather={weather}
                manualWeather={manualWeather}
                weatherOverrideActive={weatherOverrideActive}
                weatherTimeline={weatherTimeline}
                onManualChange={onManualWeatherChange}
                onOverrideToggle={onWeatherOverrideToggle}
                onTimelineChange={onWeatherTimelineChange}
                onRetry={onWeatherRetry}
                embedded
              />
            </div>

            <div
              id="sidebar-panel-simulate"
              className="sidebar-workflow-panel"
              role="tabpanel"
              aria-labelledby="sidebar-tab-simulate"
              hidden={activeWorkflow !== 'simulate'}
            >
              <SimulationCard
                orchardGeojson={orchardGeojson}
                orchardId={selectedOrchardId}
                treeOverrides={treeOverrides}
                treeStageOverrides={treeStageOverrides}
                phenologyZones={phenologyZones}
                cecidWeedZones={cecidWeedZones}
                legacyCecidEmergenceZones={legacyCecidEmergenceZones}
                onPestTypeChange={onPestTypeChange}
                onClearTreeStageOverrides={onClearTreeStageOverrides}
                onSimulationComplete={handleSimulationComplete}
                loadedParams={simulationTemplate}
                manualWeather={manualWeather}
                weatherOverrideActive={weatherOverrideActive}
                weatherTimeline={weatherTimeline}
                orchardCoordinates={orchardCoordinates}
                suggestedParams={suggestedSimParams}
                onClearSuggested={onClearSuggestedSimParams}
                embedded
              />
            </div>

            <div
              id="sidebar-panel-results"
              className="sidebar-workflow-panel"
              role="tabpanel"
              aria-labelledby="sidebar-tab-results"
              hidden={activeWorkflow !== 'results'}
            >
              {!playbackFrames.length && !decisionMetrics && (
                <div className="sidebar-results-empty">
                  <i className="bi bi-graph-up-arrow" />
                  <strong>No simulation results yet</strong>
                  <span>Run a simulation to unlock playback and decision support.</span>
                  <button type="button" className="btn btn-success btn-sm" onClick={() => selectWorkflow('simulate')}>
                    Go to Simulate
                  </button>
                </div>
              )}
              <div hidden={!playbackFrames.length}>
                <PlaybackCard
                  frames={playbackFrames}
                  currentFrameIdx={currentFrameIdx}
                  onFrameSeek={onFrameSeek}
                  embedded
                />
              </div>
              <div hidden={!decisionMetrics}>
                <DecisionSupportCard metrics={decisionMetrics} embedded />
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}
