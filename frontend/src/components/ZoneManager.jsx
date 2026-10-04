import MpSelect from './MpSelect'
import { ZONE_TYPE_OPTIONS, zoneInventoryCounts } from '../utils/zoneInventory'
import { zoneActionsForType, zoneClearLabel, zoneScopeLabel } from '../utils/zoneManagerModel'

export default function ZoneManager({
  entries,
  filter = 'all',
  onFilterChange,
  zoneVisibility = {},
  densityOptions = [],
  stageActions = {},
  statusActions = {},
  managementActions = {},
  weedActions = {},
  onClearAll,
  onClose,
}) {
  const counts = zoneInventoryCounts(entries)
  const filteredEntries = filter === 'all' ? entries : entries.filter((entry) => entry.type === filter)
  const filters = [{ value: 'all', label: 'All' }, ...ZONE_TYPE_OPTIONS]
  const clearAction = filter === 'all' ? onClearAll
    : filter === 'stage' ? stageActions.onClear
      : filter === 'status' ? statusActions.onClear
        : filter === 'management' ? managementActions.onClear
          : filter === 'cecid' ? weedActions.onClear : null

  return (
    <section id="map-zone-manager" className="map-weed-zone-manager map-zone-manager" aria-label="Zones">
      <div className="d-flex align-items-center justify-content-between gap-2 mb-2">
        <div>
          <div className="fw-bold small"><i className="bi bi-map me-1" />Zones ({counts.all})</div>
          <div className="text-muted small">All zone types in the current orchard.</div>
        </div>
        <button type="button" className="btn btn-sm btn-light" aria-label="Close zone list" onClick={onClose}>
          <i className="bi bi-x-lg" />
        </button>
      </div>
      <div className="zone-manager-filter-group mb-2" role="group" aria-label="Filter zones by type">
        {filters.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`btn btn-sm ${filter === option.value ? 'btn-success' : 'btn-outline-secondary'}`}
            aria-pressed={filter === option.value}
            onClick={() => onFilterChange?.(option.value)}
          >
            {option.label} ({counts[option.value]})
          </button>
        ))}
      </div>
      {filteredEntries.length === 0 ? (
        <div className="zone-manager-empty" role="status">
          <i className="bi bi-bounding-box-circles" aria-hidden="true" />
          <strong>{filter === 'all' ? 'No visible zones' : `No ${filters.find((option) => option.value === filter)?.label.toLowerCase() || 'matching'} zones`}</strong>
          <span>{filter === 'all' ? 'Use Draw Zone to add a stage, status, area, or weed habitat zone.' : 'Choose another filter or draw a new zone.'}</span>
        </div>
      ) : (
        <div className="d-flex flex-column gap-2">
          {filteredEntries.map((entry) => {
            const { zone, type, label, legacy } = entry
            const actions = zoneActionsForType(type, {
              stageActions, statusActions, managementActions, weedActions,
            }, legacy)
            const canEdit = type === 'management' || (type === 'cecid' && !legacy)
            const canRename = type === 'management'
            return (
              <div className="zone-manager-entry" key={`${entry.key}:${label}`}>
                <div className="zone-manager-entry-top">
                  <div className="zone-manager-entry-summary">
                    <span className="zone-manager-entry-color" style={{ backgroundColor: entry.color }} aria-hidden="true" />
                    <div className="zone-manager-entry-content">
                      <div className="zone-manager-entry-meta">
                        <span className="zone-manager-entry-type">{entry.typeLabel}</span>
                        {entry.detail && <span className="zone-manager-entry-detail">{entry.detail}</span>}
                        <span className={`badge ${entry.scope === 'orchard' ? 'text-bg-success' : 'text-bg-secondary'}`}>
                          {zoneScopeLabel(entry)}
                        </span>
                        {legacy && <span className="badge text-bg-secondary">Read-only</span>}
                      </div>
                      <div className="zone-manager-entry-label">
                        {canRename ? (
                          <input
                            className="form-control form-control-sm"
                            defaultValue={label}
                            aria-label={`Label for ${label}`}
                            onBlur={(event) => {
                              const nextLabel = event.target.value.trim() || label
                              if (nextLabel !== label) actions.onUpdate?.(zone.id, { label: nextLabel })
                            }}
                          />
                        ) : label}
                      </div>
                    </div>
                  </div>
                  <div className="zone-manager-entry-actions">
                    {canEdit && (
                      <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => actions.onRedraw?.(zone.id)}>
                        Redraw
                      </button>
                    )}
                    {actions?.onDelete && (
                      <button type="button" className="btn btn-sm btn-outline-danger" aria-label={`Delete ${label}`} onClick={() => actions.onDelete(zone.id)}>
                        <i className="bi bi-trash" />
                      </button>
                    )}
                  </div>
                </div>
                {type === 'cecid' && !legacy && (
                  <div className="zone-manager-entry-density">
                    <MpSelect small value={zone.density} options={densityOptions} onChange={(density) => weedActions.onUpdate?.(zone.id, { density })} />
                  </div>
                )}
                <div className="zone-manager-entry-footer">
                  {zoneVisibility[type] === false && <span className="text-muted">Hidden on map</span>}
                  <span>{entry.treeCount == null ? 'Tree count unavailable' : `${entry.treeCount} tree${entry.treeCount === 1 ? '' : 's'} in this area`}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {clearAction && (
        <button type="button" className="btn btn-sm btn-outline-danger mt-3 zone-manager-clear-action" onClick={clearAction}>
          {zoneClearLabel(filter)}
        </button>
      )}
      {[
        { type: 'management', label: 'Management', actions: managementActions },
        { type: 'cecid', label: 'Weed habitat', actions: weedActions },
      ].filter((item) => filter === 'all' || filter === item.type).map(({ type, label, actions }) => (
        actions.error ? (
          <div key={type} className="text-danger mt-2 small" role="alert">
            {label}: {actions.error}
            <button type="button" className="btn btn-sm btn-warning ms-2" onClick={actions.onRetry}>Retry</button>
          </div>
        ) : null
      ))}
    </section>
  )
}
