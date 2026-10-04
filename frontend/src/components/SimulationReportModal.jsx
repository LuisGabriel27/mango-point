import { useEffect, useMemo, useRef, useState } from 'react'
import RiskMap from './RiskMap'
import { buildSimulationReport, reportFilename, reportPercent, simulationReportHtml } from '../utils/simulationReport'
import { formatPhp } from '../utils/economicImpact'

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
  const dialogRef = useRef(null)
  const mapRef = useRef(null)
  const activeRef = useRef(true)
  const logoRef = useRef(null)
  const prepared = useMemo(() => {
    try { return { report: buildSimulationReport(run, { orchard, selection, displayed }) } }
    catch (failure) { return { error: failure.message } }
  }, [run, orchard, selection, displayed])
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
      if (event.key !== 'Tab') return
      const controls = [...dialogRef.current.querySelectorAll('button:not([disabled]), select:not([disabled]), [href]')]
        .filter((element) => element.offsetParent !== null)
      const first = controls[0], last = controls.at(-1)
      if (!first) { event.preventDefault(); return }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus()
      }
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
          <div><h2 id="simulation-report-title" className="orchard-modal-title">Print simulation report</h2><div className="small text-muted">{report?.orchardName || orchard?.name}</div></div>
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
            <p className="small mb-2">Includes the map, legend, zones, results and simulation settings. Choose <strong>Save as PDF</strong> in the print dialog, or download a report you can open offline.</p>
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
            <div className="small mt-2"><strong>{report.label}</strong> · {report.mapDescription} · Maximum map risk: {reportPercent(report.peak)} · Infested {report.unit}: {report.infested ?? 'Not recorded'}</div>
            {report.economic && (
              <div className="alert alert-success py-2 mt-2 mb-0 small">
                <strong>Potential savings with recommendations: {formatPhp(report.economic.estimated_savings)}</strong>
                <span className="d-block">Projected loss {formatPhp(report.economic.projected_loss)} · remaining loss {formatPhp(report.economic.remaining_loss)} · assumes {reportPercent(report.economic.recommendation_effectiveness)} of damage is prevented.</span>
              </div>
            )}
          </>}
          {(error || prepared.error) && <div className="alert alert-danger mt-2 mb-0" role="alert">{error || prepared.error}</div>}
        </div>
        <footer className="simulation-report-actions">
          <span className="small text-muted me-auto" role="status">{busy ? 'Preparing the map and report…' : 'A4 landscape · includes space for manager’s notes'}</span>
          <button type="button" className="btn btn-outline-success" disabled={!report || busy} onClick={() => exportReport('download')}>Download offline report</button>
          <button type="button" className="btn btn-success" disabled={!report || busy} onClick={() => exportReport('print')}><i className="bi bi-printer me-1" />Print / Save PDF</button>
        </footer>
      </section>
    </div>
  )
}
