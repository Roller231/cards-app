import { useCallback, useEffect, useRef, useState } from 'react'
import api from './api/client'
import Layout from './components/Layout'
import { ToastProvider, useToast } from './components/ui/ToastProvider'
import { AuthProvider, useAuth } from './context/AuthContext'
import CardDetailPage from './pages/CardDetailPage'
import FAQPage from './pages/FAQPage'
import HistoryPage from './pages/HistoryPage'
import HomePage from './pages/HomePage'
import IssueCardPage from './pages/IssueCardPage'
import WelcomePage from './pages/WelcomePage'
import CryptoPaymentPage from './pages/CryptoPaymentPage'

// Map raw Aifory transaction to frontend shape
function mapAiforyTx(tx, card) {
  const rawAmount = parseFloat(tx.amount ?? tx.Amount ?? 0)
  const typeId = tx.type ?? tx.transactionType ?? tx.typeID ?? 0
  const statusId = tx.statusID ?? tx.status_id ?? tx.statusId ?? 0

  let txType
  if (statusId === 3 || String(tx.status).toLowerCase().includes('declin')) {
    txType = 'declined'
  } else if (rawAmount > 0 || typeId === 2) {
    txType = 'topup'
  } else {
    txType = 'payment'
  }

  const merchant =
    tx.merchant || tx.merchantName || tx.description || tx.comment || ''

  return {
    id: String(tx.id ?? tx.transactionID ?? tx.transactionId ?? Math.random()),
    type: txType,
    title:
      txType === 'topup'
        ? `*** ${card.last4 || ''}`
        : merchant || 'Покупка',
    subtitle:
      txType === 'topup'
        ? 'Пополнение'
        : txType === 'declined'
          ? 'Операция отклонена'
          : 'Оплата',
    cardTitle: card.title || 'Виртуальная карта',
    cardLast4: card.last4 || '',
    amount: txType === 'topup' ? Math.abs(rawAmount) : -Math.abs(rawAmount),
    date: tx.date
      ? new Date(tx.date)
      : tx.createdAt
        ? new Date(typeof tx.createdAt === 'number' ? tx.createdAt * 1000 : tx.createdAt)
        : new Date(),
  }
}

function AppInner() {
  const { user, loading: authLoading, appConfig, commissions } = useAuth()
  const [currentPage, setCurrentPage] = useState(() => {
    try {
      return localStorage.getItem('pp_seen_welcome') ? 'home' : 'welcome'
    } catch {
      return 'welcome'
    }
  })
  const [cardTypeToIssue, setCardTypeToIssue] = useState(null)
  const [selectedCard, setSelectedCard] = useState(null)
  const [userCards, setUserCards] = useState([])
  const [transactions, setTransactions] = useState([])
  const [cardsLoading, setCardsLoading] = useState(false)
  const [transactionsLoading, setTransactionsLoading] = useState(false)
  const [historyFixedCardLast4, setHistoryFixedCardLast4] = useState(null)
  const [historyReturnCardId, setHistoryReturnCardId] = useState(null)
  const [cryptoPaymentData, setCryptoPaymentData] = useState(null)
  const [dataReady, setDataReady] = useState(false)
  const [pendingPaymentId, setPendingPaymentId] = useState(() => {
    try { return localStorage.getItem('pp_pending_payment_id') || null } catch { return null }
  })
  const { showToast } = useToast()
  const tgInitOnceRef = useRef(false)

  // Load cards from API; enrich cards missing last4 from their requisites
  const refreshCards = useCallback(async () => {
    setCardsLoading(true)
    try {
      const cards = await api.cards.list()
      const mapped = cards.map((c) => ({
        ...c,
        title: 'Виртуальная карта',
      }))
      // For any card that has no last4, fetch requisites to get it
      const needEnrich = mapped.filter((c) => !c.last4 && c.aifory_card_id)
      if (needEnrich.length > 0) {
        await Promise.allSettled(
          needEnrich.map(async (c) => {
            try {
              const req = await api.cards.requisites(c.aifory_card_id)
              const num = req?.card_number || req?.cardNumber
              if (num) c.last4 = String(num).slice(-4)
            } catch {}
          }),
        )
      }
      setUserCards(mapped)
      return mapped
    } catch (e) {
      console.error('[Cards] failed to load cards:', e.message)
      return []
    } finally {
      setCardsLoading(false)
    }
  }, [])

  // Load transactions for all cards (first 10 each) for history page
  const refreshTransactions = useCallback(
    async (cards) => {
      setTransactionsLoading(true)
      const allTx = []
      await Promise.allSettled(
        cards.map(async (card) => {
          if (!card.aifory_card_id) return
          try {
            const txList = await api.cards.transactions(card.aifory_card_id, 10, 0)
            const arr = Array.isArray(txList)
              ? txList
              : txList?.transactions ?? txList?.data ?? []
            arr.forEach((tx) => allTx.push(mapAiforyTx(tx, card)))
          } catch {}
        }),
      )
      allTx.sort((a, b) => b.date - a.date)
      setTransactions(allTx)
      setTransactionsLoading(false)
    },
    [],
  )

  // When user is authenticated, immediately fetch orders and cards.
  // If user already has orders or cards, skip Welcome and go Home.
  useEffect(() => {
    if (!user) return
    let canceled = false
    ;(async () => {
      try {
        const [ordersRes, cards] = await Promise.all([
          api.orders.list().catch(() => []),
          refreshCards(),
        ])
        if (canceled) return
        const orders = Array.isArray(ordersRes) ? ordersRes : []
        if (cards.length > 0) {
          refreshTransactions(cards)
        }
        const seen = (() => { try { return localStorage.getItem('pp_seen_welcome') } catch { return null } })()
        const shouldSkipWelcome = orders.length > 0 || cards.length > 0
        if (!seen && shouldSkipWelcome) {
          try { localStorage.setItem('pp_seen_welcome', '1') } catch {}
          if (currentPage === 'welcome') setCurrentPage('home')
        }
      } catch {}
      setDataReady(true)
    })()
    return () => { canceled = true }
  }, [user, refreshCards, refreshTransactions, currentPage])

  // After card issued: reload cards list
  const handleCardIssued = useCallback(async () => {
    const cards = await refreshCards()
    if (cards.length > 0) refreshTransactions(cards)
    setCardTypeToIssue(null)
    setCurrentPage('home')
  }, [refreshCards, refreshTransactions])

  // After deposit: reload cards to update balance
  const handleDeposited = useCallback(async () => {
    const cards = await refreshCards()
    if (selectedCard) {
      const updated = cards.find((c) => c.id === selectedCard.id)
      if (updated) setSelectedCard({ ...updated, title: 'Виртуальная карта' })
    }
  }, [refreshCards, selectedCard])

  // Telegram WebApp init
  useEffect(() => {
    if (tgInitOnceRef.current) return
    tgInitOnceRef.current = true
    let canceled = false

    const initTg = () => {
      const tg = window?.Telegram?.WebApp
      if (!tg) return false
      try {
        tg.ready()
        const platform = String(tg.platform || '').toLowerCase()
        const ua = String(navigator?.userAgent || '').toLowerCase()
        const isDesktop =
          platform === 'tdesktop' ||
          (!platform &&
            (ua.includes('windows') || ua.includes('mac os') || ua.includes('linux')) &&
            !ua.includes('android'))
        if (isDesktop && typeof tg.requestFullscreen === 'function' && !tg.isFullscreen) {
          try { tg.requestFullscreen() } catch {}
        }
        tg.expand()
        if (typeof tg.disableVerticalSwipes === 'function') tg.disableVerticalSwipes()
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

  // Background polling for pending crypto payment (runs from any page, not just CryptoPaymentPage)
  useEffect(() => {
    if (!user || !pendingPaymentId || currentPage === 'crypto-payment') return

    const _clearPending = () => {
      setPendingPaymentId(null)
      try { localStorage.removeItem('pp_pending_payment_id'); localStorage.removeItem('pp_pending_check_count') } catch {}
    }

    const check = async () => {
      try {
        const data = await api.cryptoPayments.status(pendingPaymentId)
        if (data.status === 'completed') {
          _clearPending()
          const isTopup = data.type === 'topup'
          showToast({ title: isTopup ? '✅ Пополнение карты выполнено!' : '✅ Карта успешно выпущена!' })
          const cards = await refreshCards()
          if (cards.length > 0) refreshTransactions(cards)
        } else if (data.status === 'failed') {
          _clearPending()
        } else {
          try {
            const count = parseInt(localStorage.getItem('pp_pending_check_count') || '0', 10) + 1
            if (count >= 500) {
              _clearPending()
            } else {
              localStorage.setItem('pp_pending_check_count', String(count))
            }
          } catch {}
        }
      } catch {}
    }

    check()
    const interval = setInterval(check, 20000)
    return () => clearInterval(interval)
  }, [user, pendingPaymentId, currentPage, showToast, refreshCards, refreshTransactions])

  // Show spinner while auth is loading OR while initial data fetch is in progress
  if (authLoading || (user && !dataReady)) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100dvh', background: '#F3F5F8' }}>
        <svg width="48" height="48" viewBox="0 0 48 48" style={{ animation: 'spin 1s linear infinite' }}>
          <circle cx="24" cy="24" r="20" fill="none" stroke="#DC4D35" strokeWidth="4" strokeLinecap="round" strokeDasharray="94.25 31.42" />
        </svg>
      </div>
    )
  }

  return (
    <Layout background={currentPage === 'welcome' ? 'white' : '#F3F5F8'}>
      {currentPage === 'welcome' && (
        <WelcomePage onStart={async () => {
          try { localStorage.setItem('pp_seen_welcome', '1') } catch {}
          setCurrentPage('home')
          const cards = await refreshCards()
          if (cards.length > 0) refreshTransactions(cards)
        }} />
      )}
      {currentPage === 'home' && (
        <HomePage
          userCards={userCards}
          transactions={transactions}
          commissions={commissions}
          cardsLoading={cardsLoading}
          transactionsLoading={transactionsLoading}
          onNavigateToFAQ={() => setCurrentPage('faq')}
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
      {currentPage === 'faq' && <FAQPage onBack={() => setCurrentPage('home')} />}
      {currentPage === 'history' && (
        <HistoryPage
          userCards={userCards}
          transactions={transactions}
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
          onCryptoPaymentInitiated={(paymentData) => {
            setCryptoPaymentData(paymentData)
            setPendingPaymentId(paymentData.payment_id)
            try { localStorage.setItem('pp_pending_payment_id', paymentData.payment_id); localStorage.setItem('pp_pending_check_count', '0') } catch {}
            setCurrentPage('crypto-payment')
          }}
          getCommissionForCardType={getCommissionForCardType}
        />
      )}
      {currentPage === 'crypto-payment' && cryptoPaymentData && (
        <CryptoPaymentPage
          paymentData={cryptoPaymentData}
          onBack={() => {
            const isTopup = cryptoPaymentData?.type === 'topup'
            setCryptoPaymentData(null)
            setCurrentPage(isTopup ? 'card-detail' : 'issue-card')
          }}
          onSuccess={async () => {
            const isTopup = cryptoPaymentData?.type === 'topup'
            setCryptoPaymentData(null)
            if (!isTopup) setCardTypeToIssue(null)
            setPendingPaymentId(null)
            try { localStorage.removeItem('pp_pending_payment_id') } catch {}
            setCurrentPage(isTopup ? 'card-detail' : 'home')
            const cards = await refreshCards()
            if (cards.length > 0) refreshTransactions(cards)
          }}
        />
      )}
      {currentPage === 'card-detail' && (
        <CardDetailPage
          card={selectedCard}
          transactions={transactions}
          onBack={() => {
            setSelectedCard(null)
            setCurrentPage('home')
          }}
          onTopUp={handleDeposited}
          onNavigateToHistory={(cardLast4) => {
            setHistoryFixedCardLast4(cardLast4)
            setHistoryReturnCardId(selectedCard?.id || null)
            setCurrentPage('history')
          }}
          getCommissionForCardType={getCommissionForCardType}
          onCryptoPaymentInitiated={(paymentData) => {
            setCryptoPaymentData(paymentData)
            setPendingPaymentId(paymentData.payment_id)
            try { localStorage.setItem('pp_pending_payment_id', paymentData.payment_id); localStorage.setItem('pp_pending_check_count', '0') } catch {}
            setCurrentPage('crypto-payment')
          }}
        />
      )}
    </Layout>
  )
}

function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </ToastProvider>
  )
}

export default App
