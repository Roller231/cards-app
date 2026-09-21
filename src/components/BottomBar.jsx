import { useEffect, useRef, useState } from 'react'
import Portal from './ui/Portal'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

// Space pages must reserve at the bottom so the last content isn't hidden
// under the floating bar (bar height + its bottom gap + breathing room).
// The Telegram fullscreen safe inset is already padded on #root.
export const BOTTOM_BAR_SPACE = 104

function HomeIcon({ active }) {
  const c = active ? '#FFFFFF' : '#6B7280'
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path
        d="M3.5 10.2 12 3.5l8.5 6.7V19a1.5 1.5 0 0 1-1.5 1.5h-4.2v-6.1H9.2v6.1H5A1.5 1.5 0 0 1 3.5 19v-8.8Z"
        stroke={c} strokeWidth="1.9" strokeLinejoin="round"
        fill={active ? 'rgba(255,255,255,0.22)' : 'none'}
      />
    </svg>
  )
}

function UserIcon({ active }) {
  const c = active ? '#FFFFFF' : '#6B7280'
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="8" r="4" stroke={c} strokeWidth="1.9" fill={active ? 'rgba(255,255,255,0.22)' : 'none'} />
      <path d="M4.5 20.2c.9-3.6 3.9-5.7 7.5-5.7s6.6 2.1 7.5 5.7" stroke={c} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  )
}

const TABS = [
  { id: 'home', label: 'Главная', Icon: HomeIcon },
  { id: 'profile', label: 'Профиль', Icon: UserIcon },
]

/**
 * Floating glass tab bar (Telegram / iOS style) in the app's palette.
 *
 * Rendered through a Portal straight into <body>: the Layout column carries a
 * CSS transform, and `position: fixed` inside a transformed ancestor is
 * positioned relative to that ancestor — the bar would scroll with the page
 * and "hang" at the bottom of the content instead of staying on screen.
 * Being outside #root it adds the Telegram safe inset to its own offset.
 */
export default function BottomBar({ active, onChange }) {
  const activeIndex = Math.max(0, TABS.findIndex((t) => t.id === active))
  const [pressed, setPressed] = useState(null)
  const [bounce, setBounce] = useState(null)
  const bounceTimer = useRef(null)

  useEffect(() => () => clearTimeout(bounceTimer.current), [])

  const select = (id) => {
    if (id === active) return
    try { window?.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.() } catch {}
    setBounce(id)
    clearTimeout(bounceTimer.current)
    bounceTimer.current = setTimeout(() => setBounce(null), 360)
    onChange && onChange(id)
  }

  return (
    <Portal>
      <nav
        style={{
          position: 'fixed',
          left: '50%',
          bottom: 'calc(var(--tg-safe-bottom) + 12px)',
          transform: 'translateX(-50%)',
          width: 'calc(100% - 32px)',
          maxWidth: 398,
          height: 66,
          boxSizing: 'border-box',
          padding: 6,
          borderRadius: 33,
          zIndex: 40,
          background: 'rgba(255,255,255,0.72)',
          backdropFilter: 'blur(26px) saturate(180%)',
          WebkitBackdropFilter: 'blur(26px) saturate(180%)',
          border: '1px solid rgba(255,255,255,0.85)',
          boxShadow: '0 12px 32px rgba(17,24,39,0.16), 0 1px 2px rgba(17,24,39,0.06), inset 0 1px 0 rgba(255,255,255,0.9)',
          fontFamily: font,
        }}
      >
        <div style={{ position: 'relative', display: 'flex', height: '100%' }}>
          {/* Sliding active capsule */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: 0,
              width: `${100 / TABS.length}%`,
              transform: `translateX(${activeIndex * 100}%)`,
              transition: 'transform 380ms cubic-bezier(0.32, 0.72, 0, 1)',
              borderRadius: 27,
              background: 'linear-gradient(180deg, #E25A42 0%, #DC4D35 100%)',
              boxShadow: '0 6px 16px rgba(220,77,53,0.38), inset 0 1px 0 rgba(255,255,255,0.28)',
            }}
          />
          {TABS.map(({ id, label, Icon }) => {
            const isActive = active === id
            const isBouncing = bounce === id
            return (
              <button
                key={id}
                onClick={() => select(id)}
                onPointerDown={() => setPressed(id)}
                onPointerUp={() => setPressed(null)}
                onPointerLeave={() => setPressed(null)}
                onPointerCancel={() => setPressed(null)}
                aria-current={isActive ? 'page' : undefined}
                style={{
                  position: 'relative',
                  zIndex: 1,
                  flex: 1,
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 2,
                  padding: 0,
                  borderRadius: 27,
                  WebkitTapHighlightColor: 'transparent',
                  transform: pressed === id && !isActive ? 'scale(0.94)' : 'scale(1)',
                  transition: 'transform 160ms ease',
                }}
              >
                <span
                  style={{
                    display: 'flex',
                    transform: isBouncing ? 'translateY(-2px) scale(1.12)' : 'translateY(0) scale(1)',
                    transition: 'transform 360ms cubic-bezier(0.34, 1.56, 0.64, 1)',
                  }}
                >
                  <Icon active={isActive} />
                </span>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: 0.1,
                    color: isActive ? '#FFFFFF' : '#6B7280',
                    transition: 'color 240ms ease',
                  }}
                >
                  {label}
                </span>
              </button>
            )
          })}
        </div>
      </nav>
    </Portal>
  )
}
