import test from 'node:test'
import assert from 'node:assert/strict'
import { buildZoneInventory, zoneInventoryCounts } from '../utils/zoneInventory.js'
import { saveManagementZones } from '../utils/managementZones.js'
import { zoneActionsForType, zoneClearLabel, zoneClearSummary, zoneScopeLabel } from '../utils/zoneManagerModel.js'

const AREA = {
  id: 'zone-1', label: 'Zone 1', color: '#2563eb', tree_count: 0,
  coordinates: [[0, 0], [2, 0], [2, 2], [0, 2]],
}
const STATUS = {
  id: 'status-1', status: 'infected',
  coordinates: [[3, 0], [5, 0], [5, 2], [3, 2]],
}
const TREES = [
  { tree_id: 'a', lon: 0.5, lat: 0.5 },
  { tree_id: 'b', lon: 1.5, lat: 1.5 },
  { tree_id: 'c', lon: 4, lat: 1 },
]
const inventory = (changes = {}) => buildZoneInventory({
  managementZones: [AREA], statusZones: [STATUS], treePoints: TREES,
  statusOptions: [{ value: 'infected', label: 'Infected' }], ...changes,
})

test('one status outline and one management outline are both inventoried', () => {
  const entries = inventory()
  assert.deepEqual(zoneInventoryCounts(entries), {
    all: 2, stage: 0, status: 1, management: 1, cecid: 0,
  })
  assert.equal(entries.find((entry) => entry.type === 'status').label, 'Status zone 1')
  assert.equal(entries.find((entry) => entry.type === 'status').detail, 'Infected')
  assert.equal(entries.find((entry) => entry.type === 'status').treeCount, 1)
  assert.equal(entries.find((entry) => entry.type === 'management').treeCount, 2)
})

test('stage and status zones expose their lifetime and delete action', () => {
  const entries = inventory({
    stageZones: [{ ...AREA, stage: 'mature', scope: 'scenario' }],
    statusZones: [{ ...STATUS, scope: 'orchard' }],
  })
  const actions = {
    stageActions: { onDelete() {} },
    statusActions: { onDelete() {} },
  }
  assert.equal(zoneScopeLabel(entries.find((entry) => entry.type === 'stage')), 'Scenario only')
  assert.equal(zoneScopeLabel(entries.find((entry) => entry.type === 'status')), 'Orchard')
  assert.equal(typeof zoneActionsForType('stage', actions).onDelete, 'function')
  assert.equal(typeof zoneActionsForType('status', actions).onDelete, 'function')
  assert.equal(zoneClearLabel('stage'), 'Clear stage zones')
  assert.equal(zoneClearLabel('status'), 'Clear status zones')
})

test('saved management areas count current orchard trees when the API omits tree_count', async () => {
  const saved = await saveManagementZones('orchard-a', [AREA], async (_id, payload) => ({ data: payload }))
  const entries = inventory({ managementZones: saved.zones })
  assert.equal(entries.find((entry) => entry.type === 'management').treeCount, 2)
  assert.equal(saved.zones[0].tree_count, 0)
})

test('zone types with the same ID remain separate and legacy outlines are read-only', () => {
  const entries = inventory({
    stageZones: [{ ...AREA, stage: 'mature' }],
    cecidWeedZones: [{ ...AREA, label: 'Shelter', density: 'dense' }],
    legacyCecidEmergenceZones: [{ ...AREA, label: 'Old emergence' }],
  })
  assert.equal(new Set(entries.map((entry) => entry.key)).size, 5)
  assert.deepEqual(zoneInventoryCounts(entries), { all: 5, stage: 1, status: 1, management: 1, cecid: 2 })
  const legacy = entries.find((entry) => entry.legacy)
  assert.equal(zoneActionsForType(legacy.type, { weedActions: { onDelete() {} } }, true), null)
})

test('removing zones updates counts and incomplete boundaries are omitted', () => {
  assert.deepEqual(zoneInventoryCounts(inventory({ statusZones: [] })), {
    all: 1, stage: 0, status: 0, management: 1, cecid: 0,
  })
  const entries = inventory({ managementZones: [{ ...AREA, coordinates: [[0, 0], [1, 1]] }] })
  assert.equal(entries.length, 1)
  assert.equal(entries[0].type, 'status')
})

test('clear-all summary separates temporary and persistent zones', () => {
  const entries = inventory({
    managementZones: [{ ...AREA, scope: 'orchard' }],
    stageZones: [{ ...AREA, stage: 'mature', scope: 'scenario' }],
    statusZones: [{ ...STATUS, scope: 'orchard' }],
    cecidWeedZones: [{ ...AREA, label: 'Shelter', density: 'dense', scope: 'orchard' }],
    legacyCecidEmergenceZones: [{ ...AREA, label: 'Historical outline' }],
  })

  assert.deepEqual(zoneClearSummary(entries), {
    total: 4,
    persistent: 3,
    scenario: 1,
  })
})
