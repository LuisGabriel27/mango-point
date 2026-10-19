import axios from 'axios'
import { getConnectionState, localFetchOptions, resolveApiTarget } from './offline/apiRuntime.js'
import { SESSION_INVALID_EVENT } from './utils/sessionMonitor.js'

const client = axios.create({ adapter: 'fetch' })

client.interceptors.request.use(async (config) => {
  const target = config.authTarget || await resolveApiTarget()
  config.authTarget = target
  config.baseURL = target.baseURL
  if (target.mode === 'local' || target.mode === 'local-unavailable') {
    config.fetchOptions = localFetchOptions(config)
  }
  const token = sessionStorage.getItem('access_token')
  if (token && !config.headers['Authorization']) config.headers['Authorization'] = `Bearer ${token}`
  return config
})

client.interceptors.response.use((response) => response, (error) => {
  const authorization = error.config?.headers?.Authorization
  if (error.response?.status === 401 && authorization && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SESSION_INVALID_EVENT, {
      detail: { token: String(authorization).replace(/^Bearer /, ''),
        message: error.response.data?.detail || 'Your session ended. Please sign in again.' },
    }))
  }
  return Promise.reject(error)
})

function formatValidationItem(item) {
  if (!item || typeof item !== 'object') return String(item ?? '')

  const rawLoc = Array.isArray(item.loc) ? item.loc : []
  const loc = rawLoc.filter((part) => part !== 'body').join('.')
  const message = item.msg || item.message || item.detail || JSON.stringify(item)

  return loc ? `${loc}: ${message}` : String(message)
}

export function apiErrorMessage(error, fallback = 'Request failed.') {
  if (!error?.response && error?.code === 'ERR_NETWORK') {
    const mode = error.config?.authTarget?.mode || getConnectionState().mode
    return mode.startsWith('local')
      ? 'Cannot reach MangoPoint on this device. Start the local server and check browser local network permission, then try again.'
      : 'Cannot reach the MangoPoint server. Check your internet connection and ask the server operator to run start_production.bat.'
  }
  if ([502, 503, 504].includes(error?.response?.status) && !error?.response?.data?.detail) {
    return 'The MangoPoint server is temporarily unavailable. Please try again after the server is ready.'
  }
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
  verifyLogin: (body, authTarget) => client.post('/auth/login/verify', body, { authTarget }),
  resendLogin: (body, authTarget) => client.post('/auth/login/resend', body, { authTarget }),
  logout: (token) => client.post('/auth/logout', null, token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  me: () => client.get('/auth/me'),
  refreshSession: (body) => client.post('/auth/session/refresh', body),
  updateProfile: (body) => client.patch('/auth/me', body),
  updateAccountEmail: (body) => client.patch('/auth/me/email', body),
  changePassword: (body) => client.post('/auth/password', body),
  requestPasswordChangeCode: (body) => client.post('/auth/password/code', body),
  requestEmailChangeCode: (body) => client.post('/auth/me/email/code', body),
  requestPasswordReset: (body) => client.post('/auth/password/forgot', body),
  resetPassword: (body) => client.post('/auth/password/reset', body),

  // Orchards
  getOrchards: (params = {}) => client.get('/orchards', { params }),
  getOrchard: (id) => client.get(`/orchards/${id}`),
  updateOrchard: (id, body) => client.put(`/orchards/${id}`, body),
  updateOrchardTrees: (id, body) => client.patch(`/orchards/${id}/trees`, body),
  uploadOrchard: (formData) => client.post('/orchards/upload', formData, { timeout: 300000 }),

  // Simulation
  runSimulation: (body) => client.post('/simulation/run-simulation', body, { timeout: 180000 }),
  getSimulationRuns: (params = {}) => client.get('/simulation/runs', { params }),
  getSimulationRun: (runId) => client.get(`/simulation/runs/${runId}`),
  deleteSimulationRun: (runId) => client.delete(`/simulation/runs/${encodeURIComponent(runId)}`),
  restoreSimulationRun: (runId) => client.post(`/simulation/runs/${encodeURIComponent(runId)}/restore`),

  // Monitoring
  getMonitoringMetrics: () => client.get('/monitoring/metrics'),
  getSystemOverview: (params = {}, signal) => client.get('/monitoring/overview', { params, signal }),
  getAlertMonitoringStatus: () => client.get('/monitoring/alerts/status'),
  triggerAlertScan: (params = {}) => client.post('/monitoring/alerts/scan', null, { params }),

  // Alerts
  getAlerts: (params = {}, signal) => client.get('/alerts', { params, signal }),
  getAlertStats: () => client.get('/alerts/stats/summary'),
  acknowledgeAlert: (alertId, body) => client.post(`/alerts/${alertId}/acknowledge`, body),
  resolveAlert: (alertId, notes = null) =>
    client.post(`/alerts/${alertId}/resolve`, null, { params: { resolution_notes: notes } }),
  updateAlertAction: (alertId, body) => client.post(`/alerts/${alertId}/action`, body),
  checkWeatherForecast: (body) => client.post('/alerts/check-weather-forecast', body),
  clearAlerts: () => client.delete('/alerts/clear'),
  getAlertEmailRecipients: () => client.get('/alerts/email/recipients'),
  addAlertEmailRecipient: (body) => client.post('/alerts/email/recipients', body),
  updateAlertEmailRecipient: (recipientId, body) =>
    client.patch(`/alerts/email/recipients/${recipientId}`, body),
  removeAlertEmailRecipient: (recipientId) =>
    client.delete(`/alerts/email/recipients/${recipientId}`),

  // Observations
  submitObservation: (body) => client.post('/observations/submit-observation', body),
  submitObservationsBulk: (body) => client.post('/observations/bulk', body),
  getObservations: (params = {}) => client.get('/observations/list', { params }),
  deleteObservation: (id) => client.delete(`/observations/${id}`),

  // Evaluation
  evaluate: (params = {}) => client.get('/evaluation/evaluate', { params }),
  evaluateInline: (body) => client.post('/evaluation/evaluate-inline', body),
  getMetricsHistory: (params = {}) => client.get('/evaluation/metrics-history', { params }),

  // Weather
  getLiveWeather: (params = {}) => client.get('/weather/live', { params, timeout: 20000 }),
  getWeatherForecast: (params = {}) => client.get('/weather/forecast', { params }),
  getWeatherStatus: () => client.get('/weather/status'),

  // Cloud backup
  getSyncStatus: () => client.get('/sync/status'),
  runSupabaseSync: (params = {}) => client.post('/sync/run', null, { params }),

  // Validation
  getHistoricalData: () => client.get('/validation/historical-data'),
  getValidationCases: (params = {}) => client.get('/validation/cases', { params }),
  runValidation: (body) => client.post('/validation/run', body, { timeout: 300000 }),
  getMetricsExplanation: () => client.get('/validation/metrics-explanation'),
}

export default api
