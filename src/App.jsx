import { useCardHistory } from './hooks/useCardHistory'
import { lazy, useCallback, useDeferredValue, useEffect, useRef, useState } from 'react'
import api from './api/client'
import Layout from './components/Layout'
import { ToastProvider } from './components/ui/ToastProvider'
import { AuthProvider, useAuth } from './context/AuthContext'
import ScreenLoader from './components/ScreenLoader'
import HomePage from './pages/HomePage'
import BottomBar from './components/BottomBar'
import { appIsVisible, startBalancePolling } from './utils/balancePolling'
import { metrikaHit } from './utils/metrika'

const CardDetailPage = lazy(() => import('./pages/CardDetailPage'))
const FAQPage = lazy(() => import('./pages/FAQPage'))
const HistoryPage = lazy(() => import('./pages/HistoryPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const ChinaPage = lazy(() => import('./pages/ChinaPage'))
const IssueCardPage = lazy(() => import('./pages/IssueCardPage'))

function AppInner() {
  const { user, loading: authLoading, banned, authError, appConfig, commissions, fetchMe } = useAuth()
  const [requestedPage, setCurrentPage] = useState(() => {
    // Deep link t.me/<bot>/<app>?startapp=china opens the China tab directly
    try {
      if (window?.Telegram?.WebApp?.initDataUnsafe?.start_param === 'china') return 'china'
    } catch {}
    return 'home'
  })
  const currentPage = useDeferredValue(requestedPage)
  const [cardTypeToIssue, setCardTypeToIssue] = useState(null)
  const [selectedCard, setSelectedCard] = useState(null)
  // Opens the card's top-up sheet with this payment method preselected
  // ("Перевести на карту" from the internal balance in Profile)
  const [topUpPreset, setTopUpPreset] = useState(null)

  // Virtual pageviews: pages here are React state, not URLs, so Metrika needs
  // an explicit hit on every page switch.
  useEffect(() => {
    metrikaHit(currentPage)
  }, [currentPage])
  const [userCards, setUserCards] = useState([])
  const [offers, setOffers] = useState([])
  const { transactions, status: historyStatus, refresh: refreshTransactions } = useCardHistory(userCards)
  const [historyFixedCardLast4, setHistoryFixedCardLast4] = useState(null)
  const [historyReturnCardId, setHistoryReturnCardId] = useState(null)
  const [cardsStatus, setCardsStatus] = useState('loading')
  const userId = user?.id

  // Maintenance: from the public config, or from any API call answering 503
  const [maintenanceEvent, setMaintenanceEvent] = useState('')
  useEffect(() => {
    const onMaint = (e) => setMaintenanceEvent(e?.detail || 'Ведутся технические работы.')
    window.addEventListener('pp-maintenance', onMaint)
    return () => window.removeEventListener('pp-maintenance', onMaint)
  }, [])
  const maintenanceText = appConfig?.maintenance
    ? (appConfig.maintenance_text || 'Ведутся технические работы.')
    : maintenanceEvent

  // Load cards from API; enrich cards missing last4 from their requisites
  // Silent re-fetch when the provider sync didn't finish within the request
  const refreshCardsRef = useRef(null)
  const syncRetryTimerRef = useRef(null)
  const syncRetriesRef = useRef(0)
  const cardsRequest = useRef(null)
  const loadCards = useCallback(async ({ enrich = true, snapshot = false } = {}) => {
    try {
      const { cards, synced } = await api.cards.listWithSync(snapshot)
      // Provider was slow: the background sync keeps going — ask once more
      // shortly so the fresh balances replace the cached ones by themselves.
      if (synced) {
        syncRetriesRef.current = 0
      } else if ((enrich || snapshot) && !syncRetryTimerRef.current && syncRetriesRef.current < 3) {
        syncRetriesRef.current += 1
        syncRetryTimerRef.current = setTimeout(() => {
          syncRetryTimerRef.current = null
          if (appIsVisible()) refreshCardsRef.current?.()
        }, 3000)
      }
      const mapped = cards.map((c) => ({
        ...c,
        title: 'Виртуальная карта',
      }))
      setUserCards(previous => mapped.map(card => {
        if (card.last4 || !card.aifory_card_id) return card
        const saved = previous.find(c => c.aifory_card_id === card.aifory_card_id)
        return saved?.last4 ? { ...card, last4: saved.last4 } : card
      }))
      setCardsStatus('ready')
      // For any card that has no last4, fetch requisites to get it
      const needEnrich = mapped.filter((c) => !c.last4 && c.aifory_card_id && c.status === 'active')
      if (enrich && needEnrich.length > 0) {
        void Promise.allSettled(
          needEnrich.map(async (c) => {
            try {
              const req = await api.cards.requisites(c.aifory_card_id)
              const num = req?.card_number || req?.cardNumber
              if (num) setUserCards(previous => previous.map(card =>
                card.id === c.id && !card.last4 ? { ...card, last4: String(num).slice(-4) } : card
              ))
            } catch {}
          }),
        )
      }
      return mapped
    } catch (e) {
      console.error('[Cards] failed to load cards:', e.message)
      setCardsStatus('error')
      return null
    }
  }, [])
  const refreshCards = useCallback(options => {
    if (!cardsRequest.current) {
      cardsRequest.current = loadCards(options).finally(() => { cardsRequest.current = null })
    }
    return cardsRequest.current
  }, [loadCards])
  refreshCardsRef.current = refreshCards
  useEffect(() => () => clearTimeout(syncRetryTimerRef.current), [])

  // Load card offers — carries per-user max_issued_count / current_count
  // so issue buttons can be disabled when the O-Plata limit is reached
  const refreshOffers = useCallback(async () => {
    try {
      const data = await api.cards.offers()
      setOffers(Array.isArray(data) ? data : [])
    } catch {
      setOffers([])
    }
  }, [])

  useEffect(() => {
    if (authLoading || userId == null || banned || maintenanceText) return
    refreshCards({ snapshot: true, enrich: false })
    refreshOffers()
  }, [authLoading, userId, banned, maintenanceText, refreshCards, refreshOffers])

  const refreshAll = useCallback(() => Promise.all([
    refreshCards().then(cards => cards && refreshTransactions(cards, true)),
    fetchMe(),
    refreshOffers(),
  ]), [refreshCards, refreshOffers, refreshTransactions, fetchMe])

  const retryHistory = () => cardsStatus === 'ready'
    ? refreshTransactions(userCards, true)
    : refreshCards().then(cards => cards && refreshTransactions(cards, true))
  const visibleHistoryStatus = id => cardsStatus !== 'ready' ? cardsStatus : historyStatus(id)

  // Issuing / funding at the provider finishes a bit later than our request,
  // so a single reload right after a purchase often still shows the old
  // balance — re-check a few times in the background.
  const followUpTimersRef = useRef([])
  const scheduleFollowUpRefresh = useCallback(() => {
    followUpTimersRef.current.forEach(clearTimeout)
    followUpTimersRef.current = [5000, 15000, 40000].map((ms) =>
      setTimeout(() => { if (appIsVisible()) refreshAll().catch(() => {}) }, ms),
    )
  }, [refreshAll])
  useEffect(() => () => followUpTimersRef.current.forEach(clearTimeout), [])

  useEffect(() => {
    if (authLoading || userId == null || banned || maintenanceText) return
    return startBalancePolling(() => Promise.all([refreshCards({ enrich: false }), fetchMe()]))
  }, [authLoading, userId, banned, maintenanceText, refreshCards, fetchMe])

  const refreshAfterPayment = useCallback(async () => {
    await refreshAll()
    scheduleFollowUpRefresh()
  }, [refreshAll, scheduleFollowUpRefresh])

  const handleCardIssued = () => {
    setCardTypeToIssue(null)
    setCurrentPage('home')
    return refreshAfterPayment()
  }

  // Helper to get commission for specific card type
  const getCommissionForCardType = (cardTypeId, operationType) => {
    const isOnlinePlus = String(cardTypeId) === '525847'
    if (operationType === 'issue') {
      // Return fixed fee in USD
      return isOnlinePlus ? commissions?.online_plus_issue_fee || 0 : commissions?.online_issue_fee || 0
    } else {
      // Return percentage for topup
      return isOnlinePlus ? commissions?.online_plus_topup || 0 : commissions?.online_topup || 0
    }
  }


  // All issuable offers at their O-Plata maxIssuedCount → block issuing everywhere
  const issueLimitReached =
    offers.length > 0 &&
    offers.every((o) => Number(o.current_count ?? 0) >= Number(o.max_issued_count ?? 999))

  // Card types can be disabled in the admin panel — hide their promo blocks.
  // While offers haven't loaded yet, show everything (avoid flicker/hard hide on error).
  const offersLoaded = offers.length > 0
  const onlineAvailable = !offersLoaded || offers.some((o) => o.name === 'Online')
  const onlinePlusAvailable = !offersLoaded || offers.some((o) => o.name === 'Online+Pay')
  const payAvailable = !offersLoaded || offers.some((o) => o.name === 'Pay')

  const historyCard = userCards.find(card => card.id === historyReturnCardId)

  // Maintenance: the whole app is closed
  if (maintenanceText) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100dvh', background: '#F3F5F8', padding: 32, textAlign: 'center', boxSizing: 'border-box' }}>
        <div style={{
          width: 72, height: 72, borderRadius: 36, marginBottom: 18,
          background: 'linear-gradient(135deg, #DC4D35 0%, #E8785F 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
          </svg>
        </div>
        <h2 style={{ margin: '0 0 10px', fontSize: 22, fontWeight: 700, color: '#111827' }}>Технические работы</h2>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, color: '#6b7280', maxWidth: 340 }}>{maintenanceText}</p>
        <button
          onClick={() => window.location.reload()}
          style={{ marginTop: 24, border: 'none', background: '#DC4D35', color: '#fff', borderRadius: 12, padding: '14px 28px', fontSize: 15, fontWeight: 600, cursor: 'pointer' }}
        >
          Обновить
        </button>
      </div>
    )
  }

  // Banned screen
  if (banned) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100dvh', background: '#F3F5F8', padding: 32, textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🚫</div>
        <h2 style={{ margin: '0 0 8px', fontSize: 22, fontWeight: 700, color: '#111827' }}>Аккаунт заблокирован</h2>
        <p style={{ margin: 0, fontSize: 15, color: '#6b7280', maxWidth: 300 }}>Ваш аккаунт был заблокирован администратором. Обратитесь в поддержку для получения информации.</p>
      </div>
    )
  }

  if (!authLoading && !user) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100dvh', background: '#F3F5F8', padding: 32, textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
        <h2 style={{ margin: '0 0 8px', fontSize: 22, fontWeight: 700, color: '#111827' }}>Доступ только через Telegram</h2>
        <p style={{ margin: 0, fontSize: 15, color: '#6b7280', maxWidth: 360 }}>
          {authError || 'Откройте приложение из Telegram-бота, чтобы продолжить.'}
        </p>
      </div>
    )
  }

  // Card data and history render independently after authentication.
  if (authLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100dvh', background: '#F3F5F8' }}>
        <svg width="48" height="48" viewBox="0 0 48 48" style={{ animation: 'spin 1s linear infinite' }}>
          <circle cx="24" cy="24" r="20" fill="none" stroke="#DC4D35" strokeWidth="4" strokeLinecap="round" strokeDasharray="94.25 31.42" />
        </svg>
      </div>
    )
  }

  return (
    <Layout background="#F3F5F8">
      <ScreenLoader page={currentPage}>
      {currentPage === 'home' && (
        <HomePage
          userCards={userCards}
          transactions={transactions}
          cardsStatus={cardsStatus}
          historyStatus={visibleHistoryStatus()}
          onRetry={retryHistory}
          commissions={commissions}
          issueLimitReached={issueLimitReached}
          onlineAvailable={onlineAvailable}
          onlinePlusAvailable={onlinePlusAvailable}
          payAvailable={payAvailable}
          onRefresh={refreshAll}
          onNavigateToFAQ={() => setCurrentPage('faq')}
          onNavigateToChina={() => setCurrentPage('china')}
          onNavigateToIssueCard={(cardType = null) => {
            setCardTypeToIssue(cardType)
            setCurrentPage('issue-card')
          }}
          onCardClick={(card) => {
            setSelectedCard(card)
            setCurrentPage('card-detail')
          }}
          onNavigateToHistory={() => {
            setHistoryFixedCardLast4(null)
            setHistoryReturnCardId(null)
            setCurrentPage('history')
          }}
        />
      )}
      {currentPage === 'profile' && (
        <ProfilePage
          userCards={userCards}
          onTransferToCard={(card) => {
            setSelectedCard(card)
            setTopUpPreset('balance')
            setCurrentPage('card-detail')
          }}
        />
      )}
      {currentPage === 'china' && <ChinaPage />}
      {currentPage === 'faq' && <FAQPage onBack={() => setCurrentPage('home')} />}
      {currentPage === 'history' && (
        <HistoryPage
          userCards={userCards}
          transactions={historyReturnCardId == null ? transactions : transactions.filter(tx =>
            tx.cardId === historyCard?.aifory_card_id)}
          historyStatus={visibleHistoryStatus(historyCard?.aifory_card_id)}
          onRetry={retryHistory}
          fixedCardLast4={historyFixedCardLast4}
          onBack={() => {
            if (historyReturnCardId) {
              const c = userCards.find((c) => c.id === historyReturnCardId) || null
              setSelectedCard(c)
              setCurrentPage('card-detail')
              return
            }
            setCurrentPage('home')
          }}
        />
      )}
      {currentPage === 'issue-card' && (
        <IssueCardPage
          onBack={() => setCurrentPage('home')}
          initialCardType={cardTypeToIssue}
          onCardIssued={handleCardIssued}
          getCommissionForCardType={getCommissionForCardType}
        />
      )}
      {currentPage === 'card-detail' && (
        <CardDetailPage
          card={userCards.find(c => c.id === selectedCard?.id) ?? selectedCard}
          historyStatus={visibleHistoryStatus(selectedCard?.aifory_card_id)}
          onRetry={retryHistory}
          transactions={transactions}
          onBack={() => {
            setSelectedCard(null)
            setCurrentPage('home')
          }}
          onTopUp={refreshAfterPayment}
          topUpPreset={topUpPreset}
          onTopUpPresetUsed={() => setTopUpPreset(null)}
          onNavigateToHistory={(cardLast4) => {
            setHistoryFixedCardLast4(cardLast4)
            setHistoryReturnCardId(selectedCard?.id || null)
            setCurrentPage('history')
          }}
          getCommissionForCardType={getCommissionForCardType}
        />
      )}
      </ScreenLoader>
      {(currentPage === 'home' || currentPage === 'profile' || currentPage === 'china') && (
        <BottomBar active={['home', 'profile', 'china'].includes(requestedPage) ? requestedPage : currentPage} onChange={setCurrentPage} />
      )}
    </Layout>
  )
}

function UserApp() {
  const tgInitOnceRef = useRef(false)
  // Telegram WebApp init
  useEffect(() => {
    if (tgInitOnceRef.current) return
    tgInitOnceRef.current = true
    let canceled = false

    // In fullscreen the webview covers the notch/status bar and Telegram's
    // floating close/menu buttons, so the app must pad itself out of their way.
    // Outside fullscreen Telegram already reserves that space — insets go back
    // to 0 and the layout is exactly as before.
    const applySafeAreas = (tg) => {
      const root = document.documentElement
      if (!tg.isFullscreen) {
        root.style.setProperty('--tg-safe-top', '0px')
        root.style.setProperty('--tg-safe-bottom', '0px')
        return
      }
      const device = tg.safeAreaInset || {}
      const content = tg.contentSafeAreaInset || {}
      const top = (Number(device.top) || 0) + (Number(content.top) || 0)
      const bottom = (Number(device.bottom) || 0) + (Number(content.bottom) || 0)
      root.style.setProperty('--tg-safe-top', `${top}px`)
      root.style.setProperty('--tg-safe-bottom', `${bottom}px`)
    }

    const initTg = () => {
      const tg = window?.Telegram?.WebApp
      if (!tg) return false
      try {
        tg.ready()
        tg.expand()
        if (typeof tg.disableVerticalSwipes === 'function') tg.disableVerticalSwipes()

        // requestFullscreen needs Bot API 8.0; older clients keep expand() only
        const canFullscreen =
          typeof tg.requestFullscreen === 'function' &&
          (typeof tg.isVersionAtLeast !== 'function' || tg.isVersionAtLeast('8.0'))
        if (canFullscreen && !tg.isFullscreen) {
          try { tg.requestFullscreen() } catch {}
        }

        applySafeAreas(tg)
        const onChange = () => applySafeAreas(tg)
        ;['fullscreenChanged', 'safeAreaChanged', 'contentSafeAreaChanged', 'viewportChanged'].forEach((ev) => {
          try { tg.onEvent(ev, onChange) } catch {}
        })
        try { tg.onEvent('fullscreenFailed', () => { try { tg.expand() } catch {}; applySafeAreas(tg) }) } catch {}
      } catch {}
      return true
    }

    if (initTg()) return
    let attempts = 0
    const t = setInterval(() => {
      if (canceled) return
      attempts++
      if (initTg() || attempts >= 50) clearInterval(t)
    }, 100)
    return () => { canceled = true; clearInterval(t) }
  }, [])

  const { user } = useAuth()
  return <AppInner key={user?.id ?? 'guest'} />
}

function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <UserApp />
      </AuthProvider>
    </ToastProvider>
  )
}

export default App
