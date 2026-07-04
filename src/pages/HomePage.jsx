import { useState, useRef, useCallback } from 'react'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Section from '../components/ui/Section'
import Badge from '../components/ui/Badge'
import InfoCard from '../components/ui/InfoCard'
import { H2, H3, H4, Description } from '../components/ui/Typography'
import { useDragScroll } from '../hooks/useDragScroll'
import { TxIcon } from './HistoryPage'

const PULL_THRESHOLD = 120
const PULL_MAX = 180
const PULL_DEAD_ZONE = 30

function HomePage({ userCards = [], transactions = [], onNavigateToFAQ, onNavigateToIssueCard, onCardClick, onNavigateToHistory, commissions = {}, cardsLoading = false, transactionsLoading = false, onRefresh, issueLimitReached = false }) {
  const [expandedCard, setExpandedCard] = useState(null)
  const scrollRef = useDragScroll()
  const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

  const totalBalance = userCards.reduce((sum, c) => sum + (Number(c.balance) || 0), 0)

  const isOnlineExpanded = expandedCard === 'online'
  const isOnlinePlusExpanded = expandedCard === 'online-plus'

  // Pull-to-refresh state
  const [pull, setPull] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const touchStartY = useRef(null)

  const handleTouchStart = useCallback((e) => {
    if (refreshing) return
    if ((window.scrollY || document.documentElement.scrollTop || 0) > 0) {
      touchStartY.current = null
      return
    }
    touchStartY.current = e.touches[0].clientY
  }, [refreshing])

  const handleTouchMove = useCallback((e) => {
    if (refreshing) return
    if (touchStartY.current == null) return
    const dy = e.touches[0].clientY - touchStartY.current
    if (dy <= PULL_DEAD_ZONE) {
      // Inside dead zone — ignore so casual small downward gestures don't trigger PTR.
      setPull(0)
      return
    }
    // Add some resistance after the dead zone.
    const effective = dy - PULL_DEAD_ZONE
    const resisted = Math.min(PULL_MAX, effective * 0.45)
    setPull(resisted)
  }, [refreshing])

  const handleTouchEnd = useCallback(async () => {
    if (refreshing) return
    const dist = pull
    touchStartY.current = null
    if (dist >= PULL_THRESHOLD && typeof onRefresh === 'function') {
      setRefreshing(true)
      setPull(PULL_THRESHOLD)
      try {
        await onRefresh()
      } catch {}
      setRefreshing(false)
      setPull(0)
    } else {
      setPull(0)
    }
  }, [pull, refreshing, onRefresh])

  const indicatorOffset = refreshing ? PULL_THRESHOLD : pull
  const indicatorOpacity = Math.min(1, pull / PULL_THRESHOLD)
  const indicatorRotation = Math.min(360, (pull / PULL_THRESHOLD) * 360)

  return (
    <div
      className="flex-1 flex flex-col pb-24"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
      style={{ touchAction: 'pan-y' }}
    >
      {(pull > 0 || refreshing) && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: '50%',
            transform: `translate(-50%, ${indicatorOffset - 24}px)`,
            transition: refreshing ? 'transform 200ms ease' : 'none',
            zIndex: 50,
            width: 36,
            height: 36,
            borderRadius: '50%',
            background: '#FFFFFF',
            boxShadow: '0 2px 10px rgba(0,0,0,0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: indicatorOpacity,
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              width: 18,
              height: 18,
              border: '2.5px solid #E5E7EB',
              borderTopColor: '#FF5C39',
              borderRadius: '50%',
              transform: refreshing ? 'none' : `rotate(${indicatorRotation}deg)`,
              animation: refreshing ? 'spin 0.7s linear infinite' : 'none',
            }}
          />
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <div style={{
        transform: `translateY(${indicatorOffset}px)`,
        transition: (pull === 0 && !refreshing) ? 'transform 200ms ease' : 'none',
      }}>
      <Section>
        <Card padding="24px 24px 0 24px">
          <div className="flex items-start justify-between">
            <div
              className="text-[16px] font-semibold leading-[22px]"
              style={{
                color: '#6B7280',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              Общий баланс
            </div>
            <Button variant="icon" onClick={onNavigateToFAQ}>
              <img src="/images/QuestionMark.png" alt="" />
            </Button>
          </div>

          <div className="flex items-baseline mb-4">
            <span
              style={{
                fontSize: 36,
                lineHeight: 'auto',
                fontWeight: 700,
                color: '#111827',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              {totalBalance.toLocaleString('en-US', {
                minimumFractionDigits: 0,
                maximumFractionDigits: 2,
              })}
            </span>
            <span
              style={{
                fontSize: 36,
                fontWeight: 500,
                color: '#6B7280',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                marginLeft: 4,
                textShadow: '0 0 0 currentColor',
              }}
            >
              $
            </span>
          </div>

          <div className="flex items-center justify-between mb-3">
            <h2
              style={{
                fontSize: 24,
                fontWeight: 700,
                color: '#111827',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              Мои карты
            </h2>

            <Button
              variant="link"
              disabled={issueLimitReached}
              onClick={() => {
                if (issueLimitReached) return
                onNavigateToIssueCard()
              }}
              style={issueLimitReached ? { color: '#9CA3AF', cursor: 'not-allowed' } : undefined}
            >
              <span className="relative mr-2 inline-block h-3 w-3">
                <span className="absolute left-1/2 top-1/2 h-[2.5px] w-full -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" />
                <span className="absolute left-1/2 top-1/2 h-full w-[2.5px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" />
              </span>
              <span>{issueLimitReached ? 'Лимит карт' : 'Оформить карту'}</span>
            </Button>
          </div>

          {/* Single scroll container — ref stays stable so drag-scroll listeners survive reloads */}
          {(!cardsLoading && userCards.length === 0) ? (
            <div
              className="pb-6 font-semibold"
              style={{
                fontSize: 16,
                color: '#6B7280',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                marginBlock: 12,
              }}
            >
              У вас пока нет карт
            </div>
          ) : (
            <div
              ref={scrollRef}
              className="pb-6 cards-scroll"
              style={{
                overflowX: 'auto',
                overflowY: 'hidden',
                marginLeft: -24,
                marginRight: -24,
                paddingLeft: 24,
                paddingRight: 120,
                scrollbarWidth: 'none',
                msOverflowStyle: 'none',
              }}
            >
              <div style={{ display: 'flex', gap: 12 }}>
                {cardsLoading
                  ? [1, 2].map((i) => (
                      <div
                        key={i}
                        style={{
                          minWidth: 240, height: 144, borderRadius: 20,
                          backgroundColor: '#E5E7EB', flexShrink: 0,
                          animation: 'pulse 1.5s ease-in-out infinite',
                        }}
                      />
                    ))
                  : userCards.map((card) => (
                      <div
                        key={card.id}
                    className="transition-transform duration-150 active:scale-95"
                        style={{
                      minWidth: 240,
                      height: 144,
                      borderRadius: 20,
                      padding: 18,
                          cursor: 'pointer',
                      position: 'relative',
                      color: '#FFFFFF',
                      backgroundImage: 'url(/images/CardInBalance.png)',
                      backgroundSize: 'cover',
                      backgroundPosition: 'center',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                          overflow: 'hidden',
                        }}
                        onClick={() => onCardClick && onCardClick(card)}
                      >
                        <div
                          style={{
                            fontSize: 22,
                            fontWeight: 500,
                            fontFamily:
                              '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                            lineHeight: '28px',
                            letterSpacing: '-0.3px',
                          }}
                        >
                          {Number(card.balance).toLocaleString('en-US', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}{' '}
                          $
                        </div>

                        <div>
                          <div
                            style={{
                              fontSize: 11,
                              fontWeight: 300,
                              fontFamily:
                                '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                              letterSpacing: '1.6px',
                              marginBottom: 15,
                              marginLeft: -3,
                            }}
                          >
                            {card.last4 ? `***${card.last4}` : (card.status === 'creating' ? 'Creating' : 'Processing')}
                          </div>

                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'flex-end',
                              justifyContent: 'space-between',
                              gap: 12,
                            }}
                          >



                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
            </div>
          )}
        </Card>
      </Section>

      {userCards.length === 0 && (
        <Section>
          <Card padding={isOnlineExpanded ? '20px 20px 16px 20px' : '20px'}>
          <div className="flex items-start justify-between">
            <div className="flex flex-col gap-2 flex-1">
              <div className="flex items-center gap-2">
                <div
                  className="flex items-center"
                  onClick={() => setExpandedCard(isOnlineExpanded ? null : 'online')}
                  style={{
                    height: 24,
                    backgroundColor: '#1A1F36',
                    borderRadius: 8,
                    paddingLeft: 8,
                    paddingRight: 8,
                    cursor: 'pointer',
                  }}
                >
                  <img
                    src="/images/Mastercard.png"
                    alt="Mastercard"
                    style={{ height: 14, width: 'auto' }}
                  />


                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#6B7280',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    paddingLeft: 4,
                  }}
                >
                  virtual
                </span>
                                </div>
              </div>

              <div className="flex-1">
                <h3
                  style={{
                    fontSize: 16,
                    fontWeight: 600,
                    color: '#111827',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    marginBottom: 2,
                  }}
                >
                  Online
                </h3>
                <p
                  style={{
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#6B7280',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    lineHeight: '16px',
                  }}
                >
                  Для оплаты покупок и сервисов в интернете
                </p>
              </div>
            </div>

<button
  onClick={() => setExpandedCard(isOnlineExpanded ? null : 'online')}
  className="flex items-center justify-center transition-transform duration-150 active:scale-95"
  style={{
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#F3F5F8',
    border: 'none',
    cursor: 'pointer',
    flexShrink: 0,
  }}
>
  <svg
    width="16"
    height="16"
    viewBox="0 0 14 14"
    fill="none"
    style={{
      transform: isOnlineExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
      transition: 'transform 0.2s',
    }}
  >
    <path
      d="M3 5L7 9L11 5"
      stroke="#111827"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
</button>
          </div>

          <div
            style={{
              marginTop: 16,
              overflow: 'hidden',
              maxHeight: isOnlineExpanded ? 1200 : 0,
              opacity: isOnlineExpanded ? 1 : 0,
              transition: 'max-height 300ms ease, opacity 200ms ease',
            }}
          >
            <div style={{ paddingBottom: 0 }}>
              <div className="flex gap-2" style={{ marginBottom: 16 }}>
                <div
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#10B981',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#FFFFFF',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  }}
                >
                  Бесплатное обслуживание
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{commissions.online_validity_text || '1 год'}</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Срок действия</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{commissions.online_operation_fee || 0.4} $</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за операцию</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{Number(commissions.online_issue_price_rub || 999).toLocaleString('ru-RU')} ₽</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Плата за выпуск</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{commissions.online_topup || 3.8} %</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за пополнение</div>
                </div>
              </div>

              <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px', marginBottom: 16 }}>
                <h4 style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 8 }}>Оплачивайте</h4>
                <p style={{ fontSize: 13, color: '#6B7280', fontFamily: font, lineHeight: '20px' }}>
                  Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>

                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
                    Гонконг
                    <img src="/images/HongKong.svg" alt="Hong Kong" style={{ width: 18, height: 18 }} />
                  </h4>
                  <p style={{ fontSize: 13, color: '#6B7280', fontFamily: font }}>Страна BIN</p>
                </div>
              </div>

<Button
  onClick={() => {
    if (issueLimitReached) return
    onNavigateToIssueCard('online')
  }}
  variant="secondary"
  disabled={issueLimitReached}
  fullWidth
  style={issueLimitReached ? { backgroundColor: '#D1D5DB', cursor: 'not-allowed' } : undefined}
>
  {issueLimitReached ? 'Достигнут лимит карт' : 'Оформить'}
</Button>
            </div>
          </div>
          </Card>
        </Section>
      )}

      {userCards.length === 0 && (
        <Section>
        <Card padding={isOnlinePlusExpanded ? '20px 20px 16px 20px' : '20px'}>
          <div className="flex items-start justify-between">
            <div className="flex flex-col gap-2 flex-1">
<div
  className="flex items-center"
  onClick={() => setExpandedCard(isOnlinePlusExpanded ? null : 'online-plus')}
  style={{
    height: 24,
    backgroundColor: '#1A1F36',
    borderRadius: 8,
    paddingLeft: 8,
    paddingRight: 5,
    width: 'fit-content',
    cursor: 'pointer',
  }}
>
                <img
                  src="/images/Mastercard.png"
                  alt="Mastercard"
                  style={{ height: 14, width: 'auto', }}
                />
                    <img src="/images/GooglePay.png" alt="Google Pay" style={{ height: 16, width: 'auto', paddingLeft: 4 }} />
                    <img src="/images/Apple.png" alt="Apple Pay" style={{ height: 16, width: 'auto', paddingLeft: 4 }} />

              </div>

              <div className="flex-1">
                <h3
                  style={{
                    fontSize: 16,
                    fontWeight: 600,
                    color: '#111827',
                    fontFamily: font,
                    marginBottom: 2,
                  }}
                >
                  Online + Pay
                </h3>
                <p
                  style={{
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#6B7280',
                    fontFamily: font,
                    lineHeight: '16px',
                  }}
                >
                  Оплата в магазинах через Apple Pay, Google Pay и онлайн-сервисов на сайтах
                </p>
              </div>
            </div>

<button
  onClick={() => setExpandedCard(isOnlinePlusExpanded ? null : 'online-plus')}
  className="flex items-center justify-center transition-transform duration-150 active:scale-95"
  style={{
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#F3F5F8',
    border: 'none',
    cursor: 'pointer',
    flexShrink: 0,
  }}
>
  <svg
    width="16"
    height="16"
    viewBox="0 0 14 14"
    fill="none"
    style={{
      transform: isOnlinePlusExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
      transition: 'transform 0.2s',
    }}
  >
    <path
      d="M3 5L7 9L11 5"
      stroke="#111827"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
</button>
          </div>

          <div
            style={{
              marginTop: 16,
              overflow: 'hidden',
              maxHeight: isOnlinePlusExpanded ? 1200 : 0,
              opacity: isOnlinePlusExpanded ? 1 : 0,
              transition: 'max-height 300ms ease, opacity 200ms ease',
            }}
          >
            <div style={{ paddingBottom: 0 }}>
              <div className="flex gap-2" style={{ marginBottom: 16 }}>
                <div
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#10B981',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#FFFFFF',
                    fontFamily: font,
                  }}
                >
                  Бесплатное обслуживание
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{commissions.online_plus_validity_text || '1 год'}</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Срок действия</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{commissions.online_plus_operation_fee || 0.4} $</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за операцию</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{Number(commissions.online_plus_issue_price_rub || 1999).toLocaleString('ru-RU')} ₽</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Плата за выпуск</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{commissions.online_plus_topup || 4} %</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за пополнение</div>
                </div>
              </div>

              <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px', marginBottom: 16 }}>
                <h4 style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 8 }}>Оплачивайте</h4>
                <p style={{ fontSize: 13, color: '#6B7280', fontFamily: font, lineHeight: '20px' }}>
                  Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
                    Гонконг
                    <img src="/images/HongKong.svg" alt="Hong Kong" style={{ width: 18, height: 18 }} />
                  </h4>
                  <p style={{ fontSize: 13, color: '#6B7280', fontFamily: font }}>Страна BIN</p>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 6 }}>Подключение</h4>
                  <div className="flex gap-2">
                    <img src="/images/GooglePay.png" alt="Google Pay" style={{ height: 20, width: 'auto' }} />
                    <img src="/images/Apple.png" alt="Apple Pay" style={{ height: 20, width: 'auto' }} />
                  </div>
                </div>

              </div>

<Button
  onClick={() => {
    if (issueLimitReached) return
    onNavigateToIssueCard('online-plus')
  }}
  variant="secondary"
  disabled={issueLimitReached}
  fullWidth
  style={issueLimitReached ? { backgroundColor: '#D1D5DB', cursor: 'not-allowed' } : undefined}
>
  {issueLimitReached ? 'Достигнут лимит карт' : 'Оформить'}
</Button>
            </div>
        </div>
        </Card>
        </Section>
      )}

      <Section>
        <Card padding="20px" style={{ minHeight: 250 }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 0 }}>
            <h2
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: '#111827',
                fontFamily: font,
                margin: 0,
              }}
            >
              История
            </h2>
            <Button variant="icon" onClick={onNavigateToHistory}>
              <div style={{
                width: 28, height: 28, borderRadius: 14,
                backgroundColor: '#F3F5F8',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M5 2l5 5-5 5" stroke="#111827" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </Button>
          </div>

          {transactions.length === 0 ? (
            <>
              <div className="flex flex-col items-center justify-center" style={{ paddingTop: 28, paddingBottom: 28 }}>
                <img src="/images/Union.png" alt="" style={{ width: 34, height: 34, marginBottom: 12, opacity: 0.65 }} />
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: '#6B7280',
                    fontFamily: font,
                  }}
                >
                  Нет операций
                </div>
              </div>
              <Button
                onClick={() => {
                  if (issueLimitReached) return
                  onNavigateToIssueCard()
                }}
                disabled={issueLimitReached}
                fullWidth
                style={{ borderRadius: 12, padding: '16px' }}
              >
                {issueLimitReached ? 'Достигнут лимит карт' : '+ Выпустить карту'}
              </Button>
            </>
          ) : (
            <div style={{ marginTop: 16 }}>
              {transactions.slice(0, 6).map((tx, idx) => {
                const isPositive = tx.amount > 0
                const absAmount = Math.abs(tx.amount)
                const formatted = absAmount.toLocaleString('en-US', {
                  minimumFractionDigits: absAmount % 1 !== 0 ? 2 : 0,
                  maximumFractionDigits: 2,
                })
                const amountStr = isPositive ? `+${formatted} $` : `−${formatted} $`
                const amountColor = isPositive ? '#22C55E' : tx.type === 'declined' ? '#DC4D35' : '#111827'

                return (
                  <div
                    key={tx.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      paddingTop: 16, paddingBottom: 16,
                      borderBottom: idx < 5 ? '1px solid #F3F5F8' : 'none',
                    }}
                  >
                    <TxIcon type={tx.type} size={50} iconSize={24} radius={16} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>
                        {tx.title}
                      </div>
                      <div style={{
                        fontSize: 13, color: tx.type === 'declined' ? '#DC4D35' : '#6B7280',
                        fontFamily: font, marginTop: 1,
                      }}>
                        {tx.subtitle}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                      <div style={{
                        fontSize: 16,
                        fontWeight: 600,
                        color: amountColor,
                        fontFamily: font,
                        textAlign: 'right',
                      }}>
                        {amountStr}
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, textAlign: 'right' }}>
                        {tx.cardTitle} · {tx.cardLast4}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </Section>
      </div>
    </div>
  )
}

export default HomePage
