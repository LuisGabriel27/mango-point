import { useState } from 'react'
import CollapsibleCard from '../CollapsibleCard'
import MpSelect from '../MpSelect'
import { apiErrorMessage } from '../../api'

const DEFAULT_ORCHARD_ID = 'default-orchard'

export default function OrchardSwitcher({
  orchards = [],
  selectedId,
  onSelect,
  onRefresh,
  onUpload,
  loading,
  defaultTreeCount = 0,
}) {
  const [showAddForm, setShowAddForm] = useState(false)
  const [name, setName] = useState('')
  const [treeGeojson, setTreeGeojson] = useState(null)
  const [orthophoto, setOrthophoto] = useState(null)
  const [dtm, setDtm] = useState(null)
  const [dsm, setDsm] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)

  const options = [
    { label: 'Default Orchard (BPI)', value: DEFAULT_ORCHARD_ID },
  ]
  orchards
    .filter((o) => o.orchard_id !== DEFAULT_ORCHARD_ID)
    .forEach((o) => options.push({ label: o.name || o.orchard_id, value: o.orchard_id }))

  const selected = orchards.find((o) => o.orchard_id === selectedId) ?? (
    selectedId === DEFAULT_ORCHARD_ID
      ? {
        orchard_id: DEFAULT_ORCHARD_ID,
        name: 'Default Orchard (BPI)',
        tree_count: defaultTreeCount,
        location: 'Bundled BPI orchard',
      }
      : null
  )
  const treeCount = selected?.tree_count ?? 0

  async function handleSubmit(event) {
    event.preventDefault()
    const form = event.currentTarget
    setMessage(null)

    if (!name.trim() || !treeGeojson || !orthophoto) {
      setMessage({ type: 'danger', text: 'Orchard name, tree GeoJSON, and orthophoto are required.' })
      return
    }

    setUploading(true)
    try {
      const uploaded = await onUpload?.({ name: name.trim(), treeGeojson, orthophoto, dtm, dsm })
      setName('')
      setTreeGeojson(null)
      setOrthophoto(null)
      setDtm(null)
      setDsm(null)
      form.reset()
      setShowAddForm(false)
      setMessage({ type: 'success', text: `${uploaded?.name ?? 'Orchard'} added.` })
    } catch (error) {
      setMessage({ type: 'danger', text: apiErrorMessage(error, 'Could not upload orchard files.') })
    } finally {
      setUploading(false)
    }
  }

  return (
    <CollapsibleCard iconName="pin-map" title="Orchard View">
      <label className="small fw-medium mb-1 d-block">
        <i className="bi bi-map me-1" /> Active Orchard
      </label>
      <MpSelect
        value={selectedId ?? ''}
        onChange={onSelect}
        options={options}
        className="mb-2"
      />
      <button
        type="button"
        className="btn btn-outline-secondary btn-sm w-100 mb-2"
        onClick={onRefresh}
        disabled={loading}
      >
        {loading
          ? <><span className="spinner-border spinner-border-sm me-1" />Loading...</>
          : <><i className="bi bi-arrow-clockwise me-1" />Refresh Orchards</>}
      </button>
      <button
        type="button"
        className="btn btn-success btn-sm w-100 mb-2"
        onClick={() => setShowAddForm((value) => !value)}
      >
        <i className="bi bi-plus-circle me-1" />
        Add Orchard
      </button>

      {message && (
        <div className={`alert alert-${message.type} py-2 small mb-2`} role="alert">
          {message.text}
        </div>
      )}

      {showAddForm && (
        <form onSubmit={handleSubmit} className="border rounded-2 p-2 mb-2 bg-light">
          <label className="small fw-medium mb-1 d-block" htmlFor="orchard-upload-name">
            Orchard Name
          </label>
          <input
            id="orchard-upload-name"
            className="form-control form-control-sm mb-2"
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={uploading}
            required
          />

          <label className="small fw-medium mb-1 d-block" htmlFor="orchard-upload-trees">
            Tree GeoJSON
          </label>
          <input
            id="orchard-upload-trees"
            type="file"
            accept=".geojson,.json,application/geo+json,application/json"
            className="form-control form-control-sm mb-2"
            onChange={(event) => setTreeGeojson(event.target.files?.[0] ?? null)}
            disabled={uploading}
            required
          />

          <label className="small fw-medium mb-1 d-block" htmlFor="orchard-upload-ortho">
            Orthophoto GeoTIFF
          </label>
          <input
            id="orchard-upload-ortho"
            type="file"
            accept=".tif,.tiff,image/tiff"
            className="form-control form-control-sm mb-2"
            onChange={(event) => setOrthophoto(event.target.files?.[0] ?? null)}
            disabled={uploading}
            required
          />

          <label className="small fw-medium mb-1 d-block" htmlFor="orchard-upload-dtm">
            DTM GeoTIFF
          </label>
          <input
            id="orchard-upload-dtm"
            type="file"
            accept=".tif,.tiff,image/tiff"
            className="form-control form-control-sm mb-2"
            onChange={(event) => setDtm(event.target.files?.[0] ?? null)}
            disabled={uploading}
          />

          <label className="small fw-medium mb-1 d-block" htmlFor="orchard-upload-dsm">
            DSM GeoTIFF
          </label>
          <input
            id="orchard-upload-dsm"
            type="file"
            accept=".tif,.tiff,image/tiff"
            className="form-control form-control-sm mb-2"
            onChange={(event) => setDsm(event.target.files?.[0] ?? null)}
            disabled={uploading}
          />

          <div className="d-flex gap-2">
            <button type="submit" className="btn btn-success btn-sm flex-fill" disabled={uploading}>
              {uploading
                ? <><span className="spinner-border spinner-border-sm me-1" />Uploading</>
                : <><i className="bi bi-cloud-arrow-up me-1" />Save</>}
            </button>
            <button
              type="button"
              className="btn btn-outline-secondary btn-sm"
              onClick={() => setShowAddForm(false)}
              disabled={uploading}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {selected && (
        <div className="small text-muted">
          <i className="bi bi-tree me-1" />
          {treeCount} tree{treeCount !== 1 ? 's' : ''}
          {selected.location && <> &middot; {selected.location}</>}
        </div>
      )}
    </CollapsibleCard>
  )
}
