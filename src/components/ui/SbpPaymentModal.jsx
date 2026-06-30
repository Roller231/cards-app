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
 *   amountRub      — number  exact amount in RUB (from admin settings or user input)
 *   purpose        — 'balance_topup' | 'card_issue'  (default: 'balance_topup')
 */
import { useEffect, useRef, useState } from 'react'
import api from '../../api/client'
import Button from './Button'
import Portal from './Portal'
import KycModal from './KycModal'

const POLL_INTERVAL_MS = 5000
const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

export default function SbpPaymentModal({
  isOpen,
  onClose,
  onPaid,
  amountRub: amountRubProp = 0,
  purpose = 'balance_topup',
  offerId = null,
  cardId = null,
  amountUsdRequested = null,
  skipSuccessScreen = false,
}) {
  // screen: 'checking' | 'kyc' | 'confirm' | 'loading' | 'qr' | 'success' | 'error'
  const [screen, setScreen] = useState('checking')
  const [error, setError] = useState('')
  const [invoice, setInvoice] = useState(null)   // { local_invoice_id, bb_invoice_id, qr_base64, payment_url, amount_rub }
  const [amountRub, setAmountRub] = useState(0)
  const [prediction, setPrediction] = useState(null)  // exchange prediction (gross amount + fees)
  const [showKycModal, setShowKycModal] = useState(false)
  const pollRef = useRef(null)

  const requestedUsd = typeof amountUsdRequested === 'number' && !Number.isNaN(amountUsdRequested)
    ? amountUsdRequested
    : null
  const predictedUsd = prediction
    ? (prediction.volume_take_final || prediction.volume_take_prediction || null)
    : null
  const depositUsd = requestedUsd ?? predictedUsd

  const createInvoiceFlow = async (rubAmount) => {
    try {
      setScreen('loading')
      const res = await api.sbp.createInvoice(rubAmount, purpose, offerId, cardId, amountUsdRequested)
      setInvoice(res)
      setScreen('qr')
    } catch (e) {
      // If 403 KYC error, show KYC screen instead of error
      if (e.message && e.message.toLowerCase().includes('kyc')) {
        setScreen('kyc')
      } else {
        throw e
      }
    }
  }

  // Fetch exchange prediction (gross amount with SBP fee) then show confirm screen.
  // Falls back to direct invoice creation if prediction is unavailable.
  const loadConfirm = async (rubAmount) => {
    try {
      const pred = await api.sbp.exchangePrediction(rubAmount)
      setPrediction(pred)
      setScreen('confirm')
    } catch (e) {
      // Prediction failed — skip confirm and create invoice directly
      await createInvoiceFlow(rubAmount)
    }
  }

  // Check KYC, load exchange prediction, show confirm screen
  useEffect(() => {
    if (!isOpen || !amountRubProp) return
    setScreen('checking')
    setError('')
    setInvoice(null)
    setPrediction(null)
    setAmountRub(amountRubProp)
    ;(async () => {
      try {
        // Check KYC status
        const kycRes = await api.kyc.status()
        if (kycRes.kyc_status !== 'success') {
          setScreen('kyc')
          return
        }

        await loadConfirm(amountRubProp)
      } catch (e) {
        setError(e.message || 'Ошибка создания счёта')
        setScreen('error')
      }
    })()
  }, [isOpen, amountRubProp, purpose])

  // Polling when QR is shown
  useEffect(() => {
    if (screen !== 'qr' || !invoice?.local_invoice_id) return
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.sbp.pollInvoice(invoice.local_invoice_id)
        if (res.status && ['captured', 'authorized'].includes(res.status)) {
          clearInterval(pollRef.current)
          if (skipSuccessScreen) {
            if (typeof onPaid === 'function') onPaid(res)
          } else {
            setScreen('success')
            if (typeof onPaid === 'function') onPaid(res)
          }
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

          {/* === KYC REQUIRED === */}
          {screen === 'kyc' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center', paddingTop: 8 }}>
              <div style={{ fontSize: 40 }}>🪪</div>
              <div style={{ fontSize: 17, fontWeight: 700, color: '#111827', textAlign: 'center' }}>Требуется верификация</div>
              <div style={{ fontSize: 14, color: '#6B7280', textAlign: 'center', lineHeight: 1.6 }}>
                Для оплаты через СБП необходимо пройти верификацию личности. Это займёт 1–2 минуты.
              </div>
              <Button
                onClick={() => setShowKycModal(true)}
                fullWidth
              >
                Пройти верификацию
              </Button>
            </div>
          )}

          {/* === CONFIRM (итоговая сумма с комиссией) === */}
          {screen === 'confirm' && prediction && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 15, color: '#111827', fontWeight: 600 }}>Подтверждение оплаты</div>

              <div style={{ background: '#F3F5F8', borderRadius: 12, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span style={{ fontSize: 14, color: '#6B7280' }}>К оплате через СБП</span>
                  <span style={{ fontSize: 20, fontWeight: 700, color: '#111827' }}>
                    {Math.ceil(prediction.volume_give_prediction || amountRub).toLocaleString('ru-RU')} ₽
                  </span>
                </div>
                {(prediction.comission1_abs > 0) && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#9CA3AF' }}>
                    <span>включая комиссию СБП</span>
                    <span>{Math.ceil(prediction.comission1_abs).toLocaleString('ru-RU')} ₽</span>
                  </div>
                )}
                {depositUsd && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#6B7280', borderTop: '1px solid #E5E7EB', paddingTop: 12 }}>
                    <span>Вы получите</span>
                    <span>{depositUsd.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} USDT</span>
                  </div>
                )}
              </div>

              <div style={{ fontSize: 12, color: '#9CA3AF', textAlign: 'center' }}>
                Итоговая сумма на QR-коде включает комиссию платёжной системы.
              </div>

              <Button onClick={() => createInvoiceFlow(Math.ceil(prediction.volume_give_prediction || amountRub)).catch(e => { setError(e.message || 'Ошибка создания счёта'); setScreen('error') })} fullWidth>
                Продолжить к оплате
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
              <Button onClick={() => { setError(''); setScreen('checking') }} fullWidth>
                Попробовать ещё раз
              </Button>
            </div>
          )}
        </div>
      </div>

      <KycModal
        isOpen={showKycModal}
        onClose={() => setShowKycModal(false)}
        onSuccess={() => {
          setShowKycModal(false)
          createInvoiceFlow(amountRub).catch(e => {
            setError(e.message || 'Ошибка создания счёта')
            setScreen('error')
          })
        }}
      />
    </Portal>
  )
}
