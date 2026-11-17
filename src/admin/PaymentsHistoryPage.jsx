import { useEffect, useRef, useState } from 'react'
import adminApi from './api'

const sources = { sbp: 'СБП', crypto: 'USDT', order: 'Ордер по карте', balance: 'Внутренний баланс', china: 'Alipay / WeChat', legacy: 'Заявка на пополнение' }
const purposes = { card_issue: 'Выпуск карты', card_topup: 'Пополнение карты', balance_deposit: 'Пополнение баланса', deposit: 'Пополнение баланса', crypto_deposit: 'Пополнение баланса USDT', china_payment: 'Alipay / WeChat', refund: 'Возврат', referral: 'Реферальный бонус', admin_adjust: 'Корректировка баланса' }
const statuses = { captured: 'Оплачено', authorized: 'Авторизовано', paid: 'Оплачено', completed: 'Выполнено', confirmed: 'Подтверждено', active: 'Ожидает оплаты', quoted: 'Расчёт', initiated: 'Создано', pending: 'Ожидание', processing: 'В обработке', not_started: 'Не начато', review: 'Требует проверки', failed: 'Ошибка', error: 'Ошибка', creation_unknown: 'Создание проверяется', declined: 'Отклонено', cancelled: 'Отменено', canceled: 'Отменено', expired: 'Истёк срок', unknown: 'Неизвестно', awaiting_payment: 'Ожидает оплаты', new: 'Новая', in_progress: 'В работе', done: 'Выполнено', rejected: 'Отклонено', missing_order: 'Ордер ещё не создан', missing_booking: 'Зачисление не записано', refunded: 'Возвращено' }
const control = { padding: '9px 12px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', fontSize: 13, minHeight: 38 }
const button = { ...control, cursor: 'pointer', color: '#3730a3', fontWeight: 600 }
const emptyFilters = { search: '', source: '', status: '', purpose: '', from: '', to: '' }
const dateFormatter = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
const date = value => value ? dateFormatter.format(new Date(value)) : 'Дата не сохранена'
const title = row => row.source === 'china' ? (row.description === 'wechat' ? 'WeChat Pay' : 'Alipay') : purposes[row.purpose] || row.purpose || '—'
const reference = row => `${sources[row.source]} #${row.id}`
const amount = (value, currency) => value == null ? '—' : `${Number(value).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: currency === 'USDT' ? 8 : 2 })} ${currency}`

function Status({ value }) {
  if (!value) return <span style={{ color: '#9ca3af' }}>—</span>
  const color = ['paid', 'captured', 'completed', 'confirmed', 'done'].includes(value) ? '#15803d' : ['error', 'failed', 'review', 'declined', 'rejected', 'missing_order', 'missing_booking'].includes(value) ? '#b91c1c' : '#92400e'
  return <span title={value} style={{ color, background: color + '12', padding: '4px 8px', borderRadius: 8, display: 'inline-block', fontSize: 12 }}>{statuses[value] || value}</span>
}

function EventTable({ rows, onOpen, onUserClick }) {
  const cell = { padding: '12px 14px', textAlign: 'left', borderBottom: '1px solid #f3f4f6', verticalAlign: 'top' }
  return <div className="payment-events-scroll" style={{ overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: 12, background: '#fff' }}>
    <table className="payment-events-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead><tr>{['Запись', 'Пользователь', 'Назначение', 'Сумма', 'Комиссия / стоимость выпуска', 'Статус записи', 'Исполнение', 'Дата, МСК', ''].map(label => <th key={label} style={{ ...cell, color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{label}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.key}>
        <td data-label="Запись" style={cell}><button style={{ border: 0, padding: 0, background: 'none', color: '#4338ca', cursor: 'pointer', textAlign: 'left', fontWeight: 600 }} onClick={() => onOpen(row)}>{reference(row)}</button></td>
        <td data-label="Пользователь" style={cell}><button style={{ border: 0, padding: 0, background: 'none', cursor: 'pointer', color: '#4338ca', textAlign: 'left' }} onClick={() => onUserClick?.(row.user_id)}>{row.username ? `@${row.username}` : `Пользователь #${row.user_id}`}</button><div style={{ color: '#9ca3af', fontSize: 11, marginTop: 4 }}>ID {row.user_id}</div></td>
        <td data-label="Назначение" style={cell}>{title(row)}</td>
        <td data-label="Сумма" style={{ ...cell, whiteSpace: 'nowrap', color: row.source === 'balance' ? Number(row.amount) < 0 ? '#b91c1c' : '#15803d' : '#111827' }}>{row.source === 'balance' && Number(row.amount) > 0 ? '+' : ''}{amount(row.amount, row.currency)}</td>
        <td data-label="Комиссия / стоимость выпуска" style={cell}>{row.fee != null && Number(row.fee) !== 0 ? amount(row.fee, row.currency) : '—'}</td>
        <td data-label="Статус записи" style={cell}><Status value={row.status} /></td>
        <td data-label="Исполнение" style={cell}><Status value={row.execution_status} /></td>
        <td data-label="Дата, МСК" style={{ ...cell, whiteSpace: 'nowrap' }}>{date(row.created_at)}</td>
        <td style={cell}><button style={button} onClick={() => onOpen(row)}>Подробнее</button></td>
      </tr>)}</tbody>
    </table>
  </div>
}

function PaymentDetail({ selection, onClose, onOpen, onUserClick }) {
  const dialog = useRef(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    dialog.current.showModal()
    return () => dialog.current?.close()
  }, [])
  useEffect(() => {
    let cancelled = false
    setData(null); setError('')
    adminApi.payments.detail(selection.source, selection.id).then(value => { if (!cancelled) setData(value) }).catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [selection.source, selection.id])
  const row = data?.item
  return <dialog className="payment-detail" ref={dialog} aria-labelledby="payment-detail-title" onCancel={e => { e.preventDefault(); onClose() }} onClick={e => { if (e.target === e.currentTarget) onClose() }} style={{ width: 'min(1200px, 94vw)', maxHeight: '88vh', boxSizing: 'border-box', border: 0, borderRadius: 16, padding: 24, color: '#111827' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}><h3 id="payment-detail-title" style={{ margin: 0 }}>{reference(selection)}</h3><button style={button} onClick={onClose} autoFocus>Закрыть</button></div>
    {error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}
    {!data && !error && <p role="status">Загрузка подробностей…</p>}
    {row && <>
      <dl style={{ display: 'grid', gridTemplateColumns: 'minmax(140px, 230px) minmax(0, 1fr)', gap: '12px 20px', fontSize: 14 }}>
        {[
          ['Пользователь', `${row.username ? '@' + row.username : '—'} · ID ${row.user_id}`],
          ['Назначение', title(row)], ['Сумма', amount(row.amount, row.currency)],
          ['Комиссия / стоимость выпуска', row.fee != null ? amount(row.fee, row.currency) : '—'],
          ['Статус записи', <Status value={row.status} />], ['Исполнение', <Status value={row.execution_status} />],
          ['Создано, МСК', date(row.created_at)], ['Оплачено, МСК', row.paid_at ? date(row.paid_at) : 'Время оплаты отдельно не сохранено'],
          ['ID у провайдера', row.provider_id || '—'], ['Описание', row.description || '—'],
          ...(row.recover_attempts != null ? [['Повторные попытки', row.recover_attempts === 4 ? 'Восстановление завершено' : String(row.recover_attempts)], ['Последний повтор, МСК', row.last_recover_at ? date(row.last_recover_at) : '—']] : []),
          ...(row.balance_after != null ? [['Баланс после операции', amount(row.balance_after, 'USD')]] : []),
          ...(row.last_error ? [['Причина / комментарий', row.last_error]] : []),
        ].map(([label, value]) => <div key={label} style={{ display: 'contents' }}><dt style={{ color: '#6b7280' }}>{label}</dt><dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{value}</dd></div>)}
      </dl>
      <h4 style={{ marginBottom: 10 }}>Связанные записи ({data.related.length})</h4>
      {data.related.length ? <EventTable rows={data.related} onOpen={onOpen} onUserClick={id => { onClose(); onUserClick?.(id) }} /> : <p style={{ color: '#6b7280', fontSize: 13 }}>Связанных записей нет. Оплата сохраняется в истории, даже если ордер ещё не создан.</p>}
    </>}
  </dialog>
}

export default function PaymentsHistoryPage({ onUserClick }) {
  const [filters, setFilters] = useState(emptyFilters)
  const [page, setPage] = useState(0)
  const [size, setSize] = useState(50)
  const [refresh, setRefresh] = useState(0)
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selection, setSelection] = useState(null)
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')
    const timer = setTimeout(() => {
      const params = { search: filters.search, source: filters.source, status: filters.status, purpose: filters.purpose, limit: size, offset: page * size }
      if (filters.from) params.date_from = new Date(`${filters.from}T00:00:00+03:00`).toISOString()
      if (filters.to) params.date_to = new Date(new Date(`${filters.to}T00:00:00+03:00`).getTime() + 86400000).toISOString()
      adminApi.payments.list(params).then(value => {
        if (!cancelled) { setData(value); if (page && page * size >= value.total) setPage(Math.max(0, Math.ceil(value.total / size) - 1)) }
      }).catch(e => { if (!cancelled) setError(e.message) }).finally(() => { if (!cancelled) setLoading(false) })
    }, 250)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [filters, page, size, refresh])
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === 'visible') setRefresh(x => x + 1) }, 30000)
    return () => clearInterval(timer)
  }, [])
  const change = (key, value) => { setFilters(current => ({ ...current, [key]: value })); setPage(0) }
  const pages = Math.max(1, Math.ceil(data.total / size))
  return <div>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}><h2 style={{ margin: '0 0 12px', fontSize: 22 }}>Платежи</h2><button style={button} disabled={loading} onClick={() => setRefresh(x => x + 1)}>Обновить</button></div>
    <p style={{ margin: '0 0 16px', color: '#6b7280', fontSize: 13, lineHeight: 1.6 }}>Вся история: оплаты СБП и USDT, ордера по картам, внутренний баланс и Alipay / WeChat. Связанные записи показывают этапы одной операции — их суммы не складываются. Даты указаны по Москве.</p>
    <div className="payments-filters" style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16, alignItems: 'end' }}>
      <label style={{ display: 'grid', gap: 5, fontSize: 12, color: '#6b7280', flex: '1 1 260px' }}>Поиск<input style={control} aria-label="Поиск платежей" placeholder="Username, ID записи / пользователя, Telegram ID…" value={filters.search} onChange={e => change('search', e.target.value)} /></label>
      <label style={{ display: 'grid', gap: 5, fontSize: 12, color: '#6b7280' }}>Источник<select aria-label="Источник" style={control} value={filters.source} onChange={e => change('source', e.target.value)}><option value="">Все источники</option>{Object.entries(sources).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label style={{ display: 'grid', gap: 5, fontSize: 12, color: '#6b7280' }}>Назначение<select aria-label="Назначение" style={control} value={filters.purpose} onChange={e => change('purpose', e.target.value)}><option value="">Все назначения</option>{Object.entries(purposes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label style={{ display: 'grid', gap: 5, fontSize: 12, color: '#6b7280' }}>Статус<select aria-label="Статус" style={control} value={filters.status} onChange={e => change('status', e.target.value)}><option value="">Все статусы</option>{Object.entries(statuses).filter(([key]) => !['missing_order', 'missing_booking'].includes(key)).map(([key, label]) => <option key={key} value={key}>{label} ({key})</option>)}</select></label>
      <label style={{ display: 'grid', gap: 5, fontSize: 12, color: '#6b7280' }}>С даты<input style={control} type="date" value={filters.from} onChange={e => change('from', e.target.value)} /></label>
      <label style={{ display: 'grid', gap: 5, fontSize: 12, color: '#6b7280' }}>По дату<input style={control} type="date" value={filters.to} onChange={e => change('to', e.target.value)} /></label>
      <button style={button} onClick={() => { setFilters(emptyFilters); setPage(0) }}>Сбросить</button>
    </div>
    {error && <p role="alert" style={{ padding: 12, background: '#fef2f2', borderRadius: 8, color: '#b91c1c' }}>Не удалось загрузить историю: {error}</p>}
    <div role="status" style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>{loading ? 'Обновление истории…' : data.total ? `Записи ${page * size + 1}–${Math.min((page + 1) * size, data.total)} из ${data.total}` : 'По выбранным фильтрам записей нет'}</div>
    {!error && <div aria-busy={loading} style={{ opacity: loading ? 0.6 : 1 }}><EventTable rows={data.items} onOpen={setSelection} onUserClick={onUserClick} /></div>}
    <div className="payments-pagination" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginTop: 14 }}>
      <button style={button} disabled={loading || page === 0} onClick={() => setPage(0)}>В начало</button>
      <button style={button} disabled={loading || page === 0} onClick={() => setPage(x => x - 1)}>← Назад</button>
      <label style={{ fontSize: 13, color: '#6b7280' }}>Страница <input style={{ ...control, width: 70 }} type="number" min="1" max={pages} value={page + 1} onChange={e => { const value = Number(e.target.value); if (value >= 1 && value <= pages) setPage(value - 1) }} /> из {pages}</label>
      <button style={button} disabled={loading || page + 1 >= pages} onClick={() => setPage(x => x + 1)}>Далее →</button>
      <button style={button} disabled={loading || page + 1 >= pages} onClick={() => setPage(pages - 1)}>В конец</button>
      <label style={{ fontSize: 13, color: '#6b7280', marginLeft: 'auto' }}>На странице <select style={control} value={size} onChange={e => { setSize(Number(e.target.value)); setPage(0) }}>{[25, 50, 100, 200].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
    </div>
    {selection && <PaymentDetail selection={selection} onClose={() => setSelection(null)} onOpen={setSelection} onUserClick={onUserClick} />}
  </div>
}
