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
        />
        <PlaybackCard
          frames={playbackFrames}
          currentFrameIdx={currentFrameIdx}
          onFrameSeek={onFrameSeek}
        />
        <AlertPanel
          alerts={alerts}
          loading={alertLoading}
          onRefresh={onAlertRefresh}
        />
        <DecisionSupportCard metrics={decisionMetrics} />
        <RiskLegendCard />
      </div>
    </aside>
  )
}
