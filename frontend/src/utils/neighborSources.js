export function restoreNeighborSources(params = {}) {
  if (Array.isArray(params.neighbor_sources)) return params.neighbor_sources.map((source) => ({ ...source }))
  const threat = Number(params.neighbor_threat) || 0
  return threat > 0 ? [{ label: 'Neighbor 1', direction: params.neighbor_direction || null, threat }] : []
}

export function neighborPressureSummary(sources = []) {
  const active = sources.filter((source) => source.threat > 0)
  return active.length ? active.map((source) => `${source.direction || 'All sides'} ${Math.round(source.threat * 100)}%`).join(', ') : 'No neighbor pressure'
}

export function neighborRequestFields(sources = []) {
  return {
    neighbor_sources: sources.map((source) => ({ ...source })),
    neighbor_threat: Math.min(1, sources.reduce((total, source) => total + Number(source.threat || 0), 0)),
    neighbor_direction: sources.length === 1 ? sources[0].direction : null,
  }
}
