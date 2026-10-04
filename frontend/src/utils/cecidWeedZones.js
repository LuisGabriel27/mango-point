function parseMaybeJson(value, fallback) {
  if (value == null) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch (_) {
    return fallback
  }
}

export function normalizeCecidWeedZones(value, defaultScope = 'orchard') {
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
        scope: zone?.scope === 'scenario' ? 'scenario' : defaultScope === 'orchard' ? 'orchard' : 'scenario',
      }
    })
    .filter(Boolean)
}

export function weedZonePayload(zones) {
  return normalizeCecidWeedZones(zones)
    .filter((zone) => zone.scope === 'orchard')
    .map((zone) => ({
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
      zones: [
        ...localZones.filter((zone) => zone.scope !== 'orchard'),
        ...normalizeCecidWeedZones(response?.data?.cecid_weed_zones ?? [], 'orchard'),
      ],
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
