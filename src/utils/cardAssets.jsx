// Card artwork per card type. Images live in /public/images/cards.
// Corners are rounded by the container (borderRadius + overflow hidden),
// so the source images can stay square.

export function cardBackgroundByOffer(offerId) {
  const rid = String(offerId || '')
  if (rid.includes('RT-8')) return '/images/cards/PremiumCard.png' // Online+Pay (Premium)
  if (rid.includes('RT-2')) return '/images/cards/PremiumCard.png' // legacy plus
  if (rid.includes('RAVANA:RT')) return '/images/cards/OnlineCard.png'
  return '/images/cards/OnlineCard.png'
}

export function cardBackgroundByTypeName(name) {
  const n = String(name || '').trim()
  if (n === 'Online+Pay' || n === 'Online + Pay') return '/images/cards/PremiumCard.png'
  if (n === 'Pay') return '/images/cards/Pay.png'
  if (n === 'Online') return '/images/cards/OnlineCard.png'
  return '/images/cards/OnlineCard.png'
}

// White rounded Mastercard chip shown in the bottom-right corner of every card
export function McChip({ size = 16, right = 12, bottom = 12 }) {
  return (
    <div
      style={{
        position: 'absolute',
        right,
        bottom,
        background: '#FFFFFF',
        borderRadius: size >= 20 ? 12 : 8,
        padding: size >= 20 ? '6px 12px' : '4px 9px',
        display: 'flex',
        alignItems: 'center',
        boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
      }}
    >
      <img src="/images/Mastercard.png" alt="" style={{ height: size, width: 'auto', display: 'block' }} />
    </div>
  )
}
