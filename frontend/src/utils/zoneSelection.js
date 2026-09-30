const METERS_PER_DEGREE_LAT = 111_320

export function pointInPolygon(point, polygon) {
  if (!Array.isArray(point) || !Array.isArray(polygon) || polygon.length < 3) return false
  const [x, y] = point.map(Number)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false
  let inside = false
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const [xi, yi] = polygon[index].map(Number)
    const [xj, yj] = polygon[previous].map(Number)
    const intersects = ((yi > y) !== (yj > y))
      && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || Number.EPSILON) + xi)
    if (intersects) inside = !inside
  }
  return inside
}

export function treeIdsInPolygon(treePoints = [], polygon = []) {
  return treePoints
    .filter((tree) => pointInPolygon([tree.lon, tree.lat], polygon))
    .map((tree) => String(tree.tree_id))
}

function distanceMeters(left, right) {
  const meanLat = ((Number(left[1]) + Number(right[1])) / 2) * Math.PI / 180
  const dx = (Number(left[0]) - Number(right[0])) * METERS_PER_DEGREE_LAT * Math.cos(meanLat)
  const dy = (Number(left[1]) - Number(right[1])) * METERS_PER_DEGREE_LAT
  return Math.hypot(dx, dy)
}

export function simplifyLassoCoordinates(coordinates = [], minimumSpacingMeters = 0.75) {
  const normalized = coordinates
    .filter((point) => Array.isArray(point) && point.length >= 2)
    .map((point) => [Number(point[0]), Number(point[1])])
    .filter(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat))
  if (normalized.length <= 3) return normalized

  const kept = [normalized[0]]
  for (const point of normalized.slice(1, -1)) {
    if (distanceMeters(point, kept.at(-1)) >= minimumSpacingMeters) kept.push(point)
  }
  const last = normalized.at(-1)
  if (distanceMeters(last, kept.at(-1)) > 0) kept.push(last)
  return kept
}

export function overlappingManagementZones(candidate, existingZones = [], treePoints = []) {
  const candidateIds = new Set(treeIdsInPolygon(treePoints, candidate?.coordinates || []))
  if (!candidateIds.size) return []
  return existingZones.filter((zone) => (
    treeIdsInPolygon(treePoints, zone.coordinates || []).some((treeId) => candidateIds.has(treeId))
  ))
}
