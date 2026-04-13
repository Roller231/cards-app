import { useCallback, useEffect, useState } from 'react'
import adminApi, { clearAdminToken, getAdminToken, setAdminToken } from './api'

/* ================================================================
   ADMIN SPA  –  /admin
   Pages: Login, Dashboard, Users, UserDetail, Cards, Payments, Analytics, Settings
   ================================================================ */

// ─────────── tiny helpers ───────────
const fmt = (n, d = 2) => Number(n || 0).toFixed(d)
const badge = (text, color) => (
  <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: 99, fontSize: 12, fontWeight: 600, background: color + '22', color }}>{text}</span>
)
const statusColor = { active: '#22c55e', inactive: '#ef4444', pending: '#f59e0b', completed: '#22c55e', failed: '#ef4444', processing: '#3b82f6', expired: '#6b7280' }
const Btn = ({ children, onClick, variant = 'primary', small, disabled, style: sx }) => {
  const base = { border: 'none', borderRadius: 8, cursor: disabled ? 'default' : 'pointer', fontWeight: 600, fontSize: small ? 12 : 14, padding: small ? '4px 12px' : '8px 18px', opacity: disabled ? 0.5 : 1, transition: 'all .15s' }
  const colors = variant === 'danger' ? { background: '#ef4444', color: '#fff' } : variant === 'ghost' ? { background: 'transparent', color: '#6366f1' } : { background: '#6366f1', color: '#fff' }
  return <button style={{ ...base, ...colors, ...sx }} onClick={disabled ? undefined : onClick}>{children}</button>
}
const Input = ({ label, ...props }) => (
  <div style={{ marginBottom: 12 }}>
    {label && <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4, color: '#374151' }}>{label}</label>}
    <input style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14, boxSizing: 'border-box', outline: 'none' }} {...props} />
  </div>
)
const Card = ({ title, value, sub, color = '#6366f1' }) => (
  <div style={{ background: '#fff', borderRadius: 14, padding: 20, flex: '1 1 200px', minWidth: 180, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
    <div style={{ fontSize: 13, color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>{title}</div>
    <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
    {sub && <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{sub}</div>}
  </div>
)
const Table = ({ columns, rows, onRowClick }) => (
  <div style={{ overflowX: 'auto', borderRadius: 12, border: '1px solid #e5e7eb', background: '#fff' }}>
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr>{columns.map((c, i) => <th key={i} style={{ textAlign: 'left', padding: '10px 14px', borderBottom: '1px solid #e5e7eb', color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap' }}>{c.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.length === 0 && <tr><td colSpan={columns.length} style={{ padding: 30, textAlign: 'center', color: '#9ca3af' }}>Нет данных</td></tr>}
        {rows.map((row, ri) => (
          <tr key={ri} onClick={() => onRowClick?.(row)} style={{ cursor: onRowClick ? 'pointer' : 'default', borderBottom: '1px solid #f3f4f6' }}
            onMouseEnter={e => e.currentTarget.style.background = '#f9fafb'} onMouseLeave={e => e.currentTarget.style.background = ''}>
            {columns.map((c, ci) => <td key={ci} style={{ padding: '10px 14px', whiteSpace: 'nowrap' }}>{c.render ? c.render(row) : row[c.key]}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

// ─────────── LOGIN ───────────
function LoginPage({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault(); setError(''); setLoading(true)
    try { const r = await adminApi.login(email, password); setAdminToken(r.access_token); onLogin() }
    catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#f3f4f6' }}>
      <form onSubmit={submit} style={{ background: '#fff', padding: 40, borderRadius: 16, width: 380, boxShadow: '0 4px 20px rgba(0,0,0,.08)' }}>
        <h1 style={{ margin: '0 0 8px', fontSize: 24, fontWeight: 700, color: '#111827' }}>Админ-панель</h1>
        <p style={{ margin: '0 0 24px', fontSize: 14, color: '#6b7280' }}>Войдите для управления системой</p>
        {error && <div style={{ background: '#fef2f2', color: '#dc2626', padding: '8px 12px', borderRadius: 8, fontSize: 13, marginBottom: 16 }}>{error}</div>}
        <Input label="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
        <Input label="Пароль" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
        <button type="submit" disabled={loading}
          style={{ width: '100%', marginTop: 8, padding: '12px 0', border: 'none', borderRadius: 8, background: '#6366f1', color: '#fff', fontWeight: 600, fontSize: 14, cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.6 : 1 }}>
          {loading ? 'Вход...' : 'Войти'}
        </button>
      </form>
    </div>
  )
}

// ─────────── SIDEBAR ───────────
const NAV = [
  { id: 'dashboard', icon: '📊', label: 'Дашборд' },
  { id: 'users', icon: '👥', label: 'Пользователи' },
  { id: 'cards', icon: '💳', label: 'Карты' },
  { id: 'payments', icon: '💰', label: 'Платежи' },
  { id: 'analytics', icon: '📈', label: 'Аналитика' },
  { id: 'bot', icon: '🤖', label: 'Telegram Бот' },
  { id: 'settings', icon: '⚙️', label: 'Настройки' },
]
function Sidebar({ page, setPage }) {
  return (
    <div style={{ width: 240, background: '#1e1b4b', color: '#fff', display: 'flex', flexDirection: 'column', minHeight: '100vh', flexShrink: 0 }}>
      <div style={{ padding: '24px 20px 16px', fontSize: 18, fontWeight: 700, letterSpacing: -0.5 }}>🛡️ Admin Panel</div>
      <nav style={{ flex: 1, padding: '0 8px' }}>
        {NAV.map(n => (
          <div key={n.id} onClick={() => setPage(n.id)}
            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 10, marginBottom: 2, cursor: 'pointer',
              background: page === n.id ? 'rgba(255,255,255,.15)' : 'transparent', fontWeight: page === n.id ? 600 : 400, fontSize: 14, transition: 'all .15s' }}>
            <span style={{ fontSize: 16 }}>{n.icon}</span>{n.label}
          </div>
        ))}
      </nav>
      <div style={{ padding: 16 }}>
        <Btn variant="ghost" small onClick={() => { clearAdminToken(); window.location.reload() }} style={{ color: '#c7d2fe', width: '100%' }}>
          Выйти
        </Btn>
      </div>
    </div>
  )
}

// ─────────── DASHBOARD ───────────
function DashboardPage() {
  const [data, setData] = useState(null)
  useEffect(() => { adminApi.dashboard().then(setData).catch(() => {}) }, [])
  if (!data) return <p>Загрузка...</p>
  const cp = data.crypto_payments || {}
  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 22, fontWeight: 700 }}>Дашборд</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <Card title="Пользователи" value={data.users_count} sub={`Активных: ${data.active_users} / Забанено: ${data.banned_users}`} />
        <Card title="Карты" value={data.cards_count} color="#0ea5e9" />
        <Card title="Ордера" value={data.orders_count} color="#f59e0b" />
        <Card title="Выручка (fee)" value={`$${fmt(data.total_revenue)}`} color="#22c55e" sub={`Объём: $${fmt(data.total_order_volume)}`} />
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <Card title="Крипто-платежи" value={cp.total || 0} color="#8b5cf6" sub={`✅ ${cp.completed || 0}  ⏳ ${cp.pending || 0}  ❌ ${cp.failed || 0}`} />
      </div>
      <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>Последние ордера</h3>
      <Table
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'type', label: 'Тип', render: r => badge(r.type, r.type === 'issue' ? '#6366f1' : '#0ea5e9') },
          { key: 'amount', label: 'Сумма', render: r => `$${fmt(r.amount)}` },
          { key: 'fee', label: 'Комиссия', render: r => `$${fmt(r.fee)}` },
          { key: 'status', label: 'Статус', render: r => badge(r.status, statusColor[r.status] || '#6b7280') },
          { key: 'created_at', label: 'Дата', render: r => r.created_at?.slice(0, 16).replace('T', ' ') },
        ]}
        rows={data.recent_orders || []}
      />
    </div>
  )
}

// ─────────── USERS LIST ───────────
function UsersPage({ goToUser }) {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const PAGE = 30

  const load = useCallback(async () => {
    try { const d = await adminApi.users.list(search, PAGE, page * PAGE); setUsers(d.items); setTotal(d.total) } catch {}
  }, [search, page])
  useEffect(() => { load() }, [load])

  const toggleBan = async (u) => {
    try { u.is_active ? await adminApi.users.ban(u.id) : await adminApi.users.unban(u.id); load() } catch {}
  }

  return (
    <div>
      <h2 style={{ margin: '0 0 16px', fontSize: 22, fontWeight: 700 }}>Пользователи <span style={{ color: '#9ca3af', fontWeight: 400, fontSize: 16 }}>({total})</span></h2>
      <div style={{ marginBottom: 16 }}>
        <input placeholder="Поиск по username / telegram ID…" value={search} onChange={e => { setSearch(e.target.value); setPage(0) }}
          style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #d1d5db', width: 340, fontSize: 14, outline: 'none' }} />
      </div>
      <Table
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'username', label: 'Username' },
          { key: 'telegram_user_id', label: 'Telegram ID' },
          { key: 'balance', label: 'Баланс', render: r => `$${fmt(r.balance)}` },
          { key: 'cards_count', label: 'Карты' },
          { key: 'is_active', label: 'Статус', render: r => badge(r.is_active ? 'Активен' : 'Забанен', r.is_active ? '#22c55e' : '#ef4444') },
          { key: '_actions', label: '', render: r => (
            <div style={{ display: 'flex', gap: 6 }}>
              <Btn small onClick={(e) => { e.stopPropagation(); goToUser(r.id) }}>Детали</Btn>
              <Btn small variant={r.is_active ? 'danger' : 'primary'} onClick={(e) => { e.stopPropagation(); toggleBan(r) }}>
                {r.is_active ? 'Бан' : 'Разбан'}
              </Btn>
            </div>
          )},
        ]}
        rows={users}
        onRowClick={r => goToUser(r.id)}
      />
      {total > PAGE && (
        <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
          <Btn small disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Назад</Btn>
          <span style={{ fontSize: 13, color: '#6b7280' }}>Стр. {page + 1} из {Math.ceil(total / PAGE)}</span>
          <Btn small disabled={(page + 1) * PAGE >= total} onClick={() => setPage(p => p + 1)}>Далее →</Btn>
        </div>
      )}
    </div>
  )
}

// ─────────── USER DETAIL ───────────
function UserDetailPage({ userId, goBack }) {
  const [user, setUser] = useState(null)
  const [cards, setCards] = useState([])
  const [orders, setOrders] = useState([])
  const [cpayments, setCpayments] = useState([])
  const [topups, setTopups] = useState([])
  const [tab, setTab] = useState('cards')
  const [editMode, setEditMode] = useState(false)
  const [form, setForm] = useState({})

  useEffect(() => {
    (async () => {
      try {
        const [u, c, o, cp, t] = await Promise.all([
          adminApi.users.get(userId),
          adminApi.users.cards(userId),
          adminApi.users.orders(userId),
          adminApi.users.cryptoPayments(userId),
          adminApi.users.topupRequests(userId),
        ])
        setUser(u); setCards(c); setOrders(o); setCpayments(cp); setTopups(t)
        setForm({ username: u.username, balance: u.balance, telegram_user_id: u.telegram_user_id || '' })
      } catch {}
    })()
  }, [userId])

  const save = async () => {
    try { await adminApi.users.update(userId, { username: form.username, balance: parseFloat(form.balance) || 0, telegram_user_id: form.telegram_user_id || null }); setEditMode(false); const u = await adminApi.users.get(userId); setUser(u) } catch {}
  }

  if (!user) return <p>Загрузка...</p>

  const tabs = [
    { id: 'cards', label: `Карты (${cards.length})` },
    { id: 'orders', label: `Ордера (${orders.length})` },
    { id: 'crypto', label: `Крипто-платежи (${cpayments.length})` },
    { id: 'topups', label: `Пополнения (${topups.length})` },
  ]

  return (
    <div>
      <Btn small variant="ghost" onClick={goBack} style={{ marginBottom: 12 }}>← Назад к списку</Btn>
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 24 }}>
        <div style={{ background: '#fff', borderRadius: 14, padding: 24, flex: '1 1 340px', boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Пользователь #{user.id}</h2>
            {badge(user.is_active ? 'Активен' : 'Забанен', user.is_active ? '#22c55e' : '#ef4444')}
          </div>
          {editMode ? (
            <div>
              <Input label="Username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
              <Input label="Баланс ($)" type="number" step="0.01" value={form.balance} onChange={e => setForm({ ...form, balance: e.target.value })} />
              <Input label="Telegram ID" value={form.telegram_user_id} onChange={e => setForm({ ...form, telegram_user_id: e.target.value })} />
              <div style={{ display: 'flex', gap: 8 }}><Btn small onClick={save}>Сохранить</Btn><Btn small variant="ghost" onClick={() => setEditMode(false)}>Отмена</Btn></div>
            </div>
          ) : (
            <div style={{ fontSize: 14, lineHeight: 2 }}>
              <div><strong>Username:</strong> {user.username}</div>
              <div><strong>Telegram ID:</strong> {user.telegram_user_id || '—'}</div>
              <div><strong>Баланс:</strong> ${fmt(user.balance)}</div>
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <Btn small onClick={() => setEditMode(true)}>Редактировать</Btn>
                <Btn small variant={user.is_active ? 'danger' : 'primary'} onClick={async () => {
                  user.is_active ? await adminApi.users.ban(userId) : await adminApi.users.unban(userId)
                  const u = await adminApi.users.get(userId); setUser(u)
                }}>{user.is_active ? 'Забанить' : 'Разбанить'}</Btn>
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {tabs.map(t => (
          <div key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '8px 16px', borderRadius: '8px 8px 0 0', cursor: 'pointer', fontSize: 13, fontWeight: 600,
              background: tab === t.id ? '#fff' : '#e5e7eb', color: tab === t.id ? '#111827' : '#6b7280' }}>{t.label}</div>
        ))}
      </div>

      {tab === 'cards' && <Table columns={[
        { key: 'id', label: 'ID' }, { key: 'aifory_card_id', label: 'Aifory ID', render: r => (r.aifory_card_id || '').slice(0, 12) + '…' },
        { key: 'last4', label: 'Last4' }, { key: 'currency', label: 'Валюта' },
        { key: 'balance', label: 'Баланс', render: r => `$${fmt(r.balance)}` },
        { key: 'status', label: 'Статус', render: r => badge(r.status || '?', statusColor[r.status] || '#6b7280') },
      ]} rows={cards} />}

      {tab === 'orders' && <Table columns={[
        { key: 'id', label: 'ID' }, { key: 'type', label: 'Тип', render: r => badge(r.type, r.type === 'issue' ? '#6366f1' : '#0ea5e9') },
        { key: 'amount', label: 'Сумма', render: r => `$${fmt(r.amount)}` }, { key: 'fee', label: 'Комиссия', render: r => `$${fmt(r.fee)}` },
        { key: 'status', label: 'Статус', render: r => badge(r.status, statusColor[r.status] || '#6b7280') },
        { key: 'created_at', label: 'Дата', render: r => r.created_at?.slice(0, 16).replace('T', ' ') },
      ]} rows={orders} />}

      {tab === 'crypto' && <Table columns={[
        { key: 'id', label: 'ID', render: r => r.id?.slice(0, 8) + '…' },
        { key: 'type', label: 'Тип', render: r => badge(r.type, r.type === 'issue' ? '#6366f1' : '#0ea5e9') },
        { key: 'total_usdt', label: 'USDT', render: r => `$${fmt(r.total_usdt)}` },
        { key: 'network', label: 'Сеть' },
        { key: 'status', label: 'Статус', render: r => badge(r.status, statusColor[r.status] || '#6b7280') },
        { key: 'address', label: 'Адрес', render: r => (r.address || '').slice(0, 14) + '…' },
        { key: 'created_at', label: 'Дата', render: r => r.created_at?.slice(0, 16).replace('T', ' ') },
      ]} rows={cpayments} />}

      {tab === 'topups' && <Table columns={[
        { key: 'id', label: 'ID' }, { key: 'amount', label: 'Сумма', render: r => `$${fmt(r.amount)}` },
        { key: 'status', label: 'Статус', render: r => badge(r.status, statusColor[r.status] || '#6b7280') },
        { key: 'payment_reference', label: 'Реф.' }, { key: 'comment', label: 'Коммент' },
      ]} rows={topups} />}
    </div>
  )
}

// ─────────── CARDS ───────────
function CardsPage() {
  const [cards, setCards] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [showAssign, setShowAssign] = useState(false)
  const [aiforyCards, setAiforyCards] = useState([])
  const [assignUserId, setAssignUserId] = useState('')
  const [assignCardId, setAssignCardId] = useState('')
  const [aiforyLoading, setAiforyLoading] = useState(false)

  const load = useCallback(async () => {
    try { const d = await adminApi.cards.list(search); setCards(d.items); setTotal(d.total) } catch {}
  }, [search])
  useEffect(() => { load() }, [load])

  const openAssign = async () => {
    setShowAssign(true); setAiforyLoading(true)
    try { const c = await adminApi.cards.aiforyUnassigned(); setAiforyCards(c) } catch {}
    finally { setAiforyLoading(false) }
  }
  const doAssign = async () => {
    if (!assignUserId || !assignCardId) return
    try { await adminApi.cards.assign(parseInt(assignUserId), assignCardId); setShowAssign(false); setAssignUserId(''); setAssignCardId(''); load() } catch (e) { alert(e.message) }
  }
  const doDelete = async (id) => {
    if (!confirm('Удалить привязку карты?')) return
    try { await adminApi.cards.remove(id); load() } catch {}
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Карты <span style={{ color: '#9ca3af', fontWeight: 400, fontSize: 16 }}>({total})</span></h2>
        <Btn small onClick={openAssign}>+ Назначить карту</Btn>
      </div>

      {showAssign && (
        <div style={{ background: '#fff', borderRadius: 14, padding: 20, marginBottom: 20, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>Назначить карту из Aifory</h3>
          <Input label="User ID" type="number" value={assignUserId} onChange={e => setAssignUserId(e.target.value)} />
          {aiforyLoading ? <p style={{ fontSize: 13, color: '#6b7280' }}>Загрузка карт из Aifory...</p> : (
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4, color: '#374151' }}>Карта Aifory</label>
              <select value={assignCardId} onChange={e => setAssignCardId(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14 }}>
                <option value="">Выберите карту…</option>
                {aiforyCards.map(c => (
                  <option key={c.aifory_card_id} value={c.aifory_card_id}>
                    {c.aifory_card_id.slice(0, 8)}… | •••{c.last4} | ${fmt(c.balance)} | status={c.card_status}
                  </option>
                ))}
              </select>
              {aiforyCards.length === 0 && <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>Нет свободных карт</p>}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn small onClick={doAssign} disabled={!assignUserId || !assignCardId}>Назначить</Btn>
            <Btn small variant="ghost" onClick={() => setShowAssign(false)}>Отмена</Btn>
          </div>
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <input placeholder="Поиск по last4 / holder / aifory ID…" value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #d1d5db', width: 340, fontSize: 14, outline: 'none' }} />
      </div>

      <Table
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'username', label: 'Юзер' },
          { key: 'aifory_card_id', label: 'Aifory ID', render: r => (r.aifory_card_id || '').slice(0, 12) + '…' },
          { key: 'last4', label: 'Last4' },
          { key: 'currency', label: 'Валюта' },
          { key: 'balance', label: 'Баланс', render: r => `$${fmt(r.balance)}` },
          { key: 'status', label: 'Статус', render: r => badge(r.status || '?', statusColor[r.status] || '#6b7280') },
          { key: '_actions', label: '', render: r => <Btn small variant="danger" onClick={(e) => { e.stopPropagation(); doDelete(r.id) }}>Удалить</Btn> },
        ]}
        rows={cards}
      />
    </div>
  )
}

// ─────────── PAYMENTS (orders + crypto) ───────────
function PaymentsPage() {
  const [tab, setTab] = useState('crypto')
  const [cryptoPayments, setCryptoPayments] = useState([])
  const [orders, setOrders] = useState([])
  const [cpTotal, setCpTotal] = useState(0)
  const [ordTotal, setOrdTotal] = useState(0)

  useEffect(() => {
    (async () => {
      try { const d = await adminApi.cryptoPayments.list('', 100); setCryptoPayments(d.items); setCpTotal(d.total) } catch {}
      try { const d = await adminApi.orders.list(100); setOrders(d.items); setOrdTotal(d.total) } catch {}
    })()
  }, [])

  return (
    <div>
      <h2 style={{ margin: '0 0 16px', fontSize: 22, fontWeight: 700 }}>Платежи</h2>
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {[{ id: 'crypto', label: `Крипто-платежи (${cpTotal})` }, { id: 'orders', label: `Ордера (${ordTotal})` }].map(t => (
          <div key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '8px 16px', borderRadius: '8px 8px 0 0', cursor: 'pointer', fontSize: 13, fontWeight: 600,
              background: tab === t.id ? '#fff' : '#e5e7eb', color: tab === t.id ? '#111827' : '#6b7280' }}>{t.label}</div>
        ))}
      </div>

      {tab === 'crypto' && <Table columns={[
        { key: 'id', label: 'ID', render: r => r.id?.slice(0, 8) + '…' },
        { key: 'username', label: 'Юзер' },
        { key: 'type', label: 'Тип', render: r => badge(r.type, r.type === 'issue' ? '#6366f1' : '#0ea5e9') },
        { key: 'total_usdt', label: 'USDT', render: r => `$${fmt(r.total_usdt)}` },
        { key: 'amount_usd', label: 'Сумма', render: r => `$${fmt(r.amount_usd)}` },
        { key: 'network', label: 'Сеть' },
        { key: 'status', label: 'Статус', render: r => badge(r.status, statusColor[r.status] || '#6b7280') },
        { key: 'address', label: 'Адрес', render: r => (r.address || '').slice(0, 14) + '…' },
        { key: 'created_at', label: 'Дата', render: r => r.created_at?.slice(0, 16).replace('T', ' ') },
      ]} rows={cryptoPayments} />}

      {tab === 'orders' && <Table columns={[
        { key: 'id', label: 'ID' },
        { key: 'username', label: 'Юзер' },
        { key: 'type', label: 'Тип', render: r => badge(r.type, r.type === 'issue' ? '#6366f1' : '#0ea5e9') },
        { key: 'amount', label: 'Сумма', render: r => `$${fmt(r.amount)}` },
        { key: 'fee', label: 'Комиссия', render: r => `$${fmt(r.fee)}` },
        { key: 'status', label: 'Статус', render: r => badge(r.status, statusColor[r.status] || '#6b7280') },
        { key: 'description', label: 'Описание', render: r => (r.description || '').slice(0, 40) },
        { key: 'created_at', label: 'Дата', render: r => r.created_at?.slice(0, 16).replace('T', ' ') },
      ]} rows={orders} />}
    </div>
  )
}

// ─────────── ANALYTICS ───────────
function AnalyticsPage() {
  const [data, setData] = useState(null)
  useEffect(() => { adminApi.analytics().then(setData).catch(() => {}) }, [])
  if (!data) return <p>Загрузка...</p>

  const maxRev = Math.max(...(data.daily_revenue || []).map(d => d.revenue), 1)
  const maxVol = Math.max(...(data.daily_revenue || []).map(d => d.volume), 1)

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 22, fontWeight: 700 }}>Аналитика</h2>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <Card title="Ордера на выпуск" value={data.orders_by_type?.issue || 0} color="#6366f1" />
        <Card title="Ордера на пополнение" value={data.orders_by_type?.topup || 0} color="#0ea5e9" />
      </div>

      <div style={{ background: '#fff', borderRadius: 14, padding: 20, marginBottom: 24, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>Выручка за 30 дней</h3>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 120 }}>
          {(data.daily_revenue || []).map((d, i) => (
            <div key={i} title={`${d.date}\nВыручка: $${fmt(d.revenue)}\nОбъём: $${fmt(d.volume)}\nОрдеров: ${d.orders}`}
              style={{ flex: 1, background: '#6366f1', borderRadius: '4px 4px 0 0', minHeight: 2, height: `${(d.revenue / maxRev) * 100}%`, transition: 'height .3s' }} />
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
          <span>{data.daily_revenue?.[0]?.date?.slice(5)}</span>
          <span>{data.daily_revenue?.[data.daily_revenue.length - 1]?.date?.slice(5)}</span>
        </div>
      </div>

      <div style={{ background: '#fff', borderRadius: 14, padding: 20, marginBottom: 24, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 600 }}>Объём за 30 дней</h3>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 120 }}>
          {(data.daily_revenue || []).map((d, i) => (
            <div key={i} title={`${d.date}: $${fmt(d.volume)}`}
              style={{ flex: 1, background: '#0ea5e9', borderRadius: '4px 4px 0 0', minHeight: 2, height: `${(d.volume / maxVol) * 100}%`, transition: 'height .3s' }} />
          ))}
        </div>
      </div>

      <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>Топ пользователей по объёму</h3>
      <Table
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'username', label: 'Username' },
          { key: 'total_volume', label: 'Объём', render: r => `$${fmt(r.total_volume)}` },
        ]}
        rows={data.top_users || []}
      />
    </div>
  )
}

// ─────────── SETTINGS ───────────
function SettingsPage() {
  const [items, setItems] = useState([])
  const [saving, setSaving] = useState(false)

  useEffect(() => { adminApi.settings.list().then(setItems).catch(() => {}) }, [])

  const update = (key, value) => {
    setItems(prev => prev.map(s => s.key === key ? { ...s, value } : s))
  }
  const save = async () => {
    setSaving(true)
    try {
      await adminApi.settings.update(items.map(s => ({ key: s.key, value: s.value })))
      alert('Настройки сохранены')
    } catch (e) { alert(e.message) }
    finally { setSaving(false) }
  }

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 22, fontWeight: 700 }}>Настройки</h2>
      <div style={{ background: '#fff', borderRadius: 14, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,.08)', maxWidth: 600 }}>
        {items.map(s => (
          <div key={s.key} style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 2 }}>{s.description}</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input value={s.value} onChange={e => update(s.key, e.target.value)}
                style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14, outline: 'none' }} />
              <span style={{ fontSize: 11, color: '#9ca3af', minWidth: 30 }}>{s.source === 'db' ? 'DB' : 'ENV'}</span>
            </div>
            <span style={{ fontSize: 11, color: '#9ca3af' }}>{s.key}</span>
          </div>
        ))}
        <Btn onClick={save} disabled={saving} style={{ marginTop: 8 }}>{saving ? 'Сохранение...' : 'Сохранить настройки'}</Btn>
      </div>
    </div>
  )
}

// ─────────── BOT PAGE ───────────
const HTML_GUIDE = `<b>жирный</b>
<i>курсив</i>
<u>подчёркнутый</u>
<s>зачёркнутый</s>
<a href="https://t.me">ссылка</a>
<code>моноширинный</code>
<pre>блок кода</pre>
🔥 Эмодзи вставляются напрямую
Перенос строки — обычный Enter`

function ButtonsEditor({ value, onChange }) {
  let parsed = []
  try { parsed = JSON.parse(value || '[]') } catch {}

  const update = (list) => onChange(JSON.stringify(list))
  const add = () => update([...parsed, { text: '', url: '' }])
  const remove = (i) => update(parsed.filter((_, j) => j !== i))
  const change = (i, field, val) => update(parsed.map((b, j) => j === i ? { ...b, [field]: val } : b))

  return (
    <div>
      {parsed.map((btn, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <input placeholder="Текст кнопки" value={btn.text} onChange={e => change(i, 'text', e.target.value)}
            style={{ flex: 1, padding: '7px 10px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 13 }} />
          <input placeholder="URL (https://...)" value={btn.url} onChange={e => change(i, 'url', e.target.value)}
            style={{ flex: 2, padding: '7px 10px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 13 }} />
          <Btn small variant="danger" onClick={() => remove(i)}>✕</Btn>
        </div>
      ))}
      <Btn small variant="ghost" onClick={add} style={{ marginTop: 4 }}>+ Добавить кнопку</Btn>
    </div>
  )
}

function BotPage() {
  const [tab, setTab] = useState('welcome')

  // — welcome tab state —
  const [text, setText] = useState('')
  const [buttons, setButtons] = useState('[]')
  const [parseMode, setParseMode] = useState('HTML')
  const [imageUrl, setImageUrl] = useState(null)
  const [hasImage, setHasImage] = useState(false)
  const [showGuide, setShowGuide] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testChatId, setTestChatId] = useState('')
  const [testing, setTesting] = useState(false)
  const [imgLoading, setImgLoading] = useState(false)

  // — broadcast tab state —
  const [bcText, setBcText] = useState('')
  const [bcButtons, setBcButtons] = useState('[]')
  const [bcParseMode, setBcParseMode] = useState('HTML')
  const [bcImageKey, setBcImageKey] = useState(null)
  const [bcImagePreview, setBcImagePreview] = useState(null)
  const [bcSending, setBcSending] = useState(false)
  const [bcResult, setBcResult] = useState(null)

  // — notification headers tab state —
  const [notifHeaders, setNotifHeaders] = useState({})
  const [notifSaving, setNotifSaving] = useState(false)

  // — gmail tab state —
  const [gmailConnected, setGmailConnected] = useState(false)
  const [gmailEmail, setGmailEmail] = useState('')
  const [gmailClientIdSet, setGmailClientIdSet] = useState(false)
  const [gmailLoading, setGmailLoading] = useState(false)

  useEffect(() => {
    adminApi.bot.getSettings().then(s => {
      setText(s.text || '')
      setButtons(s.buttons || '[]')
      setParseMode(s.parse_mode || 'HTML')
      setHasImage(s.has_image)
      setImageUrl(s.image_url ? s.image_url + '?t=' + Date.now() : null)
    }).catch(() => {})
    adminApi.bot.getNotificationSettings().then(s => setNotifHeaders(s || {})).catch(() => {})
    adminApi.gmail.status().then(s => {
      setGmailConnected(s.connected)
      setGmailEmail(s.email || '')
      setGmailClientIdSet(s.client_id_set)
    }).catch(() => {})
  }, [])

  const saveWelcome = async () => {
    setSaving(true)
    try { await adminApi.bot.updateSettings(text, buttons, parseMode); alert('Сохранено') }
    catch (e) { alert(e.message) }
    finally { setSaving(false) }
  }

  const uploadImg = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImgLoading(true)
    try {
      const r = await adminApi.bot.uploadImage(file)
      setHasImage(true)
      setImageUrl(r.image_url + '?t=' + Date.now())
    } catch (e) { alert(e.message) }
    finally { setImgLoading(false) }
  }

  const deleteImg = async () => {
    if (!confirm('Удалить картинку?')) return
    try { await adminApi.bot.deleteImage(); setHasImage(false); setImageUrl(null) }
    catch (e) { alert(e.message) }
  }

  const sendTest = async () => {
    if (!testChatId) return
    setTesting(true)
    try { await adminApi.bot.testWelcome(testChatId); alert('Тестовое сообщение отправлено!') }
    catch (e) { alert(e.message) }
    finally { setTesting(false) }
  }

  const uploadBcImage = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const r = await adminApi.bot.uploadBroadcastImage(file)
      setBcImageKey(r.image_key)
      setBcImagePreview(URL.createObjectURL(file))
    } catch (e) { alert(e.message) }
  }

  const sendBroadcast = async () => {
    if (!bcText.trim()) return alert('Введите текст сообщения')
    if (!confirm('Отправить рассылку всем пользователям с Telegram ID?')) return
    setBcSending(true); setBcResult(null)
    try {
      const r = await adminApi.bot.broadcast(bcText, bcParseMode, bcButtons, bcImageKey)
      setBcResult(r)
    } catch (e) { alert(e.message) }
    finally { setBcSending(false) }
  }

  const saveNotifHeaders = async () => {
    setNotifSaving(true)
    try { await adminApi.bot.updateNotificationSettings(notifHeaders); alert('Сохранено') }
    catch (e) { alert(e.message) }
    finally { setNotifSaving(false) }
  }

  const connectGmail = async () => {
    setGmailLoading(true)
    try {
      const { auth_url } = await adminApi.gmail.authUrl()
      const w = window.open(auth_url, 'gmail_auth', 'width=600,height=700')
      const onMsg = (e) => {
        if (e.data === 'gmail_connected') {
          window.removeEventListener('message', onMsg)
          adminApi.gmail.status().then(s => { setGmailConnected(s.connected); setGmailEmail(s.email || '') })
        }
      }
      window.addEventListener('message', onMsg)
    } catch (e) { alert(e.message) }
    finally { setGmailLoading(false) }
  }

  const disconnectGmail = async () => {
    if (!confirm('Отключить Gmail?')) return
    try { await adminApi.gmail.disconnect(); setGmailConnected(false); setGmailEmail('') }
    catch (e) { alert(e.message) }
  }

  const tabs = [
    { id: 'welcome', label: '📩 Приветствие' },
    { id: 'broadcast', label: '📢 Рассылка' },
    { id: 'notifications', label: '🔔 Уведомления' },
    { id: 'gmail', label: '📧 Gmail' },
  ]

  return (
    <div>
      <h2 style={{ margin: '0 0 16px', fontSize: 22, fontWeight: 700 }}>Telegram Бот</h2>
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {tabs.map(t => (
          <div key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '9px 18px', borderRadius: '8px 8px 0 0', cursor: 'pointer', fontSize: 13, fontWeight: 600,
              background: tab === t.id ? '#fff' : '#e5e7eb', color: tab === t.id ? '#111827' : '#6b7280', borderBottom: tab === t.id ? '2px solid #6366f1' : 'none' }}>
            {t.label}
          </div>
        ))}
      </div>

      {tab === 'welcome' && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          {/* Left: editor */}
          <div style={{ flex: '1 1 420px', background: '#fff', borderRadius: 14, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Текст сообщения</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ fontSize: 12, color: '#6b7280' }}>Режим:</label>
                <select value={parseMode} onChange={e => setParseMode(e.target.value)}
                  style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 12 }}>
                  <option value="HTML">HTML</option>
                  <option value="MarkdownV2">MarkdownV2</option>
                </select>
              </div>
            </div>

            <textarea value={text} onChange={e => setText(e.target.value)} rows={10}
              placeholder="Введите текст приветственного сообщения..."
              style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 13, lineHeight: 1.6, resize: 'vertical', boxSizing: 'border-box', fontFamily: 'monospace' }} />

            <div style={{ marginTop: 4, marginBottom: 16 }}>
              <span onClick={() => setShowGuide(g => !g)} style={{ fontSize: 12, color: '#6366f1', cursor: 'pointer', userSelect: 'none' }}>
                {showGuide ? '▾' : '▸'} Справка по форматированию HTML
              </span>
              {showGuide && (
                <pre style={{ background: '#f3f4f6', borderRadius: 8, padding: 12, fontSize: 12, marginTop: 8, overflow: 'auto', lineHeight: 1.8 }}>
                  {HTML_GUIDE}
                </pre>
              )}
            </div>

            <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 8px' }}>Кнопки</h3>
            <ButtonsEditor value={buttons} onChange={setButtons} />

            <h3 style={{ fontSize: 15, fontWeight: 600, margin: '16px 0 8px' }}>Изображение</h3>
            {hasImage && imageUrl && (
              <div style={{ marginBottom: 10 }}>
                <img src={imageUrl} alt="welcome" style={{ width: '100%', maxHeight: 180, objectFit: 'cover', borderRadius: 8 }} />
                <Btn small variant="danger" onClick={deleteImg} style={{ marginTop: 6 }}>Удалить</Btn>
              </div>
            )}
            <label style={{ display: 'inline-block', padding: '7px 14px', background: '#f3f4f6', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 500 }}>
              {imgLoading ? 'Загрузка...' : (hasImage ? 'Заменить картинку' : '+ Загрузить картинку')}
              <input type="file" accept="image/*" style={{ display: 'none' }} onChange={uploadImg} disabled={imgLoading} />
            </label>

            <div style={{ display: 'flex', gap: 10, marginTop: 20, flexWrap: 'wrap' }}>
              <Btn onClick={saveWelcome} disabled={saving}>{saving ? 'Сохранение...' : 'Сохранить настройки'}</Btn>
            </div>

            <div style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input placeholder="Ваш Telegram chat_id" value={testChatId} onChange={e => setTestChatId(e.target.value)}
                style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 13, width: 180 }} />
              <Btn small onClick={sendTest} disabled={testing || !testChatId} variant="ghost">
                {testing ? 'Отправка...' : '▶ Тест'}
              </Btn>
            </div>
          </div>

          {/* Right: formatting guide */}
          <div style={{ flex: '0 0 280px', background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,.08)', fontSize: 13 }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>📖 Как форматировать</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <tbody>
                {[
                  ['<b>текст</b>', 'жирный'],
                  ['<i>текст</i>', 'курсив'],
                  ['<u>текст</u>', 'подчёркнутый'],
                  ['<s>текст</s>', 'зачёркнутый'],
                  ['<code>текст</code>', 'моноширинный'],
                  ['<pre>текст</pre>', 'блок кода'],
                  ['<a href="URL">текст</a>', 'ссылка'],
                  ['🔥 😊 ✅', 'эмодзи'],
                ].map(([tag, desc]) => (
                  <tr key={tag}>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', color: '#6366f1', whiteSpace: 'nowrap' }}>{tag}</td>
                    <td style={{ padding: '4px 0', color: '#374151' }}>{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 12, padding: 10, background: '#f3f4f6', borderRadius: 8, fontSize: 11, color: '#6b7280', lineHeight: 1.6 }}>
              <strong>Пример:</strong><br />
              {'<b>🎉 Добро пожаловать!</b>'}<br />
              {'Здесь вы можете <i>выпустить</i> виртуальную карту.'}<br /><br />
              {'💳 <b>Выпуск карты</b> — за несколько минут'}<br />
              {'💰 <b>Пополнение</b> — через СБП и USDT'}
            </div>
          </div>
        </div>
      )}

      {tab === 'broadcast' && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 420px', background: '#fff', borderRadius: 14, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>Сообщение рассылки</h3>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
              <select value={bcParseMode} onChange={e => setBcParseMode(e.target.value)}
                style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 12 }}>
                <option value="HTML">HTML</option>
                <option value="MarkdownV2">MarkdownV2</option>
              </select>
            </div>
            <textarea value={bcText} onChange={e => setBcText(e.target.value)} rows={10}
              placeholder="Текст сообщения (поддерживается HTML-форматирование)..."
              style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 13, lineHeight: 1.6, resize: 'vertical', boxSizing: 'border-box', fontFamily: 'monospace' }} />

            <h3 style={{ fontSize: 15, fontWeight: 600, margin: '16px 0 8px' }}>Кнопки (необязательно)</h3>
            <ButtonsEditor value={bcButtons} onChange={setBcButtons} />

            <h3 style={{ fontSize: 15, fontWeight: 600, margin: '16px 0 8px' }}>Изображение (необязательно)</h3>
            {bcImagePreview && (
              <div style={{ marginBottom: 10 }}>
                <img src={bcImagePreview} alt="broadcast" style={{ width: '100%', maxHeight: 160, objectFit: 'cover', borderRadius: 8 }} />
                <Btn small variant="danger" onClick={() => { setBcImageKey(null); setBcImagePreview(null) }} style={{ marginTop: 6 }}>Убрать</Btn>
              </div>
            )}
            {!bcImagePreview && (
              <label style={{ display: 'inline-block', padding: '7px 14px', background: '#f3f4f6', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 500 }}>
                + Прикрепить картинку
                <input type="file" accept="image/*" style={{ display: 'none' }} onChange={uploadBcImage} />
              </label>
            )}

            <div style={{ marginTop: 20 }}>
              <Btn onClick={sendBroadcast} disabled={bcSending} style={{ background: '#dc2626' }}>
                {bcSending ? '⏳ Отправка...' : '📢 Отправить всем'}
              </Btn>
            </div>

            {bcResult && (
              <div style={{ marginTop: 16, padding: '12px 16px', borderRadius: 10, background: '#f0fdf4', border: '1px solid #86efac' }}>
                <strong>✅ Рассылка завершена</strong><br />
                <span style={{ fontSize: 13 }}>Отправлено: <b>{bcResult.sent}</b> | Ошибок: <b>{bcResult.failed}</b> | Всего с TG: <b>{bcResult.total}</b></span>
              </div>
            )}
          </div>

          <div style={{ flex: '0 0 280px', background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,.08)', fontSize: 13 }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>📖 Форматирование</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <tbody>
                {[['<b>текст</b>', 'жирный'], ['<i>текст</i>', 'курсив'], ['<u>текст</u>', 'подчёркнутый'],
                  ['<s>текст</s>', 'зачёркнутый'], ['<code>текст</code>', 'моноширинный'],
                  ['<a href="URL">текст</a>', 'ссылка'], ['🔥 😊 ✅', 'эмодзи']].map(([tag, desc]) => (
                  <tr key={tag}>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', color: '#6366f1', whiteSpace: 'nowrap' }}>{tag}</td>
                    <td style={{ padding: '4px 0', color: '#374151' }}>{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: 12, padding: 10, background: '#fef9c3', borderRadius: 8, fontSize: 11, lineHeight: 1.6 }}>
              ⚠️ Рассылка уходит только пользователям, у которых сохранён Telegram ID (те, кто входил через бот).
            </div>
          </div>
        </div>
      )}

      {tab === 'notifications' && (
        <div style={{ maxWidth: 600, background: '#fff', borderRadius: 14, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600 }}>Заголовки уведомлений</h3>
          <p style={{ fontSize: 12, color: '#6b7280', marginTop: 0, marginBottom: 16 }}>
            Эти заголовки используются в Telegram-сообщениях, которые бот отправляет пользователям при событиях с картами.
          </p>
          {[
            ['BOT_APPLE_PAY_CODE_HEADER', '🍎 Apple Pay код'],
            ['BOT_NOTIFY_CARD_ISSUED_HEADER', '✅ Карта выпущена'],
            ['BOT_NOTIFY_CARD_FAILED_HEADER', '❌ Ошибка выпуска'],
            ['BOT_NOTIFY_TOPUP_SUCCESS_HEADER', '✅ Пополнение выполнено'],
            ['BOT_NOTIFY_TOPUP_FAILED_HEADER', '❌ Ошибка пополнения'],
          ].map(([key, label]) => (
            <Input key={key} label={label} value={notifHeaders[key] || ''}
              onChange={e => setNotifHeaders(h => ({ ...h, [key]: e.target.value }))} />
          ))}
          <Btn onClick={saveNotifHeaders} disabled={notifSaving} style={{ marginTop: 8 }}>
            {notifSaving ? 'Сохранение...' : 'Сохранить'}
          </Btn>
        </div>
      )}

      {tab === 'gmail' && (
        <div style={{ maxWidth: 500, background: '#fff', borderRadius: 14, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,.08)' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600 }}>📧 Gmail API (Apple Pay коды)</h3>
          <p style={{ fontSize: 12, color: '#6b7280', marginTop: 0, marginBottom: 16 }}>
            Бот каждые 10 секунд проверяет почту через Gmail API на наличие писем с кодами Apple Pay от SUNRATE.
            При обнаружении — отправляет <b>только самый свежий</b> код для каждой карты пользователю в Telegram.
          </p>

          {gmailConnected ? (
            <div>
              <div style={{ padding: '14px 18px', borderRadius: 10, background: '#f0fdf4', border: '1px solid #86efac', marginBottom: 16 }}>
                <span style={{ fontSize: 14, fontWeight: 600 }}>✅ Gmail подключён</span><br />
                <span style={{ fontSize: 13, color: '#374151' }}>{gmailEmail || '—'}</span>
              </div>
              <Btn variant="danger" small onClick={disconnectGmail}>Отключить Gmail</Btn>
            </div>
          ) : (
            <div>
              {!gmailClientIdSet && (
                <div style={{ padding: 10, background: '#fef9c3', borderRadius: 8, fontSize: 11, lineHeight: 1.6, marginBottom: 16 }}>
                  ⚠️ Сначала задайте <b>GMAIL_CLIENT_ID</b> и <b>GMAIL_CLIENT_SECRET</b> в <code>.env</code> файле бэкенда и перезапустите сервер.
                </div>
              )}
              <Btn onClick={connectGmail} disabled={gmailLoading || !gmailClientIdSet}>
                {gmailLoading ? '⏳ Открытие...' : '🔗 Подключить Gmail'}
              </Btn>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────── MAIN ADMIN APP ───────────
export default function AdminApp() {
  const [authed, setAuthed] = useState(!!getAdminToken())
  const [page, setPage] = useState('dashboard')
  const [selectedUserId, setSelectedUserId] = useState(null)

  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />

  const goToUser = (id) => { setSelectedUserId(id); setPage('user-detail') }
  const goBackToUsers = () => { setSelectedUserId(null); setPage('users') }

  let content
  switch (page) {
    case 'dashboard': content = <DashboardPage />; break
    case 'users': content = <UsersPage goToUser={goToUser} />; break
    case 'user-detail': content = <UserDetailPage userId={selectedUserId} goBack={goBackToUsers} />; break
    case 'cards': content = <CardsPage />; break
    case 'payments': content = <PaymentsPage />; break
    case 'analytics': content = <AnalyticsPage />; break
    case 'bot': content = <BotPage />; break
    case 'settings': content = <SettingsPage />; break
    default: content = <DashboardPage />
  }

  return (
    <>
      <style>{`
        .admin-root, .admin-root * { scrollbar-width: auto !important; -ms-overflow-style: auto !important; -webkit-user-select: auto !important; user-select: auto !important; }
        .admin-root *::-webkit-scrollbar { display: block !important; width: 6px; height: 6px; }
        .admin-root *::-webkit-scrollbar-thumb { background: #c1c5cb; border-radius: 3px; }
        .admin-root *::-webkit-scrollbar-track { background: transparent; }
      `}</style>
      <div className="admin-root" style={{ display: 'flex', minHeight: '100vh', fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif', background: '#f3f4f6' }}>
        <Sidebar page={page} setPage={(p) => { setPage(p); setSelectedUserId(null) }} />
        <div style={{ flex: 1, padding: '28px 32px', overflowY: 'auto', maxHeight: '100vh' }}>
          {content}
        </div>
      </div>
    </>
  )
}
