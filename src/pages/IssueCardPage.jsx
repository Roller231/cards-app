import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'
import Button from '../components/ui/Button'
import PageHeader from '../components/ui/PageHeader'

function IssueCardPage({ onBack, initialCardType, onCardIssued, onCryptoPaymentInitiated, getCommissionForCardType }) {
  const { user, commissions } = useAuth()
  const [offers, setOffers] = useState([])
  const [offersLoading, setOffersLoading] = useState(true)
  const [selectedCardType, setSelectedCardType] = useState('')
  const [amount, setAmount] = useState(0)
  const [amountInput, setAmountInput] = useState('')
  const [totalInput, setTotalInput] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('usdt')
  const [network, setNetwork] = useState('TRC-20')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [resultScreen, setResultScreen] = useState(null) // 'success' | 'failure'
  const [errorMsg, setErrorMsg] = useState('')
  const amountInputRef = useRef(null)
  const totalInputRef = useRef(null)
  const lastEditedRef = useRef('amount')


  // Load card offers from API
  useEffect(() => {
    setOffersLoading(true)
    api.cards.offers()
      .then((data) => {
        setOffers(Array.isArray(data) ? data : [])
        setOffersLoading(false)
      })
      .catch(() => {
        setOffers([])
        setOffersLoading(false)
      })
  }, [])

  useEffect(() => {
    if (initialCardType && offers.length > 0) {
      const found = offers.find((o) => String(o.id) === String(initialCardType))
      if (found) setSelectedCardType(String(found.id))
    }
  }, [initialCardType, offers])

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

  // Alias for display: card types = offers
  const cardTypes = offers

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

  const selectedCard = cardTypes.find((c) => String(c.id) === String(selectedCardType))
  const isOnlinePlusSelected = String(selectedCardType) === '525847'
  const cardValidityText = isOnlinePlusSelected
    ? (commissions?.online_plus_validity_text || '1 год')
    : (commissions?.online_validity_text || '1 год')
  // Get fixed fee for selected card type
  const fixedFee = useMemo(() => {
    if (!selectedCardType || !getCommissionForCardType) return 0
    return getCommissionForCardType(selectedCardType, 'issue')  // Returns fixed USD amount
  }, [selectedCardType, getCommissionForCardType])
  const total = amount > 0 ? round2(amount + fixedFee) : 0
  const commission = fixedFee
  const hasAmount = amount > 0
  const amountText = amountInput || ''
  const selectedCardName = selectedCard?.name || ''

  const canIssueCard = selectedCardType !== '' && amount >= 15

  useEffect(() => {
    if (lastEditedRef.current !== 'amount') return
    if (!amount || amount <= 0) { setTotalInput(''); return }
    setTotalInput(round2(amount + fixedFee).toFixed(2))
  }, [amount, fixedFee])

  useEffect(() => {
    if (lastEditedRef.current !== 'total') return
    if (!amount || amount <= 0) { setAmountInput(''); return }
    setAmountInput(String(amount))
  }, [amount])

  useEffect(() => {
    if (lastEditedRef.current !== 'amount') return
    if (!amount || amount <= 0) { setTotalInput(''); return }
    setTotalInput(round2(amount + fixedFee).toFixed(2))
  }, [fixedFee]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (lastEditedRef.current !== 'total') return
    if (!totalInput) { setAmount(0); setAmountInput(''); return }
    const parsedTotal = parseFloat(totalInput) || 0
    if (!parsedTotal || parsedTotal <= 0) { setAmount(0); setAmountInput(''); return }
    const nextAmount = parsedTotal - fixedFee
    const safeAmount = nextAmount > 0 ? round2(nextAmount) : 0
    setAmount(safeAmount)
    setAmountInput(String(safeAmount))
  }, [fixedFee, totalInput]) // eslint-disable-line react-hooks/exhaustive-deps

  // Initiate crypto payment for card issuance
  const handleInitiateCrypto = async () => {
    setIsLoading(true)
    setErrorMsg('')
    try {
      const paymentData = await api.cryptoPayments.initiate(
        String(selectedCardType),
        amount,
        network,
      )
      setIsLoading(false)
      if (onCryptoPaymentInitiated) {
        onCryptoPaymentInitiated(paymentData)
      }
    } catch (e) {
      setIsLoading(false)
      setErrorMsg(e.message || 'Ошибка при создании платежа')
      setResultScreen('failure')
    }
  }

  return (
    <div className="flex-1 flex flex-col pb-10">
      <PageHeader title="Выпустить карту" onBack={onBack} />

      <div className="px-4 flex flex-col gap-4" style={{ paddingTop: 72 }}>
        {/* Card Type Dropdown */}
        <div style={{ position: 'relative' }}>
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: 12,
              padding: '14px 16px',
            }}
          >
            <label
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: '#6B7280',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                display: 'block',
                marginBottom: 8,
              }}
            >
              Тип карты
            </label>
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="w-full flex items-center justify-between transition-transform duration-150 active:scale-[0.98]"
              style={{
                padding: 0,
                backgroundColor: 'transparent',
                border: 'none',
                outline: 'none',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <span
                style={{
                  fontSize: 15,
                  fontWeight: selectedCardType ? 600 : 400,
                  color: selectedCardType ? '#111827' : '#6B7280',
                  fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                }}
              >
                {offersLoading ? 'Загрузка...' : selectedCardName || 'Выберите тип карты'}
              </span>
              <svg
                width="16"
                height="16"
                viewBox="0 0 14 14"
                fill="none"
                style={{
                  transform: isDropdownOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                  transition: 'transform 0.2s',
                }}
              >
                <path
                  d="M3 5L7 9L11 5"
                  stroke="#6B7280"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>

          {/* Dropdown List */}
          {isDropdownOpen && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 4px)',
                left: 0,
                right: 0,
                backgroundColor: 'white',
                borderRadius: 12,
                overflow: 'hidden',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
                zIndex: 50,
              }}
            >
              {cardTypes.map((card, index) => (
                <button
                  key={card.id}
                  onClick={() => {
                    setSelectedCardType(String(card.id))
                    setIsDropdownOpen(false)
                  }}
                  className="w-full transition-colors duration-150"
                  style={{
                    padding: '14px 16px',
                    backgroundColor: String(selectedCardType) === String(card.id) ? '#F3F5F8' : 'white',
                    border: 'none',
                    borderTop: index > 0 ? '1px solid #F3F5F8' : 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontSize: 15,
                    fontWeight: 600,
                    color: '#111827',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  }}
                  onMouseEnter={(e) => {
                    if (selectedCardType !== card.id) {
                      e.currentTarget.style.backgroundColor = '#F9FAFB'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedCardType !== card.id) {
                      e.currentTarget.style.backgroundColor = 'white'
                    }
                  }}
                >
                  {card.name}
                </button>
              ))}
            </div>
          )}
        </div>


        {/* Amount */}
        <div
          onClick={() => amountInputRef.current?.focus()}
          style={{
            backgroundColor: 'white',
            borderRadius: 12,
            padding: '14px 16px',
            cursor: 'text',
          }}
        >
          <label
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: '#6B7280',
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              display: 'block',
              marginBottom: 8,
            }}
          >
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
      border: 'none',
      outline: 'none',
      background: 'transparent',
      fontSize: 15,
      fontWeight: hasAmount ? 600 : 400,
      color: hasAmount ? '#111827' : '#6B7280',
      fontFamily:
        '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
      width: getInputWidthCh(amountText),
      minWidth: '1.5ch',
    }}
  />

<span
  style={{
    fontSize: 15,
    fontWeight: 600,
    color: '#111827',
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
  }}
>
  $
</span>
</div>
        </div>

        {hasAmount && amount < 15 && (
          <div
            style={{
              backgroundColor: '#FFFBEB',
              borderRadius: 12,
              padding: '12px 16px',
              border: '1px solid #FDE68A',
              color: '#92400E',
              fontSize: 13,
              fontWeight: 600,
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
            }}
          >
            Минимальная сумма пополнения 15 $
          </div>
        )}

        {/* Total */}
        <div
          onClick={() => totalInputRef.current?.focus()}
          style={{
            backgroundColor: 'white',
            borderRadius: 12,
            padding: '14px 16px',
            cursor: 'text',
          }}
        >
          <label
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: '#6B7280',
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              display: 'block',
              marginBottom: 8,
            }}
          >
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
                const nextAmount = parsedTotal - fixedFee
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
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                width: getInputWidthCh(totalInput),
                minWidth: '1.5ch',
              }}
            />
            <span
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: '#111827',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              $
            </span>
          </div>
        </div>

        {/* Payment Method */}
        <div style={{ marginTop: 8 }}>
          <label
            style={{
              fontSize: 17,
              fontWeight: 700,
              color: '#111827',
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              display: 'block',
              marginBottom: 12,
            }}
          >
            Способ пополнения
          </label>

          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setPaymentMethod('usdt')}
              className="transition-transform duration-150 active:scale-95"
              style={{
                backgroundColor: 'white',
                border: paymentMethod === 'usdt' ? '2px solid #111827' : '2px solid transparent',
                borderRadius: 12,
                padding: '20px 16px',
                cursor: 'pointer',
              }}
            >
              <div className="flex flex-col items-center gap-2">
                <div
                  style={{
    width: 50,
    height: 50,
    borderRadius: 25,
                    backgroundColor: '#F3F5F8',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <img
                    src="/images/TRC.png"
                    alt="TRC"
                    style={{
                      width: 32,
                      height: 32,
                      objectFit: 'contain',
                    }}
                  />
                </div>
                <span
                  style={{
                    fontSize: 15,
                    fontWeight: 600,
                    color: '#111827',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  }}
                >
                USDT
                </span>
              </div>
            </button>

            <button
              disabled
              style={{
                backgroundColor: 'white',
                border: '2px solid transparent',
                borderRadius: 12,
                padding: '20px 16px',
                cursor: 'not-allowed',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 8,
                opacity: 0.45,
                pointerEvents: 'none',
              }}
            >
              <div style={{
                width: 50, height: 50, borderRadius: 25,
                backgroundColor: '#F3F5F8',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <img src="/images/sbp.png" alt="СБП" style={{ width: 38, height: 38, objectFit: 'contain' }} />
              </div>
              <span style={{
                fontSize: 15, fontWeight: 600, color: '#111827',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}>СБП</span>
              <span style={{ fontSize: 11, fontWeight: 500, color: '#9CA3AF', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginTop: -4 }}>Скоро</span>
            </button>
          </div>
        </div>

        {/* Network selector (shown only for USDT) */}
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
                  fontSize: 13, fontWeight: 600,
                  fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  cursor: 'pointer',
                  transition: 'background-color 0.15s, color 0.15s',
                }}
              >
                {net}
              </button>
            ))}
          </div>
        )}

        {/* Issue Button */}
        <Button
          disabled={!canIssueCard}
          onClick={() => {
            if (!canIssueCard) return
            setShowConfirmation(true)
          }}
          fullWidth
          style={{ marginTop: 16 }}
        >
          Оформить карту
        </Button>
      </div>

      {/* Confirmation Modal */}
      {showConfirmation && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: '#F3F5F8',
            zIndex: 100,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Header */}
          <div className="fixed top-0 left-1/2 -translate-x-1/2 w-full max-w-[430px] z-20" style={{ backgroundColor: '' }}>
            <div className="px-4 pt-4 pb-0">
              <div className="flex items-center">
                <button
                  onClick={() => setShowConfirmation(false)}
                  className="flex items-center justify-center transition-transform duration-150 active:scale-95"
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 16,
                    backgroundColor: '#F3F5F8',
                    border: 'none',
                    cursor: 'pointer',
                    marginRight: 12,
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M10 12L6 8L10 4"
                      stroke="#111827"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          {/* Content */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              paddingTop: 40,
              paddingBottom: 32,
            }}
          >
            <div style={{ padding: '0 16px' }}>
              {/* Card Preview */}
              <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'center' }}>
                <img
                  src="/images/CardExample.png"
                  alt="Card"
                  style={{
                    width: '66.67%',
                    height: 'auto',
                    borderRadius: 12,
                  }}
                />
              </div>

              {/* Card Details */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Тип карты */}
                <div>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 400,
                      color: '#6B7280',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                      marginBottom: 4,
                    }}
                  >
                    Тип карты
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    MasterCard
                  </div>
                </div>

                {/* Срок действия */}
                <div>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 400,
                      color: '#6B7280',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                      marginBottom: 4,
                    }}
                  >
                    Срок действия
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    {cardValidityText}
                  </div>
                </div>

                {/* Обслуживание */}
                <div>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 400,
                      color: '#6B7280',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                      marginBottom: 4,
                    }}
                  >
                    Обслуживание
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    Бесплатно
                  </div>
                </div>

                {/* Сумма к пополнению */}
                <div>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 400,
                      color: '#6B7280',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                      marginBottom: 4,
                    }}
                  >
                    Сумма к пополнению
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    {total.toLocaleString('en-US')} $
                  </div>
                </div>

                {/* Способ пополнения */}
                <div>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 400,
                      color: '#6B7280',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                      marginBottom: 4,
                    }}
                  >
                    Способ пополнения
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    {paymentMethod === 'usdt' ? 'USDT' : 'СБП'}
                  </div>
                </div>
              </div>


              {/* Continue Button */}
              <Button
                onClick={() => {
                  setShowConfirmation(false)
                  handleInitiateCrypto()
                }}
                fullWidth
                style={{ marginTop: 24 }}
              >
                Подтвердить и выпустить
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Loading Screen */}
      {isLoading && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: '#F3F5F8',
            zIndex: 200,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 24,
          }}
        >
          {/* Spinner */}
          <svg
            width="48"
            height="48"
            viewBox="0 0 48 48"
            style={{
              animation: 'spin 1s linear infinite',
            }}
          >
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

          {/* Loading Text */}
          <div
            style={{
              fontSize: 16,
              fontWeight: 400,
              color: '#111827',
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
            }}
          >
            Создаём платёж...
          </div>
        </div>
      )}

      {/* Success Screen */}
      {resultScreen === 'success' && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: '#F3F5F8',
            zIndex: 200,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 16px',
          }}
        >
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 16,
              marginBottom: 'auto',
              paddingTop: '40vh',
            }}
          >
            {/* Success Icon */}
            <img
              src="/images/Agree.png"
              alt="Success"
              style={{
                width: 64,
                height: 64,
                animation: 'iconAppear 0.5s ease-out, iconIdle 2s ease-in-out 0.5s infinite',
              }}
            />

            {/* Success Text */}
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: '#111827',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                textAlign: 'center',
                animation: 'textAppear 0.5s ease-out 0.2s backwards',
              }}
            >
              Карта будет создана в течение 5 минут
            </div>
          </div>

          {/* Button at bottom */}
          <div style={{ width: '100%', maxWidth: 430, paddingBottom: 64 }}>
            <Button
              onClick={() => {
                if (onCardIssued) {
                  onCardIssued({
                    cardType: selectedCardType,
                    amount: amount,
                  })
                } else {
                  setResultScreen(null)
                  setShowConfirmation(false)
                  onBack()
                }
              }}
              fullWidth
            >
              К списку карт
            </Button>
          </div>
        </div>
      )}

      {/* Failure Screen */}
      {resultScreen === 'failure' && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: '#F3F5F8',
            zIndex: 200,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 16px',
          }}
        >
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 16,
              marginBottom: 'auto',
              paddingTop: '35vh',
            }}
          >
            {/* Failure Icon */}
            <img
              src="/images/Warning.png"
              alt="Error"
              style={{
                width: 64,
                height: 64,
                animation: 'iconAppear 0.5s ease-out, iconShake 2s ease-in-out 0.5s infinite',
              }}
            />

            {/* Failure Text */}
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: '#111827',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                textAlign: 'center',
                maxWidth: 320,
                animation: 'textAppear 0.5s ease-out 0.2s backwards',
              }}
            >
              {errorMsg || 'Не удалось связаться с банком. Проверьте интернет и повторите попытку.'}
            </div>
          </div>

          {/* Button at bottom */}
          <div style={{ width: '100%', maxWidth: 430, paddingBottom: 64 }}>
            <Button
              onClick={() => {
                setResultScreen(null)
                setIsLoading(false)
                setShowConfirmation(true)
              }}
              fullWidth
            >
              Повторить
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default IssueCardPage
