import test from 'node:test'
import assert from 'node:assert/strict'
import { filterOverviewRows, overviewTablePage } from './overviewTable.js'

const columns = [{ key: 'name', value: (row) => row.name }, { key: 'runs', value: (row) => row.runs }]

test('large summaries sort numeric totals before pagination without changing source rows', () => {
  const rows = Array.from({ length: 10003 }, (_, id) => ({ id, name: `Orchard ${id + 1}`, runs: id }))
  const sorted = filterOverviewRows(rows, columns, '', 'runs', 'desc')
  const view = overviewTablePage(sorted, 1, 25)
  assert.deepEqual(view.rows.map((row) => row.id), Array.from({ length: 25 }, (_, index) => 9977 - index))
  assert.deepEqual([view.first, view.last, view.total, view.pageCount], [26, 50, 10003, 401])
  assert.equal(rows[0].id, 0)
  assert.equal(rows.at(-1).id, 10002)
})

test('search matches names and counts regardless of case, and counts all matches before paging', () => {
  const rows = [
    { id: 'a', name: 'Alpha Orchard', runs: 0 }, { id: 'b', name: 'ALPHA Block', runs: 23 },
    { id: 'c', name: 'Beta', runs: 100 }, { id: 'd', name: null, runs: null },
  ]
  const matches = filterOverviewRows(rows, columns, '  aLpHa  ', 'name', 'asc')
  const view = overviewTablePage(matches, 0, 1)
  assert.equal(view.total, 2)
  assert.equal(view.rows[0].id, 'b')
  assert.equal(overviewTablePage(matches, 1, 1).rows[0].id, 'a')
  assert.deepEqual(filterOverviewRows(rows, columns, '100', 'runs', 'asc').map((row) => row.id), ['c'])
  assert.deepEqual(filterOverviewRows(rows, columns, 'no such orchard', 'name', 'asc'), [])
})

test('names use natural order and missing inventory stays last in both numeric sort directions', () => {
  const rows = [{ name: 'Orchard 10', runs: 10 }, { name: 'Archived', runs: null }, { name: 'Orchard 2', runs: 0 }]
  assert.deepEqual(filterOverviewRows(rows, columns, '', 'name', 'asc').map((row) => row.name),
    ['Archived', 'Orchard 2', 'Orchard 10'])
  assert.deepEqual(filterOverviewRows(rows, columns, '', 'runs', 'asc').map((row) => row.runs), [0, 10, null])
  assert.deepEqual(filterOverviewRows(rows, columns, '', 'runs', 'desc').map((row) => row.runs), [10, 0, null])
})

test('each page size reaches every record exactly once including the final partial page', () => {
  const rows = Array.from({ length: 103 }, (_, id) => ({ id }))
  for (const pageSize of [10, 25, 50]) {
    const ids = []
    const { pageCount } = overviewTablePage(rows, 0, pageSize)
    for (let page = 0; page < pageCount; page++) {
      const view = overviewTablePage(rows, page, pageSize)
      assert.ok(view.rows.length <= pageSize)
      ids.push(...view.rows.map((row) => row.id))
    }
    assert.deepEqual(ids, rows.map((row) => row.id))
    const last = overviewTablePage(rows, pageCount - 1, pageSize)
    assert.equal(last.last, 103)
    assert.equal(last.rows.length, 3)
  }
})

test('a refresh that shrinks or empties data clamps the old page instead of leaving a blank table', () => {
  const rows = [{ id: 'a' }, { id: 'b' }]
  const smaller = overviewTablePage(rows, 400, 10)
  assert.deepEqual(smaller.rows, rows)
  assert.deepEqual([smaller.page, smaller.pageCount, smaller.first, smaller.last], [0, 1, 1, 2])
  const empty = overviewTablePage([], 400, 50)
  assert.deepEqual([empty.page, empty.pageCount, empty.total, empty.first, empty.last], [0, 1, 0, 0, 0])
})
