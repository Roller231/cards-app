import { useEffect, useState } from 'react'
import PageHeader from '../components/ui/PageHeader'

function FAQPage({ onBack }) {
  const [expandedItem, setExpandedItem] = useState(null)

  useEffect(() => {
    const tg = window?.Telegram?.WebApp
    if (!tg?.BackButton) return

    tg.BackButton.show()
    tg.BackButton.onClick(onBack)

    return () => {
      tg.BackButton.hide()
      tg.BackButton.offClick(onBack)
    }
  }, [onBack])

  const faqItems = [
    {
      id: 1,
      question: 'Зачем нужна виртуальная карта Pronto?',
      answer: 'Наша виртуальная карта позволяет оплачивать покупки и подписки на все возможные международные сервисы. Также есть возможность подключить карту к Apple и Google pay прямо на вашем телефоне и оплачивать покупки оффлайн через терминал, находясь в другой стране.',
    },
    {
      id: 2,
      question: 'Как я могу получить виртуальную карту?',
      answer: 'Оформляйте карту прямо в приложении, для оформления не требуется верификация.',
    },
    {
      id: 3,
      question: 'Какие виды карт доступны в приложении?',
      answer: 'Мы предлагаем 2 типа карт:\n\n• Для подписок и покупок онлайн\n• Для подписок + ApplePay и GooglePay — для бесконтактной оплаты за рубежом',
    },
    {
      id: 4,
      question: 'Какие комиссии и лимиты у виртуальных карт?',
      answer: 'Выпуск карты: $0\nКомиссия за каждую операцию: 0,4$ (Комиссия списывается, даже если операция оказалась отклонена)\n\nПополнение:\n• Для подписок и покупок онлайн - 3,8%\n• Для подписок + ApplePay и GooglePay - 4,0%\n\nЛимит на одну операцию: до $50 000\nОбщий лимит карты: до $2 000 000\nСрок действия: 1 год',
    },
    {
      id: 5,
      question: 'Как можно пополнить карту?',
      answer: 'Пополнение осуществляется через наше приложение в usdt или через сбп.',
    },
    {
      id: 6,
      question: 'Можно ли снимать наличные с карты?',
      answer: 'Нет, карта не поддерживает снятие наличных и перевод. Карта предназначена только для оплаты!',
    },
    {
      id: 7,
      question: 'Нужно ли проходить верификацию?',
      answer: 'Для оформления и пополнения виртуальных карт верификация не требуется.',
    },
    {
      id: 8,
      question: 'В какой валюте виртуальная карта?',
      answer: 'При пополнении средства автоматически конвертируются в USD, однако оплата покупок происходит в валюте соответствующей страны конкретного сервиса или магазина, конвертация в другую валюту происходит автоматически, ваш баланс и транзакции будут отображаться в USD.',
    },
    {
      id: 9,
      question: 'Во всех ли регионах работает карта?',
      answer: 'Карта работает в большинстве стран за исключением территорий, где оплата недоступна из-за требования платежных систем.\n\nКарта не работает в следующих регионах: Россия, Беларусь, Китай, Афганистан, Иран, Северная Корея, Венесуэла. Если сервис зарегистрирован в одной из этих стран, платеж будет отклонен.',
    },
    {
      id: 10,
      question: 'Может ли транзакция быть отменена?',
      answer: 'Да, причинами может быть:\n\n• Покупка товаров или услуг у сервиса из списка запрещенных стран\n• Покупка товаров или услуг у запрещенных сервисов (казино, ставки, взрослый контент, продажа запрещенных веществ, снятие наличных также запрещено по этой карте, операция будет отменена)\n• Недостаточный баланс для совершения операции (учитывайте комиссию за операцию), при оплате в другой валюте учитывайте конвертацию (советуем держать баланс с запасом)\n• Оплата товаров с запрещенного региона (учитывайте, что некоторые сервисы могут ограничивать операции из-за региона, например, если продавец поставил запрет для пользователей из России) Совет: используйте vpn, лучше всего, если будет IP Гонконга, это связано с бином карты (BIN-Гонконг)',
    },
    {
      id: 11,
      question: 'Что делать, если платеж отменен?',
      answer: 'При успешном возврате средства зачисляются обратно на ваш баланс. Сроки возврата зависят от продавца.\n\nВажно отметить, что банк-эмитент крайне негативно относится к любым возвратам, поэтому частые отмены могут привести к блокировки карты.\n\nСовет: проверяйте баланс перед оплатой, всегда учитывайте комиссии за транзакции, если оплачиваете подписки на зарубежные сервисы, используйте vpn.',
    },
  ]

  return (
    <div className="flex-1 flex flex-col pb-10">
      <PageHeader title="FAQ" onBack={onBack} />

      <div className="px-4 flex flex-col gap-3" style={{ paddingTop: 72 }}>
        {faqItems.map((item) => {
          const isExpanded = expandedItem === item.id

          return (
            <div
              key={item.id}
              className="bg-white"
              style={{
                borderRadius: 16,
                overflow: 'hidden',
              }}
            >
              <button
                onClick={() => setExpandedItem(isExpanded ? null : item.id)}
                className="w-full flex items-center justify-between transition-transform duration-150 active:scale-[0.98]"
                style={{
                  padding: '16px 20px',
                  border: 'none',
                  background: 'white',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <span
                  style={{
                    fontSize: 15,
                    fontWeight: 600,
                    color: '#111827',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    paddingRight: 12,
                  }}
                >
                  {item.question}
                </span>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 14 14"
                  fill="none"
                  style={{
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                    flexShrink: 0,
                  }}
                >
                  <path
                    d="M3 5L7 9L11 5"
                    stroke="#6B7280"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>

              <div
                style={{
                  maxHeight: isExpanded ? 500 : 0,
                  opacity: isExpanded ? 1 : 0,
                  overflow: 'hidden',
                  transition: 'max-height 300ms ease, opacity 200ms ease',
                }}
              >
                <div
                  style={{
                    padding: '0 20px 16px 20px',
                    fontSize: 14,
                    fontWeight: 400,
                    color: '#6B7280',
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
                    lineHeight: '20px',
                  }}
                >
                  {item.answer}
                </div>
              </div>
            </div>
          )
        })}

<div
  style={{
    fontSize: 14,
    fontWeight: 600,
    color: '#111827',
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
    lineHeight: '20px',
    textAlign: 'left',
    padding: '20px 20px 24px 20px',
  }}
>
  Если не нашли ответ на вопрос, обратитесь в нашу поддержку. Спасибо за доверие!
</div>
      </div>
    </div>
  )
}

export default FAQPage
