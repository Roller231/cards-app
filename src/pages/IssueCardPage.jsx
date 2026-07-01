import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'
import Button from '../components/ui/Button'
import PageHeader from '../components/ui/PageHeader'
import SbpPaymentModal from '../components/ui/SbpPaymentModal'
import KycModal from '../components/ui/KycModal'

const PAYMENT_METHODS = [
  { id: 'sbp', label: 'СБП', description: 'Моментальный перевод через Систему Быстрых Платежей', iconSrc: '/images/sbp.png' },
]

function IssueCardPage({ onBack, initialCardType, onCardIssued }) {
  const { user } = useAuth()
  const [offers, setOffers] = useState([])
  const [offersLoading, setOffersLoading] = useState(true)
  const [selectedCardType, setSelectedCardType] = useState('')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [resultScreen, setResultScreen] = useState(null) // 'success' | 'failure'
  const [errorMsg, setErrorMsg] = useState('')
  const [issuancePrice, setIssuancePrice] = useState(null)
  const [showSbpModal, setShowSbpModal] = useState(false)
  const [showKycModal, setShowKycModal] = useState(false)
  const [kycStatus, setKycStatus] = useState(null)
  const [paymentMethod, setPaymentMethod] = useState(null) // 'sbp' | 'balance'


  // Load card offers and issuance price from API
  useEffect(() => {
    setOffersLoading(true)
    Promise.all([
      api.cards.offers(),
      api.cards.issuancePrice()
    ])
      .then(([offersData, priceData]) => {
        setOffers(Array.isArray(offersData) ? offersData : [])
        setIssuancePrice(priceData)
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

  const cardTypes = offers
  const selectedCard = cardTypes.find((c) => String(c.id) === String(selectedCardType))
  const selectedCardName = selectedCard?.name || ''
  
  // Select price based on card type
  const price = selectedCardName?.trim().toLowerCase().includes('pay')
    ? (Number(issuancePrice?.price_pay_rub) || 1999)
    : (Number(issuancePrice?.price_rub) || 999)
  
  const initialBalance = issuancePrice?.initial_balance || 0
  const maxCards = selectedCard?.max_issued_count || 999
  const currentCards = selectedCard?.current_count || 0
  const limitReached = currentCards >= maxCards
  const canIssueCard = selectedCardType !== '' && price > 0 && !limitReached


  const handleIssueCard = async () => {
    setIsLoading(true)
    setErrorMsg('')
    try {
      const usernameParts = String(user?.username || '').trim().split(/\s+/).filter(Boolean)
      const holderFirstName = usernameParts[0] || 'Test'
      const holderLastName = usernameParts.slice(1).join(' ') || 'User'
      await api.cards.issue({
        offerId: String(selectedCardType),
        holderFirstName,
        holderLastName,
        email: user?.email,
        paymentMethod: 'sbp',
      })
      setIsLoading(false)
      setResultScreen('success')
    } catch (e) {
      setIsLoading(false)
      // Check if it's a KYC verification error
      if (e.message?.includes('KYC') || e.message?.includes('verification') || e.message?.includes('identity')) {
        setShowKycModal(true)
      } else {
        setErrorMsg(e.message || 'Ошибка при выпуске карты')
        setResultScreen('failure')
      }
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
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>{card.name}</span>
                    {card.current_count >= card.max_issued_count && (
                      <span style={{ fontSize: 12, color: '#DC4D35', fontWeight: 500 }}>Лимит</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>


        {/* Price Info */}
        {issuancePrice && (
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: 12,
              padding: '14px 16px',
            }}
          >
            <div style={{ marginBottom: 12 }}>
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
                Стоимость выпуска карты
              </label>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>
                {price.toLocaleString('ru-RU')} ₽
              </div>
            </div>
            <div
              style={{
                backgroundColor: '#F3F5F8',
                borderRadius: 8,
                padding: '12px',
                fontSize: 13,
                color: '#6B7280',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              Карта будет выпущена с нулевым балансом. Вы сможете пополнить её после выпуска.
            </div>
          </div>
        )}

        {/* Card Limit Warning */}
        {selectedCard && limitReached && (
          <div
            style={{
              backgroundColor: '#FEF2F2',
              borderRadius: 12,
              padding: '14px 16px',
              border: '1px solid #FEE2E2',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'start', gap: 12 }}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" style={{ flexShrink: 0, marginTop: 2 }}>
                <path d="M10 6V10M10 14H10.01M19 10C19 14.9706 14.9706 19 10 19C5.02944 19 1 14.9706 1 10C1 5.02944 5.02944 1 10 1C14.9706 1 19 5.02944 19 10Z" stroke="#DC2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#991B1B', marginBottom: 4, fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>
                  Достигнут лимит карт
                </div>
                <div style={{ fontSize: 13, color: '#7F1D1D', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>
                  У вас уже {currentCards} из {maxCards} карт данного типа. Удалите неиспользуемые карты перед выпуском новой.
                </div>
              </div>
            </div>
          </div>
        )}

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
                <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>{method.label}</div>
                {method.description && (
                  <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4, fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>
                    {method.description}
                  </div>
                )}
              </div>
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

                {/* Стоимость выпуска */}
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
                    Стоимость выпуска
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    {price.toLocaleString('ru-RU')} ₽
                  </div>
                </div>

                {/* Начальный баланс */}
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
                    Начальный баланс карты
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      color: '#111827',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    }}
                  >
                    $0.00
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
                    СБП
                  </div>
                </div>
              </div>


              {/* Continue Button */}
              <Button
                onClick={async () => {
                  setShowConfirmation(false)
                  // Check KYC status before opening SBP
                  try {
                    const s = await api.kyc.status()
                    if (s.kyc_status === 'success') {
                      setShowSbpModal(true)
                    } else {
                      setShowKycModal(true)
                    }
                  } catch {
                    setShowKycModal(true)
                  }
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
            Выпускаем карту...
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
              {paymentMethod === 'sbp' 
                ? 'Оплата прошла успешно! Карта выпускается, ожидайте до 5 минут.'
                : 'Запрос на выпуск карты отправлен успешно. Ожидайте до 5 минут.'}
            </div>
          </div>

          {/* Button at bottom */}
          <div style={{ width: '100%', maxWidth: 430, paddingBottom: 64 }}>
            <Button
              onClick={() => {
                if (onCardIssued) {
                  onCardIssued({
                    cardType: selectedCardType,
                    price,
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

      <KycModal
        isOpen={showKycModal}
        onClose={() => setShowKycModal(false)}
        onSuccess={() => {
          setShowKycModal(false)
          setShowSbpModal(true)
        }}
      />

      <SbpPaymentModal
        isOpen={showSbpModal}
        onClose={() => setShowSbpModal(false)}
        amountRub={price || 999}
        purpose="card_issue"
        offerId={String(selectedCardType)}
        skipSuccessScreen={true}
        onPaid={() => {
          setShowSbpModal(false)
          setPaymentMethod('sbp')
          setResultScreen('success')
        }}
      />
    </div>
  )
}

export default IssueCardPage
