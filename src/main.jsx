import { lazy, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ScreenLoader from './components/ScreenLoader'

const isAdmin = window.location.pathname.startsWith('/admin')
const AdminApp = lazy(() => import('./admin/AdminApp.jsx'))
if (window.Telegram?.WebApp?.platform === 'android' || /Android/i.test(navigator.userAgent)) {
  document.documentElement.classList.add('android-webview')
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {isAdmin ? <ScreenLoader><AdminApp /></ScreenLoader> : <App />}
  </StrictMode>,
)
