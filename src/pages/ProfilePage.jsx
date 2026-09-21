import { useCallback, useEffect, useState } from 'react'
import api from '../api/client'
import Card from '../components/ui/Card'
import Section from '../components/ui/Section'
import BalanceDepositModal from '../components/ui/BalanceDepositModal'
import { BOTTOM_BAR_SPACE } from '../components/BottomBar'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/ui/ToastProvider'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.setAttribute('readonly', '')
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      ta.remove()
      return ok
    } catch {
      return false
    }
  }
}

const LEDGER_META = {
  deposit: { label: 'Пополнение баланса', icon: '/images/HistoryIcons/arrow-down.png' },
  card_issue: { label: 'Выпуск карты', icon: '/images/HistoryIcons/shop.png' },
  card_topup: { label: 'Пополнение карты', icon: '/images/HistoryIcons/arrow-circle-up.png' },
  refund: { label: 'Возврат', icon: '/images/HistoryIcons/arrow-down.png' },
  referral: { label: 'Реферальное начисление', icon: '/images/HistoryIcons/arrow-down.png' },
  admin_adjust: { label: 'Корректировка', icon: '/images/HistoryIcons/arrow-circle-up.png' },
}

function formatPhone(value) {
  const digits = String(value || '').replace(/\D/g, '')
  const norm = digits.startsWith('8') ? '7' + digits.slice(1) : (digits.startsWith('7') ? digits : '7' + digits)
  const d = norm.slice(0, 11)
  if (d.length <= 1) return '+7'
  if (d.length <= 4) return `+7 (${d.slice(1)}`
  if (d.length <= 7) return `+7 (${d.slice(1, 4)}) ${d.slice(4)}`
  if (d.length <= 9) return `+7 (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7)}`
  return `+7 (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9, 11)}`
}

function CopyIcon({ color = '#DC4D35' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <rect x="9" y="9" width="11" height="11" rx="2.5" stroke={color} strokeWidth="1.9" />
      <path d="M15 9V6.5A2.5 2.5 0 0 0 12.5 4H6.5A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15H9" stroke={color} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  )
}

export default function ProfilePage() {
  const { user, fetchMe, appConfig } = useAuth()
  const { showToast } = useToast()

  const tgUser = window?.Telegram?.WebApp?.initDataUnsafe?.user || null
  const displayName = [tgUser?.first_name, tgUser?.last_name].filter(Boolean).join(' ') || user?.username || 'Пользователь'
  const handle = tgUser?.username || (user?.username && !String(user.username).startsWith('tg_') ? user.username : null)
  const tgId = tgUser?.id || user?.telegram_user_id || ''
  const initials = displayName.trim().split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase()

  const [profile, setProfile] = useState(null)
  const [ledger, setLedger] = useState([])
  const [showDeposit, setShowDeposit] = useState(false)

  const load = useCallback(async () => {
    try {
      const [p, h] = await Promise.all([
        api.profile.get(),
        api.profile.balanceHistory(20).catch(() => ({ items: [] })),
      ])
      setProfile(p)
      setLedger(h?.items || [])
    } catch {}
  }, [])

  useEffect(() => { load() }, [load])

  // Payer phone (Bitbanker): moved here from the home screen
  const [payerPhone, setPayerPhone] = useState('')
  const [phoneEditing, setPhoneEditing] = useState(false)
  const [phoneDraft, setPhoneDraft] = useState('')
  const [phoneSaving, setPhoneSaving] = useState(false)
  const [phoneError, setPhoneError] = useState('')
  const [phoneSaved, setPhoneSaved] = useState(false)
  useEffect(() => {
    let cancelled = false
    api.kyc.status()
      .then((s) => { if (!cancelled && s?.phone) setPayerPhone(s.phone) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const savePayerPhone = async () => {
    const clean = phoneDraft.replace(/[\s()\-]/g, '')
    if (!/^\+7\d{10}$/.test(clean)) {
      setPhoneError('Введите номер полностью: +7 (9XX) XXX-XX-XX')
      return
    }
    setPhoneSaving(true)
    setPhoneError('')
    try {
      const res = await api.sbp.updatePhone(clean)
      setPayerPhone(res.phone)
      setPhoneEditing(false)
      setPhoneSaved(true)
      setTimeout(() => setPhoneSaved(false), 4000)
    } catch (e) {
      setPhoneError(e.message || 'Не удалось сохранить номер')
    } finally {
      setPhoneSaving(false)
    }
  }

  const balance = Number(profile?.balance ?? user?.balance ?? 0)
  const refPercent = Number(profile?.referral_percent ?? appConfig?.referral_percent ?? 0)
  const refLink = profile?.referral_link || ''

  const copyId = async () => {
    if (!tgId) return
    const ok = await copyText(String(tgId))
    showToast({ title: ok ? 'Telegram ID скопирован' : 'Не удалось скопировать' })
  }

  const copyRef = async () => {
    if (!refLink) return
    const ok = await copyText(refLink)
    showToast({ title: ok ? 'Ссылка скопирована' : 'Не удалось скопировать' })
  }

  const shareRef = () => {
    if (!refLink) return
    const text = `Виртуальные карты для оплаты за рубежом — ProntoPay. Оформи по моей ссылке:`
    const url = `https://t.me/share/url?url=${encodeURIComponent(refLink)}&text=${encodeURIComponent(text)}`
    const tg = window?.Telegram?.WebApp
    if (tg?.openTelegramLink) tg.openTelegramLink(url)
    else window.open(url, '_blank', 'noopener')
  }

  const money = (v) => `${Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`

  return (
    <div className="flex-1 flex flex-col" style={{ paddingBottom: BOTTOM_BAR_SPACE }}>
      {/* Header: avatar + name */}
      <Section>
        <Card padding="22px 20px">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 64, height: 64, borderRadius: 32, flexShrink: 0, overflow: 'hidden',
              background: 'linear-gradient(135deg, #DC4D35 0%, #F0906E 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: 22, fontWeight: 700, fontFamily: font,
              boxShadow: '0 6px 16px rgba(220,77,53,0.25)',
            }}>
              {tgUser?.photo_url
                ? <img src={tgUser.photo_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : initials || '🙂'}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#111827', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {displayName}
              </div>
              {handle && (
                <div style={{ fontSize: 14, color: '#6B7280', fontFamily: font, marginTop: 2 }}>@{handle}</div>
              )}
            </div>
          </div>

          {/* tgID plate */}
          <button
            onClick={copyId}
            className="transition-transform duration-150 active:scale-[0.98]"
            style={{
              marginTop: 16, width: '100%', border: 'none', cursor: 'pointer', textAlign: 'left',
              background: '#F3F5F8', borderRadius: 14, padding: '12px 14px',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
            }}
          >
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#9CA3AF', fontFamily: font, letterSpacing: 0.3, textTransform: 'uppercase' }}>
                Telegram ID
              </div>
              <div style={{ fontSize: 17, fontWeight: 700, color: '#111827', fontFamily: font, marginTop: 2, letterSpacing: 0.5 }}>
                {tgId || '—'}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#DC4D35', fontSize: 13, fontWeight: 600, fontFamily: font }}>
              <CopyIcon /> Копировать
            </div>
          </button>
        </Card>
      </Section>

      {/* Internal balance */}
      <Section>
        <Card padding="20px">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#6B7280', fontFamily: font }}>Внутренний баланс</div>
              <div style={{ display: 'flex', alignItems: 'baseline', marginTop: 4 }}>
                <span style={{ fontSize: 32, fontWeight: 700, color: '#111827', fontFamily: font }}>
                  {balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span style={{ fontSize: 24, fontWeight: 500, color: '#6B7280', fontFamily: font, marginLeft: 4 }}>$</span>
              </div>
            </div>
            <button
              onClick={() => setShowDeposit(true)}
              className="transition-transform duration-150 active:scale-95"
              style={{
                border: 'none', background: '#DC4D35', color: '#fff', borderRadius: 12,
                padding: '12px 16px', fontSize: 14, fontWeight: 600, fontFamily: font, cursor: 'pointer', flexShrink: 0,
              }}
            >
              + Пополнить
            </button>
          </div>
          <div style={{ marginTop: 14, background: '#F3F5F8', borderRadius: 12, padding: '10px 12px', fontSize: 12, color: '#6B7280', fontFamily: font, lineHeight: 1.5 }}>
            Пополняется по СБП по тому же курсу. Оплата выпуска и пополнения карт с баланса — без комиссии СБП,
            только по цене услуги.
          </div>
        </Card>
      </Section>

      {/* Referral program */}
      <Section>
        <Card padding="20px">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 14, flexShrink: 0,
              background: 'linear-gradient(135deg, #10B981 0%, #34D399 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22,
            }}>🎁</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: '#111827', fontFamily: font }}>Приглашайте друзей</div>
              <div style={{ fontSize: 13, color: '#6B7280', fontFamily: font, marginTop: 2, lineHeight: 1.4 }}>
                {refPercent > 0
                  ? `Получайте ${refPercent}% от каждой покупки друга — выпуска и пополнения карт — на внутренний баланс.`
                  : 'Делитесь ссылкой — бонусы за покупки друзей зачисляются на внутренний баланс.'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
            <div style={{ flex: 1, background: '#F3F5F8', borderRadius: 12, padding: '10px 12px' }}>
              <div style={{ fontSize: 11, color: '#9CA3AF', fontFamily: font, fontWeight: 600 }}>Приглашено</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', fontFamily: font }}>{profile?.referrals_count ?? 0}</div>
            </div>
            <div style={{ flex: 1, background: '#F3F5F8', borderRadius: 12, padding: '10px 12px' }}>
              <div style={{ fontSize: 11, color: '#9CA3AF', fontFamily: font, fontWeight: 600 }}>Заработано</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#10B981', fontFamily: font }}>{money(profile?.referral_earned_usd)}</div>
            </div>
          </div>

          <div
            onClick={copyRef}
            style={{
              marginTop: 12, background: '#F3F5F8', borderRadius: 12, padding: '10px 12px',
              display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
            }}
          >
            <div style={{ flex: 1, minWidth: 0, fontSize: 12, color: '#374151', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {refLink || 'Загружаем ссылку…'}
            </div>
            <CopyIcon color="#6B7280" />
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button
              onClick={copyRef}
              className="transition-transform duration-150 active:scale-95"
              style={{ flex: 1, border: 'none', background: '#F3F5F8', color: '#111827', borderRadius: 12, padding: '12px 0', fontSize: 14, fontWeight: 600, fontFamily: font, cursor: 'pointer' }}
            >
              Скопировать
            </button>
            <button
              onClick={shareRef}
              className="transition-transform duration-150 active:scale-95"
              style={{ flex: 1, border: 'none', background: '#DC4D35', color: '#fff', borderRadius: 12, padding: '12px 0', fontSize: 14, fontWeight: 600, fontFamily: font, cursor: 'pointer' }}
            >
              Поделиться
            </button>
          </div>
          <div style={{ fontSize: 11, color: '#9CA3AF', fontFamily: font, marginTop: 10, lineHeight: 1.5 }}>
            Бонус начисляется только за новых пользователей, которые впервые откроют приложение по вашей ссылке.
          </div>
        </Card>
      </Section>

      {/* SBP payer phone */}
      {payerPhone && (
        <Section>
          <Card padding="18px 20px">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{
                width: 46, height: 46, borderRadius: 23, flexShrink: 0,
                background: 'linear-gradient(135deg, #DC4D35 0%, #E8785F 100%)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" fill="#FFFFFF"/>
                </svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>Телефон для оплат по СБП</div>
                {!phoneEditing && (
                  <div style={{ fontSize: 12, color: phoneSaved ? '#10B981' : '#6B7280', fontFamily: font, marginTop: 1 }}>
                    {phoneSaved ? '✓ Сохранено — данные обновлены' : formatPhone(payerPhone)}
                  </div>
                )}
              </div>
              {!phoneEditing && (
                <button
                  onClick={() => { setPhoneDraft(formatPhone(payerPhone)); setPhoneError(''); setPhoneEditing(true) }}
                  style={{ border: 'none', background: '#F3F5F8', color: '#DC4D35', borderRadius: 10, padding: '9px 14px', fontSize: 13, fontWeight: 600, fontFamily: font, cursor: 'pointer', flexShrink: 0 }}
                >
                  Изменить
                </button>
              )}
            </div>
            {phoneEditing && (
              <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="tel"
                    value={phoneDraft}
                    onChange={(e) => setPhoneDraft(formatPhone(e.target.value))}
                    placeholder="+7 (9XX) XXX-XX-XX"
                    autoFocus
                    style={{
                      flex: 1, padding: '12px 14px', borderRadius: 12, fontSize: 15, fontWeight: 600,
                      fontFamily: font, border: phoneError ? '1.5px solid #EF4444' : '1.5px solid #DC4D35',
                      outline: 'none', color: '#111827', background: '#FFFFFF', minWidth: 0,
                    }}
                  />
                  <button
                    onClick={savePayerPhone}
                    disabled={phoneSaving}
                    style={{ border: 'none', background: '#DC4D35', color: '#fff', borderRadius: 12, padding: '0 16px', fontSize: 13, fontWeight: 600, fontFamily: font, cursor: 'pointer' }}
                  >
                    {phoneSaving ? '…' : 'Сохранить'}
                  </button>
                  <button
                    onClick={() => { setPhoneEditing(false); setPhoneError('') }}
                    style={{ border: 'none', background: '#F3F5F8', color: '#6B7280', borderRadius: 12, padding: '0 13px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
                  >
                    ✕
                  </button>
                </div>
                {phoneError && <div style={{ fontSize: 12, color: '#EF4444', fontFamily: font }}>{phoneError}</div>}
                <div style={{ fontSize: 11, color: '#9CA3AF', fontFamily: font, lineHeight: 1.5 }}>
                  Укажите номер, привязанный к банковскому счёту, с которого платите по СБП.
                  После сохранения проверка соответствия ФИО и номера пройдёт заново.
                </div>
              </div>
            )}
          </Card>
        </Section>
      )}

      {/* Balance operations */}
      <Section>
        <Card padding="20px">
          <h2 style={{ fontSize: 20, fontWeight: 700, color: '#111827', fontFamily: font, margin: 0 }}>Операции по балансу</h2>
          {ledger.length === 0 ? (
            <div style={{ paddingTop: 22, paddingBottom: 8, textAlign: 'center', fontSize: 13, fontWeight: 600, color: '#6B7280', fontFamily: font }}>
              Пока нет операций
            </div>
          ) : (
            <div style={{ marginTop: 8 }}>
              {ledger.map((row, idx) => {
                const meta = LEDGER_META[row.type] || { label: row.type, icon: '/images/HistoryIcons/shop.png' }
                const positive = row.amount > 0
                const abs = Math.abs(row.amount)
                const d = row.created_at ? new Date(row.created_at + (row.created_at.endsWith('Z') ? '' : 'Z')) : null
                const dateStr = d ? d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
                return (
                  <div key={row.id} style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 14, paddingBottom: 14, borderBottom: idx < ledger.length - 1 ? '1px solid #F3F5F8' : 'none' }}>
                    <div style={{ width: 40, height: 40, borderRadius: 12, background: '#F3F5F8', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <img src={meta.icon} alt="" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', fontFamily: font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{meta.label}</div>
                      <div style={{ fontSize: 12, color: '#6B7280', fontFamily: font, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {dateStr}{row.description ? ` · ${row.description}` : ''}
                      </div>
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: positive ? '#22C55E' : '#111827', fontFamily: font, flexShrink: 0 }}>
                      {positive ? '+' : '−'}{abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </Section>

      <BalanceDepositModal
        isOpen={showDeposit}
        onClose={() => { setShowDeposit(false); load(); fetchMe?.() }}
        onDeposited={load}
      />
    </div>
  )
}
