import { treeIdsInPolygon } from './zoneSelection.js'
import { isUncertainSourceStatus, sourceProbability } from './sourcePresence.js'

export const ZONE_TYPE_OPTIONS = [
  { value: 'stage', label: 'Stage' },
  { value: 'status', label: 'Status' },
  { value: 'management', label: 'Management' },
  { value: 'cecid', label: 'Weed Habitat' },
]

const STAGE_COLORS = { dormant: '#64748b', flowering: '#ec4899', fruitlet: '#f59e0b', mature: '#16a34a' }
const STATUS_COLORS = {
  healthy: '#22c55e', infected: '#ef4444', bagged: '#3b82f6',
  dead: '#424242', history_infected: '#ff9800', suspect: '#9c27b0',
}
const WEED_COLORS = { sparse: '#4ade80', moderate: '#15803d', dense: '#14532d' }

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value || ''
}

export function buildZoneInventory({
  stageZones = [], statusZones = [], managementZones = [],
  cecidWeedZones = [], legacyCecidEmergenceZones = [],
  treePoints = null, stageOptions = [], statusOptions = [],
} = {}) {
  const groups = [
    { type: 'stage', zones: stageZones },
    { type: 'status', zones: statusZones },
    { type: 'management', zones: managementZones },
    { type: 'cecid', zones: cecidWeedZones },
    { type: 'cecid', zones: legacyCecidEmergenceZones, legacy: true },
  ]
  return groups.flatMap(({ type, zones, legacy = false }) => zones
    .filter((zone) => Array.isArray(zone.coordinates) && zone.coordinates.length >= 3)
    .map((zone, index) => {
      const typeLabel = ZONE_TYPE_OPTIONS.find((option) => option.value === type).label
      const label = zone.label || (legacy ? `Legacy emergence ${index + 1}` : `${typeLabel} zone ${index + 1}`)
      let detail = type === 'stage' ? optionLabel(stageOptions, zone.stage)
        : type === 'status' ? optionLabel(statusOptions, zone.status)
          : legacy ? 'Historical replay' : ''
      if (type === 'status' && isUncertainSourceStatus(zone.status) && sourceProbability(zone.source_probability) != null) {
        detail += ` · ${Math.round(zone.source_probability * 100)}% source presence`
      }
      const color = type === 'stage' ? STAGE_COLORS[zone.stage] || '#0f5132'
        : type === 'status' ? STATUS_COLORS[zone.status] || '#f59e0b'
          : type === 'management' ? zone.color || '#2563eb'
            : legacy ? '#64748b' : WEED_COLORS[zone.density] || '#15803d'
      return {
        key: `${type}:${legacy ? 'legacy:' : ''}${zone.id ?? index}`,
        type, typeLabel, zone, label, detail, color, legacy,
        scope: zone.scope === 'orchard' ? 'orchard' : 'scenario',
        // Saved area payloads omit tree_count. Derive it from the current orchard.
        treeCount: Array.isArray(treePoints)
          ? treeIdsInPolygon(treePoints, zone.coordinates).length
          : zone.tree_count ?? null,
      }
    }))
}

export function zoneInventoryCounts(entries) {
  const counts = { all: entries.length, stage: 0, status: 0, management: 0, cecid: 0 }
  for (const entry of entries) counts[entry.type] += 1
  return counts
}
