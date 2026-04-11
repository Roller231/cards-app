const BASE = '/api'
const TOKEN_KEY = 'pp_admin_token'

export function getAdminToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function setAdminToken(t) {
  localStorage.setItem(TOKEN_KEY, t)
}
export function clearAdminToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function req(method, path, body) {
  const token = getAdminToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const opts = { method, headers }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(`${BASE}${path}`, opts)
  if (res.status === 401 || res.status === 403) {
    clearAdminToken()
    window.location.reload()
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    let detail = res.statusText
    try { const j = await res.json(); detail = j.detail || JSON.stringify(j) } catch {}
    throw new Error(detail)
  }
  const text = await res.text()
  return text ? JSON.parse(text) : {}
}

const adminApi = {
  login: (email, password) => req('POST', '/admin/auth/login', { email, password }),
  dashboard: () => req('GET', '/admin/dashboard'),
  users: {
    list: (search = '', limit = 50, offset = 0) =>
      req('GET', `/admin/users?search=${encodeURIComponent(search)}&limit=${limit}&offset=${offset}`),
    get: (id) => req('GET', `/admin/users/${id}`),
    update: (id, data) => req('PUT', `/admin/users/${id}`, data),
    ban: (id) => req('POST', `/admin/users/${id}/ban`),
    unban: (id) => req('POST', `/admin/users/${id}/unban`),
    cards: (id) => req('GET', `/admin/users/${id}/cards`),
    orders: (id) => req('GET', `/admin/users/${id}/orders`),
    cryptoPayments: (id) => req('GET', `/admin/users/${id}/crypto-payments`),
    topupRequests: (id) => req('GET', `/admin/users/${id}/topup-requests`),
  },
  cards: {
    list: (search = '', limit = 50, offset = 0) =>
      req('GET', `/admin/cards?search=${encodeURIComponent(search)}&limit=${limit}&offset=${offset}`),
    aiforyUnassigned: () => req('GET', '/admin/cards/aifory-unassigned'),
    assign: (userId, aiforyCardId) =>
      req('POST', '/admin/cards/assign', { user_id: userId, aifory_card_id: aiforyCardId }),
    remove: (id) => req('DELETE', `/admin/cards/${id}`),
    update: (id, data) => req('PUT', `/admin/cards/${id}`, data),
    transactions: (cardId) => req('GET', `/admin/cards/${cardId}/transactions`),
  },
  orders: {
    list: (limit = 50, offset = 0) => req('GET', `/admin/orders?limit=${limit}&offset=${offset}`),
  },
  cryptoPayments: {
    list: (statusFilter = '', limit = 50, offset = 0) =>
      req('GET', `/admin/crypto-payments?status_filter=${statusFilter}&limit=${limit}&offset=${offset}`),
  },
  analytics: () => req('GET', '/admin/analytics'),
  settings: {
    list: () => req('GET', '/admin/settings'),
    update: (items) => req('PUT', '/admin/settings', { settings: items }),
  },
  bot: {
    getSettings: () => req('GET', '/admin/bot/settings'),
    updateSettings: (text, buttons, parse_mode) =>
      req('PUT', '/admin/bot/settings', { text, buttons, parse_mode }),
    uploadImage: async (file) => {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch('/api/admin/bot/upload-image', {
        method: 'POST',
        headers: { Authorization: `Bearer ${getAdminToken()}` },
        body: fd,
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    deleteImage: () => req('DELETE', '/admin/bot/image'),
    testWelcome: (chatId) => req('POST', `/admin/bot/test-welcome?chat_id=${chatId}`),
    uploadBroadcastImage: async (file) => {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch('/api/admin/bot/upload-broadcast-image', {
        method: 'POST',
        headers: { Authorization: `Bearer ${getAdminToken()}` },
        body: fd,
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    broadcast: (text, parse_mode, buttons, image_key) =>
      req('POST', '/admin/bot/broadcast', { text, parse_mode, buttons, image_key: image_key || null }),
  },
}

export default adminApi
