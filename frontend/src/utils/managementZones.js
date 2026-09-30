const ZONE_COLORS = ['#2563eb', '#7c3aed', '#0891b2', '#d97706', '#be123c', '#4f46e5']

function parseMaybeJson(value, fallback) {
  if (value == null) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch (_) {
    return fallback
  }
}

export function normalizeManagementZones(value) {
  const zones = parseMaybeJson(value, [])
  if (!Array.isArray(zones)) return []
  return zones
    .map((zone, index) => {
      const coordinates = parseMaybeJson(zone?.coordinates, [])
      if (!Array.isArray(coordinates) || coordinates.length < 3) return null
      const color = /^#[0-9a-f]{6}$/i.test(String(zone?.color || ''))
        ? String(zone.color)
        : ZONE_COLORS[index % ZONE_COLORS.length]
      return {
        id: String(zone?.id || `management-zone-${index + 1}`),
        label: String(zone?.label || `Zone ${index + 1}`).trim() || `Zone ${index + 1}`,
        color,
        coordinates,
        tree_count: Number(zone?.tree_count) || 0,
      }
    })
    .filter(Boolean)
}

export function managementZonePayload(zones) {
  return normalizeManagementZones(zones).map((zone) => ({
    id: zone.id,
    label: zone.label,
    color: zone.color,
    coordinates: zone.coordinates,
  }))
}

export async function saveManagementZones(orchardId, zones, updateOrchard) {
  const localZones = normalizeManagementZones(zones)
  try {
    const response = await updateOrchard(orchardId, {
      management_zones: managementZonePayload(localZones),
    })
    return {
      ok: true,
      zones: normalizeManagementZones(response?.data?.management_zones ?? localZones),
      response,
      error: null,
      message: '',
    }
  } catch (error) {
    return {
      ok: false,
      zones: localZones,
      response: null,
      error,
      message: error?.response?.data?.detail || error?.message || 'Could not save management zones.',
    }
  }
}
