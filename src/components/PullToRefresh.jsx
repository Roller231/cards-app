import { useState, useRef, useCallback } from 'react'
import { BOTTOM_BAR_SPACE } from './BottomBar'

const PULL_THRESHOLD = 120
const PULL_MAX = 180
const PULL_DEAD_ZONE = 30

export default function PullToRefresh({ children, onRefresh }) {
  // Pull-to-refresh state
  const [pull, setPull] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const touchStartY = useRef(null)
  const distance = useRef(0)

  const handleTouchStart = useCallback((e) => {
    if (refreshing) return
    distance.current = 0
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
      distance.current = 0
      setPull(0)
      return
    }
    // Add some resistance after the dead zone.
    const effective = dy - PULL_DEAD_ZONE
    const resisted = Math.min(PULL_MAX, effective * 0.45)
    distance.current = resisted
    setPull(resisted)
  }, [refreshing])

  const handleTouchEnd = useCallback(async () => {
    if (refreshing || touchStartY.current == null) return
    const dist = distance.current
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
  }, [refreshing, onRefresh])

  const indicatorOffset = refreshing ? PULL_THRESHOLD : pull
  const indicatorOpacity = Math.min(1, pull / PULL_THRESHOLD)
  const indicatorRotation = Math.min(360, (pull / PULL_THRESHOLD) * 360)

  return (
    <div
      className="flex-1 flex flex-col"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={() => { touchStartY.current = null; if (!refreshing) setPull(0) }}
      style={{ touchAction: 'pan-y', paddingBottom: BOTTOM_BAR_SPACE }}
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
        transform: indicatorOffset ? `translateY(${indicatorOffset}px)` : 'none',
        transition: (pull === 0 && !refreshing) ? 'transform 200ms ease' : 'none',
      }}>
        {children}
      </div>
    </div>
  )
}
