import { useCallback, useEffect, useRef, useState } from 'react'
import api from './api/client'
import Layout from './components/Layout'
import { ToastProvider } from './components/ui/ToastProvider'
import { AuthProvider, useAuth } from './context/AuthContext'
import CardDetailPage from './pages/CardDetailPage'
import FAQPage from './pages/FAQPage'
import HistoryPage from './pages/HistoryPage'
import HomePage from './pages/HomePage'
import IssueCardPage from './pages/IssueCardPage'
import WelcomePage from './pages/WelcomePage'

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
  const { user, loading: authLoading, appConfig } = useAuth()
  const [currentPage, setCurrentPage] = useState('welcome')
  const [cardTypeToIssue, setCardTypeToIssue] = useState(null)
  const [selectedCard, setSelectedCard] = useState(null)
  const [userCards, setUserCards] = useState([])
  const [transactions, setTransactions] = useState([])
  const [historyFixedCardLast4, setHistoryFixedCardLast4] = useState(null)
  const [historyReturnCardId, setHistoryReturnCardId] = useState(null)
  const tgInitOnceRef = useRef(false)

  // Load cards from API
  const refreshCards = useCallback(async () => {
    try {
      const cards = await api.cards.list()
      const mapped = cards.map((c) => ({
        ...c,
        title: 'Виртуальная карта',
      }))
      setUserCards(mapped)
      return mapped
    } catch (e) {
      console.error('[Cards] failed to load cards:', e.message)
      return []
    }
  }, [])

  // Load transactions for all cards (first 10 each) for history page
  const refreshTransactions = useCallback(
    async (cards) => {
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
    },
    [],
  )

  // When user is authenticated and on home page, refresh cards
  useEffect(() => {
    if (!user) return
    refreshCards().then((cards) => {
      if (cards.length > 0) refreshTransactions(cards)
    })
  }, [user, refreshCards, refreshTransactions])

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

  // While auth is loading show nothing (or a spinner)
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
    <Layout background={currentPage === 'welcome' ? 'white' : '#F3F5F8'}>
      {currentPage === 'welcome' && (
        <WelcomePage onStart={() => setCurrentPage('home')} />
      )}
      {currentPage === 'home' && (
        <HomePage
          userCards={userCards}
          transactions={transactions}
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
          onBack={() => {
            setCardTypeToIssue(null)
            setCurrentPage('home')
          }}
          initialCardType={cardTypeToIssue}
          issueMarkupPercent={appConfig.card_issue_markup_percent}
          onCardIssued={handleCardIssued}
        />
      )}
      {currentPage === 'card-detail' && (
        <CardDetailPage
          card={selectedCard}
          transactions={transactions}
          topupMarkupPercent={appConfig.card_topup_markup_percent}
          onTopUp={handleDeposited}
          onNavigateToHistory={(cardLast4) => {
            setHistoryFixedCardLast4(cardLast4)
            setHistoryReturnCardId(selectedCard?.id || null)
            setCurrentPage('history')
          }}
          onBack={() => {
            setSelectedCard(null)
            setCurrentPage('home')
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
