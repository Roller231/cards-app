export function parseOperationDate(value) {
  if (!value || typeof value !== 'string') return null
  const iso = value.trim().replace(' ', 'T')
  const withZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(iso) ? iso : `${iso}Z`
  const date = new Date(withZone)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatOperationDate(value) {
  return parseOperationDate(value)?.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }) || ''
}
