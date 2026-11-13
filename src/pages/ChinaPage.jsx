import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import api from '../api/client'
import Card from '../components/ui/Card'
import Section from '../components/ui/Section'
import Button from '../components/ui/Button'
import SbpPaymentModal from '../components/ui/SbpPaymentModal'
import CryptoPaymentModal from '../components/ui/CryptoPaymentModal'
import { BOTTOM_BAR_SPACE } from '../components/BottomBar'
import { metrikaGoal } from '../utils/metrika'
import { useAuth } from '../context/AuthContext'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

const SERVICES = [
  { id: 'alipay', label: 'Alipay', color: '#1677FF', mark: '支' },
  { id: 'wechat', label: 'WeChat Pay', color: '#07C160', mark: '微' },
]
const STATUS_STYLE = {
  awaiting_payment: { bg: '#F3F4F6', color: '#4B5563' },
  paid: { bg: '#EFF6FF', color: '#1D4ED8' },
  new: { bg: '#EFF6FF', color: '#1D4ED8' },
  in_progress: { bg: '#FFFBEB', color: '#B45309' },
  done: { bg: '#ECFDF5', color: '#047857' },
  rejected: { bg: '#FEF2F2', color: '#B91C1C' },
}

const labelStyle = { fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font, display: 'block', marginBottom: 10 }
const fieldStyle = {
  width: '100%', boxSizing: 'border-box', border: 'none', outline: 'none', background: '#F3F5F8',
  borderRadius: 12, padding: '13px 16px', fontSize: 15, color: '#111827', fontFamily: font,
}
const fmtRub = (v) => `${Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽`

function sanitizeAmount(value) {
  const cleaned = value.replace(',', '.').replace(/[^0-9.]/g, '')
  const [i = '', ...d] = cleaned.split('.')
  return d.length > 0 ? `${i}.${d.join('').slice(0, 2)}` : i
}

function Row({ label, value, muted, strong, top }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12,
      paddingTop: top ? 10 : 0, marginTop: top ? 4 : 0, borderTop: top ? '1px solid #EEF0F3' : 'none',
    }}>
      <span style={{ fontSize: strong ? 14 : 13, color: muted ? '#6B7280' : '#111827', fontWeight: strong ? 700 : 400, fontFamily: font }}>{label}</span>
      <span style={{ fontSize: strong ? 17 : 13, color: muted ? '#6B7280' : '#111827', fontWeight: strong ? 700 : 600, fontFamily: font, whiteSpace: 'nowrap' }}>{value}</span>
    </div>
  )
}

/**
 * "Китай" tab: pay to Alipay / WeChat Pay. The user enters the yuan amount
 * and the recipient, pays in rubles by SBP, and the team sends the yuan.
 */
export default function ChinaPage() {
  const { appConfig, user, fetchMe } = useAuth()
  const sbpOff = !!appConfig?.sbp_disabled
  const [paymentMethod, setPaymentMethod] = useState(() => appConfig?.sbp_disabled && appConfig?.cryptoway_enabled ? 'crypto' : 'sbp')
  const [service, setService] = useState('alipay')
  const [recipientType, setRecipientType] = useState('phone') // alipay: 'phone' | 'qr'; wechat: always 'qr'
  const [amount, setAmount] = useState('')
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')
  const [qrFile, setQrFile] = useState(null)
  const [qrPreview, setQrPreview] = useState('')
  const [note, setNote] = useState('')
  const [quote, setQuote] = useState(null)
  const [quoteError, setQuoteError] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [payRequest, setPayRequest] = useState(null)   // request being paid (SBP modal)
  const [paidRequest, setPaidRequest] = useState(null)
  const [requests, setRequests] = useState([])
  const fileRef = useRef(null)

  const effectiveType = service === 'wechat' ? 'qr' : recipientType

  const loadRequests = useCallback(async () => {
    try {
      const r = await api.services.myRequests()
      setRequests(r?.items || [])
    } catch { /* Keep the current history if the refresh fails. */ }
  }, [])
  useEffect(() => { loadRequests() }, [loadRequests])
  useEffect(() => {
    let cancelled = false
    setQuote(null); setQuoteError(false)
    api.services.rate(paymentMethod).then(value => { if (!cancelled) setQuote(value) }).catch(() => { if (!cancelled) setQuoteError(true) })
    return () => { cancelled = true }
  }, [paymentMethod])
  useEffect(() => () => { if (qrPreview) URL.revokeObjectURL(qrPreview) }, [qrPreview])

  const amountNum = parseFloat(amount) || 0
  const calc = useMemo(() => {
    if (quote?.payment_method && quote.payment_method !== paymentMethod) return null
    if (paymentMethod !== 'sbp') {
      if (!quote?.cny_per_usdt || amountNum <= 0) return null
      return { totalUsdt: Math.round((amountNum / Number(quote.cny_per_usdt) + Number.EPSILON) * 100) / 100 }
    }
    if (!quote?.rate || amountNum <= 0) return null
    const baseRub = Math.ceil(amountNum * quote.rate)
    const fee = baseRub < Number(quote.small_payment_threshold_rub) ? Number(quote.small_payment_fee_rub) : 0
    return { baseRub, fee, total: baseRub + fee }
  }, [quote, amountNum, paymentMethod])
  const minCny = Number(quote?.min_cny?.[service] || 0)
  const belowMin = minCny > 0 && amountNum > 0 && amountNum < minCny
  const limitError = belowMin
    ? `Минимальная сумма перевода в ${service === 'wechat' ? 'WeChat Pay' : 'Alipay'} — ${minCny.toLocaleString('ru-RU')} ¥.`
    : calc && paymentMethod === 'sbp'
    ? (calc.total < quote.min_transfer_rub
        ? `Минимальная сумма оплаты по СБП — ${fmtRub(quote.min_transfer_rub)}. Увеличьте сумму в юанях.`
        : calc.total > quote.max_transfer_rub
          ? `Максимальная сумма оплаты по СБП — ${fmtRub(quote.max_transfer_rub)}. Уменьшите сумму в юанях.`
          : '')
    : ''

  const nameOk = /^[A-Za-z][A-Za-z' .-]*\s+[A-Za-z' .-]*[A-Za-z.]$/.test(name.trim())
  const phoneOk = phone.replace(/[^\d]/g, '').length >= 7
  const recipientOk = effectiveType === 'qr' ? !!qrFile : (phoneOk && nameOk)
  const balanceEnough = paymentMethod !== 'balance' || (calc && Number(user?.balance || 0) >= calc.totalUsdt)
  const canSubmit = (paymentMethod === 'crypto' ? appConfig?.cryptoway_enabled : paymentMethod === 'balance' || !sbpOff) && calc && !limitError && balanceEnough && recipientOk && !sending
  const displayedRate = Number(quote?.payment_method === paymentMethod
    ? paymentMethod === 'sbp' ? quote.base_rate : quote.cny_per_usdt
    : null)
  const rateLabel = Number.isFinite(displayedRate) && displayedRate > 0
    ? paymentMethod === 'sbp'
      ? `1 ¥ = ${displayedRate.toFixed(2)} ₽`
      : `1 ${paymentMethod === 'balance' ? '$' : 'USDT'} = ${displayedRate.toLocaleString('ru-RU')} ¥`
    : null

  const pickFile = (e) => {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!f) return
    if (f.size > 6 * 1024 * 1024) { setError('Файл слишком большой (до 6 МБ)'); return }
    setError('')
    setQrFile(f)
    if (qrPreview) URL.revokeObjectURL(qrPreview)
    setQrPreview(URL.createObjectURL(f))
  }

  const submit = async () => {
    if (!canSubmit) return
    setSending(true)
    setError('')
    try {
      const res = await api.services.createRequest({
        service,
        amount: amountNum,
        paymentMethod,
        recipientType: effectiveType,
        phone: effectiveType === 'phone' ? phone : '',
        name: effectiveType === 'phone' ? name : '',
        note: note.trim(),
        qrFile: effectiveType === 'qr' ? qrFile : null,
      })
      metrikaGoal('china_request', { service })
      if (paymentMethod === 'balance') {
        const paid = await api.services.payBalance(res.id)
        setPaidRequest(paid)
        resetForm()
        fetchMe?.()
      } else setPayRequest(res)
      loadRequests()
    } catch (e) {
      setError(e.message || 'Не удалось создать заявку')
    } finally {
      setSending(false)
    }
  }

  const resetForm = () => {
    setAmount(''); setPhone(''); setName(''); setNote(''); setQrFile(null)
    if (qrPreview) URL.revokeObjectURL(qrPreview)
    setQrPreview('')
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
          <div style={{ position: 'relative', fontSize: 26, fontWeight: 800, lineHeight: 1.15 }}>Alipay и WeChat Pay</div>
          <div style={{ position: 'relative', fontSize: 14, lineHeight: 1.5, marginTop: 8, color: 'rgba(255,255,255,0.92)' }}>
            Переведём юани на Alipay или WeChat — оплата с баланса, по СБП или USDT.
          </div>
          {rateLabel && (
            <div style={{
              position: 'relative', display: 'inline-block', marginTop: 12, padding: '6px 12px', borderRadius: 10,
              background: 'rgba(255,255,255,0.2)', fontSize: 14, fontWeight: 700,
            }}>
              {rateLabel}
            </div>
          )}
        </div>
      </Section>

      <Section>
        <Card padding="20px">
          {paidRequest ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 10, padding: '8px 0' }}>
              <img src="/images/Agree.png" alt="" style={{ width: 56, height: 56 }} />
              <div style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font }}>Заявка №{paidRequest.id} оплачена</div>
              <div style={{ fontSize: 13, color: '#6B7280', fontFamily: font, lineHeight: 1.5, maxWidth: 300 }}>
                Переводим {Number(paidRequest.amount).toLocaleString('ru-RU')} ¥ получателю. Если что-то пойдёт не так, менеджер напишет вам в Telegram.
              </div>
              <Button onClick={() => setPaidRequest(null)} fullWidth style={{ marginTop: 6 }}>Новый перевод</Button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <label style={labelStyle}>Способ оплаты</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[{ id: 'sbp', label: 'СБП', disabled: sbpOff }, ...(appConfig?.cryptoway_enabled ? [{ id: 'crypto', label: 'USDT', disabled: false }] : []), { id: 'balance', label: 'С баланса', disabled: false }].map(method => (
                    <button key={method.id} disabled={method.disabled} onClick={() => setPaymentMethod(method.id)}
                      style={{ flex: 1, borderRadius: 12, padding: 12, border: paymentMethod === method.id ? '2px solid #DC4D35' : '2px solid transparent', background: '#F3F5F8', color: '#111827', fontFamily: font, fontWeight: 600, opacity: method.disabled ? .45 : 1, cursor: 'pointer' }}>
                      {method.label}
                    </button>
                  ))}
                </div>
              </div>
              {paymentMethod === 'balance' && <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.5 }}>
                Доступно ${Number(user?.balance || 0).toFixed(2)}. Оплата без NeuroVision.
              </div>}
              {/* Service */}
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

              {/* Amount in yuan */}
              <div>
                <label style={labelStyle}>Сумма перевода</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={amount}
                    onChange={(e) => setAmount(sanitizeAmount(e.target.value))}
                    placeholder="0"
                    style={{ ...fieldStyle, fontSize: 20, fontWeight: 700, paddingRight: 44 }}
                  />
                  <span style={{ position: 'absolute', right: 16, top: '50%', transform: 'translateY(-50%)', fontSize: 20, fontWeight: 700, color: '#6B7280', fontFamily: font }}>¥</span>
                </div>
                {minCny > 0 && (
                  <div style={{ fontSize: 12, color: belowMin ? '#DC2626' : '#9CA3AF', fontFamily: font, marginTop: 6 }}>
                    Минимум {minCny.toLocaleString('ru-RU')} ¥
                  </div>
                )}
              </div>

              {/* Recipient */}
              <div>
                <label style={labelStyle}>Получатель</label>
                {service === 'alipay' && (
                  <div style={{ display: 'flex', gap: 6, marginBottom: 10, background: '#F3F5F8', borderRadius: 12, padding: 4 }}>
                    {[{ id: 'phone', label: 'Телефон и имя' }, { id: 'qr', label: 'QR-код' }].map((t) => {
                      const active = recipientType === t.id
                      return (
                        <button
                          key={t.id}
                          onClick={() => setRecipientType(t.id)}
                          style={{
                            flex: 1, border: 'none', cursor: 'pointer', borderRadius: 9, padding: '9px 0',
                            background: active ? '#FFFFFF' : 'transparent', color: active ? '#111827' : '#6B7280',
                            boxShadow: active ? '0 1px 3px rgba(17,24,39,0.12)' : 'none',
                            fontSize: 13, fontWeight: 600, fontFamily: font, transition: 'all 160ms ease',
                          }}
                        >
                          {t.label}
                        </button>
                      )
                    })}
                  </div>
                )}

                {effectiveType === 'phone' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <input
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value.replace(/[^\d+\s()-]/g, '').slice(0, 20))}
                      placeholder="Номер телефона в Alipay, например +86 138 0000 0000"
                      style={fieldStyle}
                    />
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value.replace(/[^A-Za-z' .-]/g, '').toUpperCase().slice(0, 100))}
                      placeholder="Фамилия и имя латиницей, как в Alipay"
                      autoCapitalize="characters"
                      style={fieldStyle}
                    />
                    {name && !nameOk && (
                      <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font }}>Нужны фамилия и имя через пробел, латиницей: ZHANG WEI</div>
                    )}
                  </div>
                ) : (
                  <div>
                    <input ref={fileRef} type="file" accept="image/*" onChange={pickFile} style={{ display: 'none' }} />
                    {qrPreview ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#F3F5F8', borderRadius: 12, padding: 10 }}>
                        <img src={qrPreview} alt="" style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 8, background: '#fff' }} />
                        <div style={{ flex: 1, minWidth: 0, fontSize: 13, color: '#111827', fontFamily: font }}>
                          QR-код загружен
                          <div style={{ fontSize: 12, color: '#6B7280', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{qrFile?.name}</div>
                        </div>
                        <button onClick={() => fileRef.current?.click()} style={{ border: 'none', background: '#FFFFFF', color: '#DC4D35', borderRadius: 10, padding: '8px 12px', fontSize: 13, fontWeight: 600, fontFamily: font, cursor: 'pointer' }}>
                          Заменить
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => fileRef.current?.click()}
                        className="transition-transform duration-150 active:scale-[0.98]"
                        style={{
                          width: '100%', cursor: 'pointer', borderRadius: 12, padding: '18px 12px',
                          border: '1.5px dashed #D1D5DB', background: '#FAFAFB',
                          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, fontFamily: font,
                        }}
                      >
                        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#DC4D35" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" />
                          <path d="M14 14h3v3M21 14v.01M14 21h7v-4" />
                        </svg>
                        <span style={{ fontSize: 14, fontWeight: 600, color: '#111827' }}>Загрузить QR-код для получения</span>
                        <span style={{ fontSize: 12, color: '#6B7280' }}>
                          Скриншот QR «Получить» из {service === 'wechat' ? 'WeChat' : 'Alipay'}
                        </span>
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Note */}
              <div>
                <label style={labelStyle}>Примечание (необязательно)</label>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value.slice(0, 1000))}
                  rows={2}
                  placeholder="Комментарий к переводу"
                  style={{ ...fieldStyle, fontSize: 14, resize: 'none', lineHeight: 1.45 }}
                />
              </div>

              {/* Price breakdown */}
              {amountNum > 0 && (
                <div style={{ background: '#F9FAFB', borderRadius: 12, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {quoteError || !quote || !calc ? (
                    <div style={{ fontSize: 13, color: quoteError ? '#DC2626' : '#6B7280', fontFamily: font }}>
                      {quoteError ? 'Курс временно недоступен. Попробуйте позже.' : 'Загружаем курс…'}
                    </div>
                  ) : paymentMethod !== 'sbp' ? (
                    <>
                      <Row label={paymentMethod === 'balance' ? 'CNY/USD' : 'CNY/USDT'} value={`1 ${paymentMethod === 'balance' ? 'USD' : 'USDT'} = ${Number(quote.cny_per_usdt).toLocaleString('ru-RU')} ¥`} />
                      <Row label={paymentMethod === 'balance' ? 'Списание с баланса' : `${amountNum.toLocaleString('ru-RU')} ¥ ÷ ${Number(quote.cny_per_usdt).toLocaleString('ru-RU')}`} value={paymentMethod === 'balance' ? `$${Number(calc.totalUsdt).toFixed(2)}` : `${Number(calc.totalUsdt).toFixed(2)} USDT`} strong top />
                      {!balanceEnough && <div style={{ color: '#B91C1C', fontSize: 13 }}>Недостаточно средств. Пополните внутренний баланс в профиле.</div>}
                    </>
                  ) : (
                    <>
                      <Row label="Курс юаня" value={`${Number(quote.base_rate).toFixed(2)} ₽`} />
                      {(quote.fees || []).filter((f) => Number(f.percent) > 0).map((f) => (
                        <Row key={f.label} label={f.label} value={`+${Number(f.percent).toLocaleString('ru-RU')}%`} muted />
                      ))}
                      <Row label={`${amountNum.toLocaleString('ru-RU')} ¥ по курсу ${Number(quote.rate).toFixed(2)} ₽`} value={fmtRub(calc.baseRub)} top />
                      {calc.fee > 0 && (
                        <Row label={`Комиссия платёжной системы за платёж до ${Number(quote.small_payment_threshold_rub).toLocaleString('ru-RU')} ₽`} value={`+${fmtRub(calc.fee)}`} muted />
                      )}
                      <Row label="К оплате по СБП" value={fmtRub(calc.total)} strong top />
                      {limitError && <div style={{ fontSize: 12, color: '#DC2626', fontFamily: font, lineHeight: 1.45 }}>{limitError}</div>}
                    </>
                  )}
                </div>
              )}

              {error && <div style={{ fontSize: 13, color: '#DC2626', fontFamily: font, lineHeight: 1.45 }}>{error}</div>}
              {sbpOff && paymentMethod === 'sbp' && (
                <div style={{ background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 12, padding: '12px 14px', fontSize: 13, color: '#991B1B', fontFamily: font, lineHeight: 1.5 }}>
                  {appConfig.sbp_disabled_text}
                </div>
              )}

              <Button onClick={submit} disabled={!canSubmit} fullWidth>
                {sending ? 'Обрабатываем…' : calc ? paymentMethod === 'balance' ? `Оплатить $${Number(calc.totalUsdt).toFixed(2)} с баланса` : `Оплатить ${paymentMethod === 'crypto' ? `${Number(calc.totalUsdt).toFixed(2)} USDT` : fmtRub(calc.total)}` : 'Перейти к оплате'}
              </Button>
            </div>
          )}
        </Card>
      </Section>

      {/* My requests */}
      {requests.length > 0 && (
        <Section>
          <Card padding="20px">
            <div style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, marginBottom: 4 }}>Мои переводы</div>
            {requests.map((r, idx) => {
              const st = STATUS_STYLE[r.status] || STATUS_STYLE.paid
              const d = r.created_at ? new Date(r.created_at + (r.created_at.endsWith('Z') ? '' : 'Z')) : null
              const canPay = r.status === 'awaiting_payment' && d && (Date.now() - d.getTime() < 2 * 3600 * 1000)
              return (
                <div key={r.id} style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0',
                  borderBottom: idx < requests.length - 1 ? '1px solid #F3F5F8' : 'none',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', fontFamily: font }}>
                      №{r.id} · {r.service_label} · {Number(r.amount).toLocaleString('ru-RU')} ¥
                    </div>
                    <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, marginTop: 2 }}>
                      {r.payment_method === 'balance' ? `$${Number(r.amount_usd).toFixed(2)} с баланса` : r.payment_method === 'crypto' ? `${Number(r.amount_usdt).toFixed(2)} USDT` : r.amount_rub ? fmtRub(r.amount_rub) : ''}
                      {d ? ` · ${d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}` : ''}
                    </div>
                  </div>
                  {canPay ? (
                    <button
                      disabled={sending}
                      onClick={async () => {
                        if (r.payment_method !== 'balance') { setPayRequest(r); return }
                        setSending(true); setError('')
                        try { setPaidRequest(await api.services.payBalance(r.id)); resetForm(); fetchMe?.(); loadRequests() }
                        catch (e) { setError(e.message || 'Не удалось оплатить заявку') }
                        finally { setSending(false) }
                      }}
                      style={{ border: 'none', background: '#DC4D35', color: '#fff', borderRadius: 10, padding: '7px 12px', fontSize: 13, fontWeight: 600, fontFamily: font, cursor: 'pointer', flexShrink: 0 }}
                    >
                      Оплатить
                    </button>
                  ) : (
                    <span style={{ fontSize: 12, fontWeight: 600, borderRadius: 8, padding: '4px 9px', background: st.bg, color: st.color, fontFamily: font, flexShrink: 0 }}>
                      {r.status === 'awaiting_payment' ? 'Не оплачена' : r.status_label}
                    </span>
                  )}
                </div>
              )
            })}
          </Card>
        </Section>
      )}

      <SbpPaymentModal
        isOpen={!!payRequest && payRequest.payment_method === 'sbp'}
        onClose={() => { setPayRequest(null); loadRequests() }}
        amountRub={payRequest?.amount_rub || 0}
        purpose="china_payment"
        serviceRequestId={payRequest?.id || null}
        skipSuccessScreen={true}
        onPaid={() => {
          const done = payRequest
          setPayRequest(null)
          setPaidRequest(done)
          resetForm()
          loadRequests()
          setTimeout(loadRequests, 4000)
        }}
      />
      <CryptoPaymentModal
        isOpen={!!payRequest && payRequest.payment_method === 'crypto'}
        onClose={() => { setPayRequest(null); loadRequests() }}
        purpose="china_payment"
        serviceRequestId={payRequest?.id || null}
        onPaid={() => { setPaidRequest(payRequest); setPayRequest(null); resetForm(); loadRequests(); setTimeout(loadRequests, 4000) }}
      />
    </div>
  )
}
