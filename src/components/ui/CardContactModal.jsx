import { useEffect, useState } from 'react'
import api from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import Button from './Button'
import Portal from './Portal'

export default function CardContactModal({ isOpen, onClose, onSaved }) {
  const { user, fetchMe } = useAuth()
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (isOpen) { setEmail(user?.email || ''); setPhone(user?.phone || ''); setError('') }
  }, [isOpen, user?.email, user?.phone])
  if (!isOpen) return null
  async function save(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      await api.crypto.saveContact(email.trim(), phone.trim())
      await fetchMe?.()
      onSaved?.()
    } catch (e) { setError(e.message || 'Не удалось сохранить контакты') }
    finally { setBusy(false) }
  }
  const field = { display: 'block', width: '100%', boxSizing: 'border-box', padding: 12, margin: '6px 0 14px', borderRadius: 10, border: '1px solid #D1D5DB', fontSize: 16 }
  return <Portal>
    <div onClick={busy ? undefined : onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 1060 }} />
    <form onSubmit={save} role="dialog" aria-modal="true" aria-label="Контакты для карты Online" style={{ position: 'fixed', left: '50%', bottom: 0, transform: 'translateX(-50%)', width: '100%', maxWidth: 430, boxSizing: 'border-box', borderRadius: '24px 24px 0 0', background: '#F3F5F8', padding: '24px 20px calc(24px + var(--tg-safe-bottom, 0px))', zIndex: 1061 }}>
      <h2 style={{ margin: '0 0 12px', fontSize: 22 }}>Контакты для карты Online</h2>
      <p style={{ fontSize: 14, color: '#6B7280', lineHeight: 1.5 }}>Для карты нужны действующие email и телефон. Проходить NeuroVision для оплаты с баланса не требуется.</p>
      <label>Email<input required type="email" autoComplete="email" value={email} disabled={busy} onChange={e => setEmail(e.target.value)} style={field} /></label>
      <label>Телефон с кодом страны<input required type="tel" autoComplete="tel" value={phone} disabled={busy} onChange={e => setPhone(e.target.value)} placeholder="+7 999 123-45-67" style={field} /></label>
      {error && <p role="alert" style={{ color: '#B91C1C', fontSize: 13 }}>{error}</p>}
      <Button type="submit" disabled={busy} fullWidth>{busy ? 'Сохраняем…' : 'Сохранить и продолжить'}</Button>
      <Button type="button" variant="secondary" disabled={busy} onClick={onClose} fullWidth style={{ marginTop: 10 }}>Отмена</Button>
    </form>
  </Portal>
}
