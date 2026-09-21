const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

function HomeIcon({ active }) {
  const c = active ? '#DC4D35' : '#9CA3AF'
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path
        d="M3.5 10.2 12 3.5l8.5 6.7V19a1.5 1.5 0 0 1-1.5 1.5h-4.2v-6.1H9.2v6.1H5A1.5 1.5 0 0 1 3.5 19v-8.8Z"
        stroke={c} strokeWidth="1.9" strokeLinejoin="round"
        fill={active ? 'rgba(220,77,53,0.12)' : 'none'}
      />
    </svg>
  )
}

function UserIcon({ active }) {
  const c = active ? '#DC4D35' : '#9CA3AF'
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8" r="4" stroke={c} strokeWidth="1.9" fill={active ? 'rgba(220,77,53,0.12)' : 'none'} />
      <path d="M4.5 20.2c.9-3.6 3.9-5.7 7.5-5.7s6.6 2.1 7.5 5.7" stroke={c} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  )
}

const TABS = [
  { id: 'home', label: 'Главная', Icon: HomeIcon },
  { id: 'profile', label: 'Профиль', Icon: UserIcon },
]

/**
 * App-style bottom navigation. Fixed to the bottom of the viewport and
 * centered in the 430px column; adds the Telegram fullscreen safe inset to
 * its own padding (fixed elements ignore #root's padding).
 */
export default function BottomBar({ active, onChange }) {
  return (
    <nav
      style={{
        position: 'fixed',
        bottom: 0,
        left: '50%',
        transform: 'translateX(-50%)',
        width: '100%',
        maxWidth: 430,
        zIndex: 40,
        background: 'rgba(255,255,255,0.94)',
        backdropFilter: 'blur(14px)',
        WebkitBackdropFilter: 'blur(14px)',
        borderTop: '1px solid #E5E7EB',
        paddingTop: 6,
        paddingBottom: 'calc(var(--tg-safe-bottom) + 8px)',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ display: 'flex' }}>
        {TABS.map(({ id, label, Icon }) => {
          const isActive = active === id
          return (
            <button
              key={id}
              onClick={() => onChange && onChange(id)}
              className="transition-transform duration-150 active:scale-95"
              style={{
                flex: 1,
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 3,
                padding: '6px 0 2px',
                fontFamily: font,
              }}
            >
              <Icon active={isActive} />
              <span style={{ fontSize: 11, fontWeight: 600, color: isActive ? '#DC4D35' : '#9CA3AF' }}>
                {label}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
