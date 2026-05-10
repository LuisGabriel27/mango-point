import { useState } from 'react'
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
  orchardLoading,
  weather,
  manualWeather,
  weatherOverrideActive,
  onManualWeatherChange,
  onWeatherOverrideToggle,
  orchardGeojson,
  treeOverrides,
  onSimulationComplete,
  playbackFrames,
  currentFrameIdx,
  onFrameSeek,
  alerts,
  alertLoading,
  onAlertRefresh,
  decisionMetrics,
}) {
  const [suggestedSimParams, setSuggestedSimParams] = useState(null)

  return (
    <aside className="floating-right-sidebar" id="right-sidebar">
      <div className="sidebar-scroll-frame">
        <OrchardSwitcher
          orchards={orchards}
          selectedId={selectedOrchardId}
          onSelect={onOrchardSelect}
          onRefresh={onOrchardRefresh}
          loading={orchardLoading}
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
          onSimulationComplete={onSimulationComplete}
          manualWeather={manualWeather}
          weatherOverrideActive={weatherOverrideActive}
          suggestedParams={suggestedSimParams}
          onClearSuggested={() => setSuggestedSimParams(null)}
        />
        <PlaybackCard
          frames={playbackFrames}
          currentFrameIdx={currentFrameIdx}
          onFrameSeek={onFrameSeek}
          defaultOpen={false}
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
