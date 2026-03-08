import { useEffect, useRef, useState } from 'react'
import Layout from './components/Layout'
import WelcomePage from './pages/WelcomePage'
import HomePage from './pages/HomePage'
import FAQPage from './pages/FAQPage'
import IssueCardPage from './pages/IssueCardPage'
import CardDetailPage from './pages/CardDetailPage'
import HistoryPage from './pages/HistoryPage'
import { ToastProvider } from './components/ui/ToastProvider'

const HISTORY_TITLES = {
  payment: [
    { title: 'Kanzler', subtitle: 'Магазины' },
    { title: 'Amediateka', subtitle: 'Сервисы' },
    { title: 'Steam', subtitle: 'Сервисы' },
    { title: 'Lamoda', subtitle: 'Магазины' },
  ],
  withdrawal: [
    { title: '***', subtitle: 'Вывод средств' },
  ],
  topup: [
    { title: '***', subtitle: 'Пополнение' },
  ],
  declined: [
    { title: 'Константин С.', subtitle: 'Операция отклонена' },
    { title: 'Александр П.', subtitle: 'Операция отклонена' },
  ],
}

function randomFrom(list) {
  return list[Math.floor(Math.random() * list.length)]
}

function randomAmount(type) {
  if (type === 'topup') return [1000, 1500, 3000, 5000, 10000][Math.floor(Math.random() * 5)]
  if (type === 'withdrawal') return -[500, 1200, 2500, 4000][Math.floor(Math.random() * 4)]
  if (type === 'declined') return -[490, 1200, 32480, 799][Math.floor(Math.random() * 4)]
  return -[159.99, 490, 501.69, 1299, 2499][Math.floor(Math.random() * 5)]
}

function generateCardTransactions(card) {
  const types = ['topup', 'payment', 'payment', 'withdrawal', 'declined']
  return types.map((type, index) => {
    const meta = randomFrom(HISTORY_TITLES[type])
    const dayOffset = Math.floor(Math.random() * 12)
    const date = new Date()
    date.setHours(12, 0, 0, 0)
    date.setDate(date.getDate() - dayOffset)

    return {
      id: `tx-${card.id}-${index}-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      type,
      title: type === 'topup' || type === 'withdrawal' ? `*** ${card.last4}` : meta.title,
      subtitle: meta.subtitle,
      cardTitle: card.title || 'Виртуальная карта',
      cardLast4: card.last4,
      amount: randomAmount(type),
      date,
    }
  })
}

function App() {
  const [currentPage, setCurrentPage] = useState('welcome')
  const [cardTypeToIssue, setCardTypeToIssue] = useState(null)
  const [selectedCard, setSelectedCard] = useState(null)
  const [userCards, setUserCards] = useState([])
  const [transactions, setTransactions] = useState([])
  const [historyFixedCardLast4, setHistoryFixedCardLast4] = useState(null)
  const tgInitOnceRef = useRef(false)

  const addCard = (cardData) => {
    const last4 = String(Math.floor(1000 + Math.random() * 9000))
    const first12 = String(Math.floor(10 ** 11 + Math.random() * 9 * 10 ** 11)).padStart(12, '0')
    const cardNumber = `${first12}${last4}`
    const cvv = String(Math.floor(100 + Math.random() * 900))
    const expiry = '12/28'

    const newCard = {
      id: `card-${Date.now()}`,
      balance: cardData?.amount || 0,
      last4,
      cardNumber,
      cvv,
      expiry,
      title: 'Виртуальная карта',
      ...cardData,
    }
    setUserCards((prev) => [...prev, newCard])
    setTransactions((prev) => [...generateCardTransactions(newCard), ...prev])
  }

  const topUpCardBalance = (cardId, deltaAmount, meta = null) => {
    const numericDelta = Number(deltaAmount) || 0

    setUserCards((prev) =>
      prev.map((c) =>
        c.id === cardId
          ? {
              ...c,
              balance: (Number(c.balance) || 0) + numericDelta,
            }
          : c
      )
    )

    setSelectedCard((prev) => {
      if (!prev || prev.id !== cardId) return prev
      return {
        ...prev,
        balance: (Number(prev.balance) || 0) + numericDelta,
      }
    })

    const cardLast4 =
      meta?.cardLast4 || (selectedCard?.id === cardId ? selectedCard?.last4 : null)
    const cardTitle =
      meta?.cardTitle || (selectedCard?.id === cardId ? (selectedCard?.title || 'Виртуальная карта') : 'Виртуальная карта')

    if (cardLast4) {
      setTransactions((prev) => [
        {
          id: `tx-topup-${cardId}-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
          type: 'topup',
          title: `*** ${cardLast4}`,
          subtitle: 'Пополнение',
          cardTitle,
          cardLast4,
          amount: numericDelta,
          date: new Date(),
        },
        ...prev,
      ])
    }
  }

  useEffect(() => {
    if (tgInitOnceRef.current) return
    tgInitOnceRef.current = true

    let canceled = false

    const initTelegram = () => {
      const tg = window?.Telegram?.WebApp
      if (!tg) return false

      try {
        tg.ready()
        tg.expand()

        if (typeof tg.disableVerticalSwipes === 'function') {
          tg.disableVerticalSwipes()
        }
      } catch {
        // ignore
      }

      return true
    }

    if (initTelegram()) return

    let attempts = 0
    const timer = setInterval(() => {
      if (canceled) return
      attempts += 1

      if (initTelegram() || attempts >= 50) {
        clearInterval(timer)
      }
    }, 100)

    return () => {
      canceled = true
      clearInterval(timer)
    }
  }, [])

  return (
    <ToastProvider>
      <Layout background={currentPage === 'welcome' ? 'white' : '#F3F5F8'}>
        {currentPage === 'welcome' && <WelcomePage onStart={() => setCurrentPage('home')} />}
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
            onBack={() => setCurrentPage('home')}
          />
        )}
        {currentPage === 'issue-card' && (
          <IssueCardPage
            onBack={() => {
              setCardTypeToIssue(null)
              setCurrentPage('home')
            }}
            initialCardType={cardTypeToIssue}
            onCardIssued={(cardData) => {
              addCard(cardData)
              setCardTypeToIssue(null)
              setCurrentPage('home')
            }}
          />
        )}
        {currentPage === 'card-detail' && (
          <CardDetailPage
            card={selectedCard}
            transactions={transactions}
            onTopUp={(cardId, deltaAmount, meta) => topUpCardBalance(cardId, deltaAmount, meta)}
            onNavigateToHistory={(cardLast4) => {
              setHistoryFixedCardLast4(cardLast4)
              setCurrentPage('history')
            }}
            onBack={() => {
              setSelectedCard(null)
              setCurrentPage('home')
            }}
          />
        )}
      </Layout>
    </ToastProvider>
  )
}

export default App
