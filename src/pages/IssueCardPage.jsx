import { useEffect, useRef, useState } from 'react'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'
import FormField from '../components/ui/FormField'

function IssueCardPage({ onBack, initialCardType, onCardIssued }) {
  const [selectedCardType, setSelectedCardType] = useState('')
  const [amount, setAmount] = useState(0)
  const [paymentMethod, setPaymentMethod] = useState('usdt')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [resultScreen, setResultScreen] = useState(null) // 'success' or 'failure'
  const amountInputRef = useRef(null)

  // Toggle this variable to test success/failure screens
  const SIMULATE_SUCCESS = true // Change to false to test failure screen

  useEffect(() => {
    if (initialCardType) {
      setSelectedCardType(initialCardType)
    }
  }, [initialCardType])

  // Simulate loading delay and show result after 4 seconds
  useEffect(() => {
    if (isLoading) {
      const timer = setTimeout(() => {
        setIsLoading(false)
        setResultScreen(SIMULATE_SUCCESS ? 'success' : 'failure')
      }, 4000)

      return () => clearTimeout(timer)
    }
  }, [isLoading, SIMULATE_SUCCESS])

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

  const cardTypes = [
    { id: 'online', name: 'Online', topUpCommissionPercent: 3.8 },
    { id: 'online-plus', name: 'Online + Pay', topUpCommissionPercent: 4 },
  ]

  const selectedCard = cardTypes.find((c) => c.id === selectedCardType)
  const commission =
    selectedCard && amount > 0
      ? (amount * (selectedCard.topUpCommissionPercent || 0)) / 100
      : 0
  const total = amount + commission
  const hasAmount = amount > 0
  const amountText = amount ? String(amount) : ''
  const selectedCardName = selectedCardType
    ? cardTypes.find((c) => c.id === selectedCardType)?.name
    : ''

  const canIssueCard = selectedCardType !== '' && amount >= 15

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
                {selectedCardName || 'Тип карты'}
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
                    setSelectedCardType(card.id)
                    setIsDropdownOpen(false)
                  }}
                  className="w-full transition-colors duration-150"
                  style={{
                    padding: '14px 16px',
                    backgroundColor: selectedCardType === card.id ? '#F3F5F8' : 'white',
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
<div className="flex items-center" style={{ gap: 6 }}>
  <input
    ref={amountInputRef}
    type="number"
    value={amount || ''}
    onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
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
      width: `${Math.max(amountText.length, 1) + 0.5}ch`,
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
            Итоговая сумма с учетом комиссии
          </label>
          <div className="flex items-center" style={{ gap: 6 }}>
            <span
              style={{
                fontSize: 15,
                fontWeight: hasAmount ? 600 : 400,
                color: hasAmount ? '#111827' : '#6B7280',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              {total.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
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
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 8,
              }}
            >
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
    src="/images/bank-card.png"
    alt="Bank Card"
    style={{
      width: 28,
      height: 28,
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
            </button>

            <button
              onClick={() => setPaymentMethod('sbp')}
              className="transition-transform duration-150 active:scale-95"
              style={{
                backgroundColor: 'white',
                border: paymentMethod === 'sbp' ? '2px solid #111827' : '2px solid transparent',
                borderRadius: 12,
                padding: '20px 16px',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 8,
              }}
            >
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
    src="/images/Qr_Code.png"
    alt="QR Code"
    style={{
      width: 28,
      height: 28,
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
                СБП
              </span>
            </button>
          </div>
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
          <div className="fixed top-0 left-1/2 -translate-x-1/2 w-full max-w-[430px] z-20" style={{ backgroundColor: '#F3F5F8' }}>
            <div className="px-4 pt-4 pb-6">
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
              paddingTop: 72,
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
                    7 лет
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
                  setResultScreen(null)
                  setIsLoading(true)
                }}
                fullWidth
                style={{ marginTop: 24 }}
              >
                Продолжить
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
            Начинаем выпуск карты...
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
              Карта готова!
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
              Не удалось связаться с банком. Проверьте интернет и повторите попытку.
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
