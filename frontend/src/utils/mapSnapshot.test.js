import test from 'node:test'
import assert from 'node:assert/strict'
import { captureMapSnapshot, drawSnapshotMarkers, waitForMapSnapshot } from './mapSnapshot.js'

test('map export composites HTML tree markers over the WebGL imagery at the correct pixel ratio', () => {
  const calls = []
  const context = new Proxy({}, { get: (_target, method) => (...args) => calls.push([method, ...args]), set: () => true })
  const canvas = { getContext: () => context, toDataURL: () => 'data:image/png;base64,AAAA' }
  const source = { width: 1800, height: 1000, clientWidth: 900 }
  const map = {
    getCanvas: () => source,
    project: () => ({ x: 100, y: 200 }),
    getContainer: () => ({ querySelector: () => ({ textContent: 'Tiles © Esri' }) }),
  }
  const snapshot = captureMapSnapshot(map, [{ lon: 122, lat: 10, color: '#ef4444', cecid_source: true }], () => canvas)
  assert.equal(canvas.width, 1800)
  assert.equal(canvas.height, 1000)
  assert.deepEqual(calls[0], ['drawImage', source, 0, 0])
  assert.deepEqual(calls[1], ['scale', 2, 2])
  assert.ok(calls.some(([method, x, y, radius]) => method === 'arc' && x === 100 && y === 200 && radius === 7))
  assert.ok(calls.some(([method, text]) => method === 'fillText' && text === 'S'))
  assert.equal(snapshot.attribution, 'Tiles © Esri')
})

test('report includes active Fruit Fly reservoir and infection source badges', () => {
  const labels = []
  const context = new Proxy({}, {
    get: (_target, method) => (...args) => { if (method === 'fillText') labels.push(args[0]) },
    set: () => true,
  })
  drawSnapshotMarkers(context, [
    { lon: 122, lat: 10, color: '#22c55e', initialSource: { badge: 'R', assumed: true } },
    { lon: 122, lat: 10, color: '#b91c1c', initialSource: { badge: 'S', assumed: false } },
    { lon: 122, lat: 10, color: '#22c55e', initialSource: null },
  ], () => ({ x: 100, y: 200 }))
  assert.deepEqual(labels, ['R', 'S'])
})

test('capture waits for imagery and map rendering, and reports a timeout instead of exporting early', async () => {
  await waitForMapSnapshot({ loaded: () => true, isMoving: () => false }, () => true)
  await assert.rejects(waitForMapSnapshot({ loaded: () => false, isMoving: () => true }, () => false, 0), /still loading/)
})
