import { useEffect, useRef, useState } from 'react'
import api from '../../api/client'
import Button from './Button'
import Portal from './Portal'
import SbpPaymentModal from './SbpPaymentModal'
import { useAuth } from '../../context/AuthContext'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'
const QUICK_AMOUNTS = [20, 50, 100, 200]

/**
 * Top up the INTERNAL USD balance via SBP.
 * Same money rules as a card top-up: RUB = ceil(USD x app rate), plus the
 * fixed payment-system fee when the payment is below the threshold.
 */
export default function BalanceDepositModal({ isOpen, onClose, onDeposited }) {
  const { fetchMe } = useAuth()
  const [amount, setAmount] = useState(0)
  const [amountInput, setAmountInput] = useState('')
  const [screen, setScreen] = useState('form') // 'form' | 'success'
  const [showSbpModal, setShowSbpModal] = useState(false)
  const [rateInfo, setRateInfo] = useState(null)
  const [rateError, setRateError] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!isOpen) return
    setRateError(false)
    api.sbp.rate().then(setRateInfo).catch(() => setRateError(true))
  }, [isOpen])

  useEffect(() => {
    if (isOpen && screen === 'form') setTimeout(() => inputRef.current?.focus(), 380)
  }, [isOpen, screen])

  useEffect(() => {
    if (!isOpen) {
      const t = setTimeout(() => { setAmount(0); setAmountInput(''); setScreen('form') }, 350)
      return () => clearTimeout(t)
    }
  }, [isOpen])

  const round2 = (v) => Math.round((Number(v) + Number.EPSILON) * 100) / 100
  const sanitize = (value) => {
    const cleaned = value.replace(/[^0-9.]/g, '')
    const [i = '', ...d] = cleaned.split('.')
    return d.length > 0 ? `${i}.${d.join('')}` : i
  }

  const rate = rateInfo?.rate || null
  const smallFee = Number(rateInfo?.small_payment_fee_rub ?? 210)
  const smallThreshold = Number(rateInfo?.small_payment_threshold_rub ?? 10000)
  const baseRub = rate && amount > 0 ? Math.ceil(amount * rate) : null
  const feeApplied = baseRub !== null && baseRub < smallThreshold ? smallFee : 0
  const payRub = baseRub !== null ? baseRub + feeApplied : null
  const minTransferRub = Number(rateInfo?.min_transfer_rub ?? 1022)
  const maxTransferRub = Number(rateInfo?.max_transfer_rub ?? 50000)
  const rubTooSmall = payRub !== null && payRub < minTransferRub
  const rubTooBig = payRub !== null && payRub > maxTransferRub
  const rubLimitError = rubTooSmall
    ? `Минимальная сумма перевода по СБП — ${minTransferRub.toLocaleString('ru-RU')} ₽. Увеличьте сумму.`
    : rubTooBig
      ? `Максимальная сумма перевода по СБП — ${maxTransferRub.toLocaleString('ru-RU')} ₽. Уменьшите сумму.`
      : ''
  const hasAmount = amount > 0

  return (
    <Portal>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 999,
          opacity: isOpen ? 1 : 0, transition: 'opacity 380ms cubic-bezier(0.32, 0.72, 0, 1)',
          pointerEvents: isOpen ? 'auto' : 'none',
        }}
      />
      <div
        style={{
          position: 'fixed', left: '50%', bottom: 0, width: '100%', maxWidth: 430,
          backgroundColor: '#F3F5F8', borderTopLeftRadius: 24, borderTopRightRadius: 24,
          zIndex: 1000, height: '86vh', overflow: 'hidden',
          transform: isOpen ? 'translateX(-50%) translateY(0)' : 'translateX(-50%) translateY(100%)',
          transition: 'transform 420ms cubic-bezier(0.32, 0.72, 0, 1)',
          pointerEvents: isOpen ? 'auto' : 'none',
          display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 12, paddingBottom: 4 }}>
          <div style={{ width: 36, height: 5, backgroundColor: '#9CA3AF', borderRadius: 3 }} />
        </div>
        <div style={{ padding: '28px 16px 12px 16px' }}>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: '#111827', fontFamily: font, margin: 0 }}>
            Пополнить баланс
          </h2>
          <div style={{ fontSize: 13, color: '#6B7280', fontFamily: font, marginTop: 6, lineHeight: 1.5 }}>
            Внутренний баланс в долларах. С него можно выпускать и пополнять карты — уже без комиссии СБП.
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {screen === 'form' && (
            <div style={{ padding: '0 16px 16px' }}>
              <div className="flex flex-col gap-4">
                {/* Amount */}
                <div
                  onClick={() => inputRef.current?.focus()}
                  style={{ backgroundColor: 'white', borderRadius: 12, padding: '14px 16px', cursor: 'text' }}
                >
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font, display: 'block', marginBottom: 8 }}>
                    Сумма пополнения
                  </label>
                  <div className="flex items-center" style={{ gap: 2 }}>
                    <input
                      ref={inputRef}
                      type="text"
                      inputMode="decimal"
                      value={amountInput}
                      onChange={(e) => {
                        const next = sanitize(e.target.value)
                        setAmountInput(next)
                        setAmount(round2(parseFloat(next) || 0))
                      }}
                      placeholder="0"
                      style={{
                        border: 'none', outline: 'none', background: 'transparent',
                        fontSize: 22, fontWeight: 700, color: hasAmount ? '#111827' : '#9CA3AF',
                        fontFamily: font, width: `${Math.max((amountInput || '0').length, 1) + 0.6}ch`, minWidth: '1.6ch',
                      }}
                    />
                    <span style={{ fontSize: 22, fontWeight: 700, color: '#111827', fontFamily: font }}>$</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                    {QUICK_AMOUNTS.map((q) => (
                      <button
                        key={q}
                        onClick={(e) => { e.stopPropagation(); setAmountInput(String(q)); setAmount(q) }}
                        style={{
                          border: 'none', borderRadius: 10, padding: '8px 12px', fontSize: 13, fontWeight: 600,
                          fontFamily: font, cursor: 'pointer',
                          background: amount === q ? '#DC4D35' : '#F3F5F8', color: amount === q ? '#fff' : '#111827',
                        }}
                      >
                        ${q}
                      </button>
                    ))}
                  </div>
                </div>

                {/* RUB total */}
                <div style={{ backgroundColor: 'white', borderRadius: 12, padding: '14px 16px' }}>
                  <label style={{ fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font, display: 'block', marginBottom: 8 }}>
                    К оплате по СБП
                  </label>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>
                      {!amount ? '—' : rateError ? 'недоступно' : payRub !== null ? `${payRub.toLocaleString('ru-RU')} ₽` : 'загружаем курс…'}
                    </span>
                    {rate && (
                      <span style={{ fontSize: 12, color: '#9CA3AF', fontFamily: font }}>курс {rate.toFixed(2)} ₽/$</span>
                    )}
                  </div>
                  {feeApplied > 0 && (
                    <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>
                      Включая комиссию платёжной системы {smallFee.toLocaleString('ru-RU')} ₽ — она применяется
                      к платежам до {smallThreshold.toLocaleString('ru-RU')} ₽. При сумме от {smallThreshold.toLocaleString('ru-RU')} ₽ комиссии нет.
                    </div>
                  )}
                  {rubLimitError && (
                    <div style={{ fontSize: 12, color: '#DC2626', fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>{rubLimitError}</div>
                  )}
                  {rateError && (
                    <div style={{ fontSize: 12, color: '#DC2626', fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>
                      Не удалось загрузить курс. Закройте окно и попробуйте ещё раз.
                    </div>
                  )}
                </div>

                <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 12, padding: '12px 14px', fontSize: 12, color: '#92400E', fontFamily: font, lineHeight: 1.55 }}>
                  <b>Лимиты СБП:</b> от 1 000 ₽ до 50 000 ₽ за перевод, не более 2 пополнений в сутки
                  (обновляется в 00:00 по Москве).
                  <br />
                  <b>Важно:</b> оплачивайте каждый созданный QR-код — после трёх неоплаченных подряд
                  платёжная система блокирует пополнения по СБП.
                </div>
              </div>
            </div>
          )}

          {screen === 'success' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, padding: '48px 16px' }}>
              <img src="/images/Agree.png" alt="" style={{ width: 64, height: 64, animation: 'iconAppear 0.5s ease-out, iconIdle 2s ease-in-out 0.5s infinite' }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font, textAlign: 'center' }}>
                Оплата прошла
              </div>
              <div style={{ fontSize: 13, color: '#6B7280', textAlign: 'center', maxWidth: 300, lineHeight: 1.5, fontFamily: font }}>
                ${amount.toFixed(2)} зачислятся на внутренний баланс в течение минуты. Придёт уведомление в Telegram.
              </div>
            </div>
          )}
        </div>

        <div style={{ padding: '12px 16px 24px 16px' }}>
          {screen === 'form' ? (
            <Button
              disabled={!hasAmount || !payRub || rubTooSmall || rubTooBig}
              onClick={() => setShowSbpModal(true)}
              fullWidth
            >
              Продолжить
            </Button>
          ) : (
            <Button onClick={onClose} fullWidth>Отлично</Button>
          )}
        </div>
      </div>

      <SbpPaymentModal
        isOpen={showSbpModal}
        onClose={() => setShowSbpModal(false)}
        amountRub={payRub || 0}
        purpose="balance_deposit"
        amountUsdRequested={parseFloat(amount) || 0}
        skipSuccessScreen={true}
        onPaid={() => {
          setShowSbpModal(false)
          setScreen('success')
          // The webhook credits the balance within seconds — refresh a few times
          ;[1500, 5000, 12000].forEach((ms) => setTimeout(() => { fetchMe?.(); onDeposited?.() }, ms))
        }}
      />
    </Portal>
  )
}
