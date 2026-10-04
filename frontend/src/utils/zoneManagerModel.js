export function zoneActionsForType(type, {
  stageActions = {}, statusActions = {}, managementActions = {}, weedActions = {},
} = {}, legacy = false) {
  if (type === 'stage') return stageActions
  if (type === 'status') return statusActions
  if (type === 'management') return managementActions
  if (type === 'cecid' && !legacy) return weedActions
  return null
}

export function zoneScopeLabel(entry) {
  if (entry?.type !== 'stage' && entry?.type !== 'status') return ''
  return entry.scope === 'orchard' ? 'Orchard' : 'Scenario only'
}

export function zoneClearLabel(filter) {
  if (filter === 'all') return 'Clear all zones'
  if (filter === 'stage') return 'Clear stage zones'
  if (filter === 'status') return 'Clear status zones'
  if (filter === 'management') return 'Clear management zones'
  return 'Clear weed habitats'
}

export function zoneClearSummary(entries = []) {
  const clearable = entries.filter((entry) => !entry?.legacy)
  const persistent = clearable.filter((entry) => (
    entry.scope === 'orchard'
    || entry.type === 'management'
    || entry.type === 'cecid'
  ))
  return {
    total: clearable.length,
    persistent: persistent.length,
    scenario: clearable.length - persistent.length,
  }
}
