// Self-contained HTML: the same document is used for PDF printing and offline records.
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
  const humanize = (item) => value(item).replace(/_/g, ' ')
  const details = report.recordDetails || {}
  const reference = details.reference || report.runId
  const frequency = report.mapMode === 'likelihood'
  const metricName = frequency ? 'infestation frequency' : 'one-run risk score'
  const runs = report.uncertainty?.runs ?? Math.max(1, ...(report.geojson.features || [])
    .map((feature) => Number(feature.properties?.ensemble_runs) || 1))
  const imageLogo = embeddedImage(logo)
  const title = (number, heading, description = '') => `<div class="section-title"><span class="section-number">${number}</span><div><h2>${e(heading)}</h2>${description ? `<p class="muted">${e(description)}</p>` : ''}</div></div>`
  const header = (label) => `<div class="running-heading"><strong>MangoPoint</strong><span>${e(label)}</span><span class="record-ref">Record ${e(reference)}</span></div>`
  const pair = (label, content) => `<div class="record-field"><dt>${e(label)}</dt><dd>${value(content)}</dd></div>`
  const metric = (label, content, note = '') => `<div class="metric"><span>${e(label)}</span><strong>${value(content)}</strong>${note ? `<small>${e(note)}</small>` : ''}</div>`
  const legend = (items) => items.map(([color, label]) => `<span><i style="background:${color}"></i>${e(label)}</span>`).join('')
  const notes = (label, content) => `<div class="record-notes"><h3>${e(label)}</h3>${content
    ? `<div class="notes-content">${e(content)}</div>` : '<div class="writing-lines" aria-label="Space for handwritten notes"></div>'}</div>`
  const modelMode = report.mode === 'tree_graph' ? 'Tree graph (individual trees)' : report.mode === 'grid' ? 'Grid (occupied cells)' : report.mode
  const markerLegend = treeLegend.filter(([, label]) => label === 'Bagged' || label === 'Dead')
  if (report.pest === 'cecid') markerLegend.push(['#6b7280', 'Stage not eligible'], ['#78350f', 'S: source in one run'])
  else markerLegend.push(['#78350f', 'S: source / R: reservoir in one run'])
  const riskRows = (report.riskBands || []).map((band, index) => `<tr><td><i class="band-swatch" style="background:${band.color}"></i>${e((frequency ? frequencyLegend : riskLegend)[index][1])}</td><td class="numeric">${value(band.count)}</td></tr>`).join('')
  const uncertaintyText = runs > 1
    ? `${value(runs)} repeated runs: ${value(report.uncertainty?.minimum)}–${value(report.uncertainty?.maximum)} infested ${e(report.unit)}; median ${value(report.uncertainty?.median)}. The range describes final outcomes under the saved scenario.`
    : 'Single realization. Repeated-run infestation frequency is not available for this record.'
  const provenance = report.weatherProvenance || {}
  const weather = report.weather || {}
  const weatherValues = [
    ['Temperature', weather.temperature_c ?? weather.temp_c, '°C'],
    ['Rainfall', weather.rainfall_mm ?? weather.rain_mm, 'mm'],
    ['Relative humidity', weather.humidity ?? weather.humidity_pct, '%'],
    ['Wind speed', weather.wind_speed_ms ?? weather.wind_ms, 'm/s'],
    ['Wind FROM direction', weather.wind_dir_deg ?? weather.wind_direction_deg, '°'],
  ]
  const economic = report.economic
  const economicHtml = economic ? `<section class="economic-section">
    <h3>Crop impact · scenario planning estimate</h3>
    <table class="compact"><tbody>
      <tr><th scope="row">Projected loss before action</th><td class="numeric">${formatPhp(economic.projected_loss)}</td><th scope="row">Potential savings</th><td class="numeric">${formatPhp(economic.estimated_savings)}</td></tr>
      <tr><th scope="row">Remaining loss after action</th><td class="numeric">${formatPhp(economic.remaining_loss)}</td><th scope="row">Assumed loss reduction</th><td class="numeric">${percent(economic.recommendation_effectiveness)}</td></tr>
    </tbody></table>
    <p class="caption muted">Based on ${value(economic.infested_count)} infested trees in the representative run, ${value(economic.yield_per_tree_kg)} kg/tree, PHP ${value(economic.farmgate_price_php_per_kg)}/kg and ${percent(economic.damage_rate)} damage. These are scenario estimates, not observed losses or guaranteed savings. Treatment and labor costs are not subtracted.</p>
  </section>` : '<p class="caption muted">Crop-loss estimates are omitted for grid results because simulated cells are not an individual-tree inventory.</p>'
  const priorityHtml = report.priorityLocations?.length ? `<div class="table-intro"><h3>Locations prioritized for field checking</h3>
    <p class="caption muted">Up to 10 ${e(report.unit)} with the highest displayed values at or above ${percent(report.priorityThreshold)}. This is a report screening threshold; confirm pest presence in the field.</p></div>
    <table class="priority-table"><thead><tr><th scope="col">${report.unit === 'trees' ? 'Tree ID' : 'Cell ID'}</th><th scope="col">${frequency ? 'Across-run frequency' : 'One-run score'}</th><th scope="col">State in one run</th><th scope="col">Latitude / longitude</th></tr></thead><tbody>${report.priorityLocations.map((entry) => `<tr><td>${value(entry.id)}</td><td class="numeric">${percent(entry.risk)}</td><td>${humanize(entry.state)}</td><td class="coordinates">${entry.center ? `${entry.center[1].toFixed(6)}, ${entry.center[0].toFixed(6)}` : 'Not recorded'}</td></tr>`).join('')}</tbody></table>` : `<h3>Locations prioritized for field checking</h3><p>No ${e(report.unit)} have a recorded displayed value at or above ${percent(report.priorityThreshold)}. This does not establish absence of pests.</p>`
  const sourcesHtml = report.initialSources?.length ? `<div class="table-intro"><h3>Initial source evidence and presence assumptions</h3>
    <p class="caption muted">Activity and badges describe the representative run. An assumed source is not a confirmed field observation.</p></div>
    <table class="sources-table"><thead><tr><th scope="col">Location ID</th><th scope="col">Recorded status</th><th scope="col">Source basis</th><th scope="col">Presence chance</th><th scope="col">Active</th></tr></thead><tbody>${report.initialSources.map((source) => `<tr><td>${value(source.tree_id ?? source.id ?? source.source_id ?? 'Ground source')}</td><td>${humanize(source.status)}</td><td>${humanize(source.label || source.origin || 'Not recorded')}<small class="cell-note">${source.assumed ? 'Assumed presence' : 'Recorded / selected source'}</small></td><td class="numeric">${percent(source.probability)}</td><td>${source.active === false ? 'No' : 'Yes'}</td></tr>`).join('')}</tbody></table>` : '<h3>Initial source evidence</h3><p>No source detail was saved with this run.</p>'
  const zonesHtml = report.zoneEntries?.length ? `<h3>Saved orchard and scenario zones</h3>
    <table><thead><tr><th scope="col">Zone</th><th scope="col">Type / setting</th><th scope="col">Recorded trees in area</th><th scope="col">Maximum ${frequency ? 'frequency' : 'score'}</th></tr></thead><tbody>${report.zoneEntries.map((entry) => `<tr><td>${value(entry.label)}</td><td>${value(entry.typeLabel)}${entry.detail ? `<small class="cell-note">${humanize(entry.detail)}</small>` : ''}</td><td class="numeric">${value(entry.treeCount)}</td><td class="numeric">${percent(entry.peakRisk)}</td></tr>`).join('')}</tbody></table>` : '<h3>Saved orchard and scenario zones</h3><p>No zone boundaries were saved with this simulation.</p>'
  const timelineHtml = report.timeline?.length ? `<div class="table-intro"><h3>Progression of the representative run</h3>
    <p class="caption muted">Selected saved hours; new infestation is for that individual step. Across-run frequencies describe final outcomes.</p></div>
    <table><thead><tr><th scope="col">Elapsed hour</th><th scope="col">Forecast time (Philippine time)</th><th scope="col">Infested ${e(report.unit)}</th><th scope="col">New in that step</th></tr></thead><tbody>${report.timeline.map((frame) => `<tr><td class="numeric">${value(frame.hour)}</td><td>${date(frame.datetime ?? frame.weather?.datetime)}</td><td class="numeric">${value(frame.n_infested)}</td><td class="numeric">${value(frame.n_new)}</td></tr>`).join('')}</tbody></table>` : ''
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${e(report.orchardName)} — Orchard pest simulation record</title>
<style>
@page {
  size: A4 portrait; margin: 14mm 13mm 18mm;
  @bottom-left { content: ${cssString(`MangoPoint · Run ${String(report.runId).slice(0, 40)}`)}; font: 8pt Arial,sans-serif; color: #56675f; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt Arial,sans-serif; color: #56675f; }
}
* { box-sizing: border-box; }
body { margin: 0; color: #24352d; background: #e9eeeb; font: 10pt/1.45 Arial,Helvetica,sans-serif; }
.toolbar { position: sticky; top: 0; z-index: 2; padding: 12px 20px; text-align: center; background: #173e2d; color: #fff; font-size: 10pt; }
.toolbar button { border: 0; border-radius: 4px; padding: 9px 16px; margin-right: 12px; font: inherit; font-weight: 700; cursor: pointer; background: #fff; color: #173e2d; }
.sheet { width: 210mm; margin: 18px auto; padding: 14mm 13mm 15mm; background: #fff; box-shadow: 0 3px 16px #183c2520; }
.cover-header { display: flex; align-items: center; gap: 13px; padding-bottom: 14px; border-bottom: 3px solid #1b4332; }
.cover-header img { width: 46px; height: 46px; object-fit: contain; }
.brand { font-size: 11pt; font-weight: 700; color: #1b4332; letter-spacing: .4px; }
.eyebrow { text-transform: uppercase; letter-spacing: 1.5px; font-size: 8pt; font-weight: 700; color: #617368; }
h1 { margin: 4px 0; font-size: 24pt; line-height: 1.15; letter-spacing: -.5px; color: #153e2b; }
h2 { margin: 0; font-size: 17pt; line-height: 1.25; color: #173e2d; }
h3 { margin: 16px 0 7px; font-size: 11pt; color: #173e2d; break-after: avoid; }
p { margin: 6px 0; } .muted { color: #617368; } .caption { font-size: 8.5pt; line-height: 1.4; }
.orchard-name { margin: 13px 0 3px; font-size: 16pt; font-weight: 700; overflow-wrap: anywhere; }
.record-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 20px; margin: 12px 0 17px; }
.record-field { min-width: 0; } dt { font-size: 8pt; color: #617368; margin: 0 0 2px; } dd { margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.section-title { display: flex; align-items: flex-start; gap: 12px; margin: 17px 0 12px; break-after: avoid; }
.section-number { color: #668371; font-size: 10pt; font-weight: 700; line-height: 24px; }
.section-title p { font-size: 9pt; margin: 4px 0 0; }
.metrics { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin: 12px 0; break-inside: avoid; }
.metric { padding: 12px; border: 1px solid #d2dfd7; background: #f3f7f4; border-top: 3px solid #397558; }
.metric span { display: block; font-size: 8.5pt; color: #50665a; }
.metric strong { display: block; margin: 4px 0; font-size: 25pt; line-height: 1.1; color: #153e2b; }
.metric small { display: block; font-size: 8pt; color: #617368; }
.outcome-line { padding: 9px 11px; border-left: 3px solid #84a68f; background: #f5f8f6; font-size: 9pt; }
.interpretation { margin: 13px 0; padding: 10px 12px; border: 1px solid #d2dfd7; background: #fafcfb; }
.interpretation strong { display: block; margin-bottom: 3px; font-size: 9pt; }
.interpretation p { font-size: 9pt; margin: 3px 0; }
.running-heading { display: flex; align-items: baseline; gap: 12px; padding-bottom: 8px; border-bottom: 2px solid #1b4332; color: #617368; font-size: 8pt; }
.running-heading strong { color: #1b4332; font-size: 11pt; }
.record-ref { margin-left: auto; max-width: 95mm; text-align: right; overflow-wrap: anywhere; }
.map-figure { margin: 0; break-inside: avoid; }
.map { display: block; width: 100%; height: 165mm; object-fit: contain; border: 1px solid #d2dfd7; background: #f5f7f5; }
figcaption { padding-top: 5px; font-size: 7.5pt; color: #617368; overflow-wrap: anywhere; }
.legend { display: flex; flex-wrap: wrap; gap: 7px 14px; margin: 7px 0 9px; font-size: 8pt; }
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.legend i, .band-swatch { display: inline-block; width: 9px; height: 9px; border: 1px solid #566b60; flex-shrink: 0; }
.band-swatch { margin-right: 7px; } .marker-legend i { border-radius: 50%; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 9pt; table-layout: fixed; }
th, td { padding: 7px 9px; text-align: left; vertical-align: top; border-bottom: 1px solid #d8e2dc; overflow-wrap: anywhere; }
th { font-size: 8pt; font-weight: 700; color: #476052; background: #eef4f0; }
tbody tr:nth-child(even) td { background: #fafcfb; }
thead { display: table-header-group; } tr { break-inside: avoid; }
.numeric { text-align: right; font-variant-numeric: tabular-nums; }
.priority-table th:nth-child(1) { width: 12%; } .priority-table th:nth-child(2) { width: 25%; } .priority-table th:nth-child(3) { width: 23%; } .priority-table th:nth-child(4) { width: 40%; }
.sources-table th:nth-child(1) { width: 12%; } .sources-table th:nth-child(2) { width: 20%; } .sources-table th:nth-child(3) { width: 36%; } .sources-table th:nth-child(4) { width: 20%; } .sources-table th:nth-child(5) { width: 12%; }
.risk-distribution td:first-child { width: 70%; }
.compact { font-size: 9pt; } .compact th, .compact td { padding: 7px; }
.cell-note { display: block; font-size: 8pt; color: #617368; margin-top: 2px; }
.table-intro { break-inside: avoid; break-after: avoid; }
.economic-section { break-inside: avoid; }
.coordinates { font-size: 8pt; font-variant-numeric: tabular-nums; }
.scenario-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 20px; }
.weather-strip { padding: 9px 12px; border: 1px solid #d8e2dc; margin: 10px 0; font-size: 8.5pt; }
.weather-values { display: flex; flex-wrap: wrap; gap: 5px 14px; margin-top: 5px; }
.record-notes { margin-top: 14px; }
.notes-content { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; padding: 8px 0; border-top: 1px solid #d8e2dc; }
.writing-lines { height: 24mm; background: repeating-linear-gradient(to bottom, transparent 0,transparent 7.6mm,#d8e2dc 7.6mm,#d8e2dc 7.8mm); }
.signatures { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-top: 22px; break-inside: avoid; }
.signature-line { height: 9mm; border-bottom: 1px solid #8ba494; }
.signature-name { font-size: 9pt; margin-top: 5px; } .signature-date { font-size: 8pt; color: #617368; margin-top: 5px; }
.document-end { margin-top: 20px; padding-top: 9px; border-top: 1px solid #d8e2dc; font-size: 8pt; color: #617368; break-before: avoid; break-inside: avoid; }
@media print {
  body { background: #fff; } .toolbar { display: none; }
  .sheet { width: auto; margin: 0; padding: 0; box-shadow: none; break-before: page; }
  .sheet:first-child { break-before: auto; }
  .map, .metric, th, .legend i, .band-swatch, .writing-lines { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  p { orphans: 3; widows: 3; }
}
@media screen and (max-width: 820px) { .sheet { width: calc(100% - 24px); padding: 22px; } .map { height: 130mm; } .record-grid, .scenario-grid { gap: 8px 14px; } h1 { font-size: 21pt; } }
</style></head><body>
<div class="toolbar"><button type="button" onclick="window.print()">Print / Save as PDF</button><span>A4 portrait · use 100% scale and turn off browser headers and footers.</span></div>
<main>
<section class="sheet summary-sheet" aria-label="Summary">
  <header class="cover-header">${imageLogo ? `<img src="${imageLogo}" alt="MangoPoint">` : ''}<div><div class="brand">MangoPoint</div><div class="eyebrow">Orchard management record</div><h1>Pest simulation report</h1></div></header>
  <div class="orchard-name">${e(report.orchardName)}</div>
  <p class="muted">${e(report.pestLabel)} · ${e(report.label)} · ${value(report.hours)}-hour scenario</p>
  <dl class="record-grid">
    ${pair('Record reference', reference)}${pair('Report generated · Philippine time', date(report.generatedAt))}
    ${pair('Prepared by', details.preparedBy)}${pair('Organization / office', details.organization)}
    ${pair('Forecast begins · Philippine time', date(report.forecastStart))}${pair('Reported forecast time · Philippine time', date(report.reportedAt))}
  </dl>
  ${title('01', 'Results at a glance', frequency ? `Final infestation frequency across ${runs} runs` : 'Results from one representative realization')}
  <div class="metrics">${metric(`Infested ${report.unit}${frequency ? ' (representative run)' : ''}`, report.infested, 'Simulated outcome, not a field count')}${metric(`Maximum ${metricName}`, percent(report.peak))}${metric(`${report.unit} at ≥50% ${frequency ? 'frequency' : 'score'}`, report.highRisk, 'Screening priority for field checking')}</div>
  <p class="outcome-line">${value(report.total)} simulated ${e(report.unit)} · Initially infested: ${value(report.initialInfested)} · Newly established by this hour: ${value(report.newlyInfested)}</p>
  <h3>Distribution of displayed map values</h3>
  <table class="risk-distribution"><thead><tr><th scope="col">${frequency ? 'Infestation frequency' : 'One-run risk score'}</th><th scope="col" class="numeric">${report.unit === 'trees' ? 'Trees' : 'Cells'}</th></tr></thead><tbody>${riskRows}<tr><td>Excluded or without a recorded value</td><td class="numeric">${value(report.unavailableRisk)}</td></tr></tbody></table>
  <div class="interpretation"><strong>How to interpret this record</strong><p>${frequency ? 'Frequency is the share of repeated runs with infestation. A tree infected in one run need not have a 100% across-run frequency.' : 'A one-run score describes this realization. Established infestation is shown as 100%; that is not a calibrated probability across repeated runs.'}</p><p>${uncertaintyText}</p><p>Weather, known stages and management stay fixed; uncertain sources and establishment may vary. Simulated outcomes require field verification. Repeated-run ranges are not calibrated confidence intervals.</p></div>
</section>
<section class="sheet map-sheet" aria-label="Orchard map">
  ${header('Orchard map')}${title('02', 'Spatial assessment', `${report.label} · ${report.mapDescription}`)}
  <figure class="map-figure"><img class="map" src="${mapImage}" alt="${e(report.label)} orchard map with heatmap, tree markers and saved zones"><figcaption>${e(snapshot.attribution || 'Attribution not recorded')} · North is up. Zone outlines use the saved simulation inputs.</figcaption></figure>
  <h3>${frequency ? 'Infestation frequency across runs' : 'One-run risk score'}</h3><div class="legend">${legend(frequency ? frequencyLegend : riskLegend)}</div>
  <h3>Special markers and source badges</h3><div class="legend marker-legend">${legend(markerLegend)}</div>
  <p class="caption muted">Heat shading interpolates values between modeled locations using fixed ground distances. Markers anchor the values at each location. Bagged and dead trees retain their state colors. Source badges describe one representative run; an assumed source is not a confirmed observation.</p>
</section>
<section class="sheet record-sheet" aria-label="Scenario and follow-up record">
  ${header('Scenario & follow-up')}${title('03', 'Scenario and follow-up record')}
  <dl class="scenario-grid">
    ${pair('Pest and orchard stage', `${report.pestLabel} · ${String(report.stage).replace(/_/g, ' ')}`)}
    ${pair('Modeling method', modelMode)}${pair('Scenario duration', `${report.hours ?? 'Not recorded'} hours`)}
    ${pair('Days since flowering', report.daysFlowering)}${pair('Weather source', report.weatherSource)}
    ${pair('Saved neighbor pressure', report.neighborPressure)}
    ${pair('History Infected reservoir presence', percent(report.sourceAssumptions?.history))}
    ${pair('Suspect current infection presence', percent(report.sourceAssumptions?.suspect))}
  </dl>
  <p class="caption muted">Source-presence percentages are scenario assumptions, not field-calibrated probabilities. A historical reservoir does not imply initially infested fruit.</p>
  ${report.modelInterpretation ? `<h3>Saved model assumptions</h3><dl class="scenario-grid">${Object.entries(report.modelInterpretation).map(([key, explanation]) => pair(humanize(key), explanation)).join('')}</dl>` : '<p class="caption muted">Detailed model assumptions were not recorded with this run. Refer to its saved model version.</p>'}
  <div class="weather-strip"><strong>Saved weather at the reported hour · ${date(report.reportedAt)}</strong><div class="weather-values">${weatherValues.map(([label, field, unit]) => `<span>${e(label)}: <strong>${field == null ? 'Not recorded' : `${value(field)} ${unit}`}</strong></span>`).join('')}</div>${provenance.fallback_reason ? `<p>Weather fallback: ${value(provenance.fallback_reason)}</p>` : ''}</div>
  ${economicHtml}
  ${notes('Field observations / reviewer’s notes', details.fieldNotes)}
  ${notes('Planned actions / follow-up', details.plannedActions)}
  <div class="signatures"><div><div class="signature-line"></div><div class="signature-name">Prepared by: ${details.preparedBy ? e(details.preparedBy) : '________________________'}</div><div class="signature-date">Signature / date: ________________________</div></div><div><div class="signature-line"></div><div class="signature-name">Reviewed by: ${details.reviewedBy ? e(details.reviewedBy) : '________________________'}</div><div class="signature-date">Signature / date: ________________________</div></div></div>
  <p class="caption muted">Names and notes are entered by the report preparer. Signature fields are provided for record review.</p>
</section>
<section class="sheet appendix-sheet" aria-label="Supporting record">
  ${header('Supporting record')}${title('04', 'Supporting record', 'Saved inputs, source evidence and traceable model outputs')}
  <h3>Run identification and weather provenance</h3>
  <dl class="scenario-grid">
    ${pair('Run ID', report.runId)}${pair('Orchard ID', report.orchardId)}
    ${pair('Model version', report.modelVersion)}${pair('Random seed', report.seed)}
    ${pair('Run executed · Philippine time', date(report.startedAt))}${pair('Run completed · Philippine time', date(report.completedAt))}
    ${pair('Forecast ends · Philippine time', date(report.forecastEnd))}${pair('Simulation classification threshold', percent(report.simulationRiskThreshold))}
    ${pair('Report screening threshold', percent(report.priorityThreshold))}${pair('Weather provider', provenance.provider ?? provenance.source ?? report.weatherSource)}
    ${pair('Weather forecast anchor · Philippine time', date(provenance.anchor_time))}${pair('Weather retrieved · Philippine time', date(provenance.fetched_at))}
  </dl>
  <p class="caption muted">Execution time records when the model ran; forecast time records the weather period modeled. Missing information is marked “Not recorded.” The report screening threshold is separate from the simulation’s classification threshold.</p>
  ${priorityHtml}${sourcesHtml}${zonesHtml}${timelineHtml}
  <footer class="document-end">Record ${e(reference)} · Generated ${date(report.generatedAt)} (Philippine time) · Run ${e(report.runId)}<br>End of report · MangoPoint orchard pest simulation record</footer>
</section>
</main></body></html>`
}
