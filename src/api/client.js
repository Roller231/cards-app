const defaultBase = (() => {
  if (typeof window === 'undefined') return '/api'
  if (window.location.port === '8080') {
    return 'http://localhost:8000'
  }
  return '/api'
})()

const BASE = import.meta?.env?.VITE_API_BASE_URL || defaultBase

const TOKEN_KEY = 'pp_access_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function req(method, path, body) {
  const token = getToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || JSON.stringify(j)
    } catch {}
    const err = new Error(detail)
    err.status = res.status
    throw err
  }

  const text = await res.text()
  return text ? JSON.parse(text) : {}
}

export const api = {
  auth: {
    telegramWebApp: (initData) =>
      req('POST', '/auth/telegram-webapp', { init_data: initData }),
    devBrowser: () => req('POST', '/auth/dev-browser'),
    me: () => req('GET', '/auth/me'),
    config: () => req('GET', '/auth/config'),
  },
  orders: {
    list: () => req('GET', '/orders'),
  },
  cards: {
    offers: () => req('GET', '/cards/offers'),
    issue: ({ offerId, holderFirstName, holderLastName, amount, email, documentNumber, paymentMethod = 'balance' }) =>
      req('POST', '/cards/issue', {
        offer_id: offerId,
        holder_first_name: holderFirstName,
        holder_last_name: holderLastName,
        amount,
        email,
        document_number: documentNumber,
        payment_method: paymentMethod,
      }),
    list: () => req('GET', '/cards'),
    requisites: (cardId) => req('GET', `/cards/${cardId}/requisites`),
    transactions: (cardId, limit = 50, offset = 0) =>
      req('GET', `/cards/${cardId}/transactions?limit=${limit}&offset=${offset}`),
    deposit: (cardId, amount, paymentMethod = 'balance') =>
      req('POST', `/cards/${cardId}/deposit`, { amount, payment_method: paymentMethod }),
  },
}

export default api
