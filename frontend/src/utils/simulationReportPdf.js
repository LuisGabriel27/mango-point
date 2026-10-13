import pdfEnginePath from 'html2pdf.js/dist/html2pdf.bundle.min.js?url'

// Keep the report's styles and the PDF renderer isolated from the dashboard.
// Loading the bundled renderer inside the frame preserves its own document
// context; no report content is posted to a server or third-party service.
export async function simulationReportPdf(html, report) {
  const frame = document.createElement('iframe')
  frame.setAttribute('aria-hidden', 'true')
  frame.setAttribute('title', 'Preparing PDF report')
  frame.tabIndex = -1
  frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:1024px;height:1123px;border:0;pointer-events:none;'
  try {
    await new Promise((resolve, reject) => {
      frame.onload = resolve
      frame.onerror = () => reject(new Error('Could not prepare the PDF document. Please try again.'))
      frame.srcdoc = html
      document.body.appendChild(frame)
    })
    const doc = frame.contentDocument
    const style = doc.createElement('style')
    style.textContent = `
      body { background: #fff; }
      .toolbar { display: none; }
      .sheet { width: 186mm; margin: 0; padding: 0; box-shadow: none; }
      .sheet + .sheet { break-before: page; }
    `
    doc.head.appendChild(style)
    const notes = doc.querySelector('.notes-grid')
    if (notes?.getBoundingClientRect().height > 200) {
      notes.style.display = 'block'
      for (const note of notes.children) note.style.breakInside = 'avoid'
    }
    await doc.fonts.ready
    await Promise.all([...doc.images].map((image) => image.decode()))
    // html2canvas does not implement object-fit. Use an explicit image size
    // inside the original map box so the orthophoto keeps its proportions.
    const map = doc.querySelector('img.map')
    if (map) {
      const { width, height } = map.getBoundingClientRect()
      const ratio = Math.min((width - 2) / map.naturalWidth, (height - 2) / map.naturalHeight)
      const box = doc.createElement('div')
      box.className = 'map'
      box.style.cssText = 'display:flex;align-items:center;justify-content:center;overflow:hidden;'
      map.replaceWith(box)
      map.className = ''
      map.style.cssText = `display:block;width:${map.naturalWidth * ratio}px;height:${map.naturalHeight * ratio}px;`
      box.appendChild(map)
    }
    await new Promise((resolve, reject) => {
      const script = doc.createElement('script')
      script.src = new URL(pdfEnginePath, document.baseURI).href
      script.onload = resolve
      script.onerror = () => reject(new Error('Could not load the PDF tools. Reconnect and try again, or use Print.'))
      doc.head.appendChild(script)
    })
    // The renderer checks arrays against its own window's Array constructor.
    const options = frame.contentWindow.JSON.parse(JSON.stringify({
      margin: [11, 12, 14, 12], image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, backgroundColor: '#ffffff', logging: false },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait', compress: true },
      pagebreak: { mode: ['css'], avoid: ['.section-heading', 'h3'] },
      enableLinks: false,
    }))
    const pdf = await frame.contentWindow.html2pdf().set(options)
      .from(doc.querySelector('main')).toPdf().get('pdf')
    const total = pdf.internal.getNumberOfPages()
    const reference = String(report.recordDetails?.reference || report.runId).slice(0, 70)
      .replace(/[^\x20-\x7e]/g, '-')
    pdf.setProperties({ title: `${report.orchardName} - Pest simulation report`, author: 'MangoPoint',
      subject: `${report.pestLabel} - ${report.runId}`, creator: 'MangoPoint' })
    for (let page = 1; page <= total; page++) {
      pdf.setPage(page)
      pdf.setFont('helvetica', 'normal')
      pdf.setFontSize(7)
      pdf.setTextColor('#617368')
      pdf.text(`MangoPoint - ${reference}`, 12, 289, { maxWidth: 150 })
      pdf.text(`Page ${page} / ${total}`, 198, 289, { align: 'right' })
    }
    const bytes = pdf.output('arraybuffer')
    if (new TextDecoder().decode(new Uint8Array(bytes, 0, 5)) !== '%PDF-') {
      throw new Error('Could not create a valid PDF. Please try again.')
    }
    return new Blob([bytes], { type: 'application/pdf' })
  } finally { frame.remove() }
}
