/**
 * SbpPaymentModal — full SBP payment flow via Bitbanker.
 *
 * Steps:
 *  1. Check KYC status
 *  2a. If not verified: show KYC button (opens kyc_url in new tab)
 *  2b. If verified: show amount input → confirm → create invoice → show QR
 *  3. Poll invoice status every 5s; on captured/authorized credit shown
 *
 * Props:
 *   isOpen         — boolean
 *   onClose        — () => void
 *   onPaid         — (invoiceData) => void  called when status becomes captured/authorized
 *   purpose        — 'balance_topup' | 'card_issue'  (default: 'balance_topup')
 *   minRub         — number  (default: 1000)
 *   maxRub         — number  (default: 50000)
 */
import { useEffect, useRef, useState } from 'react'
import api from '../../api/client'
import Button from './Button'
import Portal from './Portal'

const POLL_INTERVAL_MS = 5000
const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

export default function SbpPaymentModal({
  isOpen,
  onClose,
  onPaid,
  purpose = 'balance_topup',
  minRub = 1000,
  maxRub = 50000,
}) {
  // screen: 'checking' | 'kyc_required' | 'kyc_pending' | 'form' | 'loading' | 'qr' | 'success' | 'error'
  const [screen, setScreen] = useState('checking')
  const [error, setError] = useState('')
  const [amountRub, setAmountRub] = useState('')
  const [invoice, setInvoice] = useState(null)   // { local_invoice_id, bb_invoice_id, qr_base64, payment_url, amount_rub }
  const [exchangeInfo, setExchangeInfo] = useState(null)
  const pollRef = useRef(null)

  // Load exchange rates on open
  useEffect(() => {
    if (!isOpen) return
    setScreen('checking')
    setError('')
    setInvoice(null)
    setAmountRub('')
    setExchangeInfo(null)
    ;(async () => {
      try {
        const predRes = await api.sbp.prediction().catch(() => null)
        if (predRes) setExchangeInfo(predRes)
        setScreen('form')
      } catch {
        setScreen('form')
      }
    })()
  }, [isOpen])

  // Polling when QR is shown
  useEffect(() => {
    if (screen !== 'qr' || !invoice?.local_invoice_id) return
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.sbp.pollInvoice(invoice.local_invoice_id)
        if (res.status && ['captured', 'authorized'].includes(res.status)) {
          clearInterval(pollRef.current)
          setScreen('success')
          if (typeof onPaid === 'function') onPaid(res)
        } else if (['declined', 'failed', 'cancelled', 'expired'].includes(res.status)) {
          clearInterval(pollRef.current)
          setError(`Платёж ${res.status}. Попробуйте ещё раз.`)
          setScreen('error')
        }
      } catch {}
    }, POLL_INTERVAL_MS)
    return () => clearInterval(pollRef.current)
  }, [screen, invoice])

  // Cleanup on close
  useEffect(() => {
    if (!isOpen) {
      clearInterval(pollRef.current)
    }
  }, [isOpen])

  const handleCreateInvoice = async () => {
    const num = parseFloat(amountRub)
    if (!num || num < minRub) { setError(`Минимум ${minRub} ₽`); return }
    if (num > maxRub) { setError(`Максимум ${maxRub} ₽`); return }
    setError('')
    setScreen('loading')
    try {
      const res = await api.sbp.createInvoice(num, purpose)
      setInvoice(res)
      setScreen('qr')
    } catch (e) {
      setError(e.message || 'Ошибка создания счёта')
      setScreen('error')
    }
  }

  if (!isOpen) return null

  return (
    <Portal>
      <div
        style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.45)',
          display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
        }}
        onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      >
        <div
          style={{
            width: '100%', maxWidth: 480,
            background: '#FFFFFF', borderRadius: '20px 20px 0 0',
            padding: '24px 20px 40px',
            fontFamily: font,
            maxHeight: '90dvh', overflowY: 'auto',
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#111827' }}>Оплата по СБП</div>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: '#6B7280', lineHeight: 1 }}
            >×</button>
          </div>

          {/* === CHECKING === */}
          {screen === 'checking' && (
            <div style={{ textAlign: 'center', padding: '32px 0', color: '#6B7280', fontSize: 15 }}>
              Загружаем данные…
            </div>
          )}

          {/* === FORM === */}
          {screen === 'form' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {exchangeInfo && (
                <div style={{ background: '#F3F5F8', borderRadius: 12, padding: '10px 14px', fontSize: 13, color: '#6B7280' }}>
                  Комиссия СБП: {exchangeInfo.sbp_fee_pct ?? '—'}% + {exchangeInfo.sbp_fee_abs ?? '—'} ₽ фикс.
                  &nbsp;·&nbsp;Мин: {exchangeInfo.min_sbp_limit ?? minRub} ₽, макс: {exchangeInfo.max_sbp_limit ?? maxRub} ₽
                </div>
              )}
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Сумма в рублях</div>
                <input
                  type="number"
                  inputMode="numeric"
                  placeholder={`${minRub} – ${maxRub}`}
                  value={amountRub}
                  onChange={(e) => { setAmountRub(e.target.value); setError('') }}
                  style={{
                    width: '100%', padding: '12px 14px', borderRadius: 12,
                    border: '1.5px solid #E5E7EB', fontSize: 16, outline: 'none',
                    fontFamily: font, boxSizing: 'border-box',
                  }}
                />
              </div>
              {error && <div style={{ fontSize: 13, color: '#DC2626' }}>{error}</div>}
              <Button onClick={handleCreateInvoice} fullWidth disabled={!amountRub}>
                Получить QR-код
              </Button>
            </div>
          )}

          {/* === LOADING === */}
          {screen === 'loading' && (
            <div style={{ textAlign: 'center', padding: '32px 0', color: '#6B7280', fontSize: 15 }}>
              Создаём счёт…
            </div>
          )}

          {/* === QR === */}
          {screen === 'qr' && invoice && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center' }}>
              <div style={{ fontSize: 15, color: '#111827', textAlign: 'center', lineHeight: 1.5 }}>
                Отсканируйте QR-код приложением банка или нажмите кнопку «Оплатить в банке».
              </div>
              {invoice.qr_base64 ? (
                <img
                  src={`data:image/png;base64,${invoice.qr_base64}`}
                  alt="СБП QR-код"
                  style={{ width: 220, height: 220, borderRadius: 12, border: '1px solid #E5E7EB' }}
                />
              ) : (
                <div style={{ background: '#F3F5F8', borderRadius: 12, padding: '40px 20px', color: '#9CA3AF', fontSize: 14 }}>
                  QR-код ещё не готов
                </div>
              )}
              <div style={{ fontSize: 13, color: '#6B7280' }}>
                Сумма: <b>{invoice.amount_rub?.toLocaleString('ru-RU')} ₽</b>
              </div>
              {invoice.payment_url && (
                <a
                  href={invoice.payment_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'block', width: '100%', textAlign: 'center',
                    padding: '16px', backgroundColor: '#DC4D35', borderRadius: 12,
                    color: '#fff', fontWeight: 600, fontSize: 16, textDecoration: 'none',
                    fontFamily: font, boxSizing: 'border-box',
                  }}
                >
                  Оплатить в банке
                </a>
              )}
              <div style={{ fontSize: 12, color: '#9CA3AF', textAlign: 'center' }}>
                QR-код действителен 1 час. Статус обновляется автоматически.
              </div>
            </div>
          )}

          {/* === SUCCESS === */}
          {screen === 'success' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center', paddingTop: 8 }}>
              <div style={{ fontSize: 48 }}>✅</div>
              <div style={{ fontSize: 17, fontWeight: 700, color: '#111827' }}>Оплата подтверждена</div>
              <div style={{ fontSize: 14, color: '#6B7280', textAlign: 'center' }}>
                Баланс будет пополнен после конвертации USDT.
              </div>
              <Button onClick={onClose} fullWidth>Закрыть</Button>
            </div>
          )}

          {/* === ERROR === */}
          {screen === 'error' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 15, color: '#DC2626', lineHeight: 1.5 }}>{error || 'Произошла ошибка'}</div>
              <Button onClick={() => { setError(''); setScreen('form') }} fullWidth>
                Попробовать ещё раз
              </Button>
            </div>
          )}
        </div>
      </div>
    </Portal>
  )
}
