import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../../api/client'
import Portal from './Portal'
import Button from './Button'
import KycModal from './KycModal'
import { useToast } from './ToastProvider'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif'
const display = (value) => Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })
const panel = { background: '#fff', borderRadius: 14, padding: 16 }

export default function CryptoPaymentModal({ isOpen, onClose, purpose, offerId = null, cardId = null, amountUsd = null, onPaid }) {
  const [payment, setPayment] = useState(null)
  const [networks, setNetworks] = useState([])
  const [network, setNetwork] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [qr, setQr] = useState('')
  const [showKyc, setShowKyc] = useState(false)
  const [now, setNow] = useState(Date.now())
  const requestId = useRef('')
  const generation = useRef(0)
  const { showToast } = useToast()

  const load = useCallback(async (fresh = false) => {
    if (fresh || !requestId.current) requestId.current = crypto.randomUUID()
    const run = ++generation.current
    setLoading(true); setError('')
    try {
      const [available, quote] = await Promise.all([
        api.crypto.networks(),
        api.crypto.quote({ request_id: requestId.current, purpose, offer_id: offerId, card_id: cardId,
          amount_usd: purpose === 'card_topup' ? String(amountUsd) : null }),
      ])
      if (generation.current !== run) return
      setNetworks(available.networks || [])
      setPayment(quote)
      setNetwork(quote.symbol_id || (available.networks?.find(n => n.symbol_id === 'USDTTRC20') || available.networks?.[0])?.symbol_id || '')
    } catch (e) {
      if (generation.current === run) setError(e.message || 'Не удалось подготовить оплату.')
    } finally { if (generation.current === run) setLoading(false) }
  }, [purpose, offerId, cardId, amountUsd])

  useEffect(() => {
    if (!isOpen) return
    requestId.current = ''; setPayment(null); setQr(''); setShowKyc(false)
    load()
    const clock = setInterval(() => setNow(Date.now()), 1000)
    return () => { generation.current++; clearInterval(clock) }
  }, [isOpen, load])

  const refresh = useCallback(async () => {
    if (!payment?.id) return
    const run = generation.current
    try {
      const updated = await api.crypto.payment(payment.id)
      if (generation.current === run) { setPayment(updated); setError('') }
    } catch (e) { if (generation.current === run) setError(e.message || 'Статус временно недоступен. Продолжаем проверку оплаты.') }
  }, [payment?.id])

  useEffect(() => {
    if (!isOpen || !payment?.id || ['quoted', 'error', 'cancelled'].includes(payment.status) || ['completed', 'failed'].includes(payment.fulfillment_status)) return
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [isOpen, payment?.id, payment?.status, payment?.fulfillment_status, refresh])

  useEffect(() => {
    let cancelled = false
    setQr('')
    if (payment?.address) {
      import('qrcode').then(({ default: QRCode }) => QRCode.toDataURL(payment.address, { width: 240, margin: 2, errorCorrectionLevel: 'M' }))
        .then(value => { if (!cancelled) setQr(value) }).catch(() => {})
    }
    return () => { cancelled = true }
  }, [payment?.address])

  async function create() {
    if (!payment?.id || !network || loading) return
    setLoading(true); setError('')
    try { setPayment(await api.crypto.createInvoice(payment.id, network)) }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  async function cancel() {
    if (!payment?.id || loading) return
    setLoading(true); setError('')
    try { setPayment(await api.crypto.cancel(payment.id)) }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  async function copy(value) {
    try { await navigator.clipboard.writeText(value); showToast({ title: 'Скопировано' }) }
    catch { showToast({ title: 'Не удалось скопировать. Выделите значение вручную.' }) }
  }

  if (!isOpen) return null
  const needsKyc = payment?.kyc_required && !payment?.kyc_verified
  const completed = payment?.fulfillment_status === 'completed'
  const review = payment?.status === 'review' || payment?.fulfillment_status === 'review'
  const paid = payment?.status === 'paid'
  const failed = payment?.fulfillment_status === 'failed'
  const closed = ['expired', 'cancelled', 'error'].includes(payment?.status)
  const seconds = Math.max(0, Math.ceil((Date.parse(payment?.expires_at) - now) / 1000))
  const timerText = Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : '—'

  return <>
    <Portal>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 1050 }} />
      <div role="dialog" aria-modal="true" aria-label="Оплата USDT" style={{ position: 'fixed', left: '50%', bottom: 0, transform: 'translateX(-50%)', width: '100%', maxWidth: 430, maxHeight: 'calc(100dvh - var(--tg-safe-top, 0px) - 20px)', overflowY: 'auto', zIndex: 1051, borderRadius: '24px 24px 0 0', background: '#F3F5F8', padding: '20px 20px calc(24px + var(--tg-safe-bottom, 0px))', boxSizing: 'border-box', fontFamily: font, color: '#111827' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <h2 style={{ fontSize: 23, fontWeight: 700, margin: 0 }}>Оплата USDT</h2>
          <button onClick={onClose} aria-label="Закрыть" style={{ border: 0, background: 'none', fontSize: 26, color: '#6B7280', cursor: 'pointer' }}>×</button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {payment && <div style={panel}>
            <div style={{ fontSize: 13, color: '#6B7280' }}>{purpose === 'card_issue' ? 'Выпуск карты' : 'На карту'}</div>
            <div style={{ fontSize: 25, fontWeight: 700, marginTop: 4 }}>{display(payment.total_usdt)} USDT</div>
            {purpose === 'card_topup'
              ? <p style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.5, margin: '8px 0 0' }}>На карту поступит ${display(payment.amount_usd)}. Комиссия за пополнение {Number(payment.fee_percent)}% включена в сумму. Комиссии СБП нет.</p>
              : <p style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.5, margin: '8px 0 0' }}>{Number(payment.price_rub).toLocaleString('ru-RU')} ₽ ÷ {Number(payment.base_rate).toFixed(4)} ₽/USDT. Курс Bitbanker зафиксирован для этого счёта, без комиссии СБП.{Number(payment.discount_percent) > 0 ? ` Скидка ${Number(payment.discount_percent)}% учтена.` : ''}</p>}
          </div>}
          {error && <div role="alert" style={{ ...panel, background: '#FEF2F2', color: '#B91C1C', fontSize: 13, lineHeight: 1.5 }}>{error}</div>}
          {!payment && (loading ? <p>Подготавливаем оплату…</p> : <Button onClick={() => load()}>Повторить</Button>)}
          {payment?.status === 'quoted' && <>
            <div style={panel}>
              <label htmlFor="crypto-network" style={{ display: 'block', fontWeight: 600, marginBottom: 10 }}>Сеть перевода</label>
              <select id="crypto-network" value={network} onChange={e => setNetwork(e.target.value)} style={{ width: '100%', padding: 12, borderRadius: 10, border: '1px solid #D1D5DB', background: '#fff', color: '#111827', fontSize: 15 }}>
                {networks.map(n => <option key={n.symbol_id} value={n.symbol_id}>USDT · {n.name} ({n.network})</option>)}
              </select>
              <p style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.5, marginBottom: 0 }}>Комиссия Cryptoway уже учтена — дополнительных сборов с нашей стороны нет. Комиссия вашего кошелька за отправку оплачивается отдельно.</p>
            </div>
            {needsKyc && <div style={{ ...panel, fontSize: 13, lineHeight: 1.5 }}>Для выпуска и пополнения этой карты пока требуется верификация личности. Оплата криптовалютой сама по себе это требование не отменяет.</div>}
            {needsKyc
              ? <Button onClick={() => setShowKyc(true)}>Пройти верификацию</Button>
              : <Button disabled={loading || !network || seconds <= 0} onClick={create}>{loading ? 'Создаём счёт…' : 'Получить адрес для оплаты'}</Button>}
            {seconds <= 0 && <Button variant="secondary" onClick={() => load(true)}>Обновить расчёт</Button>}
          </>}
          {payment?.status === 'creating' && <p style={{ ...panel, lineHeight: 1.5 }}>Проверяем создание счёта. Адрес появится автоматически — не создавайте повторную оплату.</p>}
          {payment?.address && !paid && !closed && !review && <>
            <div style={{ ...panel, textAlign: 'center' }}>
              <div style={{ fontWeight: 600 }}>USDT · {payment.network_name}</div>
              {qr && <img src={qr} alt={`Адрес USDT в сети ${payment.network_name}`} style={{ width: 220, maxWidth: '100%', height: 'auto', display: 'block', margin: '10px auto' }} />}
              <div style={{ fontSize: 13, lineHeight: 1.5, overflowWrap: 'anywhere', userSelect: 'text' }}>{payment.address}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                <Button variant="secondary" fullWidth onClick={() => copy(payment.address)}>Адрес</Button>
                <Button variant="secondary" fullWidth onClick={() => copy(String(Number(payment.total_usdt)))}>Сумма</Button>
              </div>
            </div>
            <div style={{ ...panel, background: '#FFFBEB', color: '#92400E', fontSize: 13, lineHeight: 1.6 }}>
              {seconds > 0 ? <>Отправьте ровно <b>{display(payment.total_usdt)} USDT</b> в сети <b>{payment.network_name}</b>. До окончания счёта: {timerText}. Сумма должна дойти целиком.</> : <>Время счёта истекло. Не отправляйте новый перевод — проверяем, успел ли поступить платёж.</>}
            </div>
            {Number(payment.received_usdt) > 0 && <p style={{ fontSize: 13 }}>Подтверждено: {display(payment.received_usdt)} USDT из {display(payment.total_usdt)}.</p>}
            <Button disabled={loading} onClick={refresh}>Проверить оплату</Button>
            {Number(payment.received_usdt) === 0 && <Button variant="secondary" disabled={loading} onClick={cancel}>Отменить счёт</Button>}
          </>}
          {paid && !completed && !failed && !review && <div style={{ ...panel, lineHeight: 1.6 }}><b>Оплата получена</b><br />{purpose === 'card_issue' ? 'Выпускаем карту.' : 'Пополняем карту.'} Обработка может занять до 5 минут. Можно закрыть это окно.</div>}
          {paid && Number(payment.overpaid_usdt) > 0 && <div style={{ ...panel, lineHeight: 1.5 }}>Переплата: {display(payment.overpaid_usdt)} USDT. <a href="https://t.me/exprontopay1" style={{ color: '#DC4D35' }}>Напишите в поддержку для возврата разницы.</a></div>}
          {completed && <><div style={panel}>{purpose === 'card_issue' ? 'Карта выпущена.' : 'Карта пополнена.'}</div><Button onClick={() => { onPaid?.(); onClose() }}>Готово</Button></>}
          {(review || failed) && <div style={{ ...panel, lineHeight: 1.6 }}>
            {payment.last_error || 'Платёж требует проверки поддержки.'}
            {payment.refund_credited && <p>Возврат: {display(payment.total_usdt)} $ на внутренний баланс.</p>}
            <a href="https://t.me/exprontopay1" style={{ display: 'block', marginTop: 12, color: '#DC4D35', fontWeight: 600 }}>Связаться с поддержкой</a>
          </div>}
          {closed && !review && <><div style={panel}>{payment.status === 'expired' ? 'Срок оплаты истёк.' : payment.status === 'cancelled' ? 'Счёт отменён.' : payment.last_error || 'Не удалось открыть оплату.'}</div><Button disabled={loading} onClick={() => load(true)}>Новый счёт</Button></>}
        </div>
      </div>
    </Portal>
    <KycModal isOpen={showKyc} onClose={() => setShowKyc(false)} onSuccess={() => { setShowKyc(false); refresh() }} />
  </>
}
