export default function TxIcon({ type, size = 44, iconSize = 20, radius = 14 }) {
  const iconMap = {
    topup: {
      iconSrc: '/images/HistoryIcons/arrow-down.png',
    },
    withdrawal: {
      iconSrc: '/images/HistoryIcons/arrow-circle-up.png',
    },
    payment: {
      iconSrc: '/images/HistoryIcons/shop.png',
    },
    declined: {
      iconSrc: '/images/HistoryIcons/red-krest.png',
    },
    fee: {
      iconSrc: '/images/HistoryIcons/arrow-circle-up.png',
    },
  }
  const cfg = iconMap[type] || iconMap.payment
  return (
    <div style={{
      width: size, height: size, borderRadius: radius,
      backgroundColor: '#F3F5F8',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
    }}>
      <img
        src={cfg.iconSrc}
        alt=""
        style={{ width: iconSize, height: iconSize, objectFit: 'contain' }}
      />
    </div>
  )
}
