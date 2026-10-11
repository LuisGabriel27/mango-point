export const HISTORY_PERIOD_MONTH = 'month'
export const HISTORY_PERIOD_ALL_HISTORY = 'all-history'

function runDate(run) {
  const value = run?.started_at ?? run?.local_saved_at
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function historyMonthKey(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

export function historyMonthParts(monthKey) {
  const match = /^(\d{4})-(\d{2})$/.exec(String(monthKey || ''))
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  if (month < 1 || month > 12) return null
  return { year, month }
}

export function filterRunsByHistoryPeriod(runs = [], period, monthKey = historyMonthKey()) {
  if (period === HISTORY_PERIOD_ALL_HISTORY) return runs
  const selected = historyMonthParts(monthKey)
  if (!selected) return []
  return runs.filter((run) => {
    const date = runDate(run)
    return date?.getFullYear() === selected.year && date.getMonth() + 1 === selected.month
  })
}

export function historyPage(runs = [], requestedPage = 0, pageSize = 10) {
  const size = Math.max(1, Math.trunc(Number(pageSize) || 10))
  const pageCount = Math.max(1, Math.ceil(runs.length / size))
  const page = Math.max(0, Math.min(Math.trunc(Number(requestedPage) || 0), pageCount - 1))
  const start = page * size
  return {
    runs: runs.slice(start, start + size),
    page,
    pageCount,
    total: runs.length,
    first: runs.length ? start + 1 : 0,
    last: Math.min(start + size, runs.length),
  }
}

export function historyMonthLabel(monthKey = historyMonthKey()) {
  const selected = historyMonthParts(monthKey)
  if (!selected) return 'Selected month'
  return new Date(selected.year, selected.month - 1, 1).toLocaleDateString([], {
    year: 'numeric',
    month: 'long',
  })
}
