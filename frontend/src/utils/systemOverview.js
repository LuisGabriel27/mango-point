export function overviewDateKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-PH', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit' })
    .formatToParts(date)
  return ['year', 'month', 'day'].map((type) => parts.find((part) => part.type === type).value).join('-')
}

export function startOverviewLoad(previous, key) {
  if (previous.key === key && previous.data) {
    return { ...previous, loading: false, refreshing: true, error: '', refreshError: '' }
  }
  return { key, loading: true, refreshing: false, data: null, error: '', refreshError: '' }
}

export function failOverviewLoad(previous, key, message) {
  if (previous.key === key && previous.data) {
    return { ...previous, loading: false, refreshing: false, refreshError: message }
  }
  return { key, loading: false, refreshing: false, data: null, error: message, refreshError: '' }
}

// A canceled tab/filter request must never replace the current Overview data.
export function requestSystemOverview(fetchSummary, params, onSuccess, onFailure) {
  const controller = new AbortController()
  let current = true
  Promise.resolve().then(() => {
    if (current) return fetchSummary(params, controller.signal)
    return null
  }).then((response) => {
    if (current) onSuccess(response.data)
  }).catch((error) => {
    if (current) onFailure(error)
  })
  return () => { current = false; controller.abort() }
}
