function parseMaybeJson(value, fallback) {
  if (value == null) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch (_) {
    return fallback
  }
}

export function normalizeCecidWeedZones(value) {
  const zones = parseMaybeJson(value, [])
  if (!Array.isArray(zones)) return []
  return zones
    .map((zone, index) => {
      const coordinates = parseMaybeJson(zone?.coordinates, [])
      if (!Array.isArray(coordinates) || coordinates.length < 3) return null
      const density = ['sparse', 'moderate', 'dense'].includes(String(zone?.density).toLowerCase())
        ? String(zone.density).toLowerCase()
        : 'moderate'
      return {
        id: zone.id ?? `weed-zone-${index + 1}`,
        label: zone.label || `Weed habitat ${index + 1}`,
        density,
        coordinates,
        tree_count: zone.tree_count ?? 0,
      }
    })
    .filter(Boolean)
}

export function weedZonePayload(zones) {
  return normalizeCecidWeedZones(zones).map((zone) => ({
    id: zone.id,
    label: zone.label,
    density: zone.density,
    coordinates: zone.coordinates,
  }))
}

export async function saveCecidWeedZones(orchardId, zones, updateOrchard) {
  const localZones = normalizeCecidWeedZones(zones)
  try {
    const response = await updateOrchard(orchardId, {
      cecid_weed_zones: weedZonePayload(localZones),
    })
    return {
      ok: true,
      zones: normalizeCecidWeedZones(response?.data?.cecid_weed_zones ?? localZones),
      response,
      error: null,
      message: '',
    }
  } catch (error) {
    return {
      ok: false,
      // Keep the optimistic local value so the same payload can be retried.
      zones: localZones,
      response: null,
      error,
      message: error?.response?.data?.detail || error?.message || 'Could not save weed habitats.',
    }
  }
}
