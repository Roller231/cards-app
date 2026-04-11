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

      // Load public config (markup percents) first – no auth needed
      await loadConfig()

      // Strict mode: always authenticate via Telegram WebApp initData when available
      const tg = window?.Telegram?.WebApp
      const initData = tg?.initData
      if (initData) {
        try {
          setAuthError('')
          await loginWithTelegramWebApp(initData)
          setLoading(false)
          return
        } catch (e) {
          console.error('[Auth] Telegram WebApp auth failed:', e.message)
          clearToken()
          setUser(null)
          setAuthError('Не удалось авторизоваться через Telegram. Откройте приложение заново из Telegram.')
          setLoading(false)
          return
        }
      }

      clearToken()
      setUser(null)

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
