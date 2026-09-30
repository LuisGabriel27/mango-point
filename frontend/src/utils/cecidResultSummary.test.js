import test from 'node:test'
import assert from 'node:assert/strict'

import { summarizeCecidResult } from './cecidResultSummary.js'

test('summarizes established Cecid infestation against fruitlet eligibility', () => {
  const summary = summarizeCecidResult({
    n_infested_final: 24,
    risk_geojson: { features: Array.from({ length: 194 }, () => ({})) },
    gate_diagnostics: [
      { reachable_tree_count: 12 },
      { reachable_tree_count: 144, external_neighbor_exposed_tree_count: 30 },
    ],
    metadata: {
      stage_breakdown: { fruitlet: 147, mature: 47 },
      cecid_source_count: 2,
      cecid_assumed_source_count: 2,
      cecid_cohort_events: Array.from({ length: 14 }, () => ({})),
      cecid_uncertainty_summary: { runs: 5, minimum: 12, median: 25, maximum: 36 },
    },
  })

  assert.equal(summary.establishedTreeCount, 24)
  assert.equal(summary.eligibleTreeCount, 147)
  assert.equal(summary.orchardTreeCount, 194)
  assert.equal(summary.establishedEligibleRate, 24 / 147)
  assert.equal(summary.reachableTreeCount, 144)
  assert.equal(summary.externalNeighborTreeCount, 30)
  assert.equal(summary.sourceCount, 2)
  assert.equal(summary.assumedSourceCount, 2)
  assert.equal(summary.cohortEventCount, 14)
  assert.equal(summary.uncertainty.median, 25)
})

test('falls back to stored habitat diagnostics when top-level gates are absent', () => {
  const summary = summarizeCecidResult({
    n_infested_final: 3,
    metadata: {
      stage_breakdown: { fruitlet: 10, mature: 5 },
      cecid_habitat_diagnostics: [{ reachable_tree_count: 8 }],
    },
  })

  assert.equal(summary.orchardTreeCount, 15)
  assert.equal(summary.reachableTreeCount, 8)
})
