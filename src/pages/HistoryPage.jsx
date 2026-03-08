import { useState, useMemo, useEffect } from 'react'
import Button from '../components/ui/Button'
import Portal from '../components/ui/Portal'
import PageHeader from '../components/ui/PageHeader'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

const RU_MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]
const RU_MONTHS_GEN = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]
const RU_DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const MOCK_CARDS = [
  { last4: '1234', title: 'Виртуальная карта' },
  { last4: '5678', title: 'Виртуальная карта' },
  { last4: '8685', title: 'Виртуальная карта' },
  { last4: '1447', title: 'Виртуальная карта' },
]

export const MOCK_TRANSACTIONS = [
  {
    id: 'tx-01', type: 'payment', title: 'Kanzler',
    subtitle: 'Магазины', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: -501.69, date: new Date(2026, 1, 12),
  },
  {
    id: 'tx-02', type: 'topup', title: '*** 1234',
    subtitle: 'Пополнение', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: 5000, date: new Date(2026, 1, 12),
  },
  {
    id: 'tx-03', type: 'declined', title: 'Константин С.',
    subtitle: 'Операция отклонена', cardTitle: 'Виртуальная карта', cardLast4: '7548',
    amount: -32480, date: new Date(2026, 1, 10),
  },
  {
    id: 'tx-04', type: 'payment', title: 'Amediateka',
    subtitle: 'Сервисы', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: -490, date: new Date(2026, 1, 10),
  },
  {
    id: 'tx-05', type: 'topup', title: '*** 1234',
    subtitle: 'Пополнение', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: 5000, date: new Date(2026, 1, 10),
  },
  {
    id: 'tx-06', type: 'topup', title: '*** 1234',
    subtitle: 'Пополнение', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: 5000, date: new Date(2026, 1, 10),
  },
  {
    id: 'tx-07', type: 'topup', title: '*** 1234',
    subtitle: 'Пополнение', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: 5000, date: new Date(2026, 1, 10),
  },
  {
    id: 'tx-08', type: 'topup', title: '*** 1234',
    subtitle: 'Пополнение', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: 5000, date: new Date(2026, 1, 10),
  },
  {
    id: 'tx-09', type: 'withdrawal', title: '*** 5678',
    subtitle: 'Вывод средств', cardTitle: 'Виртуальная карта', cardLast4: '5678',
    amount: -1200, date: new Date(2026, 1, 8),
  },
  {
    id: 'tx-10', type: 'topup', title: '*** 8685',
    subtitle: 'Пополнение', cardTitle: 'Виртуальная карта', cardLast4: '8685',
    amount: 3000, date: new Date(2026, 1, 8),
  },
  {
    id: 'tx-11', type: 'payment', title: 'Kanzler',
    subtitle: 'Магазины', cardTitle: 'Виртуальная карта', cardLast4: '1234',
    amount: -501.69, date: new Date(2026, 1, 5),
  },
  {
    id: 'tx-12', type: 'topup', title: '*** 1447',
    subtitle: 'Пополнение', cardTitle: 'Виртуальная карта', cardLast4: '1447',
    amount: 10000, date: new Date(2026, 1, 3),
  },
]

const OP_TYPES = [
  { key: 'topup', label: 'Пополнения' },
  { key: 'withdrawal', label: 'Вывод средств' },
  { key: 'payment', label: 'Оплата' },
  { key: 'declined', label: 'Прерванная операция' },
]

export function TxIcon({ type, size = 44, iconSize = 20, radius = 14 }) {
  const iconMap = {
    topup: {
      iconSrc: '/images/HistoryIcons/arrow-down.png',
    },
    withdrawal: {
      iconSrc: '/images/HistoryIcons/arrow-circle-up.png',
    },
    payment: {
      iconSrc: '/images/HistoryIcons/shop.png',
    },
    declined: {
      iconSrc: '/images/HistoryIcons/red-krest.png',
    },
  }
  const cfg = iconMap[type] || iconMap.payment
  return (
    <div style={{
      width: size, height: size, borderRadius: radius,
      backgroundColor: '#F3F5F8',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
    }}>
      <img
        src={cfg.iconSrc}
        alt=""
        style={{ width: iconSize, height: iconSize, objectFit: 'contain' }}
      />
    </div>
  )
}

function TxRow({ tx, isLast }) {
  const isPositive = tx.amount > 0
  const absAmount = Math.abs(tx.amount)
  const formatted = absAmount.toLocaleString('en-US', {
    minimumFractionDigits: absAmount % 1 !== 0 ? 2 : 0,
    maximumFractionDigits: 2,
  })
  const amountStr = isPositive ? `+${formatted} $` : `−${formatted} $`
  const amountColor = isPositive ? '#22C55E' : tx.type === 'declined' ? '#DC4D35' : '#111827'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      paddingTop: 16, paddingBottom: 16,
      borderBottom: isLast ? 'none' : '1px solid #F3F5F8',
    }}>
      <TxIcon type={tx.type} size={46} iconSize={22} radius={14} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>
          {tx.title}
        </div>
        <div style={{
          fontSize: 13, color: tx.type === 'declined' ? '#DC4D35' : '#6B7280',
          fontFamily: font, marginTop: 1,
        }}>
          {tx.subtitle}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
        <div style={{
          fontSize: 16,
          fontWeight: 600,
          color: amountColor,
          fontFamily: font,
          textAlign: 'right',
        }}>
          {amountStr}
        </div>
        <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, textAlign: 'right' }}>
          {tx.cardTitle} · {tx.cardLast4}
        </div>
      </div>
    </div>
  )
}

function FilterButton({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '7px 12px',
        backgroundColor: active ? '#111827' : 'white',
        borderRadius: 20, border: 'none', cursor: 'pointer',
        fontFamily: font, fontSize: 14, fontWeight: 500,
        color: active ? 'white' : '#111827',
        transition: 'background-color 150ms',
      }}
    >
      {label}
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M3 4.5l3 3 3-3" stroke={active ? 'white' : '#6B7280'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}

function FilterChip({ label, onRemove }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      backgroundColor: '#111827', color: 'white',
      borderRadius: 20, padding: '6px 10px 6px 12px',
      fontSize: 13, fontFamily: font, fontWeight: 500,
    }}>
      {label}
      <button
        onClick={onRemove}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'rgba(255,255,255,0.7)', padding: '0 0 0 2px',
          fontSize: 16, lineHeight: 1, display: 'flex', alignItems: 'center',
        }}
      >
        ×
      </button>
    </div>
  )
}

function Checkbox({ checked }) {
  return (
    <div style={{
      width: 22, height: 22, borderRadius: 6, flexShrink: 0,
      border: `2px solid ${checked ? '#DC4D35' : '#D1D5DB'}`,
      backgroundColor: checked ? '#DC4D35' : 'white',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transition: 'background-color 150ms, border-color 150ms',
    }}>
      {checked && (
        <svg width="12" height="10" viewBox="0 0 12 10" fill="none">
          <path d="M1.5 5l3.5 3.5L10.5 1.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </div>
  )
}

function BottomSheet({ isOpen, onClose, title, height, footer, children }) {
  return (
    <Portal>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 9998,
          backgroundColor: 'rgba(0,0,0,0.45)',
          opacity: isOpen ? 1 : 0,
          pointerEvents: isOpen ? 'auto' : 'none',
          transition: 'opacity 350ms ease',
        }}
      />
      <div
        style={{
          position: 'fixed', left: 0, right: 0, bottom: 0,
          backgroundColor: 'white',
          borderTopLeftRadius: 24, borderTopRightRadius: 24,
          zIndex: 9999,
          height: height || 'auto',
          maxHeight: '90vh',
          display: 'flex', flexDirection: 'column',
          transform: isOpen ? 'translateY(0)' : 'translateY(100%)',
          transition: 'transform 420ms cubic-bezier(0.32, 0.72, 0, 1)',
          pointerEvents: isOpen ? 'auto' : 'none',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 12, paddingBottom: 4, flexShrink: 0 }}>
          <div style={{ width: 36, height: 5, backgroundColor: '#D1D5DB', borderRadius: 3 }} />
        </div>
        <div style={{ padding: '8px 16px 14px', flexShrink: 0 }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, color: '#111827', fontFamily: font, margin: 0 }}>
            {title}
          </h2>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {children}
        </div>
        {footer && (
          <div style={{ padding: '12px 16px 32px', flexShrink: 0 }}>
            {footer}
          </div>
        )}
      </div>
    </Portal>
  )
}

function CardFilterModal({ isOpen, onClose, cards, selectedCards, onApply }) {
  const [local, setLocal] = useState([])
  useEffect(() => { if (isOpen) setLocal(selectedCards) }, [isOpen, selectedCards])

  const toggle = (last4) =>
    setLocal(prev => prev.includes(last4) ? prev.filter(c => c !== last4) : [...prev, last4])

  return (
    <BottomSheet
      isOpen={isOpen} onClose={onClose} title="Выберите карту"
      footer={<Button fullWidth onClick={() => { onApply(local); onClose() }}>Посмотреть операции</Button>}
    >
      <div style={{ padding: '0 16px' }}>
        {cards.map((card, idx) => (
          <div
            key={card.last4}
            onClick={() => toggle(card.last4)}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '12px 0',
              borderBottom: idx < cards.length - 1 ? '1px solid #F3F5F8' : 'none',
              cursor: 'pointer',
            }}
          >
            <img src="/images/bank-card.png" alt="" style={{ width: 48, height: 32, objectFit: 'contain', borderRadius: 4 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>{card.title}</div>
              <div style={{ fontSize: 13, color: '#6B7280', fontFamily: font }}>···· {card.last4}</div>
            </div>
            <Checkbox checked={local.includes(card.last4)} />
          </div>
        ))}
      </div>
    </BottomSheet>
  )
}

function TypeFilterModal({ isOpen, onClose, selectedTypes, onApply }) {
  const [local, setLocal] = useState([])
  useEffect(() => { if (isOpen) setLocal(selectedTypes) }, [isOpen, selectedTypes])

  const toggle = (key) =>
    setLocal(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key])

  return (
    <BottomSheet
      isOpen={isOpen} onClose={onClose} title="Выберите тип операции"
      footer={<Button fullWidth onClick={() => { onApply(local); onClose() }}>Посмотреть операции</Button>}
    >
      <div style={{ padding: '0 16px' }}>
        {OP_TYPES.map((op, idx) => (
          <div
            key={op.key}
            onClick={() => toggle(op.key)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '14px 0',
              borderBottom: idx < OP_TYPES.length - 1 ? '1px solid #F3F5F8' : 'none',
              cursor: 'pointer',
            }}
          >
            <span style={{ fontSize: 15, fontWeight: 500, color: '#111827', fontFamily: font }}>{op.label}</span>
            <Checkbox checked={local.includes(op.key)} />
          </div>
        ))}
      </div>
    </BottomSheet>
  )
}

function CalendarPicker({ value, onChange }) {
  const today = new Date()
  const initYear = value?.start?.getFullYear() ?? today.getFullYear()
  const initMonth = value?.start?.getMonth() ?? today.getMonth()
  const [viewYear, setViewYear] = useState(initYear)
  const [viewMonth, setViewMonth] = useState(initMonth)

  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const firstDayRaw = new Date(viewYear, viewMonth, 1).getDay()
  const offset = firstDayRaw === 0 ? 6 : firstDayRaw - 1

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11) }
    else setViewMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0) }
    else setViewMonth(m => m + 1)
  }

  const toDate = (d) => new Date(viewYear, viewMonth, d)
  const sameDay = (a, b) => a && b && a.toDateString() === b.toDateString()

  const isSelected = (d) => {
    const date = toDate(d)
    if (!value?.start) return false
    if (!value?.end) return sameDay(date, value.start)
    return date >= value.start && date <= value.end
  }

  const handleClick = (d) => {
    const clicked = toDate(d)
    if (!value?.start || (value?.start && value?.end)) {
      onChange({ start: clicked, end: null })
    } else {
      if (clicked < value.start) onChange({ start: clicked, end: value.start })
      else onChange({ start: value.start, end: clicked })
    }
  }

  const cells = []
  for (let i = 0; i < offset; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)
  while (cells.length % 7 !== 0) cells.push(null)

  return (
    <div style={{ padding: '0 16px 8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <button onClick={prevMonth} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 6 }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M11 14L6 9l5-5" stroke="#6B7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span style={{ fontSize: 16, fontWeight: 600, color: '#111827', fontFamily: font }}>
          {RU_MONTHS[viewMonth]} {viewYear}
        </span>
        <button onClick={nextMonth} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 6 }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M7 14l5-5-5-5" stroke="#6B7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', marginBottom: 4 }}>
        {RU_DAYS.map(d => (
          <div key={d} style={{
            textAlign: 'center', fontSize: 13, color: '#9CA3AF',
            fontFamily: font, padding: '4px 0', fontWeight: 500,
          }}>{d}</div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', rowGap: 2 }}>
        {cells.map((d, i) => {
          if (!d) return <div key={`e-${i}`} />
          const sel = isSelected(d)
          return (
            <div
              key={d}
              onClick={() => handleClick(d)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 36, height: 36, margin: '0 auto',
                borderRadius: '50%',
                backgroundColor: sel ? '#DC4D35' : 'transparent',
                color: sel ? 'white' : '#111827',
                fontSize: 15, fontFamily: font,
                fontWeight: sel ? 600 : 400,
                cursor: 'pointer',
                transition: 'background-color 100ms',
              }}
            >
              {d}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PeriodFilterModal({ isOpen, onClose, selectedPeriod, onApply }) {
  const [range, setRange] = useState({ start: null, end: null })
  useEffect(() => { if (isOpen) setRange(selectedPeriod || { start: null, end: null }) }, [isOpen, selectedPeriod])

  const canApply = !!(range.start && range.end)

  return (
    <BottomSheet
      isOpen={isOpen} onClose={onClose} title="Выберите период"
      footer={
        <Button fullWidth disabled={!canApply} onClick={() => { if (canApply) { onApply(range); onClose() } }}>
          Посмотреть операции
        </Button>
      }
    >
      <CalendarPicker value={range} onChange={setRange} />
    </BottomSheet>
  )
}

function HistoryPage({ userCards = [], transactions = [], onBack }) {
  const [cardFilter, setCardFilter] = useState([])
  const [typeFilter, setTypeFilter] = useState([])
  const [periodFilter, setPeriodFilter] = useState(null)

  const [cardModalOpen, setCardModalOpen] = useState(false)
  const [typeModalOpen, setTypeModalOpen] = useState(false)
  const [periodModalOpen, setPeriodModalOpen] = useState(false)

  const allCards = userCards.length > 0 ? userCards.map(c => ({ last4: c.last4, title: c.title || 'Виртуальная карта' })) : []

  const filteredGroups = useMemo(() => {
    let txs = [...transactions]
    if (cardFilter.length > 0) txs = txs.filter(tx => cardFilter.includes(tx.cardLast4))
    if (typeFilter.length > 0) txs = txs.filter(tx => typeFilter.includes(tx.type))
    if (periodFilter?.start && periodFilter?.end) {
      const s = new Date(periodFilter.start); s.setHours(0, 0, 0, 0)
      const e = new Date(periodFilter.end); e.setHours(23, 59, 59, 999)
      txs = txs.filter(tx => tx.date >= s && tx.date <= e)
    }

    const groups = {}
    txs.forEach(tx => {
      const key = `${tx.date.getFullYear()}-${tx.date.getMonth()}-${tx.date.getDate()}`
      if (!groups[key]) groups[key] = { date: tx.date, txs: [] }
      groups[key].txs.push(tx)
    })
    return Object.values(groups).sort((a, b) => b.date - a.date)
  }, [transactions, cardFilter, typeFilter, periodFilter])

  const fmtDate = (d) => `${d.getDate()} ${RU_MONTHS_GEN[d.getMonth()]}`

  const chips = []
  typeFilter.forEach(type => {
    const op = OP_TYPES.find(o => o.key === type)
    chips.push({ key: `type-${type}`, label: op?.label || type, onRemove: () => setTypeFilter(prev => prev.filter(t => t !== type)) })
  })
  cardFilter.forEach(last4 => {
    chips.push({ key: `card-${last4}`, label: `···· ${last4}`, onRemove: () => setCardFilter(prev => prev.filter(c => c !== last4)) })
  })
  if (periodFilter?.start && periodFilter?.end) {
    const s = periodFilter.start, e = periodFilter.end
    const label = s.getMonth() === e.getMonth()
      ? `${s.getDate()}–${e.getDate()} ${RU_MONTHS_GEN[s.getMonth()]}`
      : `${s.getDate()} ${RU_MONTHS_GEN[s.getMonth()]} – ${e.getDate()} ${RU_MONTHS_GEN[e.getMonth()]}`
    chips.push({ key: 'period', label, onRemove: () => setPeriodFilter(null) })
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F3F5F8', display: 'flex', flexDirection: 'column', fontFamily: font }}>
      {onBack && <PageHeader title="История" onBack={onBack} />}
      <div style={{ padding: onBack ? '84px 16px 0' : '28px 16px 0' }}>
        {!onBack && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h1 style={{ fontSize: 30, fontWeight: 700, color: '#111827', fontFamily: font, margin: 0 }}>
              История
            </h1>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <FilterButton label="Карта" active={cardFilter.length > 0} onClick={() => setCardModalOpen(true)} />
          <FilterButton label="Тип операции" active={typeFilter.length > 0} onClick={() => setTypeModalOpen(true)} />
          <FilterButton label="Период" active={!!periodFilter} onClick={() => setPeriodModalOpen(true)} />
        </div>

        {chips.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
            {chips.map(chip => (
              <FilterChip key={chip.key} label={chip.label} onRemove={chip.onRemove} />
            ))}
          </div>
        )}
      </div>

      <div style={{ flex: 1, padding: '20px 0 80px' }}>
        {filteredGroups.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 16px', color: '#9CA3AF', fontSize: 15, fontFamily: font }}>
            Нет операций за выбранный период
          </div>
        ) : (
          filteredGroups.map(group => (
            <div key={group.date.toDateString()} style={{ marginBottom: 24 }}>
              <div style={{ padding: '0 16px 10px', fontSize: 16, fontWeight: 700, color: '#111827', fontFamily: font }}>
                {fmtDate(group.date)}
              </div>
              <div style={{ backgroundColor: 'white', borderRadius: 16, margin: '0 16px', overflow: 'hidden' }}>
                {group.txs.map((tx, idx) => (
                  <div key={tx.id} style={{ padding: '0 14px' }}>
                    <TxRow tx={tx} isLast={idx === group.txs.length - 1} />
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      <CardFilterModal
        isOpen={cardModalOpen} onClose={() => setCardModalOpen(false)}
        cards={allCards} selectedCards={cardFilter} onApply={setCardFilter}
      />
      <TypeFilterModal
        isOpen={typeModalOpen} onClose={() => setTypeModalOpen(false)}
        selectedTypes={typeFilter} onApply={setTypeFilter}
      />
      <PeriodFilterModal
        isOpen={periodModalOpen} onClose={() => setPeriodModalOpen(false)}
        selectedPeriod={periodFilter} onApply={setPeriodFilter}
      />
    </div>
  )
}

export default HistoryPage
