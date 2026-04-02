import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../api/client'
import PageHeader from '../components/ui/PageHeader'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

function CopyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function SpinnerIcon({ color = '#DC4D35' }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" style={{ animation: 'spin 1s linear infinite' }}>
      <circle cx="12" cy="12" r="9" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeDasharray="40 16" />
    </svg>
  )
}

export default function CryptoPaymentPage({ paymentData, onSuccess, onBack }) {
  // paymentData: { payment_id, address, network, total_usdt, amount_usd, expires_at }
  const { payment_id, address, network, total_usdt, amount_usd, type = 'issue' } = paymentData
  const isTopup = type === 'topup'

  const [status, setStatus] = useState('pending') // pending | processing | completed | failed | expired
  const [copied, setCopied] = useState(false)
  const [checking, setChecking] = useState(false)
  const pollRef = useRef(null)

  const checkStatus = useCallback(async (manual = false) => {
    if (manual) setChecking(true)
    try {
      const res = await api.cryptoPayments.status(payment_id)
      setStatus(res.status)
      if (res.status === 'completed' || res.status === 'failed' || res.status === 'expired') {
        clearInterval(pollRef.current)
      }
    } catch (e) {
      // silent
    } finally {
      if (manual) setChecking(false)
    }
  }, [payment_id])

  // Auto-poll every 5 seconds
  useEffect(() => {
    pollRef.current = setInterval(() => checkStatus(false), 5000)
    return () => clearInterval(pollRef.current)
  }, [checkStatus])

  // Telegram back button
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

  const copyAddress = async () => {
    try {
      await navigator.clipboard.writeText(address)
    } catch {
      const el = document.createElement('textarea')
      el.value = address
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // ---- SUCCESS screen ----
  if (status === 'completed') {
    return (
      <div
        style={{
          position: 'fixed', inset: 0, backgroundColor: '#F3F5F8', zIndex: 200,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, marginBottom: 'auto', paddingTop: '40vh' }}>
          <img
            src="/images/Agree.png"
            alt="Success"
            style={{ width: 64, height: 64, animation: 'iconAppear 0.5s ease-out, iconIdle 2s ease-in-out 0.5s infinite' }}
          />
          <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', fontFamily: font, textAlign: 'center', animation: 'textAppear 0.5s ease-out 0.2s backwards' }}>
            {isTopup ? 'Баланс будет пополнен в течение 5 минут' : 'Карта будет создана в течение 5 минут'}
          </div>
        </div>
        <div style={{ width: '100%', maxWidth: 430, paddingBottom: 64 }}>
          <button
            onClick={onSuccess}
            style={{
              width: '100%', padding: '16px', backgroundColor: '#DC4D35', color: 'white',
              border: 'none', borderRadius: 14, fontSize: 16, fontWeight: 600,
              fontFamily: font, cursor: 'pointer',
            }}
          >
            {isTopup ? 'К карте' : 'К списку карт'}
          </button>
        </div>
      </div>
    )
  }

  // ---- FAILED / EXPIRED screen ----
  if (status === 'failed' || status === 'expired') {
    return (
      <div
        style={{
          position: 'fixed', inset: 0, backgroundColor: '#F3F5F8', zIndex: 200,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          padding: '0 16px',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, marginBottom: 'auto', paddingTop: '35vh' }}>
          <img
            src="/images/Warning.png"
            alt="Error"
            style={{ width: 64, height: 64, animation: 'iconAppear 0.5s ease-out, iconShake 2s ease-in-out 0.5s infinite' }}
          />
          <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', fontFamily: font, textAlign: 'center', maxWidth: 300 }}>
            {status === 'expired' ? 'Время оплаты истекло. Попробуйте ещё раз.' : 'Оплата не прошла. Попробуйте ещё раз.'}
          </div>
        </div>
        <div style={{ width: '100%', maxWidth: 430, paddingBottom: 64 }}>
          <button
            onClick={onBack}
            style={{
              width: '100%', padding: '16px', backgroundColor: '#111827', color: 'white',
              border: 'none', borderRadius: 14, fontSize: 16, fontWeight: 600,
              fontFamily: font, cursor: 'pointer',
            }}
          >
            Попробовать снова
          </button>
        </div>
      </div>
    )
  }

  // ---- MAIN PAYMENT screen ----
  return (
    <div className="flex-1 flex flex-col pb-10">
      <PageHeader title={isTopup ? 'Пополнение карты' : 'Выпуск карты'} onBack={onBack} />

      <div className="px-4 flex flex-col gap-4" style={{ paddingTop: 72 }}>

        {/* Info banner */}
        <div style={{
          backgroundColor: '#FFF7ED', borderRadius: 14, padding: '14px 16px',
          display: 'flex', gap: 12, alignItems: 'flex-start',
        }}>
          <span style={{ fontSize: 18, flexShrink: 0, lineHeight: 1.3 }}>⏱</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#92400E', fontFamily: font, marginBottom: 3 }}>
              Оплата может занять до 5 минут
            </div>
            <div style={{ fontSize: 12, color: '#B45309', fontFamily: font, lineHeight: 1.5 }}>
              Если вы закроете приложение — не волнуйтесь. Как только средства поступят, всё будет обработано автоматически.
            </div>
          </div>
        </div>

        {/* Status banner */}
        <div style={{
          backgroundColor: status === 'processing' ? '#FEF3C7' : 'white',
          borderRadius: 14, padding: '14px 16px',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          {status === 'processing' ? (
            <>
              <SpinnerIcon />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#92400E', fontFamily: font }}>
                  {isTopup ? 'Транзакция найдена, пополняем карту...' : 'Транзакция найдена, выпускаем карту...'}
                </div>
              </div>
            </>
          ) : (
            <>
              <div style={{
                width: 10, height: 10, borderRadius: '50%',
                backgroundColor: '#10B981', flexShrink: 0,
                boxShadow: '0 0 0 3px rgba(16,185,129,0.2)',
              }} />
              <div style={{ fontSize: 13, fontWeight: 600, color: '#111827', fontFamily: font }}>
                Ожидаем поступление средств
              </div>
            </>
          )}
        </div>

        {/* Amount */}
        <div style={{ backgroundColor: 'white', borderRadius: 14, padding: '16px' }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#6B7280', fontFamily: font, marginBottom: 6 }}>
            Сумма к оплате
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#111827', fontFamily: font }}>
            {Number(total_usdt).toFixed(2)}&nbsp;<span style={{ fontSize: 18, color: '#6B7280' }}>USDT</span>
          </div>
          <div style={{ fontSize: 12, color: '#9CA3AF', fontFamily: font, marginTop: 4 }}>
            Включая комиссию сервиса
          </div>
        </div>

        {/* Network */}
        <div style={{ backgroundColor: 'white', borderRadius: 14, padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: '#6B7280', fontFamily: font }}>Сеть</div>
          <span style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: font }}>
            {network}
          </span>
        </div>

        {/* Address */}
        <div style={{ backgroundColor: 'white', borderRadius: 14, padding: '16px' }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#6B7280', fontFamily: font, marginBottom: 8 }}>
            Адрес кошелька
          </div>
          <div style={{
            backgroundColor: '#F3F5F8', borderRadius: 10, padding: '10px 12px',
            display: 'flex', alignItems: 'flex-start', gap: 8,
          }}>
            <div style={{
              flex: 1, fontSize: 13, fontWeight: 500, color: '#111827', fontFamily: font,
              wordBreak: 'break-all', lineHeight: 1.6,
            }}>
              {address}
            </div>
            <button
              onClick={copyAddress}
              className="transition-transform duration-150 active:scale-95"
              style={{
                flexShrink: 0, width: 36, height: 36,
                backgroundColor: copied ? '#10B981' : 'white',
                color: copied ? 'white' : '#111827',
                border: 'none', borderRadius: 10,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
                transition: 'background-color 0.2s, color 0.2s',
                marginTop: 2,
              }}
            >
              {copied ? <CheckIcon /> : <CopyIcon />}
            </button>
          </div>
        </div>

        {/* Warning */}
        <div style={{
          backgroundColor: '#FEF3C7', borderRadius: 14, padding: '12px 14px',
          display: 'flex', gap: 10, alignItems: 'flex-start',
        }}>
          <span style={{ fontSize: 16, flexShrink: 0 }}>⚠️</span>
          <div style={{ fontSize: 12, color: '#92400E', fontFamily: font, lineHeight: 1.5 }}>
            Отправляйте <strong>только USDT {network}</strong> на этот адрес. Другие токены будут утеряны.
            Адрес действителен для одной оплаты.
          </div>
        </div>

        {/* Manual check button */}
        <button
          onClick={() => checkStatus(true)}
          disabled={checking || status === 'processing'}
          className="transition-transform duration-150 active:scale-95"
          style={{
            width: '100%', padding: '16px',
            backgroundColor: checking || status === 'processing' ? '#E5A99C' : '#DC4D35',
            color: 'white',
            border: 'none',
            borderRadius: 14, fontSize: 15, fontWeight: 600,
            fontFamily: font, cursor: checking ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}
        >
          {checking ? <><SpinnerIcon color="white" /> Проверяем...</> : 'Проверить оплату'}
        </button>

      </div>
    </div>
  )
}
