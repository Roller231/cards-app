import { Component, Suspense } from 'react'

class ScreenErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return <div className="screen-status" role="alert">
        <p>Не удалось открыть раздел.</p>
        <button onClick={() => window.location.reload()}>Обновить приложение</button>
      </div>
    }
    return this.props.children
  }
}

export default function ScreenLoader({ children, page }) {
  return <Suspense fallback={<div className="screen-status" role="status">Загрузка…</div>}>
    <ScreenErrorBoundary key={page}>{children}</ScreenErrorBoundary>
  </Suspense>
}
