import { test } from 'node:test'
import assert from 'node:assert/strict'
import { SubmissionIdentity, callApi } from '../public/api.mjs'

test('identical retries keep the same ID; edited and new requests get a new ID', () => {
  let number = 0
  const identity = new SubmissionIdentity(() => `id-${++number}`)
  const first = identity.prepare({ organization: 'Example', message: 'Request a demonstration' })
  assert.equal(identity.prepare({ organization: 'Example', message: 'Request a demonstration' }).submission_id, first.submission_id)
  assert.notEqual(identity.prepare({ organization: 'Example', message: 'Discuss a license instead' }).submission_id, first.submission_id)
  identity.clear()
  assert.equal(identity.prepare({ organization: 'Example', message: 'Request a demonstration' }).submission_id, 'id-3')
})

test('API failures carry status, and success is never manufactured', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'This review changed.' }), { status: 409 })
    await assert.rejects(callApi('/access-requests'), error => error.status === 409 && error.message === 'This review changed.')
    globalThis.fetch = async () => new Response('unavailable', { status: 503 })
    await assert.rejects(callApi('/access-requests'), /temporarily unavailable/)
    globalThis.fetch = async () => new Response('', { status: 200 })
    await assert.rejects(callApi('/access-requests'), /incomplete response/)
    globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
    await assert.rejects(callApi('/access-requests'), /cannot reach/)
  } finally { globalThis.fetch = original }
})

test('request credentials go to the backend only in the authorization header', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(new URL(url).origin, 'https://mango-point-projects.vercel.app')
      assert.equal(options.headers.Authorization, 'Bearer test-token')
      assert.equal(options.credentials, 'omit')
      assert.equal(options.cache, 'no-store')
      return new Response(JSON.stringify({ requests: [] }), { status: 200 })
    }
    await callApi('/access-requests', { token: 'test-token' })
  } finally { globalThis.fetch = original }
})
