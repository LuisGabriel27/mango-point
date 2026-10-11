import { useEffect, useMemo, useState } from 'react'
import { filterOverviewRows, overviewTablePage } from '../../../utils/overviewTable'
import MpSelect from '../../MpSelect'

const PAGE_SIZES = [10, 25, 50]
const PAGE_OPTIONS = PAGE_SIZES.map((size) => ({ value: String(size), label: `${size} rows` }))
const number = (value) => value.toLocaleString('en-PH')

export default function OverviewDataTable({ id, label, rows, columns, rowKey, caption,
  emptyMessage = 'No saved activity.', initialSort = columns[0].key, initialDirection = 'asc' }) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState({ key: initialSort, direction: initialDirection })
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0])
  const [requestedPage, setPage] = useState(0)
  // Paging does not repeat filtering/sorting the complete summary.
  const filtered = useMemo(() => filterOverviewRows(rows, columns, query, sort.key, sort.direction),
    [rows, columns, query, sort.key, sort.direction])
  const view = overviewTablePage(filtered, requestedPage, pageSize)
  const showControls = rows.length > PAGE_SIZES[0] || query !== '' || pageSize !== PAGE_SIZES[0]
  const sortOptions = useMemo(() => columns.flatMap((column) => [
    { value: `${column.key}:asc`, label: `${column.label}: ${column.numeric ? 'Low to high' : column.key === 'date' ? 'Oldest first' : 'A to Z'}` },
    { value: `${column.key}:desc`, label: `${column.label}: ${column.numeric ? 'High to low' : column.key === 'date' ? 'Newest first' : 'Z to A'}` },
  ]), [columns])

  useEffect(() => {
    if (requestedPage !== view.page) setPage(view.page)
  }, [requestedPage, view.page])

  function changeSort(key) {
    setSort((current) => ({ key, direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc' }))
    setPage(0)
  }

  return <div className="overview-data-table">
    {showControls && <div className="overview-table-tools mb-3">
      <div className="overview-table-search">
        <label className="visually-hidden" htmlFor={`${id}-search`}>Search {label.toLowerCase()}</label>
        <i className="bi bi-search" aria-hidden="true" />
        <input id={`${id}-search`} type="search" className="form-control form-control-sm" value={query}
          placeholder="Search records" onChange={(event) => { setQuery(event.target.value); setPage(0) }} />
      </div>
      <div className="overview-table-order">
        <MpSelect id={`${id}-order`} ariaLabel={`Sort ${label.toLowerCase()}`} small className="mb-0"
          options={sortOptions} value={`${sort.key}:${sort.direction}`} onChange={(value) => {
            const [key, direction] = value.split(':')
            setSort({ key, direction }); setPage(0)
          }} />
      </div>
      <div className="overview-table-page-size">
        <MpSelect id={`${id}-page-size`} ariaLabel={`${label} rows per page`} small className="mb-0"
          value={String(pageSize)} options={PAGE_OPTIONS} onChange={(value) => { setPageSize(Number(value)); setPage(0) }} />
      </div>
    </div>}
    <div className="overview-table-scroll" role="region" aria-label={`${label} table`} tabIndex={0}>
      <table id={id} className="table table-sm align-middle mb-0 simulation-history-table overview-table">
        <caption>{caption || label}</caption>
        <thead><tr>{columns.map((column) => <th key={column.key} scope="col"
          className={column.numeric ? 'overview-table-number' : undefined}
          aria-sort={sort.key === column.key ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
          <button type="button" className="overview-sort-button" onClick={() => changeSort(column.key)}
            aria-label={`Sort ${label.toLowerCase()} by ${column.label.toLowerCase()}`}>
            <span>{column.label}</span><i aria-hidden="true" className={`bi bi-${sort.key === column.key
              ? (sort.direction === 'asc' ? 'arrow-up' : 'arrow-down') : 'arrow-down-up'}`} />
          </button>
        </th>)}</tr></thead>
        <tbody>{view.rows.map((row) => <tr key={rowKey(row)}>
          {columns.map((column, index) => {
            const Cell = index === 0 ? 'th' : 'td'
            const value = column.value(row)
            return <Cell key={column.key} scope={index === 0 ? 'row' : undefined}
              className={column.numeric ? 'overview-table-number' : undefined}>
              {column.format ? column.format(value) : value}
            </Cell>
          })}
        </tr>)}
          {!view.rows.length && <tr><td colSpan={columns.length} className="text-muted py-3">
            {rows.length ? 'No matching records. Try another search.' : emptyMessage}
          </td></tr>}
        </tbody>
      </table>
    </div>
    {showControls && <div className="overview-table-footer mt-2">
      <span className="small text-muted" role="status">Showing {number(view.first)}–{number(view.last)} of {number(view.total)} rows
        {query.trim() && <> (from {number(rows.length)})</>}</span>
      <nav aria-label={`${label} pages`} className="overview-table-pagination">
        <span className="small text-muted">Page {number(view.page + 1)} of {number(view.pageCount)}</span>
        <div className="btn-group btn-group-sm">
          <button type="button" className="btn btn-outline-secondary" disabled={view.page === 0}
            onClick={() => setPage(0)} aria-label={`First page of ${label.toLowerCase()}`}>First</button>
          <button type="button" className="btn btn-outline-secondary" disabled={view.page === 0}
            onClick={() => setPage(view.page - 1)} aria-label={`Previous page of ${label.toLowerCase()}`}>Previous</button>
          <button type="button" className="btn btn-outline-secondary" disabled={view.page >= view.pageCount - 1}
            onClick={() => setPage(view.page + 1)} aria-label={`Next page of ${label.toLowerCase()}`}>Next</button>
          <button type="button" className="btn btn-outline-secondary" disabled={view.page >= view.pageCount - 1}
            onClick={() => setPage(view.pageCount - 1)} aria-label={`Last page of ${label.toLowerCase()}`}>Last</button>
        </div>
      </nav>
    </div>}
  </div>
}
