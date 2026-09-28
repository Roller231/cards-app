const font = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

const fmtRub = (v) => `${Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ₽`
const fmtRate = (v) => `${Number(v).toFixed(2)} ₽/$`

function Row({ label, value, muted = false, strong = false, top = false }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12,
      paddingTop: top ? 10 : 0, marginTop: top ? 4 : 0, borderTop: top ? '1px solid #EEF0F3' : 'none',
    }}>
      <span style={{ fontSize: strong ? 14 : 13, color: muted ? '#6B7280' : '#111827', fontWeight: strong ? 700 : 400, fontFamily: font, lineHeight: 1.35 }}>
        {label}
      </span>
      <span style={{ fontSize: strong ? 17 : 13, color: muted ? '#6B7280' : '#111827', fontWeight: strong ? 700 : 600, fontFamily: font, whiteSpace: 'nowrap' }}>
        {value}
      </span>
    </div>
  )
}

/**
 * How the exchange rate becomes the amount the user pays by SBP: every
 * partner fee is listed separately, so the payment rate is fully explained
 * before the QR is created.
 *
 * rateInfo: /sbp/rate response (base_rate, rate, fees[]).
 */
export default function RateBreakdown({ rateInfo, amountUsd, baseRub, feeApplied, smallFee, smallThreshold, payRub, rateError }) {
  if (!amountUsd) {
    return <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>—</div>
  }
  if (rateError) {
    return <div style={{ fontSize: 15, fontWeight: 600, color: '#111827', fontFamily: font }}>недоступно</div>
  }
  if (!rateInfo?.rate || payRub === null) {
    return <div style={{ fontSize: 15, fontWeight: 600, color: '#6B7280', fontFamily: font }}>загружаем курс…</div>
  }
  const baseRate = Number(rateInfo.base_rate ?? rateInfo.index ?? rateInfo.rate)
  const fees = Array.isArray(rateInfo.fees) ? rateInfo.fees.filter((f) => Number(f.percent) > 0) : []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      <Row label="Биржевой курс" value={fmtRate(baseRate)} />
      {fees.map((f) => (
        <Row key={f.label} label={f.label} value={`+${Number(f.percent).toLocaleString('ru-RU')}%`} muted />
      ))}
      <Row label="Курс с учётом комиссий партнёров" value={fmtRate(rateInfo.rate)} top />
      <Row label={`${Number(amountUsd).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} $ по этому курсу`} value={fmtRub(baseRub)} muted />
      {feeApplied > 0 && (
        <Row
          label={`Комиссия платёжной системы за платёж до ${Number(smallThreshold).toLocaleString('ru-RU')} ₽`}
          value={`+${fmtRub(smallFee)}`}
          muted
        />
      )}
      <Row label="К оплате по СБП" value={fmtRub(payRub)} strong top />
      {feeApplied > 0 && (
        <div style={{ fontSize: 11, color: '#9CA3AF', fontFamily: font, lineHeight: 1.45 }}>
          При оплате от {Number(smallThreshold).toLocaleString('ru-RU')} ₽ комиссия {fmtRub(smallFee)} не взимается.
        </div>
      )}
    </div>
  )
}
