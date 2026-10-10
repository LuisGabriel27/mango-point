import { isUncertainSourceStatus, sourceProbability } from './sourcePresence.js'

const VALID_STAGES = new Set(['dormant', 'flowering', 'fruitlet', 'mature'])
const VALID_STATUSES = new Set([
  'healthy', 'infected', 'bagged', 'dead', 'history_infected', 'suspect',
])

function parseMaybeJson(value, fallback) {
  if (value == null) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch (_) {
    return fallback
  }
}

function normalizeZones(value, kind, defaultScope = 'scenario') {
  const zones = parseMaybeJson(value, [])
  if (!Array.isArray(zones)) return []
  const allowed = kind === 'stage' ? VALID_STAGES : VALID_STATUSES
  return zones.map((zone, index) => {
    const coordinates = parseMaybeJson(zone?.coordinates, [])
    const setting = String(zone?.[kind] ?? '')
    if (!Array.isArray(coordinates) || coordinates.length < 3 || !allowed.has(setting)) return null
    return {
      id: String(zone.id ?? `restored-${kind}-zone-${index + 1}`),
      [kind]: setting,
      ...(kind === 'status' && isUncertainSourceStatus(setting) && sourceProbability(zone.source_probability) != null
        ? { source_probability: sourceProbability(zone.source_probability) } : {}),
      coordinates,
      tree_count: Number.isFinite(Number(zone.tree_count)) ? Number(zone.tree_count) : 0,
      scope: zone.scope === 'scenario' ? 'scenario' : zone.scope === 'orchard' || defaultScope === 'orchard' ? 'orchard' : 'scenario',
    }
  }).filter(Boolean)
}

export function normalizeStageZones(value, defaultScope = 'scenario') {
  return normalizeZones(value, 'stage', defaultScope)
}

export function normalizeStatusZones(value, defaultScope = 'scenario') {
  return normalizeZones(value, 'status', defaultScope)
}

export function mergeStoredStatusZones(current, stored, orchardChanged = false) {
  if (orchardChanged) return stored
  const saved = new Map(stored.map((zone) => [zone.id, zone]))
  const existingIds = new Set(current.map((zone) => zone.id))
  return [
    ...current.map((zone) => zone.scope === 'orchard' ? saved.get(zone.id) : zone).filter(Boolean),
    ...stored.filter((zone) => !existingIds.has(zone.id)),
  ]
}

function persistedPayload(zones, kind) {
  return normalizeZones(zones, kind)
    .filter((zone) => zone.scope === 'orchard')
    .map((zone) => ({
      id: zone.id,
      [kind]: zone[kind],
      ...(zone.source_probability != null ? { source_probability: zone.source_probability } : {}),
      coordinates: zone.coordinates,
    }))
}

export function stageZonePayload(zones) {
  return persistedPayload(zones, 'stage')
}

export function statusZonePayload(zones) {
  return persistedPayload(zones, 'status')
}

