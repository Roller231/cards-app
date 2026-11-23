import { useEffect, useMemo, useCallback, useRef, useState } from 'react'
import api from '../api/client'

// Map raw Aifory transaction to frontend shape
function mapAiforyTx(tx, card, index) {
  const rawAmount = parseFloat(tx.display_amount ?? tx.amount ?? tx.Amount ?? 0)
  const typeId = tx.type ?? tx.transactionType ?? tx.typeID ?? 0
  const statusId = tx.statusID ?? tx.status_id ?? tx.statusId ?? 0

  // Backend now sends normalized tx_type ('topup'|'payment'|'refund'|'declined')
  // and display_amount (signed, in the card currency). The sign-based guess
  // below is only a fallback for legacy payloads.
  let txType
  if (tx.tx_type) {
    txType = tx.tx_type === 'refund' ? 'topup' : tx.tx_type
  } else if (statusId === 3 || String(tx.status).toLowerCase().includes('declin')) {
    txType = 'declined'
  } else if (rawAmount > 0 || typeId === 2) {
    txType = 'topup'
  } else {
    txType = 'payment'
  }

  const merchant = [tx.merchantName, tx.merchant?.name, tx.merchant, tx.description, tx.comment]
    .find(value => typeof value === 'string' && value.trim())
  const timestamp = tx.date ?? tx.transactionAt ?? tx.createdAt

  return {
    cardId: card.aifory_card_id,
    id: `${card.aifory_card_id}:${tx.id ?? tx.transactionID ?? tx.transactionId ?? index}`,
    type: txType,
    title:
      txType === 'topup'
        ? `*** ${card.last4 || ''}`
        : merchant || 'Покупка',
    subtitle:
      txType === 'topup'
        ? 'Пополнение'
        : txType === 'declined'
          ? 'Операция отклонена'
          : txType === 'fee'
            ? 'Комиссия'
            : 'Оплата',
    cardTitle: card.title || 'Виртуальная карта',
    cardLast4: card.last4 || '',
    amount: txType === 'topup' ? Math.abs(rawAmount) : -Math.abs(rawAmount),
    date: new Date(typeof timestamp === 'number' && timestamp < 1e12 ? timestamp * 1000 : timestamp ?? 0),
  }
}

// Keep each card's last successful page in memory for this signed-in user.
export function useCardHistory(cards) {
  const cache = useRef(new Map())
  const [pages, setPages] = useState({})
  const active = useMemo(() => cards.filter(card =>
    card.aifory_card_id && card.status?.toLowerCase() === 'active'), [cards])

  const refresh = useCallback((list, force = false) => Promise.all(list.map(card => {
    const id = card.aifory_card_id
    if (!id || card.status?.toLowerCase() !== 'active') return
    const entry = cache.current.get(id) || {}
    if (entry.pending) return entry.pending
    if (!force && Date.now() < (entry.retryAfter || 0)) return
    cache.current.set(id, entry)
    setPages(previous => previous[id]?.error ? { ...previous, [id]: { ...previous[id], error: false } } : previous)
    entry.pending = api.cards.transactions(id, 50, 0)
      .then(result => {
        const rows = Array.isArray(result) ? result : result?.transactions ?? result?.data
        if (!Array.isArray(rows)) throw new Error('Invalid card history')
        setPages(previous => ({ ...previous, [id]: { rows, error: false } }))
        entry.retryAfter = Date.now() + 60000
      })
      .catch(() => {
        setPages(previous => ({ ...previous, [id]: { ...previous[id], error: true } }))
        entry.retryAfter = Date.now() + 3000
      })
      .finally(() => {
        entry.pending = null
      })
    return entry.pending
  })), [])

  useEffect(() => { refresh(active) }, [active, refresh])

  const transactions = useMemo(() => active.flatMap(card =>
    (pages[card.aifory_card_id]?.rows || []).map((tx, index) => mapAiforyTx(tx, card, index))
  ).sort((a, b) => b.date - a.date), [active, pages])

  function status(cardId) {
    const visible = cardId ? active.filter(c => c.aifory_card_id === cardId) : active
    if (visible.some(c => pages[c.aifory_card_id]?.error)) return 'error'
    if (visible.some(c => !pages[c.aifory_card_id]?.rows)) return 'loading'
    return 'ready'
  }

  return { transactions, status, refresh }
}
