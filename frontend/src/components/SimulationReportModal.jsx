import { useEffect, useMemo, useRef, useState } from 'react'
import RiskMap from './RiskMap'
import { buildSimulationReport, reportFilename, reportPercent, simulationReportHtml } from '../utils/simulationReport'
import { formatPhp } from '../utils/economicImpact'

const RECORD_FIELDS = [
  { name: 'reference', label: 'Report reference', maxLength: 120 },
  { name: 'preparedBy', label: 'Prepared by', maxLength: 160 },
  { name: 'organization', label: 'Organization / office', maxLength: 200 },
  { name: 'reviewedBy', label: 'Reviewed by', maxLength: 160 },
]
const NOTE_FIELDS = [
  { name: 'fieldNotes', label: 'Field notes', maxLength: 3000 },
  { name: 'plannedActions', label: 'Planned actions / follow-up', maxLength: 3000 },
]
const EMPTY_RECORD_DETAILS = {
  reference: '', preparedBy: '', organization: '', reviewedBy: '', fieldNotes: '', plannedActions: '',
}

export function ReportRecordFields({ recordDetails, onChange, disabled = false }) {
  const update = (name, maxLength) => (event) => {
    const nextValue = event.target.value.slice(0, maxLength)
    onChange((current) => ({ ...current, [name]: nextValue }))
  }
  return <>
    <div className="simulation-report-fields">
      {RECORD_FIELDS.map(({ name, label, maxLength }) => (
        <label key={name} className="simulation-report-field" htmlFor={`report-${name}`}>
          <span>{label}</span>
          <input id={`report-${name}`} name={name} type="text" className="form-control form-control-sm"
            maxLength={maxLength} value={recordDetails[name]} disabled={disabled}
            onChange={update(name, maxLength)} />
        </label>
      ))}
    </div>
    <div className="simulation-report-note-fields">
      {NOTE_FIELDS.map(({ name, label, maxLength }) => (
        <label key={name} className="simulation-report-field" htmlFor={`report-${name}`}>
          <span>{label}</span>
          <textarea id={`report-${name}`} name={name} className="form-control form-control-sm" rows={3}
            maxLength={maxLength} value={recordDetails[name]} disabled={disabled}
            onChange={update(name, maxLength)} />
        </label>
      ))}
    </div>
  </>
}

export function handleReportTabKey(event, dialog, activeElement) {
  if (event.key !== 'Tab') return
  const controls = [...dialog.querySelectorAll('button:not([disabled]), select:not([disabled]), input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), [href]')]
    .filter((element) => element.offsetParent !== null)
  const first = controls[0], last = controls.at(-1)
  if (!first) { event.preventDefault(); return }
  if (event.shiftKey && (activeElement === first || activeElement === dialog)) {
    event.preventDefault(); last.focus()
  } else if (!event.shiftKey && activeElement === last) {
    event.preventDefault(); first.focus()
  }
}

async function loadReportLogo() {
  try {
    const response = await fetch('/brand/mangopoint-logo-v2.png')
    if (!response.ok) return ''
    const blob = await response.blob()
    return await new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = () => resolve('')
      reader.readAsDataURL(blob)
    })
  } catch (_) { return '' }
}

export default function SimulationReportModal({ run, orchard, displayed, onClose }) {
  const [selection, setSelection] = useState('final')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [recordDetails, setRecordDetails] = useState(EMPTY_RECORD_DETAILS)
  const dialogRef = useRef(null)
  const mapRef = useRef(null)
  const activeRef = useRef(true)
  const logoRef = useRef(null)
  const prepared = useMemo(() => {
    try { return { report: buildSimulationReport(run, { orchard, selection, displayed, recordDetails }) } }
    catch (failure) { return { error: failure.message } }
  }, [run, orchard, selection, displayed, recordDetails])
  const report = prepared.report

  useEffect(() => {
    activeRef.current = true
    logoRef.current = loadReportLogo()
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialogRef.current?.focus()
    const handleKeys = (event) => {
      if (event.key === 'Escape') onClose()
      handleReportTabKey(event, dialogRef.current, document.activeElement)
    }
    document.addEventListener('keydown', handleKeys)
    return () => {
      activeRef.current = false
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeys)
      previousFocus?.focus?.()
    }
  }, [onClose])

  const exportReport = async (action) => {
    if (!report || busy) return
    // Open synchronously from the click so browser popup protection permits it.
    const printWindow = action === 'print' ? window.open('', '_blank') : null
    if (action === 'print' && !printWindow) {
      setError('Allow the report tab to open, or download the offline report and print it from there.')
      return
    }
    if (printWindow) {
      printWindow.opener = null
      printWindow.document.title = 'Preparing MangoPoint report'
      printWindow.document.body.textContent = 'Preparing the map and simulation report…'
    }
    setBusy(true)
    setError('')
    try {
      const snapshot = await mapRef.current.captureImage()
      const logo = await logoRef.current
      if (!activeRef.current) { printWindow?.close(); return }
      const html = simulationReportHtml(report, snapshot, logo)
      if (printWindow) {
        if (printWindow.closed) return
        printWindow.document.open()
        printWindow.document.write(html)
        printWindow.document.close()
        await Promise.all([...printWindow.document.images].map((image) => image.decode()))
        printWindow.focus()
        printWindow.print()
      } else {
        const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
        const link = document.createElement('a')
        link.href = url
        link.download = reportFilename(report)
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
    } catch (failure) {
      printWindow?.close()
      if (activeRef.current) setError(failure.message || 'Could not prepare the report. Please try again.')
    } finally {
      if (activeRef.current) setBusy(false)
    }
  }

  return (
    <div className="orchard-modal-backdrop simulation-report-backdrop">
      <section ref={dialogRef} className="orchard-modal-dialog simulation-report-dialog" role="dialog" aria-modal="true" aria-labelledby="simulation-report-title" tabIndex={-1}>
        <header className="orchard-modal-header">
          <div><h2 id="simulation-report-title" className="orchard-modal-title">Prepare simulation report</h2><div className="small text-muted">{report?.orchardName || orchard?.name}</div></div>
          <button type="button" className="btn btn-sm btn-light" aria-label="Close report" onClick={onClose}><i className="bi bi-x-lg" /></button>
        </header>
        <div className="simulation-report-body">
          {report && <>
            <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
              <label className="d-flex align-items-center gap-2 small fw-semibold">Report result
                <select className="form-select form-select-sm" value={selection} disabled={busy} onChange={(event) => { setSelection(event.target.value); setError('') }}>
                  <option value="final">Final result</option>
                  {displayed?.geojson?.features?.length > 0 && <option value="displayed">{displayed.frame ? `Displayed hour (${displayed.frame.hour})` : 'Currently displayed result'}</option>}
                </select>
              </label>
              <span className="small text-muted">{report.pestLabel} · {report.hours} h simulation</span>
            </div>
            <p className="simulation-report-intro">An A4 portrait record of the orchard map, modeled results, source assumptions and simulation settings. Add the record details below, then choose <strong>Save as PDF</strong> in the print dialog.</p>
            <section className="simulation-report-record" aria-labelledby="simulation-report-record-title">
              <div className="simulation-report-section-heading">
                <h3 id="simulation-report-record-title">Record details</h3>
                <span>Optional · included in this export</span>
              </div>
              <ReportRecordFields recordDetails={recordDetails} onChange={setRecordDetails} disabled={busy} />
            </section>
            <section className="simulation-report-preview" aria-labelledby="simulation-report-preview-title">
              <div className="simulation-report-section-heading">
                <h3 id="simulation-report-preview-title">Map and results</h3>
                <span>{report.label}</span>
              </div>
              <div className="simulation-report-map">
              <RiskMap
                key={`${report.runId}:${selection}`}
                ref={mapRef}
                reportMode
                geojson={report.geojson}
                baseGeojson={report.baseGeojson}
                stageZones={report.stageZones}
                statusZones={report.statusZones}
                managementZones={report.managementZones}
                cecidWeedZones={report.cecidWeedZones}
                legacyCecidEmergenceZones={report.legacyCecidEmergenceZones}
                orthophotoOverlay={report.orthophotoOverlay}
                viewportKey={report.orchardId}
                fitToOrthophoto={report.orthophotoOverlay !== false}
                pestType={report.pest}
                cecidMapMode={report.mapMode}
              />
              </div>
            <div className="small mt-2"><strong>{report.label}</strong> · {report.mapDescription} · Maximum map {report.mapMode === 'likelihood' ? 'frequency' : 'risk'}: {reportPercent(report.peak)} · Infested {report.unit}{report.mapMode === 'likelihood' ? ' in one run' : ''}: {report.infested ?? 'Not recorded'}</div>
            {Number(report.uncertainty?.runs) > 1 && <p className="small text-muted mb-0">{report.uncertainty.runs} runs: {report.uncertainty.minimum}–{report.uncertainty.maximum} infested {report.unit}, median {report.uncertainty.median}. Tree states and source badges describe one run; across-runs shading shows infestation frequency.</p>}
            {report.economic && (
              <div className="simulation-report-planning-estimate">
                <strong>Economic planning estimate</strong>
                <span>Damage exposure: {formatPhp(report.economic.projected_loss)} · modeled loss avoided: {formatPhp(report.economic.estimated_savings)} · remaining exposure: {formatPhp(report.economic.remaining_loss)}.</span>
                <span>Assumes {reportPercent(report.economic.recommendation_effectiveness)} of damage is prevented. Treatment and labor costs are excluded; actual outcomes depend on field conditions.</span>
              </div>
            )}
            </section>
          </>}
          {(error || prepared.error) && <div className="alert alert-danger mt-2 mb-0" role="alert">{error || prepared.error}</div>}
        </div>
        <footer className="simulation-report-actions">
          <span className="small text-muted me-auto" role="status">{busy ? 'Preparing the map and report…' : 'A4 portrait · orchard simulation record'}</span>
          <button type="button" className="btn btn-outline-success" disabled={!report || busy} onClick={() => exportReport('download')}>Download offline report</button>
          <button type="button" className="btn btn-success" disabled={!report || busy} onClick={() => exportReport('print')}><i className="bi bi-printer me-1" />Print / Save PDF</button>
        </footer>
      </section>
    </div>
  )
}
