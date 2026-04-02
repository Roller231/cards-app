import { useState, useRef, useEffect } from 'react'
import api from '../../api/client'
import Button from './Button'
import Portal from './Portal'

function TopUpModal({ isOpen, onClose, card, onTopUp, topupMarkupPercent = 0, onCryptoPaymentInitiated }) {
  const [depositError, setDepositError] = useState('')
  const [amount, setAmount] = useState(0)
  const [amountInput, setAmountInput] = useState('')
  const [totalInput, setTotalInput] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('usdt')
  const [network, setNetwork] = useState('TRC-20')
  const [screen, setScreen] = useState('form') // 'form' | 'confirmation' | 'loading' | 'success' | 'failure'
  const amountInputRef = useRef(null)
  const totalInputRef = useRef(null)
  const lastEditedRef = useRef('amount')

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
        setTotalInput('')
        setPaymentMethod('usdt')
        setScreen('form')
        setDepositError('')
        lastEditedRef.current = 'amount'
      }, 350)
      return () => clearTimeout(t)
    }
  }, [isOpen])

  // Deposit call — only for SBP (USDT goes through CryptoPaymentPage)
  useEffect(() => {
    if (screen !== 'loading') return
    if (!card?.aifory_card_id) {
      setDepositError('Отсутствует ID карты')
      setScreen('failure')
      return
    }
    let canceled = false
    api.cards.deposit(card.aifory_card_id, amount)
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

  // Crypto topup initiation
  const handleCryptoInitiate = async () => {
    if (!card?.aifory_card_id) return
    setScreen('loading-crypto')
    try {
      const paymentData = await api.cryptoPayments.initiateTopup(
        card.aifory_card_id,
        card.offer_id || '',
        amount,
        network,
      )
      onClose()
      if (typeof onCryptoPaymentInitiated === 'function') {
        onCryptoPaymentInitiated(paymentData)
      }
    } catch (e) {
      setDepositError(e.message || 'Ошибка при создании платежа')
      setScreen('failure')
    }
  }

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

  const commissionRate = topupMarkupPercent / 100
  const total = amount > 0 ? round2(amount * (1 + commissionRate)) : 0
  const commission = amount > 0 ? round2(total - amount) : 0
  const hasAmount = amount > 0
  const amountText = amountInput || ''
  const fullCardNumber = card?.cardNumber
    ? `${card.cardNumber.slice(0, 4)} ${card.cardNumber.slice(4, 8)} ${card.cardNumber.slice(8, 12)} ${card.cardNumber.slice(12, 16)}`
    : card?.last4
      ? `•••• •••• •••• ${card.last4}`
      : '—'

  const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

  useEffect(() => {
    if (lastEditedRef.current !== 'amount') return
    if (!amount || amount <= 0) {
      setTotalInput('')
      return
    }
    const nextTotal = round2(amount * (1 + commissionRate))
    setTotalInput(nextTotal.toFixed(2))
  }, [amount, commissionRate])

  useEffect(() => {
    if (lastEditedRef.current !== 'total') return
    if (!amount || amount <= 0) {
      setAmountInput('')
      return
    }
    setAmountInput(String(amount))
  }, [amount])

  useEffect(() => {
    // If user last edited the total, keep total constant and recompute amount when commission changes.
    if (lastEditedRef.current !== 'total') return
    if (!totalInput) {
      setAmount(0)
      setAmountInput('')
      return
    }

    const parsedTotal = parseFloat(totalInput) || 0
    if (!parsedTotal || parsedTotal <= 0) {
      setAmount(0)
      setAmountInput('')
      return
    }

    const nextAmount = commissionRate > 0 ? parsedTotal / (1 + commissionRate) : parsedTotal
    const safeAmount = nextAmount > 0 ? Number(nextAmount.toFixed(2)) : 0
    setAmount(safeAmount)
    setAmountInput(String(safeAmount))
  }, [commissionRate, totalInput])

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

  const PaymentButtons = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="grid grid-cols-2 gap-3">
        {/* USDT button */}
        <button
          onClick={() => setPaymentMethod('usdt')}
          className="transition-transform duration-150 active:scale-95"
          style={{
            backgroundColor: 'white',
            border: paymentMethod === 'usdt' ? '2px solid #111827' : '2px solid transparent',
            borderRadius: 12, padding: '20px 16px', cursor: 'pointer',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
          }}
        >
          <div style={{ width: 50, height: 50, borderRadius: 25, backgroundColor: '#F3F5F8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <img src="/images/TRC.png" alt="USDT" style={{ width: 32, height: 32, objectFit: 'contain' }} />
          </div>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>USDT</span>
        </button>

        {/* SBP button — disabled */}
        <button
          disabled
          style={{
            backgroundColor: 'white',
            border: '2px solid transparent',
            borderRadius: 12, padding: '20px 16px',
            cursor: 'not-allowed', opacity: 0.45, pointerEvents: 'none',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
          }}
        >
          <div style={{ width: 50, height: 50, borderRadius: 25, backgroundColor: '#F3F5F8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <img src="/images/sbp.png" alt="СБП" style={{ width: 38, height: 38, objectFit: 'contain' }} />
          </div>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>СБП</span>
          <span style={{ fontSize: 11, fontWeight: 500, color: '#9CA3AF', fontFamily: font, marginTop: -4 }}>Скоро</span>
        </button>
      </div>

      {/* Network selector — shown for USDT */}
      {paymentMethod === 'usdt' && (
        <div style={{ display: 'flex', gap: 8 }}>
          {['TRC-20', 'ERC-20'].map((net) => (
            <button
              key={net}
              onClick={() => setNetwork(net)}
              className="transition-transform duration-150 active:scale-[0.97]"
              style={{
                flex: 1, padding: '10px 0',
                backgroundColor: network === net ? '#111827' : 'white',
                color: network === net ? 'white' : '#6B7280',
                border: 'none', borderRadius: 10,
                fontSize: 13, fontWeight: 600, fontFamily: font,
                cursor: 'pointer',
                transition: 'background-color 0.15s, color 0.15s',
              }}
            >
              {net}
            </button>
          ))}
        </div>
      )}
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
                      lastEditedRef.current = 'amount'
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

              {/* Total with commission */}
              <div
                onClick={() => totalInputRef.current?.focus()}
                style={{ backgroundColor: 'white', borderRadius: 12, padding: '14px 16px', cursor: 'text' }}
              >
                <label style={{ fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font, display: 'block', marginBottom: 8 }}>
                  Итоговая сумма с учетом комиссии
                </label>
                <div className="flex items-center" style={{ gap: 2 }}>
                  <input
                    ref={totalInputRef}
                    type="text"
                    inputMode="decimal"
                    value={totalInput}
                    onChange={(e) => {
                      const next = sanitizeDecimalInput(e.target.value)
                      lastEditedRef.current = 'total'
                      setTotalInput(next)
                      const parsedTotal = parseFloat(next) || 0
                      const nextAmount = commissionRate > 0 ? parsedTotal / (1 + commissionRate) : parsedTotal
                      const safeAmount = nextAmount > 0 ? round2(nextAmount) : 0
                      setAmount(safeAmount)
                      setAmountInput(next ? String(safeAmount) : '')
                    }}
                    placeholder="0"
                    style={{
                      border: 'none',
                      outline: 'none',
                      background: 'transparent',
                      fontSize: 15,
                      fontWeight: hasAmount ? 600 : 400,
                      color: hasAmount ? '#111827' : '#6B7280',
                      fontFamily: font,
                      width: getInputWidthCh(totalInput),
                      minWidth: '1.5ch',
                    }}
                  />
                  <span style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>$</span>
                </div>
              </div>

              {/* Payment Method */}
              <div style={{ marginTop: 8 }}>
                <label style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, display: 'block', marginBottom: 12 }}>
                  Способ пополнения
                </label>
                <PaymentButtons />
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
                label="Сумма к пополнению с учетом комиссии"
                value={`${total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`}
              />
              <DetailRow
                label="Способ пополнения"
                value={paymentMethod === 'usdt' ? 'USDT' : 'СБП'}
              />
            </div>
          </div>
        )}

        {/* LOADING-CRYPTO SCREEN */}
        {screen === 'loading-crypto' && (
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
              <circle cx="24" cy="24" r="20" fill="none" stroke="#DC4D35" strokeWidth="4" strokeLinecap="round" strokeDasharray="94.25 31.42" />
            </svg>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font }}>
              Создаём платёж...
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
              Ожидаем ответа банка...
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
              В течение минуты деньги зачислятся на карту
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
              <Button disabled={!hasAmount} onClick={() => setScreen('confirmation')} fullWidth>
                Продолжить
              </Button>
            )}

            {screen === 'confirmation' && (
              <Button
                onClick={() => paymentMethod === 'usdt' ? handleCryptoInitiate() : setScreen('loading')}
                fullWidth
              >
                Продолжить
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
    </Portal>
  )
}

export default TopUpModal
