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
import { loadKycWidget, kycSessionId, openKycBrowser, copyKycLink } from '../../utils/kycWidget'
import { lockBackgroundScroll } from '../../utils/lockBackgroundScroll'
import { normalizeEmail, emailInputProps } from '../../utils/email'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

/** Current value of a Telegram safe-area CSS variable, in px (0 by default). */
function readSafeInset(varName) {
  try {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(varName)
    return Math.round(parseFloat(raw) || 0)
  } catch {
    return 0
  }
}

function formatPhoneInput(value) {
  // Remove all non-digits
  const digits = value.replace(/\D/g, '')
  // If starts with 8, replace with 7
  const normalized = digits.startsWith('8') ? '7' + digits.slice(1) : digits
  // If doesn't start with 7, prepend it
  const withCountry = normalized.startsWith('7') ? normalized : '7' + normalized
  // Take max 11 digits (7 + 10)
  const limited = withCountry.slice(0, 11)
  // Format as +7 (XXX) XXX-XX-XX
  if (limited.length <= 1) return '+7'
  if (limited.length <= 4) return `+7 (${limited.slice(1)}`
  if (limited.length <= 7) return `+7 (${limited.slice(1, 4)}) ${limited.slice(4)}`
  if (limited.length <= 9) return `+7 (${limited.slice(1, 4)}) ${limited.slice(4, 7)}-${limited.slice(7)}`
  return `+7 (${limited.slice(1, 4)}) ${limited.slice(4, 7)}-${limited.slice(7, 9)}-${limited.slice(9, 11)}`
}

export default function KycModal({ isOpen, onClose, onSuccess }) {
  const [screen, setScreen] = useState('contact')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('+7')
  const [gender, setGender] = useState('')  // 'MALE' | 'FEMALE'
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [credentials, setCredentials] = useState(null)
  const [widgetLoading, setWidgetLoading] = useState(false)
  const [browserHelp, setBrowserHelp] = useState(false)
  const [copied, setCopied] = useState(false)
  const [notice, setNotice] = useState('')
  const activeRef = useRef(false)
  const credentialsRef = useRef(null)
  const pendingRef = useRef(false)
  const completedRef = useRef(false)
  const lifecycleRef = useRef(0)
  const onSuccessRef = useRef(onSuccess)

  useEffect(() => { onSuccessRef.current = onSuccess }, [onSuccess])

  useEffect(() => {
    if (isOpen) return lockBackgroundScroll()
  }, [isOpen])

  const acceptResult = (result) => {
    if (!activeRef.current || completedRef.current) return
    if (result.kyc_status === 'success' && result.passport_saved !== false && result.has_passport_data !== false) {
      completedRef.current = true
      pendingRef.current = false
      setScreen('success')
      onSuccessRef.current?.()
    } else if (result.kyc_status === 'failed') {
      pendingRef.current = false
      setError('Проверка не пройдена. Вернитесь к контактным данным и начните заново.')
      setScreen('error')
    }
  }

  useEffect(() => {
    lifecycleRef.current += 1
    activeRef.current = isOpen
    if (!isOpen) {
      credentialsRef.current = null
      pendingRef.current = false
      completedRef.current = false
      setCredentials(null)
      setScreen('contact')
      setError('')
      setNotice('')
      setBrowserHelp(false)
      setWidgetLoading(false)
      setCopied(false)
      setLoading(false)
      return
    }
    let cancelled = false
    let checking = false
    const check = async () => {
      if (cancelled || checking || document.visibilityState === 'hidden' || !pendingRef.current) return
      checking = true
      try {
        const result = await api.kyc.refresh()
        if (!cancelled) acceptResult(result)
      } catch { /* Keep the browser link available; the next foreground check retries. */ }
      finally { checking = false }
    }
    api.kyc.status().then(status => {
      if (cancelled) return
      setEmail(normalizeEmail(status.email))
      setPhone(formatPhoneInput(status.phone || ''))
      setGender(status.gender || '')
      pendingRef.current = Boolean(credentialsRef.current) || status.kyc_status === 'pending'
      acceptResult(status)
      void check()
    }).catch(() => {})
    const interval = setInterval(check, 8000)
    window.addEventListener('focus', check)
    document.addEventListener('visibilitychange', check)
    return () => {
      cancelled = true
      activeRef.current = false
      clearInterval(interval)
      window.removeEventListener('focus', check)
      document.removeEventListener('visibilitychange', check)
    }
  }, [isOpen])

  if (!isOpen) return null

  const openNvWidget = async (creds) => {
    setWidgetLoading(true)
    setError('')
    try {
      const widget = await loadKycWidget()
      if (!activeRef.current || credentialsRef.current !== creds) return
      widget.setupKYC({
        scenarioId: creds.schema_id,
        clientKey: creds.client_key_encrypted,
        clientUser: String(creds.user_id ?? ''),
        theme: 'light',
        topOffset: readSafeInset('--tg-safe-top'),
        bottomOffset: readSafeInset('--tg-safe-bottom'),
        closeCb: () => {
          if (activeRef.current && credentialsRef.current === creds && !completedRef.current) {
            setWidgetLoading(false)
            setBrowserHelp(true)
          }
        },
        successCb: async (payload) => {
          if (!activeRef.current || credentialsRef.current !== creds) return
          setScreen('processing')
          try {
            const sessionId = kycSessionId(payload)
            const result = sessionId ? await api.kyc.complete(sessionId) : await api.kyc.refresh()
            if (credentialsRef.current === creds) acceptResult(result)
          } catch (e) {
            if (activeRef.current && credentialsRef.current === creds) setError(e.message || 'Не удалось получить результат проверки')
          }
        },
      })
    } catch (e) {
      if (activeRef.current && credentialsRef.current === creds) {
        setError(e.message || 'Не удалось открыть проверку в Telegram. Продолжите в браузере.')
        setBrowserHelp(true)
      }
    } finally {
      if (activeRef.current && credentialsRef.current === creds) setWidgetLoading(false)
    }
  }

  const handleContactSubmit = async () => {
    if (!email.trim() || !phone.trim()) return setError('Введите email и номер телефона')
    const domain = email.trim().toLowerCase().split('@').pop()
    if (domain !== 'gmail.com' && domain !== 'icloud.com') return setError('Используйте почту Gmail (@gmail.com) или iCloud (@icloud.com)')
    if (gender !== 'MALE' && gender !== 'FEMALE') return setError('Выберите пол')
    const phoneClean = phone.replace(/[\s()-]/g, '')
    if (!/^\+7\d{10}$/.test(phoneClean)) return setError('Телефон в формате +7XXXXXXXXXX')
    setError('')
    setLoading(true)
    const lifecycle = lifecycleRef.current
    try {
      await api.kyc.updateContact(normalizeEmail(email), phoneClean, gender)
      if (!activeRef.current || lifecycle !== lifecycleRef.current) return
      const creds = await api.kyc.start()
      if (!activeRef.current || lifecycle !== lifecycleRef.current) return
      credentialsRef.current = creds
      pendingRef.current = true
      setCredentials(creds)
      setBrowserHelp(false)
      setCopied(false)
      setNotice('')
      setScreen('widget')
      void openNvWidget(creds)
    } catch (e) {
      if (activeRef.current && lifecycle === lifecycleRef.current) setError(e.message || 'Ошибка, попробуйте ещё раз')
    } finally {
      if (activeRef.current && lifecycle === lifecycleRef.current) setLoading(false)
    }
  }

  const checkManually = async () => {
    const lifecycle = lifecycleRef.current
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const result = await api.kyc.refresh()
      if (!activeRef.current || lifecycle !== lifecycleRef.current) return
      acceptResult(result)
      if (result.kyc_status === 'pending') setNotice('Результат пока не получен. Завершите проверку в браузере и вернитесь сюда.')
    } catch (e) {
      if (activeRef.current && lifecycle === lifecycleRef.current) setError(e.message || 'Не удалось проверить результат. Попробуйте позже.')
    } finally {
      if (activeRef.current && lifecycle === lifecycleRef.current) setLoading(false)
    }
  }

  const browserFallback = credentials?.verification_url && (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, textAlign: 'left' }}>
      <Button fullWidth style={{ fontSize: 14, lineHeight: 1.45 }} onClick={() => {
        setBrowserHelp(true)
        setNotice('')
        try {
          if (!openKycBrowser(credentials.verification_url)) setNotice('Если браузер не открылся, скопируйте ссылку ниже.')
        } catch { setNotice('Скопируйте ссылку и откройте её в браузере.') }
      }}>Виджет не открылся? Открыть в браузере</Button>
      {browserHelp && (
        <div style={{ padding: 16, borderRadius: 14, background: '#F3F5F8', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#111827' }}>Пройдите проверку в браузере</div>
          <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.6 }}>
            Если кнопка не открывает страницу, скопируйте ссылку и вставьте её в адресную строку Safari или Chrome. Разрешите доступ к камере и следуйте инструкциям.
          </div>
          <input aria-label="Ссылка на проверку" readOnly value={credentials.verification_url} onFocus={e => e.target.select()}
            style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #E5E7EB', background: '#FFFFFF', borderRadius: 10, padding: 12, fontSize: 13, color: '#6B7280', textOverflow: 'ellipsis' }} />
          <Button fullWidth style={{ backgroundColor: '#FFFFFF', color: '#DC4D35', fontSize: 14, padding: 13 }} onClick={async () => {
            const ok = await copyKycLink(credentials.verification_url)
            if (!activeRef.current) return
            setCopied(ok)
            if (!ok) setNotice('Нажмите на ссылку выше, выделите её и скопируйте вручную.')
          }}>{copied ? 'Ссылка скопирована' : 'Скопировать ссылку'}</Button>
          <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.5 }}>Ссылка предназначена только для вашей проверки. Не передавайте её другим людям.</div>
        </div>
      )}
      <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.6 }}>
        После проверки вернитесь в Telegram. Мы автоматически проверим результат — или нажмите кнопку ниже.
      </div>
      <Button fullWidth variant="link" style={{ justifyContent: 'center', padding: 10 }} disabled={loading} onClick={checkManually}>
        {loading ? 'Проверяем…' : 'Проверить результат'}
      </Button>
      {notice && <div role="status" style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.5 }}>{notice}</div>}
    </div>
  )

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
          maxHeight: '90dvh', overflowY: 'auto', overscrollBehavior: 'contain', WebkitOverflowScrolling: 'touch',
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
                Для оплаты по СБП необходимо пройти верификацию личности. Введите ваши контактные данные и отсканируйте паспорт.
              </div>

              {/* Bank identity-match warning */}
              <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 12, padding: '12px 14px', fontSize: 12, color: '#92400E', lineHeight: 1.55 }}>
                <b>Важно:</b> ФИО (по паспорту) и номер телефона должны совпадать с данными владельца
                банковского счёта, с которого вы будете оплачивать по СБП. При несовпадении платежи
                могут отклоняться или блокироваться.
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
                  Email <span style={{ fontWeight: 400, color: '#9CA3AF' }}>(только Gmail или iCloud)</span>
                </label>
                <input
                  type="email"
                  {...emailInputProps}
                  value={email}
                  onChange={e => setEmail(normalizeEmail(e.target.value))}
                  placeholder="example@gmail.com"
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
                  onChange={e => setPhone(formatPhoneInput(e.target.value))}
                  placeholder="+7 (999) 123-45-67"
                  style={{
                    padding: '12px 14px', borderRadius: 10, border: '1.5px solid #E5E7EB',
                    fontSize: 15, outline: 'none', fontFamily: font,
                  }}
                  onFocus={e => e.target.style.borderColor = '#DC4D35'}
                  onBlur={e => e.target.style.borderColor = '#E5E7EB'}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Пол</label>
                <div style={{ display: 'flex', gap: 10 }}>
                  {[
                    { value: 'MALE', label: 'Мужской' },
                    { value: 'FEMALE', label: 'Женский' },
                  ].map(opt => {
                    const active = gender === opt.value
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setGender(opt.value)}
                        style={{
                          flex: 1,
                          padding: '12px 14px',
                          borderRadius: 10,
                          border: `1.5px solid ${active ? '#DC4D35' : '#E5E7EB'}`,
                          background: active ? '#FEF2F0' : '#FFFFFF',
                          color: active ? '#DC4D35' : '#374151',
                          fontWeight: active ? 600 : 500,
                          fontSize: 15,
                          fontFamily: font,
                          cursor: 'pointer',
                        }}
                      >
                        {opt.label}
                      </button>
                    )
                  })}
                </div>
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

          {(screen === 'widget' || screen === 'processing') && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div style={{ textAlign: 'center', paddingTop: 8 }}>
                <div style={{ width: 64, height: 64, borderRadius: 20, background: '#FFF0EB', margin: '0 auto 16px', display: 'grid', placeItems: 'center', color: '#DC4D35' }}>
                  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M8 5l1.5-2h5L16 5h4a2 2 0 012 2v12a2 2 0 01-2 2H4a2 2 0 01-2-2V7a2 2 0 012-2h4z"/><circle cx="12" cy="13" r="4"/></svg>
                </div>
                <div style={{ fontWeight: 700, fontSize: 18, color: '#111827', marginBottom: 8 }}>
                  {screen === 'processing' ? 'Проверяем данные' : 'Продолжите проверку'}
                </div>
                <div style={{ fontSize: 14, color: '#6B7280', lineHeight: 1.6 }}>
                  {widgetLoading ? 'Загружаем окно проверки…' : screen === 'processing' ? 'Получаем результат верификации. Это может занять немного времени.' : 'Следуйте инструкциям в окне проверки. Если оно не появилось, откройте проверку в браузере.'}
                </div>
              </div>
              {error && <div role="alert" style={{ background: '#FFF0EB', borderRadius: 12, padding: 12, fontSize: 13, color: '#B6402C', lineHeight: 1.5 }}>{error}</div>}
              {browserFallback}
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
