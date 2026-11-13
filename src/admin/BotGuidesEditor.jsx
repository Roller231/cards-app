import { useState } from 'react'
import adminApi from './api'

const field = { width: '100%', boxSizing: 'border-box', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13 }
const action = { border: '1px solid #d1d5db', borderRadius: 7, padding: '6px 10px', background: '#fff', cursor: 'pointer', fontSize: 12 }

export default function BotGuidesEditor({ value, onChange, onBusyChange }) {
  const [uploading, setUploading] = useState(null)
  const [error, setError] = useState('')
  const change = (id, patch) => onChange(value.map(item => item.id === id ? { ...item, ...patch } : item))
  const move = (index, step) => {
    const items = [...value]
    ;[items[index], items[index + step]] = [items[index + step], items[index]]
    onChange(items)
  }
  async function upload(id, event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (file.size > 50 * 1024 * 1024) { setError('Видео должно быть не больше 50 МБ.'); return }
    setUploading(id); onBusyChange(true); setError('')
    try {
      const result = await adminApi.bot.uploadGuideVideo(file)
      change(id, { ...result, has_video: true })
    } catch (e) { setError(e.message || 'Не удалось загрузить видео') }
    finally { setUploading(null); onBusyChange(false) }
  }
  return <section style={{ marginTop: 20 }}>
    <h3 style={{ fontSize: 15, margin: '0 0 8px' }}>Кнопки-инструкции</h3>
    <p style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.6, margin: '0 0 12px' }}>
      Эти кнопки появляются под приветствием после кнопок-ссылок. Видео или текст приходят только по нажатию на нужную инструкцию.
      После изменений нажмите «Сохранить настройки».
    </p>
    {error && <div role="alert" style={{ color: '#b91c1c', fontSize: 13, marginBottom: 10 }}>{error}</div>}
    {value.map((item, index) => <div key={item.id} style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: 12, marginBottom: 12 }}>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between', flexWrap: 'wrap', marginBottom: 10 }}>
        <label style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={item.enabled} disabled={!!uploading} onChange={e => change(item.id, { enabled: e.target.checked })} /> Показывать кнопку
        </label>
        <div style={{ display: 'flex', gap: 5 }}>
          <button type="button" aria-label="Выше" style={action} disabled={!!uploading || index === 0} onClick={() => move(index, -1)}>↑</button>
          <button type="button" aria-label="Ниже" style={action} disabled={!!uploading || index === value.length - 1} onClick={() => move(index, 1)}>↓</button>
          <button type="button" style={{ ...action, color: '#b91c1c' }} disabled={!!uploading} onClick={() => {
            if (window.confirm(`Удалить инструкцию «${item.title}»? Изменение применится после сохранения.`)) onChange(value.filter(guide => guide.id !== item.id))
          }}>Удалить</button>
        </div>
      </div>
      <label style={{ display: 'block', fontSize: 12, marginBottom: 10 }}>Текст кнопки
        <input style={{ ...field, marginTop: 4 }} value={item.title} maxLength={64} disabled={!!uploading} onChange={e => change(item.id, { title: e.target.value })} />
      </label>
      <label style={{ display: 'block', fontSize: 12, marginBottom: 10 }}>Текст инструкции (HTML)
        <textarea style={{ ...field, marginTop: 4, resize: 'vertical' }} rows={4} maxLength={4096} value={item.text} disabled={!!uploading} onChange={e => change(item.id, { text: e.target.value })} />
      </label>
      {item.video_url && <video key={item.video_url} controls playsInline preload="none" src={item.video_url} style={{ width: '100%', maxHeight: 220, background: '#111827', borderRadius: 8, marginBottom: 8 }} />}
      {!item.video_url && item.video_key && <p style={{ color: '#b45309', fontSize: 12 }}>Видео ещё не загружено. Добавьте MP4 ниже.</p>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <label style={{ ...action, display: 'inline-block', background: '#f3f4f6' }}>
          {uploading === item.id ? 'Загружаем видео…' : item.video_url ? 'Заменить видео' : '+ Загрузить видео'}
          <input type="file" accept="video/mp4,.mp4" disabled={!!uploading} onChange={event => upload(item.id, event)} style={{ display: 'none' }} />
        </label>
        {item.video_key && <button type="button" style={action} disabled={!!uploading} onClick={() => change(item.id, { video_key: null, video_url: null, has_video: false })}>Убрать видео</button>}
        <span style={{ fontSize: 11, color: '#6b7280' }}>MP4, до 50 МБ. Можно оставить только текст.</span>
      </div>
    </div>)}
    <button type="button" disabled={!!uploading || value.length >= 20} style={{ ...action, color: '#6366f1' }} onClick={() => onChange([...value, {
      id: crypto.randomUUID(), title: 'Новая инструкция', text: '', enabled: true, video_key: null,
    }])}>+ Добавить инструкцию</button>
  </section>
}
