// Yandex.Metrika helpers. The app is an SPA without URL routing (pages are
// React state), so Metrika would only ever see one pageview per session —
// we report virtual pageviews and funnel goals manually.
//
// Every call is wrapped: if the counter script is blocked or not loaded yet,
// the app must keep working silently.

const COUNTER_ID = 111788180

function ymSafe(...args) {
  try {
    if (typeof window !== 'undefined' && typeof window.ym === 'function') {
      window.ym(COUNTER_ID, ...args)
    }
  } catch {
    /* analytics must never break the app */
  }
}

/** Virtual pageview for an SPA page (e.g. metrikaHit('issue-card')). */
export function metrikaHit(page) {
  const url = `/${String(page || '').replace(/^\/+/, '')}`
  ymSafe('hit', url, { title: url })
}

/** Conversion goal (create matching goals in Metrika as "JavaScript event"). */
export function metrikaGoal(name, params) {
  if (!name) return
  ymSafe('reachGoal', name, params || {})
}
