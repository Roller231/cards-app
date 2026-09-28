import { useCallback, useEffect, useState } from 'react'
import api from '../api/client'
import Card from '../components/ui/Card'
import Section from '../components/ui/Section'
import Button from '../components/ui/Button'
import { BOTTOM_BAR_SPACE } from '../components/BottomBar'
import { metrikaGoal } from '../utils/metrika'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

const SERVICES = [
  { id: 'alipay', label: 'Alipay', color: '#1677FF', mark: '支' },
  { id: 'wechat', label: 'WeChat Pay', color: '#07C160', mark: '微' },
  { id: 'other', label: 'Другой', color: '#6B7280', mark: '…' },
]
const CURRENCIES = [
  { id: 'CNY', label: '¥ Юань' },
  { id: 'USD', label: '$ Доллар' },
  { id: 'EUR', label: '€ Евро' },
]
const STATUS_STYLE = {
  new: { bg: '#EFF6FF', color: '#1D4ED8' },
  in_progress: { bg: '#FFFBEB', color: '#B45309' },
  done: { bg: '#ECFDF5', color: '#047857' },
  rejected: { bg: '#FEF2F2', color: '#B91C1C' },
}

const labelStyle = { fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font, display: 'block', marginBottom: 10 }

function sanitizeAmount(value) {
  const cleaned = value.replace(',', '.').replace(/[^0-9.]/g, '')
  const [i = '', ...d] = cleaned.split('.')
  return d.length > 0 ? `${i}.${d.join('').slice(0, 2)}` : i
}

/**
 * "Китай" tab: Alipay / WeChat Pay payments. The user leaves a request;
 * managers get it in Telegram and in the admin panel and contact the user.
 */
export default function ChinaPage() {
  const [service, setService] = useState('alipay')
  const [currency, setCurrency] = useState('CNY')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(null)       // created request
  const [requests, setRequests] = useState([])

  const loadRequests = useCallback(async () => {
    try {
      const r = await api.services.myRequests()
      setRequests(r?.items || [])
    } catch {}
  }, [])
  useEffect(() => { loadRequests() }, [loadRequests])

  const amountNum = parseFloat(amount) || 0
  const canSubmit = amountNum > 0 && (service !== 'other' || note.trim().length > 0) && !sending

  const submit = async () => {
    if (!canSubmit) return
    setSending(true)
    setError('')
    try {
      const res = await api.services.createRequest({ service, amount: amountNum, currency, note: note.trim() || null })
      metrikaGoal('service_request', { service, currency })
      setSent(res)
      setAmount('')
      setNote('')
      loadRequests()
    } catch (e) {
      setError(e.message || 'Не удалось отправить заявку')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col" style={{ paddingBottom: BOTTOM_BAR_SPACE }}>
      {/* Hero */}
      <Section>
        <div style={{
          position: 'relative', overflow: 'hidden', borderRadius: 20, padding: '22px 20px',
          background: 'linear-gradient(135deg, #DC4D35 0%, #E8785F 100%)', color: '#FFFFFF', fontFamily: font,
        }}>
          <div style={{ position: 'absolute', right: -30, top: -30, width: 150, height: 150, borderRadius: '50%', background: 'rgba(255,255,255,0.12)' }} />
          <div style={{ position: 'relative', fontSize: 26, fontWeight: 800, lineHeight: 1.15 }}>
            Alipay и WeChat Pay
          </div>
          <div style={{ position: 'relative', fontSize: 14, lineHeight: 1.5, marginTop: 8, color: 'rgba(255,255,255,0.92)' }}>
            Оставьте заявку — менеджер свяжется с вами в Telegram и поможет с оплатой.
          </div>
        </div>
      </Section>

      {/* Form or success */}
      <Section>
        <Card padding="20px">
          {sent ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 10, padding: '8px 0' }}>
              <img src="/images/Agree.png" alt="" style={{ width: 56, height: 56 }} />
              <div style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font }}>Заявка №{sent.id} отправлена</div>
              <div style={{ fontSize: 13, color: '#6B7280', fontFamily: font, lineHeight: 1.5, maxWidth: 300 }}>
                Менеджер напишет вам в Telegram в ближайшее время. Подтверждение пришло в чат с ботом.
              </div>
              <Button onClick={() => setSent(null)} fullWidth style={{ marginTop: 6 }}>Новая заявка</Button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <label style={labelStyle}>Сервис</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {SERVICES.map((s) => {
                    const active = service === s.id
                    return (
                      <button
                        key={s.id}
                        onClick={() => setService(s.id)}
                        className="transition-transform duration-150 active:scale-95"
                        style={{
                          flex: 1, cursor: 'pointer', borderRadius: 14, padding: '12px 6px',
                          border: active ? '2px solid #DC4D35' : '2px solid transparent',
                          background: active ? '#FFF5F3' : '#F3F5F8',
                          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, fontFamily: font,
                        }}
                      >
                        <span style={{
                          width: 34, height: 34, borderRadius: 10, background: s.color, color: '#fff',
                          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17, fontWeight: 700,
                        }}>{s.mark}</span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>{s.label}</span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div>
                <label style={labelStyle}>Сумма</label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => setAmount(sanitizeAmount(e.target.value))}
                  placeholder="0"
                  style={{
                    width: '100%', boxSizing: 'border-box', border: 'none', outline: 'none', background: '#F3F5F8',
                    borderRadius: 12, padding: '14px 16px', fontSize: 20, fontWeight: 700, color: '#111827', fontFamily: font,
                  }}
                />
                <div style={{ display: 'flex', gap: 6, marginTop: 8, background: '#F3F5F8', borderRadius: 12, padding: 4 }}>
                  {CURRENCIES.map((c) => {
                    const active = currency === c.id
                    return (
                      <button
                        key={c.id}
                        onClick={() => setCurrency(c.id)}
                        style={{
                          flex: 1, border: 'none', cursor: 'pointer', borderRadius: 9, padding: '9px 0',
                          background: active ? '#FFFFFF' : 'transparent', color: active ? '#111827' : '#6B7280',
                          boxShadow: active ? '0 1px 3px rgba(17,24,39,0.12)' : 'none',
                          fontSize: 13, fontWeight: 600, fontFamily: font, transition: 'all 160ms ease',
                        }}
                      >
                        {c.label}
                      </button>
                    )
                  })}
                </div>
              </div>

              <div>
                <label style={labelStyle}>Примечание{service === 'other' ? '' : ' (необязательно)'}</label>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value.slice(0, 1000))}
                  rows={3}
                  placeholder={service === 'other'
                    ? 'Какой сервис нужен и что оплатить'
                    : 'Что нужно оплатить: магазин, сервис, ссылка на товар…'}
                  style={{
                    width: '100%', boxSizing: 'border-box', border: 'none', outline: 'none', background: '#F3F5F8',
                    borderRadius: 12, padding: '12px 16px', fontSize: 14, color: '#111827', fontFamily: font,
                    resize: 'none', lineHeight: 1.45,
                  }}
                />
              </div>

              {error && <div style={{ fontSize: 13, color: '#DC2626', fontFamily: font, lineHeight: 1.45 }}>{error}</div>}

              <Button onClick={submit} disabled={!canSubmit} fullWidth>
                {sending ? 'Отправляем…' : 'Оставить заявку'}
              </Button>
            </div>
          )}
        </Card>
      </Section>

      {/* My requests */}
      {requests.length > 0 && (
        <Section>
          <Card padding="20px">
            <div style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 4 }}>Мои заявки</div>
            {requests.map((r, idx) => {
              const st = STATUS_STYLE[r.status] || STATUS_STYLE.new
              const d = r.created_at ? new Date(r.created_at + (r.created_at.endsWith('Z') ? '' : 'Z')) : null
              return (
                <div key={r.id} style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0',
                  borderBottom: idx < requests.length - 1 ? '1px solid #F3F5F8' : 'none',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', fontFamily: font }}>
                      №{r.id} · {r.service_label}
                    </div>
                    <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, marginTop: 2 }}>
                      {Number(r.amount).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} {r.currency}
                      {d ? ` · ${d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}` : ''}
                    </div>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 600, borderRadius: 8, padding: '4px 9px', background: st.bg, color: st.color, fontFamily: font, flexShrink: 0 }}>
                    {r.status_label}
                  </span>
                </div>
              )
            })}
          </Card>
        </Section>
      )}
    </div>
  )
}
