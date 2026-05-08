import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const client = axios.create({ baseURL: API_BASE })

client.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token')
  if (token) config.headers['Authorization'] = `Bearer ${token}`
  return config
})

function formatValidationItem(item) {
  if (!item || typeof item !== 'object') return String(item ?? '')

  const rawLoc = Array.isArray(item.loc) ? item.loc : []
  const loc = rawLoc.filter((part) => part !== 'body').join('.')
  const message = item.msg || item.message || item.detail || JSON.stringify(item)

  return loc ? `${loc}: ${message}` : String(message)
}

export function apiErrorMessage(error, fallback = 'Request failed.') {
  const detail =
    error?.response?.data?.detail ??
    error?.response?.data?.message ??
    error?.message

  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const message = detail.map(formatValidationItem).filter(Boolean).join(' ')
    return message || fallback
  }
  if (typeof detail === 'object') {
    return formatValidationItem(detail) || fallback
  }

  return String(detail)
}

const api = {
  // Auth
  login: (usernameOrEmail, password) =>
    client.post('/auth/login', { username_or_email: usernameOrEmail, password }),
  logout: () => client.post('/auth/logout'),
  me: () => client.get('/auth/me'),

  // Orchards
  getOrchards: (params = {}) => client.get('/orchards', { params }),
  getOrchard: (id) => client.get(`/orchards/${id}`),

  // Simulation
  runSimulation: (body) => client.post('/simulation/run-simulation', body, { timeout: 180000 }),
  getSimulationRuns: (params = {}) => client.get('/simulation/runs', { params }),
  getSimulationRun: (runId) => client.get(`/simulation/runs/${runId}`),

  // Monitoring
  getMonitoringMetrics: () => client.get('/monitoring/metrics'),
  getAlertMonitoringStatus: () => client.get('/monitoring/alerts/status'),
  triggerAlertScan: (params = {}) => client.post('/monitoring/alerts/scan', null, { params }),

  // Alerts
  getAlerts: (params = {}) => client.get('/alerts', { params }),
  getAlertStats: () => client.get('/alerts/stats/summary'),
  acknowledgeAlert: (alertId, body) => client.post(`/alerts/${alertId}/acknowledge`, body),
  resolveAlert: (alertId, notes = null) =>
    client.post(`/alerts/${alertId}/resolve`, null, { params: { resolution_notes: notes } }),
  updateAlertAction: (alertId, body) => client.post(`/alerts/${alertId}/action`, body),

  // Observations
  submitObservation: (body) => client.post('/observations/submit-observation', body),
  getObservations: (params = {}) => client.get('/observations/list', { params }),
  deleteObservation: (id) => client.delete(`/observations/${id}`),

  // Evaluation
  evaluate: (params = {}) => client.get('/evaluation/evaluate', { params }),
  evaluateInline: (body) => client.post('/evaluation/evaluate-inline', body),
  getMetricsHistory: (params = {}) => client.get('/evaluation/metrics-history', { params }),

  // Weather
  getLiveWeather: (params = {}) => client.get('/weather/live', { params }),
  getWeatherForecast: (params = {}) => client.get('/weather/forecast', { params }),
  getWeatherStatus: () => client.get('/weather/status'),

  // Validation
  getHistoricalData: () => client.get('/validation/historical-data'),
  getValidationCases: (params = {}) => client.get('/validation/cases', { params }),
  runValidation: (body) => client.post('/validation/run', body, { timeout: 300000 }),
  getMetricsExplanation: () => client.get('/validation/metrics-explanation'),
}

export default api
