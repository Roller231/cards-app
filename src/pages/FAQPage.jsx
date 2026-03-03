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
      answer: 'Наша виртуальная карта позволяет оплачивать покупки и подписки на все зарубежные международные сервисы. Также есть возможность привязать карту к ApplePay и GooglePay для оплаты в телефоне и оплачивать покупки офлайн через ApplePay и GooglePay в других странах.',
    },
    {
      id: 2,
      question: 'Как я могу получить виртуальную карту?',
      answer: 'Для получения виртуальной карты необходимо зарегистрироваться в приложении и выбрать подходящий тариф.',
    },
    {
      id: 3,
      question: 'Какие виды карт доступны в приложении?',
      answer: 'В приложении доступны различные виды виртуальных карт для разных целей использования.',
    },
    {
      id: 4,
      question: 'Какие комиссии и лимиты у виртуальных карт?',
      answer: 'Комиссии и лимиты зависят от выбранного тарифа. Подробную информацию можно посмотреть в описании каждой карты.',
    },
    {
      id: 5,
      question: 'Как можно пополнить карту?',
      answer: 'Карту можно пополнить различными способами, включая банковский перевод и криптовалюту.',
    },
    {
      id: 6,
      question: 'Можно ли снимать наличные с карты?',
      answer: 'Виртуальные карты предназначены для онлайн-платежей и не поддерживают снятие наличных.',
    },
    {
      id: 7,
      question: 'Нужно ли проходить верификацию?',
      answer: 'Верификация может потребоваться в зависимости от выбранного тарифа и лимитов.',
    },
    {
      id: 8,
      question: 'В какой валюте виртуальная карта?',
      answer: 'Виртуальные карты выпускаются в долларах США (USD).',
    },
    {
      id: 9,
      question: 'Во всех ли регионах работает карта?',
      answer: 'Карта работает в большинстве регионов, где принимаются международные платежные системы.',
    },
    {
      id: 10,
      question: 'Может ли транзакция быть отменена?',
      answer: 'Отмена транзакции зависит от политики продавца. Обратитесь в службу поддержки для уточнения.',
    },
    {
      id: 11,
      question: 'Что делать, если платеж отменен?',
      answer: 'Если платеж отменен, средства вернутся на карту в течение нескольких рабочих дней.',
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
