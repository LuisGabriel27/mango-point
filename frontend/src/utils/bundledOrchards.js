export const GUIMARAS_WONDERS_FARM_ID = 'guimaras-wonders-farm'

export const GUIMARAS_WONDERS_FARM_OVERLAY_COORDINATES = [
  [122.61086363208625, 10.63229086053964],
  [122.61419986820223, 10.63229086053964],
  [122.61419986820223, 10.629772719131637],
  [122.61086363208625, 10.629772719131637],
]

function hasTreeGeojson(value) {
  return value?.type === 'FeatureCollection'
    && Array.isArray(value.features)
    && value.features.length > 0
}

function hasOverlayCoordinates(value) {
  return Array.isArray(value)
    && value.length === 4
    && value.every((point) => (
      Array.isArray(point)
      && Number.isFinite(Number(point[0]))
      && Number.isFinite(Number(point[1]))
    ))
}

export function mergeBundledOrchards(records, bundledOrchard) {
  const source = Array.isArray(records) ? records : []
  if (!bundledOrchard?.orchard_id) return source

  const existingIndex = source.findIndex(
    (record) => record?.orchard_id === bundledOrchard.orchard_id,
  )
  if (existingIndex < 0) {
    return [...source, bundledOrchard].sort((left, right) => (
      String(left?.name ?? '').localeCompare(String(right?.name ?? ''))
    ))
  }

  const existing = source[existingIndex]
  const merged = {
    ...bundledOrchard,
    ...existing,
    geojson: hasTreeGeojson(existing.geojson)
      ? existing.geojson
      : bundledOrchard.geojson,
    orthophoto_coordinates: hasOverlayCoordinates(existing.orthophoto_coordinates)
      ? existing.orthophoto_coordinates
      : bundledOrchard.orthophoto_coordinates,
  }

  return source.map((record, index) => (index === existingIndex ? merged : record))
}
