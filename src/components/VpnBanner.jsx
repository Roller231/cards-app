import { metrikaGoal } from '../utils/metrika'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'
const VPN_BOT_URL = 'https://t.me/exprontovpn_bot'

function openVpnBot() {
  metrikaGoal('vpn_banner_click')
  const tg = window?.Telegram?.WebApp
  if (tg?.openTelegramLink) tg.openTelegramLink(VPN_BOT_URL)
  else window.open(VPN_BOT_URL, '_blank', 'noopener')
}

/** Partner VPN banner on the home screen (worded as a partner service). */
export default function VpnBanner() {
  return (
    <div
      onClick={openVpnBot}
      className="transition-transform duration-150 active:scale-[0.99]"
      style={{
        position: 'relative',
        overflow: 'hidden',
        borderRadius: 20,
        padding: '20px',
        cursor: 'pointer',
        background: 'linear-gradient(135deg, #1A1F36 0%, #2B3263 60%, #3B4371 100%)',
        color: '#FFFFFF',
        fontFamily: font,
      }}
    >
      {/* soft glow */}
      <div style={{
        position: 'absolute', right: -40, top: -40, width: 170, height: 170, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(220,77,53,0.55) 0%, rgba(220,77,53,0) 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        <div style={{
          width: 46, height: 46, borderRadius: 14, flexShrink: 0,
          background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.18)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M12 3 4.5 6v5.6c0 4.4 3.1 8.3 7.5 9.4 4.4-1.1 7.5-5 7.5-9.4V6L12 3Z" stroke="#FFFFFF" strokeWidth="1.8" strokeLinejoin="round" />
            <path d="m8.8 12.2 2.2 2.2 4.3-4.4" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 17, fontWeight: 700 }}>Быстрый VPN в Telegram</span>
            <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 8px', borderRadius: 8, background: '#DC4D35' }}>
              🇸🇬 Сингапур
            </span>
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.45, color: 'rgba(255,255,255,0.78)', marginTop: 6 }}>
            Стабильные серверы в разных странах, в том числе в Сингапуре. Подключение за минуту прямо в боте.
          </div>
        </div>
      </div>

      <div style={{
        position: 'relative', marginTop: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: 8, background: '#FFFFFF', color: '#111827', borderRadius: 12, padding: '12px 0',
        fontSize: 15, fontWeight: 600,
      }}>
        Подключить VPN
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M5 2l5 5-5 5" stroke="#111827" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  )
}
