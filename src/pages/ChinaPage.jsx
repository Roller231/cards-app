import Card from '../components/ui/Card'
import Section from '../components/ui/Section'
import { BOTTOM_BAR_SPACE } from '../components/BottomBar'

const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'
const CHANNEL_URL = 'https://t.me/exprontopay'

function openChannel() {
  const tg = window?.Telegram?.WebApp
  if (tg?.openTelegramLink) tg.openTelegramLink(CHANNEL_URL)
  else window.open(CHANNEL_URL, '_blank', 'noopener')
}

const POINTS = [
  { icon: '🛍', title: 'Покупки в Китае', text: 'Оплачивайте в магазинах, кафе и такси по QR-коду, как местные.' },
  { icon: '📱', title: 'Онлайн-сервисы', text: 'Оплата китайских сервисов и продавцов, которые принимают только местные кошельки.' },
  { icon: '⚡', title: 'Прямо из ProntoPay', text: 'Пополнение по СБП и оплата в пару нажатий, без поиска посредников.' },
]

/**
 * "Китай" tab: Alipay & WeChat Pay. The mechanics are not final yet, so for
 * now this is a "coming soon" page; later it becomes the "Сервисы" section.
 */
export default function ChinaPage() {
  return (
    <div className="flex-1 flex flex-col" style={{ paddingBottom: BOTTOM_BAR_SPACE }}>
      <Section>
        <div style={{
          position: 'relative', overflow: 'hidden', borderRadius: 20, padding: '24px 20px',
          background: 'linear-gradient(135deg, #DC4D35 0%, #E8785F 100%)', color: '#FFFFFF', fontFamily: font,
        }}>
          <div style={{
            position: 'absolute', right: -30, top: -30, width: 150, height: 150, borderRadius: '50%',
            background: 'rgba(255,255,255,0.12)',
          }} />
          <div style={{
            display: 'inline-block', fontSize: 12, fontWeight: 700, padding: '4px 10px', borderRadius: 8,
            background: 'rgba(255,255,255,0.22)', marginBottom: 14,
          }}>
            Скоро
          </div>
          <div style={{ position: 'relative', fontSize: 26, fontWeight: 800, lineHeight: 1.15 }}>
            Alipay и WeChat Pay
          </div>
          <div style={{ position: 'relative', fontSize: 14, lineHeight: 1.5, marginTop: 10, color: 'rgba(255,255,255,0.9)' }}>
            Готовим оплату в Китае через самые популярные кошельки страны.
          </div>
        </div>
      </Section>

      <Section>
        <Card padding="8px 20px">
          {POINTS.map((p, idx) => (
            <div key={p.title} style={{
              display: 'flex', gap: 14, alignItems: 'flex-start', padding: '14px 0',
              borderBottom: idx < POINTS.length - 1 ? '1px solid #F3F5F8' : 'none',
            }}>
              <div style={{
                width: 40, height: 40, borderRadius: 12, background: '#F3F5F8', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20,
              }}>{p.icon}</div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>{p.title}</div>
                <div style={{ fontSize: 13, color: '#6B7280', fontFamily: font, marginTop: 3, lineHeight: 1.45 }}>{p.text}</div>
              </div>
            </div>
          ))}
        </Card>
      </Section>

      <Section>
        <button
          onClick={openChannel}
          className="transition-transform duration-150 active:scale-[0.98]"
          style={{
            width: '100%', border: 'none', cursor: 'pointer', borderRadius: 14, padding: '16px 0',
            background: '#111827', color: '#FFFFFF', fontSize: 15, fontWeight: 600, fontFamily: font,
          }}
        >
          Узнать о запуске первым
        </button>
        <div style={{ fontSize: 12, color: '#9CA3AF', fontFamily: font, textAlign: 'center', marginTop: 8 }}>
          Напишем о запуске в нашем Telegram-канале
        </div>
      </Section>
    </div>
  )
}
