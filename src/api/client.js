const BASE = '/api'

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
    me: () => req('GET', '/auth/me'),
    config: () => req('GET', '/auth/config'),
  },
  orders: {
    list: () => req('GET', '/orders'),
  },
  cryptoPayments: {
    initiate: (offerId, amountUsd, network = 'TRC-20') =>
      req('POST', '/crypto-payments/initiate', { offer_id: offerId, amount_usd: amountUsd, network }),
    initiateTopup: (cardAiforyId, offerIdHint, amountUsd, network = 'TRC-20') =>
      req('POST', '/crypto-payments/topup-initiate', {
        card_aifory_id: cardAiforyId,
        offer_id: offerIdHint,
        amount_usd: amountUsd,
        network,
      }),
    status: (paymentId) => req('GET', `/crypto-payments/${paymentId}/status`),
  },
  cards: {
    offers: () => req('GET', '/cards/offers'),
    issue: (offerId, holderFirstName, holderLastName, amount) =>
      req('POST', '/cards/issue', {
        offer_id: offerId,
        holder_first_name: holderFirstName,
        holder_last_name: holderLastName,
        amount,
      }),
    list: () => req('GET', '/cards'),
    requisites: (cardId) => req('GET', `/cards/${cardId}/requisites`),
    transactions: (cardId, limit = 50, offset = 0) =>
      req('GET', `/cards/${cardId}/transactions?limit=${limit}&offset=${offset}`),
    deposit: (cardId, amount) =>
      req('POST', `/cards/${cardId}/deposit`, { amount }),
  },
}

export default api
