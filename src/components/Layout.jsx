import { useEffect, useState } from 'react'

function Layout({ children, background = 'white' }) {
  const [entered, setEntered] = useState(false)

  useEffect(() => {
    const reduceMotion = window?.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    if (reduceMotion) {
      setEntered(true)
      return
    }

    const id = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <div className="min-h-screen flex justify-center" style={{ background }}>
      <div
        className="w-full max-w-[430px] min-h-screen flex flex-col"
        style={{
          background,
          transform: entered ? 'translateY(0px)' : 'translateY(14px)',
          opacity: entered ? 1 : 0,
          transition: 'transform 260ms ease, opacity 200ms ease',
          willChange: 'transform, opacity',
        }}
      >
        {children}
      </div>
    </div>
  )
}

export default Layout
