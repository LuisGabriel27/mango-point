import { useState, useEffect, useRef } from 'react'
import OrchardSwitcher from './cards/OrchardSwitcher'
import WeatherCard from './cards/WeatherCard'
import SimulationCard from './cards/SimulationCard'
import PlaybackCard from './cards/PlaybackCard'
import AlertPanel from './cards/AlertPanel'
import DecisionSupportCard from './cards/DecisionSupportCard'
import RiskLegendCard from './cards/RiskLegendCard'

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
  onManualWeatherChange,
  onWeatherOverrideToggle,
  orchardGeojson,
  treeOverrides,
  treeStageOverrides,
  phenologyZones,
  onClearTreeStageOverrides,
  onSimulationComplete,
  simulationTemplate,
  playbackFrames,
  currentFrameIdx,
  onFrameSeek,
  alerts,
  alertLoading,
  onAlertRefresh,
  decisionMetrics,
  defaultTreeCount = 0,
}) {
  const [suggestedSimParams, setSuggestedSimParams] = useState(null)
  const [playbackAutoOpen, setPlaybackAutoOpen] = useState(0)
  const prevFramesLen = useRef(0)

  useEffect(() => {
    if (prevFramesLen.current === 0 && playbackFrames.length > 0) {
      setPlaybackAutoOpen((n) => n + 1)
    }
    prevFramesLen.current = playbackFrames.length
  }, [playbackFrames.length])

  return (
    <aside className="floating-right-sidebar" id="right-sidebar">
      <div className="sidebar-scroll-frame">
        <OrchardSwitcher
          orchards={orchards}
          selectedId={selectedOrchardId}
          onSelect={onOrchardSelect}
          onRefresh={onOrchardRefresh}
          onUpload={onOrchardUpload}
          loading={orchardLoading}
          defaultTreeCount={defaultTreeCount}
        />
        <WeatherCard
          weather={weather}
          manualWeather={manualWeather}
          weatherOverrideActive={weatherOverrideActive}
          onManualChange={onManualWeatherChange}
          onOverrideToggle={onWeatherOverrideToggle}
        />
        <SimulationCard
          orchardGeojson={orchardGeojson}
          orchardId={selectedOrchardId}
          treeOverrides={treeOverrides}
          treeStageOverrides={treeStageOverrides}
          phenologyZones={phenologyZones}
          onClearTreeStageOverrides={onClearTreeStageOverrides}
          onSimulationComplete={onSimulationComplete}
          loadedParams={simulationTemplate}
          manualWeather={manualWeather}
          weatherOverrideActive={weatherOverrideActive}
          suggestedParams={suggestedSimParams}
          onClearSuggested={() => setSuggestedSimParams(null)}
        />
        <PlaybackCard
          frames={playbackFrames}
          currentFrameIdx={currentFrameIdx}
          onFrameSeek={onFrameSeek}
          autoOpenSignal={playbackAutoOpen}
        />
        <AlertPanel
          alerts={alerts}
          loading={alertLoading}
          onRefresh={onAlertRefresh}
          onApplySuggested={setSuggestedSimParams}
        />
        <DecisionSupportCard metrics={decisionMetrics} defaultOpen={false} />
        <RiskLegendCard defaultOpen={false} />
      </div>
    </aside>
  )
}
