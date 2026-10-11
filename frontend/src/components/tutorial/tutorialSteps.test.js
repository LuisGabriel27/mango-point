import test from 'node:test'
import assert from 'node:assert/strict'
import { buildTutorialSteps, tutorialPlacement } from './tutorialSteps.js'

const text = (steps) => steps.map((step) => `${step.title} ${step.content} ${step.data.tip}`).join(' ')

test('quick start teaches the complete workflow without overwhelming a first-time user', () => {
  const steps = buildTutorialSteps({ guide: 'workflow' })
  assert.equal(steps.length, 16)
  assert.match(text(steps), /Choose the orchard/)
  assert.match(text(steps), /Choose the pest/)
  assert.match(text(steps), /Run Simulation/)
  assert.match(text(steps), /modeled outcome/)
  assert.match(text(steps), /real field check/)
  assert.match(text(steps), /recovery email/i)
  assert.match(text(steps), /Change your password/i)
  assert.match(text(steps), /bell shows active alerts/i)
  const notificationStep = steps.find((step) => step.id === 'notifications')
  assert.equal(notificationStep.target, '[data-tour="notification-list"]')
  assert.equal(notificationStep.placement, 'left')
  assert.equal(steps.some((step) => step.id === 'notification-emails'), false)
  assert.deepEqual(
    [...new Set(steps.map((step) => step.data.phase).filter((phase) => phase !== 'explore'))],
    ['setup', 'simulate', 'results', 'history', 'verify', 'settings'],
  )
})

test('administrator quick start explains notification recipient management', () => {
  const steps = buildTutorialSteps({ guide: 'workflow', isAdmin: true })
  const recipientStep = steps.find((step) => step.id === 'notification-emails')
  assert.equal(steps.length, 17)
  assert.equal(recipientStep.target, '[data-tour="settings-notification-emails"]')
  assert.equal(recipientStep.data.view.settingsTab, 'notifications')
  assert.match(text(steps), /Add recipient/)
  assert.match(text(steps), /pause, resume or delete/i)
})

test('notification tutorial stays beside the alert panel without covering it', () => {
  const notificationStep = buildTutorialSteps({ guide: 'workflow' }).find((step) => step.id === 'notifications')
  assert.equal(tutorialPlacement(notificationStep, false), 'left')
  assert.equal(tutorialPlacement(notificationStep, true), 'bottom')
  assert.equal(tutorialPlacement({ id: 'orchard', placement: 'left' }, true), 'center')
})

test('the Cecid guide explains every gate in farm language and adds custom-weather help only when relevant', () => {
  const live = buildTutorialSteps({ guide: 'cecid', customWeather: false })
  const custom = buildTutorialSteps({ guide: 'cecid', customWeather: true })
  const content = text(live)
  assert.match(content, /fruitlets must be present/i)
  assert.match(content, /starting source/i)
  assert.match(content, /soil must be moist/i)
  assert.match(content, /rain break/i)
  assert.match(content, /dawn and dusk/i)
  assert.match(content, /check wind/i)
  assert.match(content, /Cloud percentage alone and shade under a tree are not enough/i)
  assert.equal(live.some((step) => step.id === 'soil'), false)
  assert.equal(custom.some((step) => step.id === 'soil'), true)
  assert.equal(custom.some((step) => step.id === 'weather-rain'), true)
})

test('the Fruit Fly guide keeps mature fruit, initial adults and activity conditions distinct', () => {
  const steps = buildTutorialSteps({ guide: 'fruitfly', customWeather: true })
  const content = text(steps)
  assert.match(content, /mature fruit must be present/i)
  assert.match(content, /adult pressure/i)
  assert.match(content, /25°C is a reference value, not a normal hard on\/off switch/i)
  assert.match(content, /does not need Cecid’s wet-soil emergence sequence/i)
  assert.match(content, /New infestation will not become another adult source/i)
})

test('result steps adapt to real availability without manufacturing an output', () => {
  const empty = buildTutorialSteps({ guide: 'results' })
  const loaded = buildTutorialSteps({ guide: 'results', hasResult: true, hasPlayback: true, hasRepeatedRuns: true })
  assert.match(text(empty), /No result is loaded yet/)
  assert.equal(empty.some((step) => step.id === 'legend'), false)
  assert.equal(loaded.some((step) => step.id === 'legend'), true)
  assert.equal(loaded.some((step) => step.id === 'playback'), true)
  assert.equal(loaded.some((step) => step.id === 'map-mode'), true)
})

test('every tutorial target and presentation request is declarative', () => {
  for (const guide of ['workflow', 'cecid', 'fruitfly', 'results']) {
    for (const step of buildTutorialSteps({ guide, customWeather: true, hasResult: true, hasPlayback: true })) {
      assert.match(step.target, /^\[data-tour="[a-z0-9_-]+"\]$/)
      assert.equal(typeof step.data.view, 'object')
      assert.equal(Object.values(step).some((value) => typeof value === 'function'), false)
    }
  }
})
