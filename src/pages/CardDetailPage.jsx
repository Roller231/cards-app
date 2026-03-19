import { useState, useEffect, useCallback } from 'react'
import api from '../api/client'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Section from '../components/ui/Section'
import PageHeader from '../components/ui/PageHeader'
import { useToast } from '../components/ui/ToastProvider'
import TopUpModal from '../components/ui/TopUpModal'
import { TxIcon } from './HistoryPage'

function CardDetailPage({ card, transactions = [], onBack, onTopUp, onNavigateToHistory, getCommissionForCardType }) {
  const [showCardNumber, setShowCardNumber] = useState(false)
  const [isTopUpModalOpen, setIsTopUpModalOpen] = useState(false)
  const [requisites, setRequisites] = useState(null)  // { pan, expiry, cvv, holder }
  const [requisitesLoading, setRequisitesLoading] = useState(false)
  const [cardTransactionsApi, setCardTransactionsApi] = useState(null)  // null = not loaded yet
  const [txLoading, setTxLoading] = useState(false)
  const { showToast } = useToast()

  // Load transactions for this card on mount
  useEffect(() => {
    if (!card?.aifory_card_id) return
    setTxLoading(true)
    api.cards.transactions(card.aifory_card_id, 50, 0)
      .then((res) => {
        const arr = Array.isArray(res) ? res : res?.transactions ?? res?.data ?? []
        setCardTransactionsApi(arr)
      })
      .catch(() => setCardTransactionsApi([]))
      .finally(() => setTxLoading(false))
  }, [card?.aifory_card_id])

  const loadRequisites = useCallback(async () => {
    if (!card?.aifory_card_id) return
    if (requisites) {
      // Toggle off if already shown
      setShowCardNumber((prev) => !prev)
      return
    }
    setRequisitesLoading(true)
    try {
      const res = await api.cards.requisites(card.aifory_card_id)
      // Expected: { pan, expiry, cvv, holder } or { card_number, expiry_date, cvv, holder_name }
      setRequisites({
        pan: res.pan ?? res.card_number ?? res.cardNumber ?? '',
        expiry: res.expiry ?? res.expiry_date ?? res.expiryDate ?? '',
        cvv: res.cvv ?? res.cvc ?? '',
        holder: res.holder ?? res.holder_name ?? res.holderName ?? '',
      })
      setShowCardNumber(true)
    } catch (e) {
      showToast({ title: 'Не удалось получить реквизиты: ' + (e.message || 'ошибка') })
    } finally {
      setRequisitesLoading(false)
    }
  }, [card?.aifory_card_id, requisites, showToast])

  useEffect(() => {
    const tg = window?.Telegram?.WebApp
    if (!tg?.BackButton) return

    tg.BackButton.show()
    tg.BackButton.onClick(onBack)

    return () => {
      tg.BackButton.hide()
      tg.BackButton.offClick(onBack)
    }
  }, [onBack])

  if (!card) return null

  // Use loaded requisites when available; fallback to card fields (local DB)
  const pan = requisites?.pan || card.cardNumber || ''
  const expiryRaw = requisites?.expiry || card.expiry || ''
  const cvvVal = requisites?.cvv || card.cvv || ''

  const displayNumber = showCardNumber
    ? (pan
        ? `${pan.slice(0, 4)} ${pan.slice(4, 8)} ${pan.slice(8, 12)} ${pan.slice(12, 16)}`
        : `•••• •••• •••• ${card.last4}`)
    : `•••• •••• •••• ${card.last4}`

  const displayExpiry = showCardNumber ? (expiryRaw || '•• / ••') : '•• / ••'
  const displayCvv = showCardNumber ? (cvvVal || '•••') : '•••'
  const hiddenTextColor = '#6B7280'
  const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

  // Prefer API-loaded per-card transactions; fallback to global prop
  const mapApiTx = (tx) => {
    const rawAmount = parseFloat(tx.amount ?? tx.Amount ?? 0)
    const typeId = tx.type ?? tx.transactionType ?? tx.typeID ?? 0
    const statusId = tx.statusID ?? tx.status_id ?? tx.statusId ?? 0
    let txType
    if (statusId === 3 || String(tx.status || '').toLowerCase().includes('declin')) txType = 'declined'
    else if (rawAmount > 0 || typeId === 2) txType = 'topup'
    else txType = 'payment'
    return {
      id: String(tx.id ?? tx.transactionID ?? tx.transactionId ?? Math.random()),
      type: txType,
      title: txType === 'topup' ? `*** ${card.last4 || ''}` : (tx.merchant || tx.merchantName || tx.description || 'Покупка'),
      subtitle: txType === 'topup' ? 'Пополнение' : txType === 'declined' ? 'Операция отклонена' : 'Оплата',
      cardTitle: 'Виртуальная карта',
      cardLast4: card.last4 || '',
      amount: txType === 'topup' ? Math.abs(rawAmount) : -Math.abs(rawAmount),
      date: tx.date ? new Date(tx.date) : tx.createdAt ? new Date(typeof tx.createdAt === 'number' ? tx.createdAt * 1000 : tx.createdAt) : new Date(),
    }
  }
  const cardTransactions = cardTransactionsApi !== null
    ? cardTransactionsApi.map(mapApiTx)
    : transactions.filter((t) => t.cardLast4 === card.last4)

  const copyToClipboard = async (text) => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
        return true
      }
    } catch {
      // ignore
    }

    try {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'absolute'
      textarea.style.left = '-9999px'
      textarea.style.top = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(textarea)
      return ok
    } catch {
      return false
    }
  }

  const handleCopy = async (label, value) => {
    if (!value) return
    const ok = await copyToClipboard(String(value))
    showToast({ title: ok ? `${label} скопирован` : 'Не удалось скопировать' })
  }

  return (
    <div className="flex-1 flex flex-col pb-10">
      <PageHeader title="" onBack={onBack} />

      {/* Card Preview */}
      <Section>
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            paddingTop: 30,
          }}
        >
          <div
            style={{
              width: 240,
              height: 144,
              borderRadius: 20,
              padding: 18,
              position: 'relative',
              color: '#FFFFFF',
              backgroundImage: 'url(/images/CardInBalance.png)',
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                fontSize: 22,
                fontWeight: 500,
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                lineHeight: '28px',
                letterSpacing: '-0.3px',
              }}
            >
              {Number(card.balance).toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}{' '}
              $
            </div>

            <div>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 300,
                  fontFamily:
                    '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  letterSpacing: '1.6px',
                  marginBottom: 15,
                  marginLeft: -3,
                }}
              >
                ***{card.last4}
              </div>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-end',
                  justifyContent: 'space-between',
                  gap: 12,
                }}
              >



              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* Card Details */}
      <Section>
        <Card padding="20px">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 16,
              paddingTop: 20,
            }}
          >
            <h2
              style={{
                fontSize: 22,
                fontWeight: 600,
                color: '#111827',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                margin: 0,
              }}
            >
              Реквизиты карты
            </h2>
            <button
              onClick={loadRequisites}
            disabled={requisitesLoading}
              style={{
                fontSize: 16,
                fontWeight: 600,
                color: '#DC4D35',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
              }}
            >
              {requisitesLoading ? 'Загрузка...' : showCardNumber ? 'Скрыть' : 'Показать'}
            </button>
          </div>

          {/* Card Number */}
          <div
            style={{
              backgroundColor: '#F3F5F8',
              borderRadius: 12,
              padding: '16px',
              marginBottom: 12,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div
                style={{
                  fontSize: 17,
                  fontWeight: 600,
                  color: hiddenTextColor,
                  fontFamily:
                    '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  letterSpacing: '0.5px',
                  cursor: showCardNumber ? 'pointer' : 'default',
                }}
                onClick={() => showCardNumber && handleCopy('Номер карты', pan || displayNumber.replace(/[•\s]/g, ''))}
              >
                {displayNumber}
              </div>
              {showCardNumber && (
                <img
                  src="/images/Copy.png"
                  alt="Copy"
                  style={{
                    width: 20,
                    height: 20,
                    cursor: 'pointer',
                  }}
                  onClick={() => handleCopy('Номер карты', pan || displayNumber.replace(/[•\s]/g, ''))}
                />
              )}
            </div>
          </div>

          {/* Expiry Date and CVV */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div
              style={{
                backgroundColor: '#F3F5F8',
                borderRadius: 12,
                padding: '16px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div
                  style={{
                    fontSize: 17,
                    fontWeight: 600,
                    color: hiddenTextColor,
                    fontFamily:
                      '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    cursor: showCardNumber ? 'pointer' : 'default',
                  }}
                  onClick={() => showCardNumber && handleCopy('Срок действия', expiryRaw)}
                >
                  {displayExpiry.replace('/', ' / ')}
                </div>
                {showCardNumber && (
                  <img
                    src="/images/Copy.png"
                    alt="Copy"
                    style={{
                      width: 20,
                      height: 20,
                      cursor: 'pointer',
                    }}
                    onClick={() => handleCopy('Срок действия', expiryRaw)}
                  />
                )}
              </div>
            </div>

            <div
              style={{
                backgroundColor: '#F3F5F8',
                borderRadius: 12,
                padding: '16px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div
                  style={{
                    fontSize: 17,
                    fontWeight: 600,
                    color: hiddenTextColor,
                    fontFamily:
                      '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    cursor: showCardNumber ? 'pointer' : 'default',
                  }}
                  onClick={() => showCardNumber && handleCopy('CVC', cvvVal)}
                >
                  {displayCvv}
                </div>
                {showCardNumber && (
                  <img
                    src="/images/Copy.png"
                    alt="Copy"
                    style={{
                      width: 20,
                      height: 20,
                      cursor: 'pointer',
                    }}
                    onClick={() => handleCopy('CVC', cvvVal)}
                  />
                )}
              </div>
            </div>
          </div>
        </Card>
      </Section>

      {/* Top-up Button */}
      <Section>
        <Button
          onClick={() => setIsTopUpModalOpen(true)}
          fullWidth
          style={{ borderRadius: 12, padding: '16px' }}
        >
          <span className="relative mr-3 inline-block" style={{ width: 14, height: 14 }}>
            <span className="absolute left-1/2 top-1/2 w-full -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" style={{ height: 3 }} />
            <span className="absolute left-1/2 top-1/2 h-full -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" style={{ width: 3 }} />
          </span>
          <span>Пополнить</span>
        </Button>
      </Section>

      {/* Transaction History */}
      <Section>
        <Card padding="20px" style={{ minHeight: 250 }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 0 }}>
            <h2
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: '#111827',
                fontFamily: font,
                margin: 0,
              }}
            >
              История
            </h2>
            <Button
              variant="icon"
              onClick={() => onNavigateToHistory && onNavigateToHistory(card.last4)}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 14,
                  backgroundColor: '#F3F5F8',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M5 2l5 5-5 5"
                    stroke="#111827"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </Button>
          </div>

          {cardTransactions.length === 0 ? (
            <div
              className="flex flex-col items-center justify-center"
              style={{ paddingTop: 28, paddingBottom: 28 }}
            >
              <img
                src="/images/Union.png"
                alt=""
                style={{ width: 34, height: 34, marginBottom: 12, opacity: 0.65 }}
              />
              <div style={{ fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font }}>
                Нет операций
              </div>
            </div>
          ) : (
            <div style={{ marginTop: 16 }}>
              {cardTransactions.slice(0, 6).map((tx, idx) => {
                const isPositive = tx.amount > 0
                const absAmount = Math.abs(tx.amount)
                const formatted = absAmount.toLocaleString('en-US', {
                  minimumFractionDigits: absAmount % 1 !== 0 ? 2 : 0,
                  maximumFractionDigits: 2,
                })
                const amountStr = isPositive ? `+${formatted} $` : `−${formatted} $`
                const amountColor = isPositive ? '#22C55E' : tx.type === 'declined' ? '#DC4D35' : '#111827'

                return (
                  <div
                    key={tx.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      paddingTop: 16,
                      paddingBottom: 16,
                      borderBottom: idx < 5 ? '1px solid #F3F5F8' : 'none',
                    }}
                  >
                    <TxIcon type={tx.type} size={50} iconSize={24} radius={16} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>
                        {tx.title}
                      </div>
                      <div
                        style={{
                          fontSize: 13,
                          color: tx.type === 'declined' ? '#DC4D35' : '#6B7280',
                          fontFamily: font,
                          marginTop: 1,
                        }}
                      >
                        {tx.subtitle}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                      <div style={{ fontSize: 16, fontWeight: 600, color: amountColor, fontFamily: font, textAlign: 'right' }}>
                        {amountStr}
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, textAlign: 'right' }}>
                        {tx.cardTitle} · {tx.cardLast4}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </Section>

      {/* Top-up Modal */}
      <TopUpModal
        isOpen={isTopUpModalOpen}
        onClose={() => setIsTopUpModalOpen(false)}
        card={card}
        onTopUp={onTopUp}
        topupMarkupPercent={card?.offer_id ? getCommissionForCardType(card.offer_id, 'topup') : 0}
      />
    </div>
  )
}

export default CardDetailPage
