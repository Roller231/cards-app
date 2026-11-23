import assert from 'node:assert/strict'
import test from 'node:test'
import { startBalancePolling } from '../src/utils/balancePolling.js'

function setup(t, refresh) {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 0 })
  const doc = new EventTarget()
  doc.visibilityState = 'visible'
  const events = new EventTarget()
  const tg = {
    onEvent: (name, fn) => events.addEventListener(name, fn),
    offEvent: (name, fn) => events.removeEventListener(name, fn),
  }
  globalThis.document = doc
  globalThis.window = { Telegram: { WebApp: tg } }
  const stop = startBalancePolling(refresh)
  t.after(() => { stop(); delete globalThis.document; delete globalThis.window })
  return {
    visibility(value) { doc.visibilityState = value; doc.dispatchEvent(new Event('visibilitychange')) },
    telegram(name) { events.dispatchEvent(new Event(name)) },
    stop,
  }
}

test('polls after 30s in foreground and refreshes once on overdue return', async t => {
  const refresh = t.mock.fn()
  const app = setup(t, refresh)
  t.mock.timers.tick(29_999)
  assert.equal(refresh.mock.callCount(), 0)
  t.mock.timers.tick(1)
  await Promise.resolve()
  assert.equal(refresh.mock.callCount(), 1)
  app.visibility('hidden')
  t.mock.timers.tick(90_000)
  assert.equal(refresh.mock.callCount(), 1)
  app.visibility('visible')
  app.telegram('activated')
  t.mock.timers.tick(0)
  assert.equal(refresh.mock.callCount(), 2)
  await Promise.resolve()
  app.telegram('deactivated')
  t.mock.timers.tick(60_000)
  assert.equal(refresh.mock.callCount(), 2)
  app.telegram('activated')
  t.mock.timers.tick(0)
  assert.equal(refresh.mock.callCount(), 3)
  app.stop()
  await Promise.resolve()
  t.mock.timers.tick(60_000)
  assert.equal(refresh.mock.callCount(), 3)
})

test('slow response cannot overlap another tick or restart polling after unmount', async t => {
  let resolve
  const refresh = t.mock.fn(() => new Promise(done => { resolve = done }))
  const app = setup(t, refresh)
  t.mock.timers.tick(30_000)
  app.visibility('hidden')
  app.visibility('visible')
  t.mock.timers.tick(120_000)
  assert.equal(refresh.mock.callCount(), 1)
  app.stop()
  resolve()
  await Promise.resolve()
  t.mock.timers.tick(60_000)
  assert.equal(refresh.mock.callCount(), 1)
})
