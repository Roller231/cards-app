import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'
import Button from '../components/ui/Button'
import PageHeader from '../components/ui/PageHeader'

const PAYMENT_METHODS = [
  { id: 'sbp', label: 'СБП', iconSrc: '/images/sbp.png' },
  { id: 'trc20', label: 'USDT TRC-20', iconSrc: '/images/TRC.png' },
  { id: 'erc20', label: 'USDT ERC-20', iconSrc: '/images/erc.png' },
]

function IssueCardPage({ onBack, initialCardType, onCardIssued, onCryptoPaymentInitiated }) {
  const { user, commissions } = useAuth()
  const [offers, setOffers] = useState([])
  const [offersLoading, setOffersLoading] = useState(true)
  const [selectedCardType, setSelectedCardType] = useState('')
  const [amount, setAmount] = useState(0)
  const [amountInput, setAmountInput] = useState('')
  const [totalInput, setTotalInput] = useState('')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [resultScreen, setResultScreen] = useState(null) // 'success' | 'failure'
  const [errorMsg, setErrorMsg] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('sbp')
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
  const fixedFee = useMemo(() => {
    return Number(selectedCard?.issue_fee || 0)
  }, [selectedCard])
  const minimumCardBalance = Number(selectedCard?.minimum_card_balance || 0)
  const commission = round2(fixedFee)
  const total = amount > 0 ? round2(amount + commission) : 0
  const hasAmount = amount > 0
  const amountText = amountInput || ''
  const selectedCardName = selectedCard?.name || ''

  const canIssueCard = selectedCardType !== '' && amount >= minimumCardBalance && total > 0

  useEffect(() => {
    if (lastEditedRef.current !== 'amount') return
    if (!amount || amount <= 0) { setTotalInput(''); return }
    setTotalInput(round2(amount + commission).toFixed(2))
  }, [amount, commission])

  useEffect(() => {
    if (lastEditedRef.current !== 'total') return
    if (!amount || amount <= 0) { setAmountInput(''); return }
    setAmountInput(String(amount))
  }, [amount])

  useEffect(() => {
    if (lastEditedRef.current !== 'amount') return
    if (!amount || amount <= 0) { setTotalInput(''); return }
    setTotalInput(round2(amount + commission).toFixed(2))
  }, [commission]) // eslint-disable-line react-hooks/exhaustive-deps

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

  const handleIssueCard = async () => {
    setIsLoading(true)
    setErrorMsg('')
    try {
      const usernameParts = String(user?.username || '').trim().split(/\s+/).filter(Boolean)
      const holderFirstName = usernameParts[0] || 'Test'
      const holderLastName = usernameParts.slice(1).join(' ') || 'User'
      if (paymentMethod === 'trc20' || paymentMethod === 'erc20') {
        const network = paymentMethod === 'erc20' ? 'ERC-20' : 'TRC-20'
        const result = await api.cryptoPayments.initiate(String(selectedCardType), amount, network)
        setIsLoading(false)
        setShowConfirmation(false)
        onCryptoPaymentInitiated?.({ ...result, type: 'issue' })
      } else {
        await api.cards.issue({
          offerId: String(selectedCardType),
          holderFirstName,
          holderLastName,
          amount,
          email: user?.email,
          paymentMethod: 'sbp',
        })
        setIsLoading(false)
        setResultScreen('success')
      }
    } catch (e) {
      setIsLoading(false)
      setErrorMsg(e.message || 'Ошибка при выпуске карты')
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

        {selectedCard && (
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 12,
              padding: '12px 16px',
              color: '#111827',
              fontSize: 13,
              fontWeight: 600,
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
            }}
          >
            Минимум для данной карты: {minimumCardBalance.toLocaleString('en-US', { maximumFractionDigits: 2 })} $
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
            Способ оплаты
          </label>
          {PAYMENT_METHODS.map((method) => (
            <div
              key={method.id}
              onClick={() => setPaymentMethod(method.id)}
              style={{
                backgroundColor: 'white',
                borderRadius: 12,
                padding: '14px 16px',
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: method.iconSrc ? 12 : 0,
                cursor: 'pointer',
                border: paymentMethod === method.id ? '2px solid #DC4D35' : '2px solid transparent',
                boxSizing: 'border-box',
              }}
            >
              {method.iconSrc ? (
                <img src={method.iconSrc} alt="" style={{ width: 22, height: 22, objectFit: 'contain', flexShrink: 0 }} />
              ) : null}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>{method.label}</div>
              </div>
              {paymentMethod === method.id && (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#DC4D35" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </div>
          ))}
        </div>

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

                {/* Способ оплаты */}
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
                    Способ оплаты
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    {PAYMENT_METHODS.find((m) => m.id === paymentMethod)?.label || 'СБП'}
                  </div>
                </div>
              </div>


              {/* Continue Button */}
              <Button
                onClick={() => {
                  setShowConfirmation(false)
                  handleIssueCard()
                }}
                fullWidth
                style={{ marginTop: 24 }}
              >
                {paymentMethod === 'sbp' ? 'Подтвердить и выпустить' : 'Перейти к оплате'}
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
            {paymentMethod === 'sbp' ? 'Выпускаем карту...' : 'Создаём платёж...'}
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
                maxWidth: 320,
                lineHeight: 1.5,
                animation: 'textAppear 0.5s ease-out 0.2s backwards',
              }}
            >
              Запрос на выпуск карты отправлен успешно. Ожидайте до 5 минут.
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
