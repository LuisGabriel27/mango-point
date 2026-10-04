export async function waitForMapSnapshot(map, isReady, timeoutMs = 20000) {
  const start = Date.now()
  while (!isReady() || !map.loaded() || map.isMoving()) {
    if (Date.now() - start >= timeoutMs) {
      throw new Error('The map is still loading. Wait for the orchard image to appear, then try again.')
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
}

// MapLibre's canvas contains imagery, heatmaps and polygons. Its HTML tree
// markers must be added separately or they disappear from a printed map.
export function drawSnapshotMarkers(context, points, project) {
  for (const point of points) {
    const { x, y } = project([point.lon, point.lat])
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue
    context.save()
    context.beginPath()
    context.arc(x, y, 7, 0, Math.PI * 2)
    context.fillStyle = point.color
    context.fill()
    context.strokeStyle = '#ffffff'
    context.lineWidth = 2
    context.stroke()
    if (point.stage_color) {
      context.beginPath()
      context.arc(x, y, 10, 0, Math.PI * 2)
      context.strokeStyle = point.stage_color
      context.lineWidth = 2
      context.stroke()
    }
    if (point.cecid_source) {
      context.fillStyle = '#78350f'
      context.fillRect(x + 3, y - 16, 13, 13)
      context.fillStyle = '#ffffff'
      context.font = 'bold 10px Arial'
      context.textAlign = 'center'
      context.fillText('S', x + 9.5, y - 6)
    }
    context.restore()
  }
}

export function captureMapSnapshot(map, points, createCanvas = () => document.createElement('canvas')) {
  const source = map.getCanvas()
  const canvas = createCanvas()
  canvas.width = source.width
  canvas.height = source.height
  const context = canvas.getContext('2d')
  if (!context || !canvas.width || !canvas.height) throw new Error('The map image is not ready yet.')
  context.drawImage(source, 0, 0)
  const scale = source.width / source.clientWidth
  context.scale(scale, scale)
  drawSnapshotMarkers(context, points, (coordinate) => map.project(coordinate))
  // Report maps stay north-up, with rotation disabled.
  context.fillStyle = 'rgba(255,255,255,.94)'
  context.fillRect(source.clientWidth - 48, 12, 34, 48)
  context.fillStyle = '#1b4332'
  context.font = 'bold 22px Arial'
  context.textAlign = 'center'
  context.fillText('↑', source.clientWidth - 31, 38)
  context.font = 'bold 11px Arial'
  context.fillText('N', source.clientWidth - 31, 53)
  return {
    dataUrl: canvas.toDataURL('image/png'),
    attribution: map.getContainer().querySelector('.maplibregl-ctrl-attrib-inner')?.textContent?.trim() || 'MapLibre · © OpenStreetMap contributors · Tiles © Esri',
  }
}
