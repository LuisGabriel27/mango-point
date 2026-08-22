import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DEFAULT_SIDEBAR_WORKFLOW,
  nextSidebarWorkflowId,
  parseStoredSidebarCollapsed,
  sidebarWorkflowForEvent,
} from './sidebarWorkspace.js'

test('simulation workspace defaults to Simulate', () => {
  assert.equal(DEFAULT_SIDEBAR_WORKFLOW, 'simulate')
})

test('workflow keyboard navigation wraps and supports Home and End', () => {
  assert.equal(nextSidebarWorkflowId('setup', 'ArrowLeft'), 'results')
  assert.equal(nextSidebarWorkflowId('results', 'ArrowRight'), 'setup')
  assert.equal(nextSidebarWorkflowId('results', 'Home'), 'setup')
  assert.equal(nextSidebarWorkflowId('setup', 'End'), 'results')
  assert.equal(nextSidebarWorkflowId('simulate', 'Enter'), 'simulate')
})

test('successful results and prefills select the intended workflow', () => {
  assert.equal(sidebarWorkflowForEvent('simulation-success', 'simulate'), 'results')
  assert.equal(sidebarWorkflowForEvent('historical-result', 'setup'), 'results')
  assert.equal(sidebarWorkflowForEvent('alert-prefill', 'results'), 'simulate')
  assert.equal(sidebarWorkflowForEvent('historical-template', 'results'), 'simulate')
  assert.equal(sidebarWorkflowForEvent('unknown', 'setup'), 'setup')
})

test('only the explicit stored true value collapses the workspace', () => {
  assert.equal(parseStoredSidebarCollapsed('true'), true)
  assert.equal(parseStoredSidebarCollapsed('false'), false)
  assert.equal(parseStoredSidebarCollapsed(null), false)
})
