import { useState, useEffect } from 'react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Section from '../components/ui/Section'
import PageHeader from '../components/ui/PageHeader'
import { useToast } from '../components/ui/ToastProvider'
import TopUpModal from '../components/ui/TopUpModal'
import { TxIcon } from './HistoryPage'

function CardDetailPage({ card, transactions = [], onBack, onTopUp, onNavigateToHistory }) {
  const [showCardNumber, setShowCardNumber] = useState(false)
  const [isTopUpModalOpen, setIsTopUpModalOpen] = useState(false)
  const { showToast } = useToast()

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

  const displayNumber = showCardNumber
    ? `${card.cardNumber?.slice(0, 4) || '0000'} ${card.cardNumber?.slice(4, 8) || '0000'} ${
        card.cardNumber?.slice(8, 12) || '0000'
      } ${card.cardNumber?.slice(12, 16) || card.last4}`
    : `•••• •••• •••• ${card.last4}`

  const displayExpiry = showCardNumber ? card.expiry || '12/28' : '•• / ••'
  const displayCvv = showCardNumber ? card.cvv || '123' : '•••'
  const hiddenTextColor = '#6B7280'
  const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

  const cardTransactions = transactions.filter((t) => t.cardLast4 === card.last4)

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
            paddingTop: 65,
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
              onClick={() => setShowCardNumber(!showCardNumber)}
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
              {showCardNumber ? 'Скрыть' : 'Показать'}
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
                onClick={() => showCardNumber && handleCopy('Номер карты', card.cardNumber || displayNumber.replaceAll('•', ''))}
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
                  onClick={() => handleCopy('Номер карты', card.cardNumber || displayNumber.replaceAll('•', ''))}
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
                  onClick={() => showCardNumber && handleCopy('Срок действия', card.expiry || displayExpiry.replaceAll('•', ''))}
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
                    onClick={() => handleCopy('Срок действия', card.expiry || displayExpiry.replaceAll('•', ''))}
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
                  onClick={() => showCardNumber && handleCopy('CVC', card.cvv || displayCvv.replaceAll('•', ''))}
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
                    onClick={() => handleCopy('CVC', card.cvv || displayCvv.replaceAll('•', ''))}
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
      />
    </div>
  )
}

export default CardDetailPage
