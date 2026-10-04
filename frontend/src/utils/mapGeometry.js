function averageCoordinates(coordinates) {
  const points = coordinates
    .filter((coord) => Array.isArray(coord) && coord.length >= 2)
    .map((coord) => [Number(coord[0]), Number(coord[1])])
    .filter(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat))

  if (!points.length) return null

  const lon = points.reduce((sum, point) => sum + point[0], 0) / points.length
  const lat = points.reduce((sum, point) => sum + point[1], 0) / points.length
  return [lon, lat]
}

export function geometryCenter(geometry) {
  if (!geometry) return null

  if (geometry.type === 'Point') {
    const lon = Number(geometry.coordinates?.[0])
    const lat = Number(geometry.coordinates?.[1])
    return Number.isFinite(lon) && Number.isFinite(lat) ? [lon, lat] : null
  }

  if (geometry.type === 'MultiPoint' || geometry.type === 'LineString') {
    return averageCoordinates(geometry.coordinates || [])
  }

  if (geometry.type === 'Polygon') {
    const ring = geometry.coordinates?.[0] || []
    const openRing = ring.length > 1 && ring[0]?.[0] === ring.at(-1)?.[0] && ring[0]?.[1] === ring.at(-1)?.[1]
      ? ring.slice(0, -1)
      : ring
    return averageCoordinates(openRing)
  }

  if (geometry.type === 'MultiPolygon') {
    const outerRings = (geometry.coordinates || []).flatMap((polygon) => polygon?.[0] || [])
    return averageCoordinates(outerRings)
  }

  return null
}
