import { useEffect, useRef, useState } from 'react'
import Layout from './components/Layout'
import WelcomePage from './pages/WelcomePage'
import HomePage from './pages/HomePage'
import FAQPage from './pages/FAQPage'
import IssueCardPage from './pages/IssueCardPage'

function App() {
  const [currentPage, setCurrentPage] = useState('welcome')
  const [cardTypeToIssue, setCardTypeToIssue] = useState(null)
  const [userCards, setUserCards] = useState([])
  const tgInitOnceRef = useRef(false)

  const addCard = (cardData) => {
    const newCard = {
      id: `card-${Date.now()}`,
      balance: Math.floor(Math.random() * 50000) + Math.random(),
      last4: String(Math.floor(1000 + Math.random() * 9000)),
      title: 'Виртуальная карта',
      ...cardData,
    }
    setUserCards((prev) => [...prev, newCard])
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
    <Layout background={currentPage === 'welcome' ? 'white' : '#F3F5F8'}>
      {currentPage === 'welcome' && <WelcomePage onStart={() => setCurrentPage('home')} />}
      {currentPage === 'home' && (
        <HomePage
          userCards={userCards}
          onNavigateToFAQ={() => setCurrentPage('faq')}
          onNavigateToIssueCard={(cardType = null) => {
            setCardTypeToIssue(cardType)
            setCurrentPage('issue-card')
          }}
        />
      )}
      {currentPage === 'faq' && <FAQPage onBack={() => setCurrentPage('home')} />}
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
    </Layout>
  )
}

export default App
