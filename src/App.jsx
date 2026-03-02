import { useEffect, useRef, useState } from 'react'
import Layout from './components/Layout'
import WelcomePage from './pages/WelcomePage'
import HomePage from './pages/HomePage'
import FAQPage from './pages/FAQPage'
import IssueCardPage from './pages/IssueCardPage'

function App() {
  const [currentPage, setCurrentPage] = useState('welcome')
  const [cardTypeToIssue, setCardTypeToIssue] = useState(null)
  const tgInitOnceRef = useRef(false)

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
        />
      )}
    </Layout>
  )
}

export default App
