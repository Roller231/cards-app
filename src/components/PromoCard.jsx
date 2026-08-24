import { useEffect, useState } from 'react'
import Card from './ui/Card'
import Button from './ui/Button'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

// Maps the offer's internal type code (backend `name`) to the promo config key
export const PROMO_KEY_BY_TYPE = {
  'Online': 'online',
  'Online+Pay': 'online-plus',
  'Pay': 'pay',
}

// Builds the promo card descriptors from admin-editable config.
// Respect explicitly-set values: 0 for numbers and '' for texts are valid.
const pick = (cfg, key, fallback) => (cfg && cfg[key] !== undefined && cfg[key] !== null ? cfg[key] : fallback)
const numOr = (v, d) => (v === null || v === undefined || v === '' ? d : Number(v))

export function usePromoCards({ onlineAvailable = true, onlinePlusAvailable = true, payAvailable = true } = {}) {
  const { appConfig, commissions } = useAuth()
  const promo = appConfig?.cards_promo || {}
  // Live SBP exchange rate (RUB per 1 USD), computed by the backend
  // (Bitbanker index × fee multipliers). One fetch shared by all promo cards.
  const [sbpRate, setSbpRate] = useState(null)
  useEffect(() => {
    let cancelled = false
    api.sbp.rate()
      .then((r) => { if (!cancelled && r && r.rate) setSbpRate(Number(r.rate)) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  return [
    {
      key: 'online', available: onlineAvailable, payIcons: false,
      title: pick(promo.online, 'title', 'Online'),
      desc: pick(promo.online, 'desc', 'Для оплаты покупок и сервисов в интернете'),
      badge: pick(promo.online, 'badge', 'Бесплатное обслуживание'),
      pays: pick(promo.online, 'pays', 'Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр.'),
      bin: pick(promo.online, 'bin', 'Гонконг'),
      validity: commissions.online_validity_text || '1 год',
      operationFee: numOr(commissions.online_operation_fee, 0.4),
      priceRub: numOr(commissions.online_issue_price_rub, 999),
      topup: numOr(commissions.online_topup, 3.8),
      sbpRate,
    },
    {
      key: 'online-plus', available: onlinePlusAvailable, payIcons: true,
      title: pick(promo.online_plus, 'title', 'Online + Pay'),
      desc: pick(promo.online_plus, 'desc', 'Оплата в магазинах через Apple Pay, Google Pay и онлайн-сервисов на сайтах'),
      badge: pick(promo.online_plus, 'badge', 'Бесплатное обслуживание'),
      pays: pick(promo.online_plus, 'pays', 'Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр.'),
      bin: pick(promo.online_plus, 'bin', 'США'),
      validity: commissions.online_plus_validity_text || '1 год',
      operationFee: numOr(commissions.online_plus_operation_fee, 0.4),
      priceRub: numOr(commissions.online_plus_issue_price_rub, 1999),
      topup: numOr(commissions.online_plus_topup, 4),
      sbpRate,
    },
    {
      key: 'pay', available: payAvailable, payIcons: true,
      title: pick(promo.pay, 'title', 'Pay'),
      desc: pick(promo.pay, 'desc', 'Универсальная карта для международных оплат и подписок'),
      badge: pick(promo.pay, 'badge', 'Бесплатное обслуживание'),
      pays: pick(promo.pay, 'pays', 'Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр.'),
      bin: pick(promo.pay, 'bin', 'США'),
      validity: commissions.univ_validity_text || '1 год',
      operationFee: numOr(commissions.univ_operation_fee, 0.4),
      priceRub: numOr(commissions.univ_issue_price_rub, 1999),
      topup: numOr(commissions.univ_topup, 4),
      sbpRate,
    },
  ]
}

// The promo card itself — identical on the home screen and the issue screen.
export default function PromoCard({ pc, expanded, onToggle, issueLimitReached = false, onIssue, showIssueButton = true }) {
  return (
    <Card padding={expanded ? '20px 20px 16px 20px' : '20px'}>
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-2 flex-1">
          <div
            className="flex items-center"
            onClick={onToggle}
            style={{ height: 24, backgroundColor: '#1A1F36', borderRadius: 8, paddingLeft: 8, paddingRight: pc.payIcons ? 5 : 8, width: 'fit-content', cursor: 'pointer' }}
          >
            <img src="/images/Mastercard.png" alt="Mastercard" style={{ height: 14, width: 'auto' }} />
            {pc.payIcons ? (
              <>
                <img src="/images/GooglePay.png" alt="Google Pay" style={{ height: 16, width: 'auto', paddingLeft: 4 }} />
                <img src="/images/Apple.png" alt="Apple Pay" style={{ height: 16, width: 'auto', paddingLeft: 4 }} />
              </>
            ) : (
              <span style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, paddingLeft: 4 }}>virtual</span>
            )}
          </div>

          <div className="flex-1">
            <h3 style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{pc.title}</h3>
            <p style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, lineHeight: '16px' }}>{pc.desc}</p>
          </div>
        </div>

        <button
          onClick={onToggle}
          className="flex items-center justify-center transition-transform duration-150 active:scale-95"
          style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: '#F3F5F8', border: 'none', cursor: 'pointer', flexShrink: 0 }}
        >
          <svg width="16" height="16" viewBox="0 0 14 14" fill="none" style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
            <path d="M3 5L7 9L11 5" stroke="#111827" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <div style={{ marginTop: 16, overflow: 'hidden', maxHeight: expanded ? 1200 : 0, opacity: expanded ? 1 : 0, transition: 'max-height 300ms ease, opacity 200ms ease' }}>
        <div style={{ paddingBottom: 0 }}>
          {pc.badge && (
            <div className="flex gap-2" style={{ marginBottom: 16 }}>
              <div style={{ padding: '6px 12px', backgroundColor: '#10B981', borderRadius: 8, fontSize: 12, fontWeight: 400, color: '#FFFFFF', fontFamily: font }}>
                {pc.badge}
              </div>
            </div>
          )}

          {/* Tile order is fixed by product: SBP rate, top-up fee, issue price,
              operation fee, validity, BIN country — then the "pay for" block. */}
          <div className="grid grid-cols-2 gap-3" style={{ marginBottom: 16 }}>
            <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>
                {pc.sbpRate ? `${Number(pc.sbpRate).toFixed(2)} ₽` : '—'}
              </div>
              <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Курс СБП за 1 $</div>
            </div>
            <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{pc.topup} %</div>
              <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за пополнение</div>
            </div>
            <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{Number(pc.priceRub).toLocaleString('ru-RU')} ₽</div>
              <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Плата за выпуск</div>
            </div>
            <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{pc.operationFee} $</div>
              <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Комиссия за операцию</div>
            </div>
            <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2 }}>{pc.validity}</div>
              <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Срок действия</div>
            </div>
            <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font, marginBottom: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
                {pc.bin}
                {pc.bin === 'Гонконг' && (
                  <img src="/images/HongKong.svg" alt="" style={{ width: 18, height: 18 }} />
                )}
              </div>
              <div style={{ fontSize: 12, fontWeight: 400, color: '#6B7280', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Страна BIN</div>
            </div>
            {pc.payIcons && (
              <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px' }}>
                <h4 style={{ fontSize: 15, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 6 }}>Подключение</h4>
                <div className="flex gap-2">
                  <img src="/images/GooglePay.png" alt="Google Pay" style={{ height: 20, width: 'auto' }} />
                  <img src="/images/Apple.png" alt="Apple Pay" style={{ height: 20, width: 'auto' }} />
                </div>
              </div>
            )}
          </div>

          {pc.pays && (
            <div style={{ backgroundColor: '#F3F5F8', borderRadius: 12, padding: '12px 16px', marginBottom: 16 }}>
              <h4 style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 8 }}>Оплачивайте</h4>
              <p style={{ fontSize: 13, color: '#6B7280', fontFamily: font, lineHeight: '20px' }}>{pc.pays}</p>
            </div>
          )}

          {showIssueButton && (
            <Button
              onClick={() => {
                if (issueLimitReached) return
                if (typeof onIssue === 'function') onIssue(pc.key)
              }}
              variant="secondary"
              disabled={issueLimitReached}
              fullWidth
              style={issueLimitReached ? { backgroundColor: '#D1D5DB', cursor: 'not-allowed' } : undefined}
            >
              {issueLimitReached ? 'Достигнут лимит карт' : 'Оформить'}
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}
