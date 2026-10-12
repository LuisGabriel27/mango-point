import { callApi, STATUS_LABELS, SECTOR_LABELS, INTEREST_LABELS, dateLabel } from './api.mjs'

const $ = selector => document.querySelector(selector)
const storageKey = 'mangopoint-request-review-token-v1'
let token = null
let records = []
let total = 0
let page = 0
let search = ''
let selected = null
let sessionGeneration = 0
let listGeneration = 0
let saving = false
const drafts = new Map()
const controllers = new Set()
const pageSize = 25

function storedToken() { try { return sessionStorage.getItem(storageKey) } catch { return null } }
function storeToken(value) { try { value ? sessionStorage.setItem(storageKey, value) : sessionStorage.removeItem(storageKey) } catch { /* Memory-only sessions still work. */ } }
function showError(selector, message) { const node = $(selector); node.textContent = message; node.hidden = !message }
function node(tag, value, className) { const element = document.createElement(tag); if (value !== undefined) element.textContent = value; if (className) element.className = className; return element }

function signOut(message = '') {
  sessionGeneration += 1
  for (const controller of controllers) controller.abort()
  controllers.clear()
  token = null
  storeToken(null)
  records = []
  selected = null
  drafts.clear()
  $('#request-dialog').close()
  $('#request-rows').replaceChildren()
  $('#request-details').replaceChildren()
  $('#detail-message').textContent = ''
  $('#detail-organization').textContent = ''
  $('#detail-reference').textContent = ''
  $('#request-review-form').reset()
  $('#review-inbox').hidden = true
  $('#review-login').hidden = false
  $('#restore-session').hidden = true
  $('#review-user').textContent = ''
  $('#review-login-form').reset()
  showError('#login-error', message)
  $('#review-login-form').elements.username.focus()
}

async function request(path, options = {}) {
  const controller = new AbortController()
  const generation = sessionGeneration
  controllers.add(controller)
  try {
    const data = await callApi(path, { ...options, token, signal: controller.signal })
    if (generation !== sessionGeneration) throw new Error('Session ended.')
    return data
  } catch (error) {
    if (error.status === 401 && generation === sessionGeneration) signOut('Your session expired. Please sign in again.')
    throw error
  } finally { controllers.delete(controller) }
}

function activateSession(user, accessToken) {
  if (user?.role !== 'admin' || !(user.user_id > 0)) throw new Error('Request review is available only to saved MangoPoint administrator accounts.')
  sessionGeneration += 1
  token = accessToken
  storeToken(token)
  page = 0
  search = ''
  $('#search-input').value = ''
  $('#status-filter').value = ''
  $('#review-user').textContent = user.full_name || user.username
  $('#review-login').hidden = true
  $('#review-inbox').hidden = false
  $('#review-login-form').reset()
  showError('#inbox-error', '')
  loadInbox()
}

$('#review-login-form').addEventListener('submit', async event => {
  event.preventDefault()
  const form = event.currentTarget
  if (!form.reportValidity()) return
  const button = $('#login-button')
  button.disabled = true
  button.textContent = 'Signing in…'
  showError('#login-error', '')
  try {
    const data = await callApi('/auth/login', { method: 'POST', body: {
      username_or_email: form.elements.username.value.trim(), password: form.elements.password.value,
    } })
    if (!data.access_token) throw new Error('Sign-in could not be confirmed. Please try again.')
    activateSession(data.user, data.access_token)
  } catch (error) { showError('#login-error', error.message) }
  finally { button.disabled = false; button.textContent = 'Sign in to review ↗' }
})

async function restoreSession() {
  const saved = storedToken()
  if (!saved) return
  const generation = sessionGeneration
  $('#login-button').disabled = true
  $('#restore-session').disabled = true
  showError('#login-error', '')
  try {
    const data = await callApi('/auth/me', { token: saved })
    if (generation === sessionGeneration) activateSession(data.user, saved)
  } catch (error) {
    if (generation !== sessionGeneration) return
    if (error.status === 401 || error.status === 403) { storeToken(null); $('#restore-session').hidden = true }
    else $('#restore-session').hidden = false
    showError('#login-error', error.message)
  } finally { $('#login-button').disabled = false; $('#restore-session').disabled = false }
}

$('#restore-session').addEventListener('click', restoreSession)
$('#logout-button').addEventListener('click', () => signOut())

async function loadInbox() {
  const generation = ++listGeneration
  const session = sessionGeneration
  $('#inbox-loading').hidden = false
  $('#inbox-empty').hidden = true
  $('#inbox-table-wrapper').hidden = true
  $('#inbox-pagination').hidden = true
  showError('#inbox-error', '')
  const status = $('#status-filter').value
  for (const stat of document.querySelectorAll('.stat')) { stat.classList.toggle('active', stat.dataset.status === status); stat.setAttribute('aria-pressed', String(stat.dataset.status === status)) }
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(page * pageSize) })
  if (status) params.set('status', status)
  if (search) params.set('search', search)
  try {
    const data = await request(`/access-requests?${params}`)
    if (generation !== listGeneration || session !== sessionGeneration) return
    if (!Array.isArray(data.requests)) throw new Error('The inbox response was incomplete. Please refresh.')
    records = data.requests
    total = data.total
    if (page > 0 && records.length === 0) { page -= 1; loadInbox(); return }
    for (const key of Object.keys(STATUS_LABELS)) $(`#count-${key}`).textContent = String(data.counts[key] || 0)
    renderRows()
    $('#inbox-empty').hidden = records.length !== 0
    $('#empty-description').textContent = status || search ? 'No requests match these filters. Try another status or search.' : 'New organization requests will appear here after they are submitted.'
    $('#inbox-table-wrapper').hidden = records.length === 0
    $('#inbox-pagination').hidden = total === 0
    $('#page-label').textContent = `Showing ${page * pageSize + 1}–${page * pageSize + records.length} of ${total} requests`
    $('#previous-page').disabled = page === 0
    $('#next-page').disabled = (page + 1) * pageSize >= total
  } catch (error) {
    if (generation === listGeneration && session === sessionGeneration) showError('#inbox-error', `${error.message} Use Refresh to try again.`)
  } finally { if (generation === listGeneration) $('#inbox-loading').hidden = true }
}

function renderRows() {
  $('#request-rows').replaceChildren()
  for (const record of records) {
    const row = node('tr')
    const organization = node('td'); organization.append(node('strong', record.organization), node('small', `${SECTOR_LABELS[record.sector]} · ${record.reference}`))
    const contact = node('td'); contact.append(node('span', record.contact_name), node('small', record.email))
    const status = node('td'); status.append(node('span', STATUS_LABELS[record.status], `status-pill status-${record.status}`))
    const action = node('td'); const button = node('button', 'Review ↗', 'text-link'); button.type = 'button'; button.setAttribute('aria-label', `Review ${record.organization}`); button.addEventListener('click', () => openRequest(record)); action.append(button)
    row.append(organization, contact, node('td', dateLabel(record.created_at)), status, action)
    $('#request-rows').append(row)
  }
}

function openRequest(record, useLatest = false) {
  if (useLatest) drafts.delete(record.request_id)
  const draft = drafts.get(record.request_id)
  selected = { ...record, version: draft?.version || record.version }
  $('#detail-organization').textContent = record.organization
  $('#detail-reference').textContent = `${record.reference} · Received ${dateLabel(record.created_at)}`
  const details = $('#request-details'); details.replaceChildren()
  for (const [label, value] of [
    ['Contact person', record.contact_name], ['Email', record.email], ['Phone', record.phone || 'Not provided'],
    ['Sector', SECTOR_LABELS[record.sector]], ['Location', record.location],
    ['Orchards', record.orchard_count ?? 'Not provided'], ['Interested in', INTEREST_LABELS[record.interest]],
    ['Last saved', dateLabel(record.updated_at)],
  ]) { const item = node('div'); item.append(node('dt', label), node('dd', value)); details.append(item) }
  $('#detail-message').textContent = record.message
  $('#detail-status').value = draft?.status ?? record.status
  $('#detail-notes').value = draft?.notes ?? record.notes
  showError('#detail-error', '')
  $('#reload-detail').hidden = !draft || draft.version === record.version
  if (draft && draft.version !== record.version) showError('#detail-error', 'A newer review is available. Your unsaved edits are preserved below. Load the latest review before saving.')
  if (!$('#request-dialog').open) $('#request-dialog').showModal()
}

function rememberDraft() {
  if (selected) drafts.set(selected.request_id, { status: $('#detail-status').value, notes: $('#detail-notes').value, version: selected.version })
}
$('#detail-status').addEventListener('change', rememberDraft)
$('#detail-notes').addEventListener('input', rememberDraft)
for (const selector of ['#close-detail', '#cancel-detail']) $(selector).addEventListener('click', () => { if (!saving) $('#request-dialog').close() })
$('#request-dialog').addEventListener('cancel', event => { if (saving) event.preventDefault() })
$('#request-dialog').addEventListener('keydown', event => {
  if (event.key !== 'Tab') return
  const controls = [...$('#request-dialog').querySelectorAll('button, select, textarea, input, a[href]')]
    .filter(control => !control.disabled && control.getClientRects().length > 0)
  if (!controls.length) { event.preventDefault(); return }
  const first = controls[0]
  const last = controls[controls.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
})

$('#request-review-form').addEventListener('submit', async event => {
  event.preventDefault()
  if (!selected || saving) return
  const session = sessionGeneration
  const requestId = selected.request_id
  saving = true
  $('#save-review').disabled = true
  $('#detail-status').disabled = true
  $('#detail-notes').disabled = true
  showError('#detail-error', '')
  try {
    const saved = await request(`/access-requests/${requestId}`, { method: 'PATCH', body: {
      expected_version: selected.version, status: $('#detail-status').value, notes: $('#detail-notes').value.trim(),
    } })
    if (session !== sessionGeneration) return
    drafts.delete(requestId)
    $('#request-dialog').close()
    $('#review-notice').textContent = `Review saved for ${saved.reference}.`
    $('#review-notice').hidden = false
    await loadInbox()
  } catch (error) {
    if (session !== sessionGeneration) return
    showError('#detail-error', error.message)
    $('#reload-detail').hidden = error.status !== 409
  } finally { saving = false; $('#save-review').disabled = false; $('#detail-status').disabled = false; $('#detail-notes').disabled = false }
})

$('#reload-detail').addEventListener('click', async () => {
  if (!selected) return
  $('#reload-detail').disabled = true
  try { const record = await request(`/access-requests/${selected.request_id}`); openRequest(record, true) }
  catch (error) { showError('#detail-error', error.message) }
  finally { $('#reload-detail').disabled = false }
})

$('#status-filter').addEventListener('change', () => { page = 0; loadInbox() })
for (const stat of document.querySelectorAll('.stat')) stat.addEventListener('click', () => { $('#status-filter').value = stat.dataset.status; page = 0; loadInbox() })
$('#search-form').addEventListener('submit', event => { event.preventDefault(); search = $('#search-input').value.trim(); page = 0; loadInbox() })
$('#refresh-inbox').addEventListener('click', () => { $('#review-notice').hidden = true; loadInbox() })
$('#previous-page').addEventListener('click', () => { if (page > 0) { page -= 1; loadInbox() } })
$('#next-page').addEventListener('click', () => { if ((page + 1) * pageSize < total) { page += 1; loadInbox() } })
restoreSession()
