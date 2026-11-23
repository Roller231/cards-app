const PERIOD = 30_000

export function appIsVisible() {
  return document.visibilityState === 'visible' && window.Telegram?.WebApp?.isActive !== false
}

export function startBalancePolling(refresh) {
  const tg = window.Telegram?.WebApp
  let next = Date.now() + PERIOD
  let timer
  let stopped = false
  let busy = false
  let telegramActive = tg?.isActive !== false

  function schedule() {
    clearTimeout(timer)
    if (!stopped && !busy && telegramActive && appIsVisible()) {
      timer = setTimeout(tick, Math.max(0, next - Date.now()))
    }
  }

  async function tick() {
    if (stopped || busy || !telegramActive || !appIsVisible()) return
    busy = true
    next = Date.now() + PERIOD
    try {
      await refresh()
    } finally {
      busy = false
      if (next <= Date.now()) next = Date.now() + PERIOD
      schedule()
    }
  }

  function activate() { telegramActive = true; schedule() }
  function deactivate() { telegramActive = false; clearTimeout(timer) }
  document.addEventListener('visibilitychange', schedule)
  tg?.onEvent?.('activated', activate)
  tg?.onEvent?.('deactivated', deactivate)
  schedule()
  return () => {
    stopped = true
    clearTimeout(timer)
    document.removeEventListener('visibilitychange', schedule)
    tg?.offEvent?.('activated', activate)
    tg?.offEvent?.('deactivated', deactivate)
  }
}
