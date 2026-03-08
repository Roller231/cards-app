import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

const ToastContext = createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const showToast = useCallback(({ title }) => {
    const id = `${Date.now()}-${idRef.current++}`
    const toast = { id, title, leaving: false }
    setToasts((prev) => [...prev, toast])

    window.setTimeout(() => {
      setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)))

      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 220)
    }, 2200)
  }, [])

  const value = useMemo(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        style={{
          position: 'fixed',
          top: 14,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          pointerEvents: 'none',
          width: 'calc(100% - 32px)',
          maxWidth: 430,
        }}
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={t.leaving ? 'toast-leave' : 'toast-enter'}
            style={{
              backgroundColor: '#111827',
              color: '#FFFFFF',
              borderRadius: 14,
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 14,
              fontWeight: 600,
              textAlign: 'center',
              fontFamily:
                '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
              boxShadow: '0 10px 25px rgba(17, 24, 39, 0.25)',
              pointerEvents: 'none',
            }}
          >
            {t.title}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return ctx
}
