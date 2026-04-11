import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import api, { clearToken, getToken, setToken } from '../api/client'

// Dev fallback local test user (username=string, tgID=string)
const DEV_TG_ID = 'string'
const DEV_USERNAME = 'string'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [banned, setBanned] = useState(false)
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

  const loginDev = useCallback(async () => {
    const res = await api.auth.telegramLogin(DEV_TG_ID, DEV_USERNAME)
    setToken(res.access_token)
    return fetchMe()
  }, [fetchMe])

  useEffect(() => {
    const init = async () => {
      setLoading(true)

      // Load public config (markup percents) first – no auth needed
      await loadConfig()

      // If we already have a token, try to reuse it
      if (getToken()) {
        const me = await fetchMe()
        if (me) {
          setLoading(false)
          return
        }
        clearToken()
      }

      // Try Telegram WebApp initData
      const tg = window?.Telegram?.WebApp
      const initData = tg?.initData
      if (initData) {
        try {
          await loginWithTelegramWebApp(initData)
          setLoading(false)
          return
        } catch (e) {
          console.error('[Auth] Telegram WebApp auth failed:', e.message)
        }
      }

      // Dev fallback: log in as local test user (username=string, tgID=string)
      try {
        await loginDev()
      } catch (e) {
        console.error('[Auth] Dev fallback login failed:', e.message)
      }

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
