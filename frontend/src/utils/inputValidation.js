export function emailValidationError(value) {
  const email = String(value || '').trim().toLowerCase()
  const parts = email.split('@')
  if (email.length > 254 || parts.length !== 2) return 'Enter a valid email address.'
  const [local, domain] = parts
  const labels = domain.split('.')
  if (!local || local.length > 64 || local.startsWith('.') || local.endsWith('.') || local.includes('..')
      || !/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local) || labels.length < 2 || /^[0-9]+$/.test(labels.at(-1))
      || labels.some((label) => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) return 'Enter a valid email address.'
  return ''
}

export function nameValidationError(value, optional = false) {
  const name = String(value || '')
  if (optional && !name.trim()) return ''
  if (/[\u0000-\u001f\u007f<>]/.test(name)) return 'Name cannot contain control characters or angle brackets.'
  if (!name.trim() || name.trim().length > 200 || !/\p{L}/u.test(name)) return 'Enter a name with at least one letter, up to 200 characters.'
  return ''
}
