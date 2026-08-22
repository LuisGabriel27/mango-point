import { useEffect, useRef, useState } from 'react'
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
  embedded = false,
}) {
  const [showAddForm, setShowAddForm] = useState(false)
  const [name, setName] = useState('')
  const [treeGeojson, setTreeGeojson] = useState(null)
  const [orthophoto, setOrthophoto] = useState(null)
  const [dtm, setDtm] = useState(null)
  const [dsm, setDsm] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)
  const addButtonRef = useRef(null)
  const modalRef = useRef(null)
  const nameInputRef = useRef(null)
  const uploadingRef = useRef(uploading)

  useEffect(() => {
    uploadingRef.current = uploading
  }, [uploading])

  useEffect(() => {
    if (!showAddForm) return undefined

    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.requestAnimationFrame(() => nameInputRef.current?.focus())

    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !uploadingRef.current) {
        setShowAddForm(false)
        return
      }
      if (event.key !== 'Tab' || !modalRef.current) return
      const focusable = [...modalRef.current.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
      if (previousFocus?.focus) previousFocus.focus()
      else addButtonRef.current?.focus()
    }
  }, [showAddForm])

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
    <>
    <CollapsibleCard iconName="pin-map" title="Orchard" embedded={embedded}>
      <label className="small fw-medium mb-1 d-block">
        <i className="bi bi-map me-1" /> Active Orchard
      </label>
      <div className="orchard-select-row mb-2">
        <MpSelect
          value={selectedId ?? ''}
          onChange={onSelect}
          options={options}
        />
        <button
          type="button"
          className="btn btn-outline-secondary btn-sm sidebar-square-btn"
          onClick={onRefresh}
          disabled={loading}
          aria-label="Refresh orchards"
          title="Refresh orchards"
        >
          {loading
            ? <span className="spinner-border spinner-border-sm" />
            : <i className="bi bi-arrow-clockwise" />}
        </button>
      </div>
      <button
        ref={addButtonRef}
        type="button"
        className="btn btn-outline-success btn-sm w-100 mb-2"
        onClick={() => setShowAddForm(true)}
      >
        <i className="bi bi-plus-circle me-1" />
        Add Orchard
      </button>

      {message && (
        <div className={`alert alert-${message.type} py-2 small mb-2`} role="alert">
          {message.text}
        </div>
      )}

      {selected && (
        <div className="small text-muted">
          <i className="bi bi-tree me-1" />
          {treeCount} tree{treeCount !== 1 ? 's' : ''}
          {selected.location && <> &middot; {selected.location}</>}
        </div>
      )}
    </CollapsibleCard>

      {showAddForm && (
        <div
          className="orchard-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !uploading) setShowAddForm(false)
          }}
        >
          <div
            ref={modalRef}
            className="orchard-modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="orchard-modal-title"
          >
            <div className="orchard-modal-header">
              <div>
                <div className="orchard-modal-eyebrow">Orchard setup</div>
                <h2 id="orchard-modal-title" className="orchard-modal-title">Add orchard</h2>
              </div>
              <button
                type="button"
                className="btn-close"
                aria-label="Close add orchard dialog"
                onClick={() => setShowAddForm(false)}
                disabled={uploading}
              />
            </div>
            <form onSubmit={handleSubmit} className="orchard-modal-form">
          <label className="small fw-medium mb-1 d-block" htmlFor="orchard-upload-name">
            Orchard Name
          </label>
          <input
            ref={nameInputRef}
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

          <div className="orchard-modal-actions">
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
          </div>
        </div>
      )}
    </>
  )
}
