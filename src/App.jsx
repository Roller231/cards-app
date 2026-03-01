import { useState } from 'react'
import Layout from './components/Layout'
import WelcomePage from './pages/WelcomePage'
import HomePage from './pages/HomePage'

function App() {
  const [currentPage, setCurrentPage] = useState('welcome')

  return (
    <Layout>
      {currentPage === 'welcome' && <WelcomePage onStart={() => setCurrentPage('home')} />}
      {currentPage === 'home' && <HomePage />}
    </Layout>
  )
}

export default App
