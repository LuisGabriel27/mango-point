const collator = new Intl.Collator('en-PH', { numeric: true, sensitivity: 'base' })

export function filterOverviewRows(rows, columns, query, sortKey, direction) {
  const search = query.trim().toLocaleLowerCase('en-PH')
  const filtered = search ? rows.filter((row) => columns.some((column) =>
    String(column.value(row) ?? '').toLocaleLowerCase('en-PH').includes(search))) : rows
  const column = columns.find((item) => item.key === sortKey)
  if (!column) return filtered
  return [...filtered].sort((a, b) => {
    const left = column.value(a), right = column.value(b)
    // Missing inventory stays at the end in either direction.
    if (left == null || right == null) return left == null ? (right == null ? 0 : 1) : -1
    const order = typeof left === 'number' && typeof right === 'number'
      ? left - right : collator.compare(String(left), String(right))
    return direction === 'desc' ? -order : order
  })
}

export function overviewTablePage(rows, requestedPage, pageSize) {
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const page = Math.max(0, Math.min(requestedPage, pageCount - 1))
  const start = page * pageSize
  return { rows: rows.slice(start, start + pageSize), page, pageCount,
    total: rows.length, first: rows.length ? start + 1 : 0, last: Math.min(start + pageSize, rows.length) }
}
