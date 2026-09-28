import { metrikaGoal } from '../utils/metrika'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'
const VPN_BOT_URL = 'https://t.me/exprontovpn_bot'

function openVpnBot() {
  metrikaGoal('vpn_banner_click')
  const tg = window?.Telegram?.WebApp
  if (tg?.openTelegramLink) tg.openTelegramLink(VPN_BOT_URL)
  else window.open(VPN_BOT_URL, '_blank', 'noopener')
}

/** Partner VPN banner at the bottom of the home screen (compact row). */
export default function VpnBanner() {
  return (
    <div
      onClick={openVpnBot}
      className="transition-transform duration-150 active:scale-[0.99]"
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        borderRadius: 16, padding: '12px 14px', cursor: 'pointer',
        background: 'linear-gradient(135deg, #1A1F36 0%, #2B3263 100%)',
        color: '#FFFFFF', fontFamily: font,
      }}
    >
      <div style={{
        width: 36, height: 36, borderRadius: 11, flexShrink: 0,
        background: 'rgba(255,255,255,0.12)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none">
          <path d="M12 3 4.5 6v5.6c0 4.4 3.1 8.3 7.5 9.4 4.4-1.1 7.5-5 7.5-9.4V6L12 3Z" stroke="#FFFFFF" strokeWidth="1.9" strokeLinejoin="round" />
          <path d="m8.8 12.2 2.2 2.2 4.3-4.4" stroke="#FFFFFF" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>VPN с сервером в Сингапуре</div>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)', marginTop: 1 }}>Подключение за минуту в Telegram-боте</div>
      </div>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ flexShrink: 0 }}>
        <path d="M5 2l5 5-5 5" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}
