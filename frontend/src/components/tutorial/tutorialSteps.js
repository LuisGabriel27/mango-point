export const TUTORIAL_VERSION = 'beginner-v3-settings-v17'
export const tourTarget = (id) => `[data-tour="${id}"]`

export function tutorialPlacement(step, compactViewport) {
  if (!compactViewport) return step.placement
  return step.id === 'notifications' ? 'bottom' : 'center'
}

export function tutorialPreferenceKey(user) {
  const id = user?.user_id ?? user?.id ?? user?.username
  return id == null ? null : `mangopoint:tutorial:${TUTORIAL_VERSION}:${encodeURIComponent(id)}`
}

export function readTutorialPreference(key) {
  try { return key ? localStorage.getItem(key) === 'seen' : false } catch { return false }
}

export function rememberTutorial(key) {
  try { if (key) localStorage.setItem(key, 'seen') } catch { /* Manual replay remains available. */ }
}

function phaseFor(id, view) {
  if (view.workspace) return view.workspace
  if (view.tab === 'history') return 'history'
  if (view.navbarPanel) return 'settings'
  if (['legend', 'map-mode', 'report'].includes(id)) return 'results'
  return 'explore'
}

// Tour hooks change only the visible tab/panel. They never click application
// controls, change form values, call an API, create a result, or save a record.
export function buildTutorialSteps({ guide = 'workflow', customWeather = false, hasResult = false,
  hasPlayback = false, hasRepeatedRuns = false, isAdmin = false } = {}) {
  const steps = []
  const add = (id, title, content, tip, view = {}, target = id) => {
    const { placement, ...presentationView } = view
    steps.push({
      id,
      title,
      content,
      target: tourTarget(target),
      data: {
        view: { tab: 'live-map', ...presentationView },
        tip,
        phase: phaseFor(id, presentationView),
      },
      placement: placement ?? (presentationView.workspace ? 'left' : 'bottom'),
    })
  }
  const setup = { workspace: 'setup' }
  const simulate = { workspace: 'simulate' }
  const model = { ...simulate, panel: 'model' }

  if (guide === 'workflow') {
    add('welcome', 'Welcome to MangoPoint',
      'The usual path has four parts: set up the orchard, run a forecast, read the result, then compare it with a real field check.',
      'This quick tour only points and explains. It will not change anything or run a forecast.', {}, 'tutorial-start')
    add('orchard', '1. Choose the orchard',
      'Start by choosing the farm or orchard you want to study. Check the orchard name and tree count before continuing.',
      'Every map, weather request, result and field record belongs to the selected orchard.', setup)
    add('weather-source', '2. Check the weather',
      'Use Live Forecast for current forecast weather. Use Custom Weather only when you want to enter a planned or known weather pattern.',
      'Weather affects pest activity. If the label says synthetic, the app is using fallback test weather.', setup)
    add('pest', '3. Choose the pest',
      'Choose Cecid Fly or Fruit Fly. Then choose the fruit stage that is actually present in the orchard.',
      'Cecid needs fruitlets. Fruit Fly needs green mature or ripening fruit. Open the matching pest guide for the full checklist.', simulate)
    add('duration', '4. Choose how far ahead to look',
      'Pick 24 hours, 48 hours, 72 hours or 7 days.',
      'Longer forecasts need weather for the full period. A longer period does not automatically mean more spread.', simulate)
    add('engine', '5. Choose how the map is calculated',
      'Grid looks at small map cells. Tree Graph follows links between individual tree crowns. Both use the same pest and weather choices.',
      'If you are unsure, start with Grid. You can later compare it with Tree Graph.', model)
    add('source-presence', '6. Tell the system where pest pressure starts',
      'Review trees marked Infected, History Infected or Suspect. Only use source percentages that match your farm evidence.',
      'A source means where the forecast begins. The default 50% choices are placeholders, not measured probabilities.', model)
    add('repeated-runs', '7. Choose one or several runs',
      'A single run shows one possible outcome. Five or nine runs show how often the same trees are affected when uncertain events vary.',
      'Across runs is a model frequency. It is not the percentage of fruit damaged.', model)
    add('run', '8. Review, then run',
      'Check the orchard, pest, fruit stage, weather, source, duration and map method. After closing the tour, press Run Simulation yourself.',
      'The tutorial never presses this button. If the button is unavailable, wait for the orchard map to finish loading.', simulate)
    add('results', hasResult ? '9. Read the result' : '9. Results appear here',
      hasResult
        ? 'Use the map, legend and playback to see where and when modeled risk changed.'
        : 'After a successful run, this panel will show playback and decision support. You can also load an older result from History.',
      'A forecast is a modeled outcome. It is not proof that a tree is infested.', { workspace: 'results' })
    add('history', '10. Find saved forecasts',
      'History lists completed runs. Load Result opens an old result. Use as Template brings its settings back for a new run.',
      'Loading a result or template does not run a new forecast.', { tab: 'history' }, 'history-heading')
    add('verify', '11. Check the orchard in person',
      'Run a simulation or use History → Load Result first. Then record the inspected tree, date, method and whether the forecast pest was Present, Absent or Not inspected.',
      'Only save what was actually observed. Never copy a simulated result into a field record.', { workspace: 'verify' })
    add('recovery-email', '12. Set your recovery email',
      'In Settings > Account, use Login and recovery email to save an address you can access. Enter your current password, then choose Save recovery email after closing the tutorial.',
      'This is also your login email and receives password-reset codes. Replace the default local address, which cannot receive email.',
      { navbarPanel: 'settings', settingsTab: 'account', placement: 'auto' }, 'settings-recovery-email')
    add('password-settings', '13. Change your password',
      'In Settings > Account, enter the current password, a new password of at least eight characters, and the new password again. Then choose Change password.',
      'If you forget it later, Forgot password? sends a reset code to the saved recovery email. The tutorial never changes your password.',
      { navbarPanel: 'settings', settingsTab: 'account', placement: 'auto' }, 'settings-password')
    if (isAdmin) add('notification-emails', '14. Add notification email recipients',
      'In Settings > Notification emails, enter an optional name and email address, then choose Add recipient. You can also edit, pause, resume or delete a recipient.',
      'Recipients do not need MangoPoint accounts. Email delivery requires Brevo or SMTP to be configured on the API server.',
      { navbarPanel: 'settings', settingsTab: 'notifications', placement: 'auto' }, 'settings-notification-emails')
    add('notifications', `${isAdmin ? '15' : '14'}. Read and manage notifications`,
      'The bell shows active alerts. Open it after the tour to read the warning and suggested response. Acknowledge marks it reviewed; Resolve closes it.',
      'Emailed shows that email was sent. Open Simulation Controls only prepares inputs; you must review them and run the forecast. An alert is not proof of infestation.',
      { navbarPanel: 'notifications', placement: 'left' }, 'notification-list')
    add('finish', 'You now know the main flow',
      'Choose a pest guide next for the exact Cecid or Fruit Fly conditions. You can reopen Tutorial from the top bar at any time.',
      'Setup → Simulate → Results → Verify, then keep your account and alert contacts current.', {}, 'tutorial-start')
    return steps
  }

  if (guide === 'cecid') {
    add('welcome', 'Cecid Fly setup',
      'This guide shows the conditions MangoPoint checks before fruit-attacking Cecid can emerge, move and affect fruitlets.',
      'A “gate” simply means a condition that must be suitable. Several gates must work together.', {}, 'tutorial-start')
    add('orchard', 'Start with the correct orchard',
      'Choose the orchard and check that its tree map is loaded.',
      'The source, fruit stage and weather must all describe the same orchard.', setup)
    add('cecid-stage', 'Gate 1: fruitlets must be present',
      'In Simulate, choose Cecid Fly and set Orchard Stage to Fruitlet. Also check any stage zones drawn on the map.',
      'This model is for fruit-attacking Cecid. Dormant, flowering and mature fruit do not open the host gate.', simulate, 'stage')
    add('cecid-source', 'Gate 2: there must be a starting source',
      'Use real source evidence when available: Infected, History Infected, Suspect or a selected source area. Review uncertain source percentages.',
      'With no source evidence, a run may assume 1–3 soil starting points. Those are scenario assumptions, not observed infected fruit.', model, 'source-presence')
    add('cecid-moisture', 'Gate 3: the soil must be moist enough',
      'Live Forecast uses recent rain. In Custom Weather, describe the starting soil as Dry, Moist now, Recently wet or Custom.',
      'Moist soil can support adult emergence. Moisture fades over time. Cloud or tree shade cannot replace soil moisture.', setup, 'weather-source')
    add('cecid-dry-window', 'Gate 4: wait for a rain break',
      'Rain may wet the soil, but adults need a dry or nearly dry period for activity. Plan rain first, then a dry period.',
      'Continuing or heavy rain reduces or stops emergence and movement during that hour.', setup, 'weather-source')
    add('cecid-light', 'Gate 5: use suitable outdoor light',
      'Dawn and dusk are the clearest activity windows. Some dim or cloudy daylight may also help when the light data supports it.',
      'Cloud percentage alone and shade under a tree are not enough. Bright daylight or unknown sunlight should not be called favorable.', setup, 'weather-source')
    add('cecid-wind', 'Gate 6: check wind',
      'Gentle wind is more suitable. Stronger wind lowers controlled flight, while wind direction changes which trees are downwind.',
      'Wind changes the chance and direction of movement; it does not create a source.', setup, 'weather-source')
    if (customWeather) {
      add('weather-schedule', 'Build the weather in time order',
        'Set the start date and time in Guimaras time. Make weather periods that cover the whole forecast.',
        'A useful Cecid scenario usually shows wetting, then a dry dawn, dusk or supported dim-light period.', { ...setup, panel: 'weather' })
      add('weather-rain', 'Enter rain for each period',
        'Rainfall is entered per hour. Check the start and end hour for every wet and dry period.',
        'Later overlapping periods win. Uncovered hours use default dry weather.', { ...setup, panel: 'weather-periods' }, 'weather-rainfall_mm')
      add('weather-light', 'Describe light separately from clouds',
        'Choose the outdoor daylight condition only when you can label it as observed or assumed. Review solar data when the light is not specified.',
        'Canopy shade is not an outdoor light observation.', { ...setup, panel: 'weather-periods' })
      add('soil', 'Describe the soil at Hour 0',
        'Open Soil & Cecid test preset and choose the starting soil condition that matches what you know.',
        'The Dawn + dusk preset is only a test scenario. It is not proof of favorable conditions at the farm.', { ...setup, panel: 'soil' }, 'soil-settings')
    }
    add('repeated-runs', 'Use repeated runs for uncertainty',
      'Choose 5 or 9 runs when source presence or establishment is uncertain.',
      'One run is one possible path. Across runs shows how often infestation appeared in the model.', model)
    add('gate-review', 'Check the Cecid timeline',
      'After reviewing inputs, run the forecast yourself. Cecid timeline checks explain which hours were favorable or limited.',
      'Even when all gates are suitable, infestation is still uncertain. Favorable conditions do not guarantee damage.', simulate, 'run')
    add('results', hasResult ? 'Read this Cecid result' : 'Return after running',
      hasResult ? 'Check sources, favorable hours, reachable fruitlet trees and established infestation separately.' : 'Run the forecast, then replay this guide to inspect the real result.',
      'New fruit infestation does not create a new soil source in the same forecast.', { workspace: 'results' })
    add('finish', 'Cecid checklist complete',
      'Fruitlets + source + moist soil + a dry suitable-light period + suitable wind. Then run, read the timeline and verify in the field.',
      'Use farm observations whenever possible and label assumptions clearly.', {}, 'tutorial-start')
    return steps
  }

  if (guide === 'fruitfly') {
    add('welcome', 'Fruit Fly setup',
      'This guide shows the main checks for Oriental Fruit Fly before you run a forecast.',
      'Fruit Fly uses different conditions from Cecid. It does not need Cecid’s wet-soil emergence sequence.', {}, 'tutorial-start')
    add('orchard', 'Start with the correct orchard',
      'Choose the orchard and wait for its tree map to load.',
      'The fruit stage, source and weather should describe this same orchard.', setup)
    add('fruitfly-stage', 'Gate 1: mature fruit must be present',
      'Choose Fruit Fly and set Orchard Stage to Green mature / ripening. Check any stage zones on the map.',
      'Fruitlets, flowers and dormant trees do not open the Fruit Fly host gate in this model.', simulate, 'stage')
    add('fruitfly-age', 'Check days since flowering',
      'Set Days Since Flowering to match the orchard. A higher value represents riper, more attractive fruit within the mature stage.',
      'This slider does not replace choosing Green mature / ripening.', simulate, 'fruit-age')
    add('fruitfly-source', 'Gate 2: there must be adult pressure',
      'Review Infected, History Infected and Suspect trees, plus any nearby orchard pressure. Set uncertainty from your evidence.',
      'Fruit damage does not prove adults are present. New infestation will not become another adult source during this forecast.', model, 'source-presence')
    add('fruitfly-weather', 'Gate 3: check warmth and time of day',
      'Daylight has full modeled activity. Twilight is lower, and darkness has a small assumed allowance. Temperature raises or lowers activity gradually.',
      '25°C is a reference value, not a normal hard on/off switch. Wind changes directional exposure.', setup, 'weather-source')
    if (customWeather) {
      add('weather-schedule', 'Cover the full forecast with weather',
        'Set the start time in Guimaras time and create periods for the whole run.',
        'Use realistic temperature, wind and light values. Uncovered hours use default weather.', { ...setup, panel: 'weather' })
      add('weather-temperature', 'Enter temperature for each period',
        'Use the expected or observed temperature. Check that the period starts and ends at the intended hour.',
        'Warmer conditions change activity, but mature fruit and a starting source are still required.', { ...setup, panel: 'weather-periods' }, 'weather-temperature_c')
      add('weather-wind', 'Enter wind speed and direction',
        'Wind from means the direction the wind comes from. Enter speed in metres per second.',
        'Wind can shift pressure toward downwind trees.', { ...setup, panel: 'weather-periods' }, 'weather-wind_speed_ms')
    }
    add('repeated-runs', 'Use repeated runs for uncertainty',
      'Choose 5 or 9 runs if you want to see how often trees are affected when uncertain events vary.',
      'Across runs is model frequency, not measured fruit damage.', model)
    add('run', 'Review, then run',
      'Check mature fruit, days since flowering, adult source pressure, weather, duration and map method. Then close the guide and press Run Simulation.',
      'The tutorial never starts the run for you.', simulate)
    add('results', hasResult ? 'Read this Fruit Fly result' : 'Return after running',
      hasResult ? 'Separate initial adult sources from newly infested fruit when reading the map.' : 'Run the forecast, then replay this guide to inspect the real result.',
      'The forecast does not simulate a new egg-to-adult generation or individual flight paths.', { workspace: 'results' })
    add('finish', 'Fruit Fly checklist complete',
      'Mature or ripening fruit + realistic fruit age + initial adult pressure + suitable weather and time of day. Then run and verify in the field.',
      'Keep modeled infestation separate from what scouts actually observe.', {}, 'tutorial-start')
    return steps
  }

  add('welcome', 'Understanding results',
    'This guide explains what the result means, where saved runs go and how to compare a forecast with a field inspection.',
    'A model result is a warning or planning aid. It is not a field observation.', {}, 'tutorial-start')
  add('results', hasResult ? 'Start with the result panel' : 'No result is loaded yet',
    hasResult ? 'Check the pest, orchard, weather source and model version before interpreting the map.' : 'Run a forecast or use History → Load Result, then replay this guide.',
    'Changing controls after a run does not change the result that is already loaded.', { workspace: 'results' })
  if (hasPlayback) add('playback', 'Watch one run over time',
    'Use Play or the hour slider to see one representative run develop hour by hour.',
    'The displayed hour may differ from the final forecast hour.', { workspace: 'results' })
  if (hasResult) {
    add('legend', 'Use the legend before reading colors',
      'Open the legend and check risk colors, tree states and source badges. Click a tree for its details.',
      'A source badge is a scenario input. An infested tree on the map is a modeled outcome.', { panel: 'legend' })
    if (hasRepeatedRuns) add('map-mode', 'Across runs and One run are different',
      'Across runs shows how often infestation appeared over several runs. One run shows one possible map.',
      'Frequency is not calibrated field probability and not the percentage of damaged fruit.', { tab: 'live-map' })
    add('report', 'Check before sharing a report',
      'Confirm the orchard, pest, model version, weather source and whether the report uses the final or displayed hour.',
      'Print or export only through the normal button after closing the tutorial.', { workspace: 'results' })
  }
  add('history', 'History keeps completed runs',
    'Load Result reopens an output. Use as Template restores inputs for another run.',
    'A template does not run automatically. Check its saved assumptions before using it.', { tab: 'history' }, 'history-heading')
  add('verify', 'Verify with a real field check',
    'Load a completed forecast first, then record the tree, date, method and actual finding: Present, Absent or Not inspected. Every verification stays linked to that forecast.',
    'Do not save simulated infestation as an observation.', { workspace: 'verify' })
  add('overview', 'Other views provide context',
    'Overview summarizes saved activity. Crop Impact contains estimates. Spread & Weather shows modeled spread beside weather.',
    'These views support interpretation; they do not prove forecast accuracy or measured farm benefit.', { tab: 'overview' }, 'overview-heading')
  add('settings', 'Help remains available',
    isAdmin
      ? 'Tutorial stays in the top bar. Settings also contains account and administrator notification controls.'
      : 'Tutorial stays in the top bar. Settings contains your account controls; some tools are for administrators only.',
    'Close this guide before making account or notification changes.', {}, 'settings')
  add('finish', 'Results guide complete',
    'Read the assumptions, inspect the modeled result, find the saved run, then verify it in the orchard.',
    'Forecast → field check → comparison. Keep those records separate.', {}, 'tutorial-start')
  return steps
}
