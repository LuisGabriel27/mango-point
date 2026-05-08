import CollapsibleCard from '../CollapsibleCard'

const ALL_ID = '__all_orchards__'

export default function OrchardSwitcher({ orchards = [], selectedId, onSelect, onRefresh, loading }) {
  const options = []
  if (orchards.length > 1) options.push({ label: 'All registered orchards', value: ALL_ID })
  orchards.forEach((o) => options.push({ label: o.name || o.orchard_id, value: o.orchard_id }))
  if (!options.length) options.push({ label: 'Default Orchard', value: 'default-orchard' })

  const selected = orchards.find((o) => o.orchard_id === selectedId)
  const treeCount = selectedId === ALL_ID
    ? orchards.reduce((s, o) => s + (o.tree_count || 0), 0)
    : selected?.tree_count ?? 0

  return (
    <CollapsibleCard iconName="pin-map" title="Orchard View">
      <label className="small fw-medium mb-1 d-block">
        <i className="bi bi-map me-1" /> Active Orchard
      </label>
      <select
        className="form-select mb-2"
        value={selectedId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <button
        type="button"
        className="btn btn-outline-secondary btn-sm w-100 mb-2"
        onClick={onRefresh}
        disabled={loading}
      >
        {loading
          ? <><span className="spinner-border spinner-border-sm me-1" />Loading…</>
          : <><i className="bi bi-arrow-clockwise me-1" />Refresh Orchards</>}
      </button>
      {selected && (
        <div className="small text-muted">
          <i className="bi bi-tree me-1" />
          {treeCount} tree{treeCount !== 1 ? 's' : ''}
          {selected.location && <> · {selected.location}</>}
        </div>
      )}
    </CollapsibleCard>
  )
}
