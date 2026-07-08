import { useState, useRef, useEffect } from 'react'
import api from '../../api/client'
import Button from './Button'
import Portal from './Portal'
import SbpPaymentModal from './SbpPaymentModal'

const TOPUP_PAYMENT_METHODS = [
  { id: 'sbp', label: 'СБП', description: 'Мгновенное пополнение через Систему Быстрых Платежей', iconSrc: '/images/sbp.png' },
]

function TopUpModal({ isOpen, onClose, card, onTopUp }) {
  const [depositError, setDepositError] = useState('')
  const [amount, setAmount] = useState(0)
  const [amountInput, setAmountInput] = useState('')
  const [screen, setScreen] = useState('form') // 'form' | 'confirmation' | 'loading' | 'success' | 'failure'
  const [showSbpModal, setShowSbpModal] = useState(false)
  // App rate = [BB index] × bitbFee × myFee × clarusFee (computed on backend,
  // multipliers configured in the admin panel). Plus a fixed fee for small payments.
  const [rateInfo, setRateInfo] = useState(null)  // { index, rate, small_payment_fee_rub, small_payment_threshold_rub }
  const [rateError, setRateError] = useState(false)
  const amountInputRef = useRef(null)

  // Load the app exchange rate once on open
  useEffect(() => {
    if (!isOpen || rateInfo !== null) return
    setRateError(false)
    api.sbp.rate()
      .then(setRateInfo)
      .catch(() => setRateError(true))
  }, [isOpen])

  // Auto-focus amount input when modal opens
  useEffect(() => {
    if (isOpen && screen === 'form') {
      setTimeout(() => amountInputRef.current?.focus(), 380)
    }
  }, [isOpen, screen])

  // Reset state when modal closes (after animation)
  useEffect(() => {
    if (!isOpen) {
      const t = setTimeout(() => {
        setAmount(0)
        setAmountInput('')
        setScreen('form')
        setDepositError('')
      }, 350)
      return () => clearTimeout(t)
    }
  }, [isOpen])

  // Deposit call — SBP direct
  useEffect(() => {
    if (screen !== 'loading') return
    if (!card?.aifory_card_id) {
      setDepositError('Отсутствует ID карты')
      setScreen('failure')
      return
    }
    let canceled = false
    api.cards.deposit(card.aifory_card_id, amount, 'sbp')
      .then(() => {
        if (canceled) return
        setScreen('success')
        if (typeof onTopUp === 'function') onTopUp()
      })
      .catch((e) => {
        if (canceled) return
        setDepositError(e.message || 'Ошибка пополнения')
        setScreen('failure')
      })
    return () => { canceled = true }
  }, [screen]) // eslint-disable-line react-hooks/exhaustive-deps

  const round2 = (v) => Math.round((Number(v) + Number.EPSILON) * 100) / 100

  const sanitizeDecimalInput = (value) => {
    const cleaned = value.replace(/[^0-9.]/g, '')
    const [integerPart = '', ...decimalParts] = cleaned.split('.')
    return decimalParts.length > 0
      ? `${integerPart}.${decimalParts.join('')}`
      : integerPart
  }

  const getInputWidthCh = (value) => {
    const text = String(value || '')
    const digitsCount = text.replace(/\./g, '').length
    const dotsCount = (text.match(/\./g) || []).length
    const visualLength = digitsCount + dotsCount * 0.35
    return `${Math.max(visualLength, 1) + 0.5}ch`
  }

  const hasAmount = amount > 0
  const amountText = amountInput || ''
  // payRub = ceil(amount × rate); payments below the threshold additionally
  // carry Bitbanker's fixed fee (210 ₽), payments above pay exactly the amount.
  const rate = rateInfo?.rate || null
  const smallFee = Number(rateInfo?.small_payment_fee_rub ?? 210)
  const smallThreshold = Number(rateInfo?.small_payment_threshold_rub ?? 10000)
  const baseRub = rate && amount > 0 ? Math.ceil(amount * rate) : null
  const feeApplied = baseRub !== null && baseRub < smallThreshold ? smallFee : 0
  const payRub = baseRub !== null ? baseRub + feeApplied : null
  // Bitbanker prod limits: 1000..50000 RUB per SBP transfer
  const rubTooSmall = payRub !== null && payRub < 1000
  const rubTooBig = payRub !== null && payRub > 50000
  const rubLimitError = rubTooSmall
    ? 'Минимальная сумма перевода по СБП — 1 000 ₽. Увеличьте сумму пополнения.'
    : rubTooBig
      ? 'Максимальная сумма перевода по СБП — 50 000 ₽. Уменьшите сумму пополнения.'
      : ''
  const fullCardNumber = card?.cardNumber
    ? `${card.cardNumber.slice(0, 4)} ${card.cardNumber.slice(4, 8)} ${card.cardNumber.slice(8, 12)} ${card.cardNumber.slice(12, 16)}`
    : card?.last4
      ? `•••• •••• •••• ${card.last4}`
      : '—'

  const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

  const DetailRow = ({ label, value }) => (
    <div>
      <div style={{ fontSize: 13, fontWeight: 400, color: '#6B7280', fontFamily: font, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>
        {value}
      </div>
    </div>
  )

  return (
    <Portal>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          zIndex: 999,
          opacity: isOpen ? 1 : 0,
          transition: 'opacity 380ms cubic-bezier(0.32, 0.72, 0, 1)',
          pointerEvents: isOpen ? 'auto' : 'none',
        }}
      />

      {/* Modal Sheet */}
      <div
        style={{
          position: 'fixed',
          left: '50%',
          bottom: 0,
          width: '100%',
          maxWidth: 430,
          backgroundColor: '#F3F5F8',
          borderTopLeftRadius: 24,
          borderTopRightRadius: 24,
          zIndex: 1000,
          height: '90vh',
          overflow: 'hidden',
          transform: isOpen ? 'translateX(-50%) translateY(0)' : 'translateX(-50%) translateY(100%)',
          transition: 'transform 420ms cubic-bezier(0.32, 0.72, 0, 1)',
          pointerEvents: isOpen ? 'auto' : 'none',
        }}
      >
        {/* Handle bar */}
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 12, paddingBottom: 4 }}>
          <div style={{ width: 36, height: 5, backgroundColor: '#9CA3AF', borderRadius: 3 }} />
        </div>

        {/* Title */}
        <div style={{ padding: '50px 16px 12px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h2
              style={{
                fontSize: 24,
                fontWeight: 700,
                color: '#111827',
                fontFamily: font,
                margin: 0,
              }}
            >
              Пополнить баланс
            </h2>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(80vh - 12px - 4px - 44px)' }}>
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
            }}
          >

        {/* FORM SCREEN */}
        {screen === 'form' && (
          <div style={{ padding: '0 16px 0 16px' }}>
            <div className="flex flex-col gap-4" style={{ paddingBottom: 16 }}>
              {/* Amount */}
              <div
                onClick={() => amountInputRef.current?.focus()}
                style={{ backgroundColor: 'white', borderRadius: 12, padding: '14px 16px', cursor: 'text' }}
              >
                <label style={{ fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font, display: 'block', marginBottom: 8 }}>
                  Сумма
                </label>
                <div className="flex items-center" style={{ gap: 2 }}>
                  <input
                    ref={amountInputRef}
                    type="text"
                    inputMode="decimal"
                    value={amountInput}
                    onChange={(e) => {
                      const next = sanitizeDecimalInput(e.target.value)
                      setAmountInput(next)
                      setAmount(round2(parseFloat(next) || 0))
                    }}
                    placeholder="0"
                    style={{
                      border: 'none', outline: 'none', background: 'transparent',
                      fontSize: 15, fontWeight: hasAmount ? 600 : 400,
                      color: hasAmount ? '#111827' : '#6B7280', fontFamily: font,
                      width: getInputWidthCh(amountText), minWidth: '1.5ch',
                    }}
                  />
                  <span style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>$</span>
                </div>
              </div>

              {/* RUB total block */}
              <div style={{ backgroundColor: 'white', borderRadius: 12, padding: '14px 16px' }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font, display: 'block', marginBottom: 8 }}>
                  Сумма к оплате
                </label>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>
                    {!amount
                      ? '—'
                      : rateError
                        ? 'недоступно'
                        : payRub !== null
                          ? `${payRub.toLocaleString('ru-RU')} ₽`
                          : 'загружаем курс…'
                    }
                  </span>
                  {rate && amount > 0 && (
                    <span style={{ fontSize: 12, color: '#9CA3AF', fontFamily: font }}>
                      курс {rate.toFixed(2)} ₽/$
                    </span>
                  )}
                </div>
                {feeApplied > 0 && (
                  <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>
                    Включая комиссию платёжной системы {smallFee.toLocaleString('ru-RU')} ₽ —
                    она применяется к платежам до {smallThreshold.toLocaleString('ru-RU')} ₽.
                    При сумме от {smallThreshold.toLocaleString('ru-RU')} ₽ комиссии нет.
                  </div>
                )}
                {rubLimitError && (
                  <div style={{ fontSize: 12, color: '#DC2626', fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>
                    {rubLimitError}
                  </div>
                )}
                {rateError && (
                  <div style={{ fontSize: 12, color: '#DC2626', fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>
                    Не удалось загрузить курс. Закройте окно и попробуйте ещё раз.
                  </div>
                )}
              </div>

              {/* Payment Method */}
              <div style={{ marginTop: 8 }}>
                <label style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, display: 'block', marginBottom: 12 }}>
                  Способ оплаты
                </label>
                {TOPUP_PAYMENT_METHODS.map((method) => (
                  <div
                    key={method.id}
                    style={{
                      backgroundColor: 'white',
                      borderRadius: 12,
                      padding: '14px 16px',
                      marginBottom: 8,
                      display: 'flex',
                      alignItems: 'center',
                      gap: method.iconSrc ? 12 : 0,
                      border: '2px solid transparent',
                      boxSizing: 'border-box',
                    }}
                  >
                    {method.iconSrc ? (
                      <img src={method.iconSrc} alt="" style={{ width: 22, height: 22, objectFit: 'contain', flexShrink: 0 }} />
                    ) : null}
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>{method.label}</div>
                      {method.description && (
                        <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4, fontFamily: font }}>
                          {method.description}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* SBP limits info (Bitbanker prod) */}
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

        {/* CONFIRMATION SCREEN */}
        {screen === 'confirmation' && (
          <div style={{ padding: '0 16px 0 16px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24, paddingTop: 20, paddingBottom: 16}}>
              <DetailRow label="Номер карты" value={fullCardNumber} />
              <DetailRow
                label="Сумма к пополнению"
                value={`${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`}
              />
              <DetailRow
                label="Способ оплаты"
                value="СБП"
              />
            </div>
          </div>
        )}

        {/* LOADING SCREEN (inside sheet) */}
        {screen === 'loading' && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 24,
              flex: 1,
              transform: 'translateY(16px)',
            }}
          >
            <svg width="48" height="48" viewBox="0 0 48 48" style={{ animation: 'spin 1s linear infinite' }}>
              <circle
                cx="24"
                cy="24"
                r="20"
                fill="none"
                stroke="#DC4D35"
                strokeWidth="4"
                strokeLinecap="round"
                strokeDasharray="94.25 31.42"
              />
            </svg>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font }}>
              Пополняем карту...
            </div>
          </div>
        )}

        {/* SUCCESS SCREEN (inside sheet) */}
        {screen === 'success' && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 16,
              flex: 1,
              transform: 'translateY(16px)',
            }}
          >
            <img
              src="/images/Agree.png"
              alt="Success"
              style={{
                width: 64,
                height: 64,
                animation: 'iconAppear 0.5s ease-out, iconIdle 2s ease-in-out 0.5s infinite',
              }}
            />
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: '#111827',
                fontFamily: font,
                textAlign: 'center',
                animation: 'textAppear 0.5s ease-out 0.2s backwards',
              }}
            >
              Карта успешно пополнена
            </div>
            <div
              style={{
                fontSize: 13,
                color: '#6B7280',
                textAlign: 'center',
                maxWidth: 280,
                lineHeight: 1.4,
                fontFamily: font,
                animation: 'textAppear 0.5s ease-out 0.35s backwards',
              }}
            >
              Средства появятся на карте в течение 5 минут. Вы получите пуш-уведомление, как только баланс обновится.
            </div>
          </div>
        )}

        {/* FAILURE SCREEN (inside sheet) */}
        {screen === 'failure' && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 16,
              flex: 1,
              paddingLeft: 16,
              paddingRight: 16,
              transform: 'translateY(16px)',
            }}
          >
            <img
              src="/images/Warning.png"
              alt="Error"
              style={{
                width: 64,
                height: 64,
                animation: 'iconAppear 0.5s ease-out, iconShake 2s ease-in-out 0.5s infinite',
              }}
            />
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: '#111827',
                fontFamily: font,
                textAlign: 'center',
                maxWidth: 320,
                animation: 'textAppear 0.5s ease-out 0.2s backwards',
              }}
            >
              {depositError || 'Не удалось связаться с банком. Проверьте интернет и повторите попытку.'}
            </div>
          </div>
        )}

          </div>

          <div style={{ padding: '12px 16px 24px 16px' }}>
            {screen === 'form' && (
              <Button
                disabled={!hasAmount || !payRub || rubTooSmall || rubTooBig}
                onClick={() => setShowSbpModal(true)}
                fullWidth
              >
                Продолжить
              </Button>
            )}

            {screen === 'confirmation' && (
              <Button
                onClick={() => setScreen('loading')}
                fullWidth
              >
                Подтвердить и пополнить
              </Button>
            )}

            {screen === 'success' && (
              <Button onClick={onClose} fullWidth>
                Отлично
              </Button>
            )}

            {screen === 'failure' && (
              <Button onClick={() => setScreen('confirmation')} fullWidth>
                Повторить
              </Button>
            )}
          </div>
        </div>
      </div>

      <SbpPaymentModal
        isOpen={showSbpModal}
        onClose={() => setShowSbpModal(false)}
        amountRub={payRub || 0}
        purpose="balance_topup"
        cardId={card?.aifory_card_id}
        amountUsdRequested={parseFloat(amount) || 0}
        onPaid={() => {
          setShowSbpModal(false)
          setScreen('success')
          if (typeof onTopUp === 'function') onTopUp()
        }}
      />
    </Portal>
  )
}

export default TopUpModal
