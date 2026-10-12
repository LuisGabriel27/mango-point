import { callApi, SubmissionIdentity } from './api.mjs'

const form = document.querySelector('#inquiry-form')
const fields = document.querySelector('#inquiry-fields')
const errorBox = document.querySelector('#inquiry-error')
const button = document.querySelector('#submit-request')
const identity = new SubmissionIdentity()
let pending = false

form.addEventListener('submit', async event => {
  event.preventDefault()
  if (pending || !form.reportValidity()) return
  const values = new FormData(form)
  const rawCount = values.get('orchard_count').trim()
  const payload = identity.prepare({
    organization: values.get('organization').trim(), sector: values.get('sector'),
    contact_name: values.get('contact_name').trim(), email: values.get('email').trim().toLowerCase(),
    phone: values.get('phone').trim(), location: values.get('location').trim(),
    orchard_count: rawCount === '' ? null : Number(rawCount), interest: values.get('interest'),
    message: values.get('message').trim(), consent: values.get('consent') === 'on',
    website: values.get('website').trim(),
  })
  pending = true
  fields.disabled = true
  errorBox.hidden = true
  button.textContent = 'Sending request…'
  try {
    const receipt = await callApi('/access-requests', { method: 'POST', body: payload })
    if (!receipt.reference || !receipt.created_at) throw new Error('We could not confirm receipt. Your details are still here; please try again.')
    document.querySelector('#receipt-reference').textContent = receipt.reference
    form.hidden = true
    document.querySelector('#inquiry-success').hidden = false
    document.querySelector('#success-title').focus()
  } catch (error) {
    errorBox.textContent = error.message
    errorBox.hidden = false
  } finally {
    pending = false
    fields.disabled = false
    button.innerHTML = 'Send request <span aria-hidden="true">↗</span>'
  }
})

document.querySelector('#new-request').addEventListener('click', () => {
  identity.clear()
  form.reset()
  errorBox.hidden = true
  form.hidden = false
  document.querySelector('#inquiry-success').hidden = true
  document.querySelector('#copy-reference').textContent = 'Copy reference'
  form.elements.organization.focus()
})

document.querySelector('#copy-reference').addEventListener('click', async event => {
  try {
    await navigator.clipboard.writeText(document.querySelector('#receipt-reference').textContent)
    event.currentTarget.textContent = 'Reference copied'
  } catch {
    document.querySelector('#receipt-reference').focus()
    event.currentTarget.textContent = 'Select the reference above to copy'
  }
})
