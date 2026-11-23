import Button from './ui/Button'

export default function HistoryStatus({ status, onRetry }) {
  if (status === 'ready') return null
  return (
    <div role="status" style={{ padding: 16, color: '#6B7280', fontSize: 14 }}>
      {status === 'error' ? (
        <>Не удалось загрузить все операции. <Button variant="link" onClick={onRetry}>Повторить</Button></>
      ) : 'Загружаем операции…'}
    </div>
  )
}
