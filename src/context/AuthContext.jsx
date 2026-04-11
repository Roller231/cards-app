import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import api, { clearToken, getToken, setToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [banned, setBanned] = useState(false)
  const [authError, setAuthError] = useState('')
  const [appConfig, setAppConfig] = useState({
    card_issue_markup_percent: 0,
    card_topup_markup_percent: 0,
  })

  const loadConfig = useCallback(async () => {
    try {
      const cfg = await api.auth.config()
      setAppConfig(cfg)
    } catch {}
  }, [])

  const fetchMe = useCallback(async () => {
    try {
      const me = await api.auth.me()
      setBanned(false)
      setUser(me)
      return me
    } catch (err) {
      if (err.status === 403 && err.message === 'ACCOUNT_BANNED') {
        setBanned(true)
      }
      return null
    }
  }, [])

  const loginWithTelegramWebApp = useCallback(
    async (initData) => {
      const res = await api.auth.telegramWebApp(initData)
      setToken(res.access_token)
      return fetchMe()
    },
    [fetchMe],
  )

  useEffect(() => {
    const init = async () => {
      setLoading(true)

      // Load public config first – no auth needed
      await loadConfig()

      const tg = window?.Telegram?.WebApp
      // Signal Telegram the app is ready (required for some clients to expose initData)
      try { tg?.ready?.() } catch {}
      const initData = tg?.initData

      // Case 1: initData present → always do a fresh TG auth (ignores any cached token)
      if (initData) {
        clearToken()
        try {
          setAuthError('')
          await loginWithTelegramWebApp(initData)
          setLoading(false)
          return
        } catch (e) {
          console.error('[Auth] Telegram WebApp auth failed:', e.message)
          clearToken()
          setUser(null)
          setAuthError(`Ошибка авторизации Telegram: ${e.message}. Попробуйте переоткрыть из бота.`)
          setLoading(false)
          return
        }
      }

      // Case 2: no initData (Desktop Telegram, direct URL open, etc.)
      // Allow reuse of an existing token ONLY if user was previously TG-authenticated
      if (getToken()) {
        const me = await fetchMe()
        if (me?.telegram_user_id) {
          // Legitimate returning TG user with cached session
          setLoading(false)
          return
        }
        // No TG ID → stale dev/default session, reject it
        clearToken()
        setUser(null)
      }

      // Case 3: no initData, no valid TG token → block
      setAuthError('Доступ только через Telegram WebApp. Откройте приложение из Telegram-бота.')
      setLoading(false)
    }

    init()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const {
    online_issue_fee_usd = 0,
    online_topup_markup_percent = 0,
    online_plus_issue_fee_usd = 0,
    online_plus_topup_markup_percent = 0,
  } = appConfig || {}

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      banned,
      authError,
      appConfig,
      commissions: {
        online_issue_fee: online_issue_fee_usd,
        online_topup: online_topup_markup_percent,
        online_plus_issue_fee: online_plus_issue_fee_usd,
        online_plus_topup: online_plus_topup_markup_percent,
      },
      fetchMe,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
