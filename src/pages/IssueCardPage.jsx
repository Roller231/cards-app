import { useEffect, useRef, useState } from 'react'

function IssueCardPage({ onBack }) {
  const [selectedCardType, setSelectedCardType] = useState('')
  const [amount, setAmount] = useState(0)
  const [paymentMethod, setPaymentMethod] = useState('usdt')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const amountInputRef = useRef(null)

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
    { id: 'online', name: 'Online', commission: 0.4 },
    { id: 'online-plus', name: 'Online + Apple Pay + Google Pay', commission: 0.4 },
  ]

  const selectedCard = cardTypes.find((c) => c.id === selectedCardType)
  const commission = selectedCard && amount > 0 ? selectedCard.commission : 0
  const total = amount + commission
  const hasAmount = amount > 0
  const amountText = amount ? String(amount) : ''
  const selectedCardName = selectedCardType
    ? cardTypes.find((c) => c.id === selectedCardType)?.name
    : ''

  return (
    <div className="flex-1 flex flex-col pb-10">
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-full max-w-[430px] z-20">
        <div className="px-4 pt-4 pb-6">
          <div className="flex items-center">
            <button
              onClick={onBack}
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
            <h1
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: '#111827',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              Выпустить карту
            </h1>
          </div>
        </div>
      </div>

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

        {/* Commission */}
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
            Комиссия
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
              {commission.toFixed(1)}
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
            Итоговая сумма
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
              {total.toLocaleString('en-US')}
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
        <button
          disabled={!selectedCardType || amount <= 0}
          className="w-full transition-transform duration-150 active:scale-95"
          style={{
            marginTop: 16,
            padding: '16px',
            backgroundColor: selectedCardType && amount > 0 ? '#DC4D35' : '#D1D5DB',
            borderRadius: 12,
            border: 'none',
            fontSize: 16,
            fontWeight: 600,
            color: '#FFFFFF',
            fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
            cursor: selectedCardType && amount > 0 ? 'pointer' : 'not-allowed',
          }}
        >
          Оформить карту
        </button>
      </div>
    </div>
  )
}

export default IssueCardPage
