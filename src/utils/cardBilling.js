// Addresses already stored on a card retain their country. A Pay artwork or
// the currently available Online BIN must never relabel an existing address.
const LEGACY_CARD_DATA = [
  { label: 'Имя владельца', value: 'Howard Willis' },
  { label: 'Адрес', value: 'Singapore 160 Lor 1 Toa Payoh #01-1564' },
  { label: 'Страна', value: 'Singapore' },
  { label: 'Почтовый индекс', value: '310160' },
]

export function cardDataRows(card) {
  if (!card?.billing_address) return LEGACY_CARD_DATA
  const country = card.billing_country || 'Singapore'
  const isSingapore = ['singapore', 'sg', 'сингапур'].includes(country.trim().toLowerCase())
  const postal = isSingapore ? String(card.billing_postal ?? '').trim() : ''
  return [
    { label: 'Имя владельца', value: card.billing_name },
    { label: 'Адрес', value: card.billing_address },
    { label: 'Страна', value: country },
    postal && {
      label: 'Почтовый индекс',
      value: postal,
    },
  ].filter(Boolean)
}
