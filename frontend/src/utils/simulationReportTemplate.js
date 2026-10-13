// Self-contained report layout used for PDF generation and browser printing.
function embeddedImage(value) {
  return /^data:image\/(png|jpeg);base64,[a-zA-Z0-9+/=]+$/.test(value || '') ? value : ''
}
function cssString(value) {
  return `"${String(value).replace(/[\\"]/g, '\\$&').replace(/[\r\n\f]/g, ' ')
    .replace(/</g, '\\3c ').replace(/>/g, '\\3e ')}"`
}

export function renderSimulationReport(report, snapshot, logo, format) {
  const mapImage = embeddedImage(snapshot?.dataUrl)
  if (!mapImage) throw new Error('A complete map image is required before the report can be exported.')
  const { escapeReportHtml: e, reportPercent: percent, reportDate: date, formatPhp,
    riskLegend, frequencyLegend, treeLegend } = format
  const value = (item) => item == null || item === '' ? 'Not recorded' : e(item)
  const human = (item) => value(item).replace(/_/g, ' ')
  const details = report.recordDetails || {}
  const reference = details.reference || report.runId
  const frequency = report.mapMode === 'likelihood'
  const runs = report.uncertainty?.runs ?? report.settings?.find(([label]) => label === 'Repeated runs')?.[1] ?? 1
  const imageLogo = embeddedImage(logo)
  const method = report.mode === 'tree_graph' ? 'Tree Graph' : report.mode === 'grid' ? 'Grid · Cellular Automata' : report.mode
  const pair = (label, content) => `<div class="record-field"><dt>${e(label)}</dt><dd>${value(content)}</dd></div>`
  const heading = (label) => `<header class="masthead"><div class="brand-lockup">${imageLogo ? `<img src="${imageLogo}" alt="MangoPoint logo">` : ''}<div><strong>MangoPoint</strong><span>Orchard management record</span></div></div><div class="masthead-record"><strong>${e(label)}</strong><span>Record ${e(reference)}</span><small>Generated ${date(report.generatedAt)} · Philippine time</small></div></header>`
  const section = (label, title) => `<div class="section-heading"><span>${e(label)}</span><h2>${e(title)}</h2></div>`
  const metric = (label, content, note) => `<div class="metric"><span>${e(label)}</span><strong>${value(content)}</strong><small>${e(note)}</small></div>`
  const legend = (items) => items.map(([color, label]) => `<span><i style="background:${color}"></i>${e(label)}</span>`).join('')
  const notes = (label, content) => content ? `<div class="record-notes"><h3>${e(label)}</h3><p>${e(content)}</p></div>` : ''
  const sourceGroups = (report.sourceSummary || []).filter((group) => group.key !== 'other' || group.count > 0)
  const sourceIds = (group) => group.ids.length ? `${group.ids.slice(0, 6).map(e).join(', ')}${group.ids.length > 6 ? ` · +${group.ids.length - 6} more` : ''}` : '—'
  const sourceRows = sourceGroups.map((group) => {
    const probabilities = [...new Set(group.sources.map((source) => source.probability).filter((p) => p != null))]
    const chance = probabilities.length ? probabilities.length === 1 ? percent(probabilities[0]) : `${percent(Math.min(...probabilities))}–${percent(Math.max(...probabilities))}` : 'Not recorded'
    return `<tr><th scope="row">${e(group.label)}</th><td class="numeric">${group.count}</td><td>${sourceIds(group)}</td><td>${group.count ? chance : '—'}</td></tr>`
  }).join('')
  const sourceNote = report.initialSources.length
    ? 'Recorded / selected infected trees are input records; adult presence is not independently verified by this report. Historical, suspect and fallback presence remains assumed.'
    : 'No source detail was saved with this run. The report cannot establish that the simulation had zero sources.'
  const sourceTable = report.initialSources.length ? `<table class="sources-summary"><thead><tr><th>Starting source basis</th><th class="numeric">Count</th><th>Location IDs · first 6</th><th>Presence chance</th></tr></thead><tbody>${sourceRows}</tbody></table>` : ''
  const keyFinding = report.infested == null ? 'The saved map is available; an infestation count was not recorded.'
    : `${report.infested} of ${report.total} simulated ${report.unit} are infested in the ${frequency ? 'representative' : 'reported'} run.`
  const uncertaintyText = Number(runs) > 1
    ? `${value(runs)} repeated runs${report.uncertainty?.minimum != null && report.uncertainty?.maximum != null ? ` · ${value(report.uncertainty.minimum)}–${value(report.uncertainty.maximum)} final infested ${e(report.unit)} · median ${value(report.uncertainty.median)}` : ' · outcome range not recorded'}.`
    : 'Single realization; repeated-run infestation frequency is unavailable.'
  const provenance = report.weatherProvenance || {}
  const weather = report.weather || {}
  const weatherValues = [
    ['Temperature', weather.temperature_c ?? weather.temp_c, '°C'], ['Rainfall', weather.rainfall_mm ?? weather.rain_mm, 'mm'],
    ['Relative humidity', weather.humidity ?? weather.humidity_pct, '%'], ['Wind speed', weather.wind_speed_ms ?? weather.wind_ms, 'm/s'],
    ['Wind FROM direction', weather.wind_dir_deg ?? weather.wind_direction_deg, '°'],
  ]
  const lightDescription = weather.daylight_condition
    ? `${String(weather.daylight_condition).replace(/_/g, ' ')} · ${weather.daylight_condition_basis || 'assumed'}` : 'Not recorded'
  const markerLegend = treeLegend.filter(([, label]) => label === 'Bagged' || label === 'Dead')
  if (report.pest === 'cecid') markerLegend.push(['#6b7280', 'Stage not eligible'])
  markerLegend.push(['#78350f', report.pest === 'cecid' ? 'S · starting source' : 'S · source / R · historical reservoir'])
  const priorityHtml = report.priorityLocations.length ? `<table class="inspection"><thead><tr><th>${report.unit === 'trees' ? 'Tree ID' : 'Cell ID'}</th><th>Map ${frequency ? 'frequency' : 'score'}</th><th>State in one run</th><th class="numeric">Checked</th></tr></thead><tbody>${report.priorityLocations.slice(0, 5).map((entry) => `<tr><td>${value(entry.id)}</td><td>${percent(entry.risk)}</td><td>${human(entry.state)}</td><td class="numeric">□</td></tr>`).join('')}</tbody></table>`
    : `<p class="small">No recorded locations meet the ${percent(report.priorityThreshold)} report screening threshold. This does not establish pest absence.</p>`
  const economic = report.economic
  const economicHtml = economic ? `<div class="economic-section"><h3>Crop impact · scenario planning estimate</h3><div class="economic-values"><span>Before action <strong>${formatPhp(economic.projected_loss)}</strong></span><span>After action <strong>${formatPhp(economic.remaining_loss)}</strong></span><span>Potential savings <strong>${formatPhp(economic.estimated_savings)}</strong></span></div><p class="small">Assumes ${percent(economic.recommendation_effectiveness)} loss reduction, ${value(economic.yield_per_tree_kg)} kg/tree, PHP ${value(economic.farmgate_price_php_per_kg)}/kg and ${percent(economic.damage_rate)} damage. Treatment and labor costs are not subtracted. Estimates are not measured losses or guaranteed benefits.</p></div>`
    : '<p class="small muted">Crop-loss estimates omitted: simulated cells are not an individual-tree inventory.</p>'
  const settings = (report.settings || []).map(([label, content]) => pair(label, content)).join('')
  const sourceDefaults = `<div class="source-defaults"><dl>${pair('History Infected reservoir presence', percent(report.sourceAssumptions?.history))}${pair('Suspect current infection presence', percent(report.sourceAssumptions?.suspect))}</dl><p class="small muted">Defaults are scenario assumptions; per-location chances in the table take precedence. Historical sources do not imply initially infested fruit.</p></div>`
  const weatherPlan = report.weatherBlocks?.length ? `${report.weatherBlocks.length} custom weather periods; detailed schedule is available in the optional supporting tables.`
    : report.weatherSeriesCount ? `${report.weatherSeriesCount} saved custom weather hours.` : report.weatherInput ? 'Constant custom weather scenario.' : 'Weather schedule details not recorded in the request.'
  const actionsHtml = (report.actions || []).map((action, i) => `<li><div class="action-number">${i + 1}</div><div><h3>${e(action.title)} <span>${e(action.timing)}</span></h3><p>${e(action.detail)}</p></div></li>`).join('')
  const modelNotes = report.modelInterpretation && (report.modelInterpretation.source_rule && report.modelInterpretation.outside_pressure
    ? [report.modelInterpretation.source_rule, report.modelInterpretation.outside_pressure] : Object.values(report.modelInterpretation).slice(0, 2))
  const interpretation = modelNotes ? `<p class="small muted">Saved model interpretation (summary): ${modelNotes.map((note) => e(String(note).split(/(?<=\.)\s+/)[0])).join(' ')} Full saved text is available in the optional supporting tables.</p>`
    : '<p class="small muted">Detailed model assumptions were not recorded with this run. Refer to its saved model version.</p>'
  const attribution = snapshot.attribution || 'Orchard imagery attribution not recorded'
  const basemapNote = snapshot.mapBase === 'locations-only' ? 'Orthophoto unavailable · locations on a white background'
    : snapshot.mapBase === 'orthophoto' ? 'Orchard orthophoto · surrounding basemap excluded' : 'Saved orchard map'
  const sourceDetail = report.initialSources.length ? `<h3>All saved source inputs</h3><table><thead><tr><th>Location</th><th>Recorded status</th><th>Source basis</th><th>Chance</th><th>Active*</th></tr></thead><tbody>${report.initialSources.map((source) => `<tr><td>${value(source.tree_id ?? source.id ?? source.source_id ?? 'Ground source')}</td><td>${human(source.status)}</td><td>${human(source.label || source.origin)}<small class="cell-note">${source.assumed === true ? 'Assumed presence' : source.assumed === false ? 'Recorded / selected source' : 'Presence basis not recorded'}</small></td><td>${percent(source.probability)}</td><td>${source.active === true ? 'Yes' : source.active === false ? 'No' : 'Not recorded'}</td></tr>`).join('')}</tbody></table><p class="small">*Active refers to the starting realization, not a field-confirmed adult count.</p>` : ''
  const zoneDetail = report.zoneEntries.length ? `<h3>Saved orchard and scenario zones</h3><table><thead><tr><th>Zone</th><th>Type / setting</th><th>Recorded trees</th><th>Maximum value</th></tr></thead><tbody>${report.zoneEntries.map((entry) => `<tr><td>${value(entry.label)}</td><td>${value(entry.typeLabel)}${entry.detail ? `<small class="cell-note">${human(entry.detail)}</small>` : ''}</td><td>${value(entry.treeCount)}</td><td>${percent(entry.peakRisk)}</td></tr>`).join('')}</tbody></table>` : ''
  const timelineDetail = report.timeline.length ? `<h3>Selected hours · representative run</h3><table><thead><tr><th>Hour</th><th>Forecast time · Philippine time</th><th>Infested ${e(report.unit)}</th><th>New that step</th></tr></thead><tbody>${report.timeline.map((frame) => `<tr><td>${value(frame.hour)}</td><td>${date(frame.datetime ?? frame.weather?.datetime)}</td><td>${value(frame.n_infested)}</td><td>${value(frame.n_new)}</td></tr>`).join('')}</tbody></table>` : ''
  const parameterDetail = report.parameterOverrides?.length ? `<h3>Saved model parameter values / overrides</h3><dl class="settings-grid">${report.parameterOverrides.map(([label, setting]) => pair(label.replace(/_/g, ' '), setting)).join('')}</dl>` : ''
  const weatherDetail = report.weatherBlocks?.length ? `<h3>Saved custom weather periods</h3><table><thead><tr><th>Hours</th><th>Temperature / rain</th><th>Wind FROM</th><th>Daylight condition / basis</th></tr></thead><tbody>${report.weatherBlocks.map((block) => `<tr><td>${value(block.start_hour)}–${value(block.end_hour)}</td><td>${value(block.temperature_c)} °C / ${value(block.rainfall_mm)} mm</td><td>${value(block.wind_speed_ms)} m/s / ${value(block.wind_dir_deg ?? block.wind_direction_deg)}°</td><td>${human(block.daylight_condition)}<small>${human(block.daylight_condition_basis)}</small></td></tr>`).join('')}</tbody></table>` : ''
  const appendix = report.includeDetails ? `<section class="sheet supporting-sheet">${heading('Supporting tables')}<div class="page-body">${section('Saved evidence', 'Detailed record')}<p class="small muted">These inputs belong to the saved simulation. They are not independent field observations.</p>${sourceDetail}${zoneDetail}${weatherDetail}${timelineDetail}${parameterDetail}${report.modelInterpretation ? `<h3>All saved model assumptions</h3><dl class="settings-grid">${Object.entries(report.modelInterpretation).map(([key, explanation]) => pair(key.replace(/_/g, ' '), explanation)).join('')}</dl>` : ''}</div></section>` : ''

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${e(report.orchardName)} — Pest simulation report</title>
<style>
@page { size: A4 portrait; margin: 11mm 12mm 14mm;
  @bottom-left { content: ${cssString(`MangoPoint · ${String(reference).slice(0, 70)}`)}; font: 7pt Arial; color: #617368; }
  @bottom-right { content: "Page " counter(page) " / " counter(pages); font: 7pt Arial; color: #617368; }
}
* { box-sizing: border-box; } body { margin: 0; color: #203d2c; background: #e9eeea; font: 9pt/1.4 Arial, sans-serif; }
.toolbar { background: #153c29; padding: 13px; color: #fff; text-align: center; } .toolbar button { padding: 8px 14px; border: 0; border-radius: 4px; font: inherit; font-weight: 700; cursor: pointer; } .toolbar span { padding-left: 12px; font-size: 8pt; }
.sheet { width: 210mm; margin: 18px auto; padding: 11mm 12mm; background: #fff; box-shadow: 0 2px 15px #183c2520; }
.masthead { display: flex; justify-content: space-between; gap: 14px; align-items: center; padding: 9px 15px; background: #153c29; color: #fff; border-bottom: 4px solid #f1ad24; break-inside: avoid; }
.brand-lockup { display: flex; align-items: center; gap: 10px; } .brand-lockup img { width: 35px; height: 35px; object-fit: contain; background: #fff; border-radius: 6px; padding: 3px; } .brand-lockup strong { display: block; font-size: 17pt; } .brand-lockup span { display: block; color: #f6bd50; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 1.4px; }
.masthead-record { text-align: right; max-width: 80mm; overflow-wrap: anywhere; } .masthead-record strong { display: block; font-size: 9pt; } .masthead-record span { font-size: 7pt; color: #d4e2d8; } .masthead-record small { display: block; font-size: 6pt; color: #d4e2d8; }
.page-body { padding: 13px 2px 0; } h1 { font-size: 19pt; line-height: 1.18; margin: 0 0 5px; letter-spacing: -.4px; overflow-wrap: anywhere; } h2 { font-size: 14pt; line-height: 1.2; margin: 5px 0 8px; } h3 { font-size: 9pt; margin: 0 0 5px; break-after: avoid; } p { margin: 4px 0; } .muted { color: #617368; } .small { font-size: 7.5pt; line-height: 1.4; } .subline { font-size: 8pt; color: #617368; }
.section-heading { margin: 8px 0 5px; break-after: avoid; } .section-heading h2 { font-size: 13pt; margin: 4px 0 6px; } .section-heading > span, .tag { display: inline-block; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; background: #f5b42d; color: #153c29; padding: 3px 7px; border-radius: 3px; }
dl { margin: 0; } .record-grid, .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px 20px; margin: 10px 0; } .record-field { min-width: 0; break-inside: avoid; } dt { color: #617368; font-size: 7pt; margin: 0 0 1px; } dd { margin: 0; font-weight: 600; font-size: 8pt; overflow-wrap: anywhere; }
.finding { font-size: 13pt; font-weight: 700; line-height: 1.25; margin: 6px 0 9px; } .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin: 9px 0; break-inside: avoid; } .metric { border-top: 3px solid #e9a523; background: #f1f5ef; padding: 8px 10px; } .metric span { display: block; font-size: 7pt; color: #536c5d; } .metric strong { display: block; font-size: 22pt; line-height: 1.25; margin: 3px 0; } .metric small { display: block; font-size: 6.5pt; color: #617368; }
.outcome-line { font-size: 7.5pt; padding-left: 8px; border-left: 3px solid #e9a523; margin: 8px 0; }
.map-figure { margin: 9px 0 0; break-inside: avoid; } .map { width: 100%; height: 76mm; display: block; object-fit: contain; background: #fff; border: 1px solid #dce5da; border-radius: 5px; } figcaption { font-size: 6.5pt; color: #617368; padding-top: 4px; } .legend { display: flex; flex-wrap: wrap; gap: 4px 12px; margin: 6px 0; font-size: 7pt; } .legend span { display: inline-flex; align-items: center; gap: 4px; } .legend i, .band-swatch { display: inline-block; width: 8px; height: 8px; border: 1px solid #688373; flex-shrink: 0; } .marker-legend i { border-radius: 50%; }
.next-step { margin-top: 10px; padding: 10px 12px; border-radius: 5px; background: #153c29; color: #fff; break-inside: avoid; } .next-step strong { display: block; color: #f8c360; font-size: 7pt; text-transform: uppercase; letter-spacing: .7px; } .next-step p { font-size: 8pt; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 7.5pt; margin: 7px 0 9px; } th, td { text-align: left; vertical-align: top; padding: 5px 7px; border-bottom: 1px solid #dce5da; overflow-wrap: anywhere; } thead th { background: #f0f4ee; color: #506959; font-size: 6.8pt; } tbody th { font-weight: 600; } .numeric { text-align: right; } .sources-summary th:first-child { width: 31%; } .sources-summary th:nth-child(2) { width: 10%; } .sources-summary th:nth-child(4) { width: 20%; } thead { display: table-header-group; } tr { break-inside: avoid; } .cell-note { display: block; color: #617368; font-size: 6.5pt; } .band-swatch { margin-right: 5px; }
.source-defaults dl { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; } .weather-strip { border: 1px solid #dce5da; border-radius: 4px; padding: 7px 9px; margin: 9px 0; font-size: 7.5pt; break-inside: avoid; } .weather-values { display: flex; flex-wrap: wrap; gap: 3px 13px; margin-top: 3px; }
.actions { list-style: none; padding: 0; margin: 6px 0; } .actions li { display: flex; gap: 9px; margin: 8px 0; break-inside: avoid; } .action-number { width: 21px; height: 21px; flex: 0 0 21px; text-align: center; line-height: 21px; border-radius: 50%; background: #eef3eb; font-weight: 700; } .actions h3 { margin-bottom: 2px; } .actions h3 span { font-size: 6.5pt; color: #617368; font-weight: 400; margin-left: 4px; } .actions p { font-size: 7.5pt; margin: 0; }
.economic-section { background: #f7f9f4; border: 1px solid #dce5da; border-radius: 4px; padding: 8px 10px; margin: 9px 0; break-inside: avoid; } .economic-values { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; font-size: 7pt; } .economic-values strong { display: block; font-size: 10pt; margin: 2px 0; }
.record-notes { margin: 7px 0; } .record-notes p { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8pt; } .notes-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; } .signatures { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 8px; break-inside: avoid; } .signatures > div { border-top: 1px solid #839787; padding-top: 4px; font-size: 7pt; }
.trace { border-top: 1px solid #dce5da; margin-top: 8px; padding-top: 5px; } .trace dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px 12px; } .supporting-sheet h3 { margin-top: 13px; } .document-end { margin-top: 5px; font-size: 6.5pt; color: #617368; }
.follow-up-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; } .follow-up-columns > div { min-width: 0; } .follow-up-columns .economic-values { grid-template-columns: 1fr; gap: 3px; } .follow-up-columns .economic-values span { display: flex; justify-content: space-between; gap: 6px; align-items: baseline; } .follow-up-columns .economic-values strong { display: inline; font-size: 9pt; }
.follow-up-sheet .page-body { padding-top: 7px; } .sources-summary th, .sources-summary td { padding-top: 4px; padding-bottom: 4px; }
@media print { body { background: #fff; print-color-adjust: exact; -webkit-print-color-adjust: exact; } .toolbar { display: none; } .sheet { width: auto; margin: 0; padding: 0; box-shadow: none; } .sheet + .sheet { break-before: page; } }
@media screen and (max-width: 820px) { .sheet { width: 100%; padding: 15px; margin: 10px auto; } .record-grid, .settings-grid { gap: 8px; } }
</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print</button><span>A4 portrait · disable browser headers and footers</span></div><main>
<section class="sheet summary-sheet">${heading('Pest simulation report')}<div class="page-body">
  <h1>${e(report.orchardName)}</h1><p class="subline">${e(report.pestLabel)} · ${value(method)} · ${e(report.label)} · ${value(report.hours)}-hour scenario</p>
  <dl class="record-grid">${pair('Forecast begins · Philippine time', date(report.forecastStart))}${pair('Reported forecast time · Philippine time', date(report.reportedAt))}${pair('Prepared by', details.preparedBy)}${pair('Organization / office', details.organization)}</dl>
  <span class="tag">Key finding${report.hour != null ? ` · Hour ${e(report.hour)}` : ''}</span><p class="finding">${e(keyFinding)}</p>
  <div class="metrics">${metric(`Infested ${report.unit}${frequency ? ' (representative run)' : ''}`, report.infested, 'Simulated outcome · not a field count')}${metric(`Maximum ${frequency ? 'across-run frequency' : 'one-run risk score'}`, percent(report.peak), frequency ? `Across ${runs} repeated runs` : 'Value in the reported realization')}${metric(`${report.unit === 'trees' ? 'Trees' : 'Cells'} at ≥50%`, report.highRisk, 'Priority for field checking')}</div>
  <p class="outcome-line">${value(report.total)} simulated ${e(report.unit)} · Initially infested: ${value(report.initialInfested)} · Newly established by this hour: ${value(report.newlyInfested)}</p>
  <p class="small muted">${uncertaintyText}</p>
  <figure class="map-figure"><img class="map" src="${mapImage}" alt="${e(report.label)} orchard orthophoto with simulation shading and source markers"><figcaption>${e(basemapNote)} · North is up · ${e(attribution)}</figcaption></figure>
  <div class="legend">${legend(frequency ? frequencyLegend : riskLegend)}</div><div class="legend marker-legend">${legend(markerLegend)}</div>
  <p class="small muted">${frequency ? 'Shading shows the share of repeated runs with infestation; tree states and source badges show one representative run.' : 'Shading shows one-run scores. Established infestation is 100% in that run; it is not a calibrated field probability.'} Zone outlines follow saved inputs.</p>
  <h3 style="margin-top:9px">Inspection checklist · first 5 priority locations</h3>${priorityHtml}
  <div class="next-step"><strong>Recommended next step</strong><p>${e(report.actions?.[0]?.detail || 'Inspect the mapped locations and record pest signs before making management decisions.')}</p></div>
</div></section>
<section class="sheet follow-up-sheet">${heading('Sources, settings & follow-up')}<div class="page-body">
  ${section('Starting evidence', 'What the simulation started with')}${sourceTable}<p class="small muted">${e(sourceNote)}</p>${sourceDefaults}
  <div class="follow-up-columns"><div>
  ${section('Saved scenario', 'Simulation settings')}<dl class="settings-grid">${pair('Pest', report.pestLabel)}${pair('Method / duration', `${method} · ${report.hours ?? 'Not recorded'} hours`)}${settings}</dl>
  <div class="weather-strip"><strong>Saved weather at the reported hour · ${date(report.reportedAt)}</strong><div class="weather-values">${weatherValues.map(([label, field, unit]) => `<span>${e(label)}: <strong>${field == null ? 'Not recorded' : `${value(field)} ${unit}`}</strong></span>`).join('')}<span>Outdoor daylight: <strong>${e(lightDescription)}</strong></span></div><p class="small muted">${e(weatherPlan)}</p>${provenance.fallback_reason ? `<p>Weather fallback: ${value(provenance.fallback_reason)}</p>` : ''}</div>
  </div><div>
  ${section('Field follow-up', 'Action plan')}<p class="small muted">Suggested inspection and management steps for this report. Actions have not been performed.</p><ol class="actions">${actionsHtml}</ol>
  ${economicHtml}</div></div><div class="notes-grid">${notes('Field observations / reviewer’s notes', details.fieldNotes)}${notes('Planned actions / follow-up', details.plannedActions)}</div>
  <div class="signatures"><div>Prepared by: ${details.preparedBy ? e(details.preparedBy) : '________________________'}<br>Signature / date: ________________________</div><div>Reviewed by: ${details.reviewedBy ? e(details.reviewedBy) : '________________________'}<br>Signature / date: ________________________</div></div>
  <div class="trace"><dl>${pair('Model version', report.modelVersion)}${pair('Run ID / orchard ID', `${report.runId} / ${report.orchardId}`)}${pair('Run executed · Philippine time', date(report.startedAt))}${pair('Weather provider', provenance.provider ?? provenance.source ?? report.weatherSource)}${pair('Simulation classification threshold', percent(report.simulationRiskThreshold))}${pair('Report screening threshold', percent(report.priorityThreshold))}</dl>${interpretation}<p class="small muted">Report screening is separate from simulation classification. Repeated-run ranges are not calibrated confidence intervals. Confirm modeled outcomes in the field.</p></div>
</div></section>${appendix}</main></body></html>`
}
