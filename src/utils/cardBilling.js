// Addresses already stored on a card retain their country. A Pay artwork or
// the currently available Online BIN must never relabel an existing address.
export const HK_POSTAL_PLACEHOLDER = '000000'

const LEGACY_CARD_DATA = [
  { label: 'Имя владельца', value: 'Howard Willis' },
  { label: 'Адрес', value: 'Singapore 160 Lor 1 Toa Payoh #01-1564' },
  { label: 'Страна', value: 'Singapore' },
  { label: 'Почтовый индекс', value: '310160' },
]

export function cardDataRows(card) {
  if (!card?.billing_address) return LEGACY_CARD_DATA
  const country = card.billing_country || 'Singapore'
  const isHongKong = ['hong kong', 'hongkong', 'hk', 'гонконг'].includes(country.trim().toLowerCase())
  // Older HK cards have NULL here. Display a form placeholder without
  // regenerating or changing the saved card identity.
  const postal = String(card.billing_postal ?? '').trim() || (isHongKong ? HK_POSTAL_PLACEHOLDER : '')
  return [
    { label: 'Имя владельца', value: card.billing_name },
    { label: 'Адрес', value: card.billing_address },
    { label: 'Страна', value: country },
    postal && {
      label: 'Почтовый индекс',
      value: postal,
      ...(isHongKong && postal === HK_POSTAL_PLACEHOLDER
        ? { hint: 'В Гонконге нет почтовых индексов. Укажите 000000, если форма требует индекс.' }
        : {}),
    },
  ].filter(Boolean)
}
