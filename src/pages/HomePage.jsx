import { useState } from 'react'

function HomePage() {
  const [expandedCard, setExpandedCard] = useState(null)

  const isOnlineExpanded = expandedCard === 'online'
  const isOnlinePlusExpanded = expandedCard === 'online-plus'

  return (
    <div className="flex-1 flex flex-col pb-10">
      <div className="px-4 pt-4">
        <div
          className="bg-white w-full"
          style={{
            borderRadius: 20,
            padding: '24px 24px 0 24px',
          }}
        >
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
            <button
              className="flex items-center justify-center"
              style={{
                width: 28,
                height: 28,
                borderRadius: 30,

                backgroundColor: 'transparent',
              }}
            >
              {/* <span
                style={{
                  color: '#6B7280',
                  fontSize: 21,
                  fontWeight: 650,
                  lineHeight: 1,
                }}
              >
                ?
              </span> */}
              <img src="/images/QuestionMark.png" alt="" />
            </button>
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
              0
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

            <button
              className="flex items-center"
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: '#DC4D35',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <span className="relative mr-2 inline-block h-3 w-3">
                <span className="absolute left-1/2 top-1/2 h-[2.5px] w-full -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" />
                <span className="absolute left-1/2 top-1/2 h-full w-[2.5px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" />
              </span>
              <span>Оформить карту</span>
            </button>
          </div>

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
        </div>
      </div>

      <div className="px-4 pt-4">
        <div
          className="bg-white w-full"
          style={{
            borderRadius: 20,
            padding: isOnlineExpanded ? '20px 20px 16px 20px' : '20px',
          }}
        >
          <div className="flex items-start justify-between">
            <div className="flex flex-col gap-2 flex-1">
              <div className="flex items-center gap-2">
                <div
                  className="flex items-center"
                  style={{
                    height: 24,
                    backgroundColor: '#1A1F36',
                    borderRadius: 8,
                    paddingLeft: 8,
                    paddingRight: 8,
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
              className="flex items-center justify-center"
              style={{
                width: 28,
                height: 28,
                borderRadius: 14,
                backgroundColor: 'transparent',
                border: 'none',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ transform: isOnlineExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
                <path d="M3 5L7 9L11 5" stroke="#9CA3AF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
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
                <div
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#3B82F6',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#FFFFFF',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  }}
                >
                  Бесплатный выпуск
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>0 $</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Выпуск карты</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>1 год</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Срок действия</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>0,4 $</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за операцию</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>3,8 %</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за пополнение</div>
                </div>
              </div>

              <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px', marginBottom: 16 }}>
                <h4 style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 8 }}>Оплачивайте</h4>
                <p style={{ fontSize: 13, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', lineHeight: '20px' }}>
                  Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 6 }}>Подключение</h4>
                  <div className="flex gap-2">
                    <img src="/images/GooglePay.png" alt="Google Pay" style={{ height: 20, width: 'auto' }} />
                    <img src="/images/Apple.png" alt="Apple Pay" style={{ height: 20, width: 'auto' }} />
                  </div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 6 }}>Гонконг</h4>
                  <p style={{ fontSize: 13, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>Страна BIN</p>
                </div>
              </div>

<button
  className="w-full transition-transform duration-150 active:scale-95"
  style={{
    padding: '14px',
    backgroundColor: '#DC4D35',
    borderRadius: 12,
    border: 'none',
    fontSize: 16,
    fontWeight: 600,
    color: '#FFFFFF',
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
    cursor: 'pointer',
  }}
>
  Оформить
</button>
            </div>
          </div>
        </div>
      </div>

      <div className="px-4 pt-4">
        <div
          className="bg-white w-full"
          style={{
            borderRadius: 20,
            padding: isOnlinePlusExpanded ? '20px 20px 16px 20px' : '20px',
          }}
        >
          <div className="flex items-start justify-between">
            <div className="flex flex-col gap-2 flex-1">
<div
  className="flex items-center"
  style={{
    height: 24,
    backgroundColor: '#1A1F36',
    borderRadius: 8,
    paddingLeft: 8,
    paddingRight: 5,
    width: 'fit-content',
  }}
>
                <img
                  src="/images/Mastercard.png"
                  alt="Mastercard"
                  style={{ height: 14, width: 'auto', }}
                />
                    <img src="/images/GooglePay.png" alt="Google Pay" style={{ height: 16, width: 'auto', paddingLeft: 4 }} />

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
                  Online + Apple Pay + Google Pay
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
                  Оплата в магазинах через Apple Pay, Google Pay и онлайн-сервисов на сайтах
                </p>
              </div>
            </div>

            <button
              onClick={() => setExpandedCard(isOnlinePlusExpanded ? null : 'online-plus')}
              className="flex items-center justify-center"
              style={{
                width: 28,
                height: 28,
                borderRadius: 14,
                backgroundColor: 'transparent',
                border: 'none',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ transform: isOnlinePlusExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
                <path d="M3 5L7 9L11 5" stroke="#9CA3AF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
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
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  }}
                >
                  Бесплатное обслуживание
                </div>
                <div
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#3B82F6',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 400,
                    color: '#FFFFFF',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                  }}
                >
                  Бесплатный выпуск
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>0 $</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Выпуск карты</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>1 год</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Срок действия</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>0,4 $</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за операцию</div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 2 }}>4 %</div>
                  <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за пополнение</div>
                </div>
              </div>

              <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px', marginBottom: 16 }}>
                <h4 style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 8 }}>Оплачивайте</h4>
                <p style={{ fontSize: 13, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', lineHeight: '20px' }}>
                  Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 6 }}>Подключение</h4>
                  <div className="flex gap-2">
                    <img src="/images/GooglePay.png" alt="Google Pay" style={{ height: 20, width: 'auto' }} />
                    <img src="/images/Apple.png" alt="Apple Pay" style={{ height: 20, width: 'auto' }} />
                  </div>
                </div>
                <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif', marginBottom: 6 }}>Гонконг</h4>
                  <p style={{ fontSize: 13, color: '#6B7280', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif' }}>Страна BIN</p>
                </div>
              </div>

<button
  className="w-full transition-transform duration-150 active:scale-95"
  style={{
    padding: '14px',
    backgroundColor: '#DC4D35',
    borderRadius: 12,
    border: 'none',
    fontSize: 16,
    fontWeight: 600,
    color: '#FFFFFF',
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
    cursor: 'pointer',
  }}
>
  Оформить
</button>
            </div>
        </div>
      </div>

      </div>

      <div className="px-4 pt-4">
<div
  className="bg-white w-full"
  style={{
    borderRadius: 20,
    padding: '20px',
    minHeight: 250, // ← добавили минимальную высоту
  }}
>
          <h2
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: '#111827',
              fontFamily:
                '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              marginBottom: 0,
            }}
          >
            История
          </h2>

          <div className="flex flex-col items-center justify-center" style={{ paddingTop: 28, paddingBottom: 28 }}>
            <img src="/images/Union.png" alt="" style={{ width: 34, height: 34, marginBottom: 12, opacity: 0.65 }} />
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: '#6B7280',
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              }}
            >
              Нет операций
            </div>
          </div>

          <button
            type="button"
            style={{ backgroundColor: '#DC4D35' }}
            className="w-full rounded-2xl py-4 text-base font-semibold text-white transition-transform duration-150 active:scale-95"
          >
            + Выпустить карту
          </button>
        </div>
      </div>
    </div>
  )
}

export default HomePage
