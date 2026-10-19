import test from 'node:test'
import assert from 'node:assert/strict'
import { apiErrorMessage } from './api.js'

test('unreachable production servers give actionable connection guidance', () => {
  const message = apiErrorMessage({ code: 'ERR_NETWORK', message: 'Network Error' })
  assert.match(message, /Cannot reach the MangoPoint server/)
  assert.match(message, /start_production\.bat/)
})

test('proxy outages hide gateway HTML while preserving API validation details', () => {
  assert.match(apiErrorMessage({ response: { status: 502, data: '<html>Bad gateway</html>' } }), /temporarily unavailable/)
  assert.equal(apiErrorMessage({ response: { status: 503, data: { detail: 'Database unavailable' } } }), 'Database unavailable')
  assert.equal(apiErrorMessage({ response: { status: 401, data: { detail: 'Invalid credentials' } } }), 'Invalid credentials')
})

test('a failed pinned login request explains its issuing API rather than a changed connection target', () => {
  const message = apiErrorMessage({ code: 'ERR_NETWORK', config: { authTarget: { mode: 'local' } } })
  assert.match(message, /on this device/)
  assert.doesNotMatch(message, /server operator/)
})
