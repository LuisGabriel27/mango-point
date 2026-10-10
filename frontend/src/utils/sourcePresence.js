import { treeIdsInPolygon } from './zoneSelection.js'

export function isUncertainSourceStatus(status) {
  return status === 'history_infected' || status === 'suspect'
}

export function sourceProbability(value) {
  if (value == null || (typeof value === 'string' && value.trim() === '') || typeof value === 'boolean') return null
  const probability = Number(value)
  return Number.isFinite(probability) && probability >= 0 && probability <= 1 ? probability : null
}

// Later zones replace earlier zones. A tree edit may choose null explicitly to
// return to the scenario default, even when its containing zone has a value.
export function sourcePresenceOverrides(zones = [], treePoints = [], statuses = {}, individual = {}) {
  const zoneSettings = {}
  for (const zone of zones) {
    for (const id of treeIdsInPolygon(treePoints, zone.coordinates || [])) {
      zoneSettings[id] = { status: zone.status, probability: sourceProbability(zone.source_probability) }
    }
  }
  const result = {}
  for (const tree of treePoints) {
    const id = String(tree.tree_id)
    const zone = zoneSettings[id]
    const status = statuses[id] ?? zone?.status ?? tree.status
    if (!isUncertainSourceStatus(status)) continue
    const probability = Object.hasOwn(individual, id)
      ? sourceProbability(individual[id])
      : zone?.status === status ? zone.probability : null
    if (probability != null) result[id] = probability
  }
  return result
}
