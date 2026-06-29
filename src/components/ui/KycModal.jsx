/**
 * KycModal — NeuroVision KYC flow.
 *
 * Steps:
 *  1. 'contact' — user enters email and phone
 *  2. 'widget'  — NeuroVision widget opens (injected script)
 *  3. 'processing' — waiting for backend to fetch session result
 *  4. 'success' — KYC complete
 *  5. 'error'   — something went wrong
 *
 * Props:
 *   isOpen    — boolean
 *   onClose   — () => void
 *   onSuccess — () => void  called when KYC completes successfully
 */
import { useEffect, useRef, useState } from 'react'
import api from '../../api/client'
import Button from './Button'
import Portal from './Portal'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

export default function KycModal({ isOpen, onClose, onSuccess }) {
  const [screen, setScreen] = useState('contact')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const widgetLoadedRef = useRef(false)

  useEffect(() => {
    if (!isOpen) {
      setScreen('contact')
      setError('')
      widgetLoadedRef.current = false
      return
    }
    // Load existing email/phone from backend; if already verified, short-circuit
    api.kyc.status().then(status => {
      if (status.email) setEmail(status.email)
      if (status.phone) setPhone(status.phone)
      if (status.kyc_status === 'success') {
        if (typeof onSuccess === 'function') onSuccess()
      }
    }).catch(() => {})
  }, [isOpen])

  if (!isOpen) return null

  // Step 1: save contact info and open widget
  const handleContactSubmit = async () => {
    if (!email.trim() || !phone.trim()) {
      setError('Введите email и номер телефона')
      return
    }
    const phoneClean = phone.replace(/[\s()\-]/g, '')
    if (!/^\+7\d{10}$/.test(phoneClean)) {
      setError('Телефон в формате +7XXXXXXXXXX')
      return
    }
    setError('')
    setLoading(true)
    try {
      // Save contact to backend
      await api.kyc.updateContact(email.trim(), phoneClean)
      // Get widget credentials from backend
      const creds = await api.kyc.start()
      setLoading(false)
      setScreen('widget')
      // Load and open NeuroVision widget
      openNvWidget(creds.schema_id, creds.client_key_encrypted)
    } catch (e) {
      setLoading(false)
      setError(e.message || 'Ошибка, попробуйте ещё раз')
    }
  }

  const openNvWidget = (schemaId, clientKey) => {
    const doOpen = () => {
      if (!window.KYCWidget) {
        setError('Не удалось загрузить виджет верификации')
        setScreen('error')
        return
      }
      window.KYCWidget.setupKYC({
        schemaId,
        clientKey,
        theme: 'light',
        closeCb: () => {
          // Only reset to contact form if user closed the widget WITHOUT completing
          // (i.e. screen is still 'widget'). If success/processing — leave it alone.
          setScreen(prev => (prev === 'widget' ? 'contact' : prev))
        },
        successCb: async (payload) => {
          setScreen('processing')
          // Try sessionId from payload first, then poll our backend (webhook may arrive later)
          const sessionId = payload?.sessionId || payload?.session_id || payload?.id
          if (sessionId) {
            await handleKycComplete(sessionId)
          } else {
            // No sessionId in payload — poll our backend waiting for webhook to deliver data
            await pollKycStatus()
          }
        },
      })
    }

    if (window.KYCWidget) {
      doOpen()
      return
    }
    // Lazy-load widget script
    if (!document.getElementById('nv-kyc-widget-script')) {
      const s = document.createElement('script')
      s.id = 'nv-kyc-widget-script'
      s.src = 'https://kyc.neuro-vision.ru/lib/widget-lib.js'
      s.defer = true
      s.crossOrigin = 'anonymous'
      s.onload = doOpen
      s.onerror = () => {
        setError('Не удалось загрузить виджет верификации')
        setScreen('error')
      }
      document.head.appendChild(s)
    }
  }

  const handleKycComplete = async (sessionId) => {
    try {
      const result = await api.kyc.complete(sessionId)
      if (result.kyc_status === 'success') {
        setScreen('success')
        if (typeof onSuccess === 'function') onSuccess()
      } else if (result.kyc_status === 'failed') {
        setError('Верификация не пройдена. Попробуйте ещё раз.')
        setScreen('error')
      } else {
        // Still processing — poll
        await pollKycStatus()
      }
    } catch (e) {
      setError(e.message || 'Ошибка обработки результата')
      setScreen('error')
    }
  }

  const pollKycStatus = async () => {
    // Poll for up to 3 minutes (36 * 5s) waiting for webhook to update our DB
    for (let i = 0; i < 36; i++) {
      await new Promise(r => setTimeout(r, 5000))
      try {
        const status = await api.kyc.status()
        if (status.kyc_status === 'success') {
          setScreen('success')
          if (typeof onSuccess === 'function') onSuccess()
          return
        }
        if (status.kyc_status === 'failed') {
          setError('Верификация не пройдена. Попробуйте ещё раз.')
          setScreen('error')
          return
        }
        // kyc_status === 'pending' or null — keep polling
      } catch {}
    }
    // Timed out — but user may still be verified via webhook later
    // Show success-ish message and let them retry
    setError('Данные верификации ещё обрабатываются. Подождите минуту и попробуйте снова.')
    setScreen('error')
  }

  return (
    <Portal>
      <div
        style={{
          position: 'fixed', inset: 0, zIndex: 1100,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
        }}
        onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      >
        <div style={{
          width: '100%', maxWidth: 480,
          background: '#FFFFFF', borderRadius: '20px 20px 0 0',
          padding: '24px 20px 40px',
          fontFamily: font,
          maxHeight: '90dvh', overflowY: 'auto',
        }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#111827' }}>Верификация личности</div>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: '#6B7280' }}
            >×</button>
          </div>

          {/* CONTACT */}
          {screen === 'contact' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 14, color: '#6B7280', lineHeight: 1.6 }}>
                Для выпуска карты необходимо пройти верификацию личности. Введите ваши контактные данные и отсканируйте паспорт.
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="example@mail.ru"
                  style={{
                    padding: '12px 14px', borderRadius: 10, border: '1.5px solid #E5E7EB',
                    fontSize: 15, outline: 'none', fontFamily: font,
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={e => e.target.style.borderColor = '#DC4D35'}
                  onBlur={e => e.target.style.borderColor = '#E5E7EB'}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Номер телефона</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="+79991234567"
                  style={{
                    padding: '12px 14px', borderRadius: 10, border: '1.5px solid #E5E7EB',
                    fontSize: 15, outline: 'none', fontFamily: font,
                  }}
                  onFocus={e => e.target.style.borderColor = '#DC4D35'}
                  onBlur={e => e.target.style.borderColor = '#E5E7EB'}
                />
              </div>

              {error && (
                <div style={{ fontSize: 13, color: '#DC2626' }}>{error}</div>
              )}

              <Button onClick={handleContactSubmit} fullWidth disabled={loading}>
                {loading ? 'Загрузка…' : 'Далее — сканирование паспорта'}
              </Button>

              <div style={{ fontSize: 12, color: '#9CA3AF', textAlign: 'center', lineHeight: 1.5 }}>
                Ваши данные защищены и используются только для верификации. Мы не передаём их третьим лицам.
              </div>
            </div>
          )}

          {/* WIDGET OPEN */}
          {screen === 'widget' && (
            <div style={{ textAlign: 'center', padding: '32px 0', color: '#6B7280', fontSize: 15 }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>📷</div>
              <div style={{ fontWeight: 600, color: '#111827', marginBottom: 8 }}>Откройте виджет</div>
              <div style={{ fontSize: 14 }}>Виджет верификации запущен. Следуйте инструкциям на экране.</div>
            </div>
          )}

          {/* PROCESSING */}
          {screen === 'processing' && (
            <div style={{ textAlign: 'center', padding: '24px 0', color: '#6B7280', fontSize: 15, display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 32 }}>⏳</div>
              <div style={{ fontWeight: 600, color: '#111827' }}>Проверяем данные</div>
              <div style={{ fontSize: 14 }}>Обрабатываем результаты верификации…</div>
              <Button
                onClick={async () => {
                  try {
                    const status = await api.kyc.status()
                    if (status.kyc_status === 'success') {
                      setScreen('success')
                      if (typeof onSuccess === 'function') onSuccess()
                    } else {
                      setError('Данные ещё обрабатываются. Подождите немного.')
                      setScreen('error')
                    }
                  } catch (e) {
                    setError(e.message || 'Ошибка проверки статуса')
                    setScreen('error')
                  }
                }}
                fullWidth
              >
                Проверить статус вручную
              </Button>
            </div>
          )}

          {/* SUCCESS */}
          {screen === 'success' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center', paddingTop: 8 }}>
              <div style={{ fontSize: 48 }}>✅</div>
              <div style={{ fontSize: 17, fontWeight: 700, color: '#111827' }}>Верификация пройдена</div>
              <div style={{ fontSize: 14, color: '#6B7280', textAlign: 'center' }}>
                Ваша личность подтверждена. Теперь вы можете выпускать карты и оплачивать через СБП.
              </div>
              <Button onClick={onClose} fullWidth>Продолжить</Button>
            </div>
          )}

          {/* ERROR */}
          {screen === 'error' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 32, textAlign: 'center' }}>❌</div>
              <div style={{ fontSize: 15, color: '#DC2626', lineHeight: 1.5, textAlign: 'center' }}>
                {error || 'Произошла ошибка верификации'}
              </div>
              <Button onClick={() => { setError(''); setScreen('contact') }} fullWidth>
                Попробовать ещё раз
              </Button>
            </div>
          )}
        </div>
      </div>
    </Portal>
  )
}
