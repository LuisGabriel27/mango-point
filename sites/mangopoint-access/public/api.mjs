// Public service addresses only. Authentication tokens exist in browser memory
// or session storage; no database credentials belong in this website.
export const API_BASE = 'https://mango-point-projects.vercel.app/api'
export const STATUS_LABELS = { new: 'New', reviewing: 'In discussion', approved: 'Approved', closed: 'Closed' }
export const SECTOR_LABELS = { government: 'Government / LGU', cooperative: 'Grower cooperative', farm: 'Farm / orchard', research: 'Research / education', business: 'Private business', other: 'Other sector' }
export const INTEREST_LABELS = { demonstration: 'System demonstration', license: 'Organization licensing', subscription: 'Subscription access', unsure: 'Help choosing an arrangement' }

export async function callApi(path, { method = 'GET', body, token, signal } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 20000)
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method, signal: controller.signal, cache: 'no-store', credentials: 'omit',
      headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      let message = 'The service is temporarily unavailable. Please try again later.'
      if (typeof data?.detail === 'string') message = data.detail
      else if (Array.isArray(data?.detail)) message = data.detail.map(item => item.msg || 'Check your request details.').join(' ')
      const error = new Error(message)
      error.status = response.status
      throw error
    }
    if (!data) throw new Error('The service returned an incomplete response. Please try again.')
    return data
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request timed out. Your details are still here; you can safely try again.')
    if (error instanceof TypeError) throw new Error('We cannot reach the MangoPoint service. Your details are still here. Please try again when the service is available.')
    throw error
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}

export class SubmissionIdentity {
  constructor(makeId = () => crypto.randomUUID()) { this.makeId = makeId; this.clear() }
  prepare(fields) {
    const signature = JSON.stringify(fields)
    if (signature !== this.signature) { this.id = this.makeId(); this.signature = signature }
    return { ...fields, submission_id: this.id }
  }
  clear() { this.signature = null; this.id = null }
}

export function dateLabel(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat('en-PH', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Manila',
  }).format(date)
}
