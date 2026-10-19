import test from 'node:test'
import assert from 'node:assert/strict'
import { emailValidationError, nameValidationError } from './inputValidation.js'

test('email validation accepts common address forms and rejects malformed domains and local parts', () => {
  for (const email of ['person+alerts@example.com', "o'connor@example.com", ' PERSON@example.co.uk ']) assert.equal(emailValidationError(email), '')
  for (const email of ['', 'a..b@example.com', '.a@example.com', 'a.@example.com', 'a@-example.com', 'a@example-.com',
    'a@example..com', 'a@example.com.', 'a b@example.com', 'a@localhost', 'a@@example.com', 'a'.repeat(65)+'@example.com']) {
    assert.notEqual(emailValidationError(email), '', email)
  }
})

test('name validation preserves international names and rejects markup, controls, and empty required values', () => {
  for (const name of ['María O’Neill', 'Juan Dela Cruz', 'Team 2']) assert.equal(nameValidationError(name), '')
  for (const name of ['', '   ', '<script>', '12345', 'Name\nTest']) assert.notEqual(nameValidationError(name), '')
  assert.equal(nameValidationError('  ', true), '')
})
