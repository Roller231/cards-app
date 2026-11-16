import test from 'node:test'
import assert from 'node:assert/strict'
import { kycSessionId, openKycBrowser, loadKycWidget } from '../src/utils/kycWidget.js'

test('NeuroVision JSON-string and object callbacks return the session id', () => {
  assert.equal(kycSessionId('{"sessionId":"own-session"}'), 'own-session')
  assert.equal(kycSessionId({ sessionId: 'own-session' }), 'own-session')
  assert.equal(kycSessionId('broken json'), null)
  assert.equal(kycSessionId(null), null)
})

test('browser handoff uses the existing verification link through Telegram', () => {
  const calls = []
  globalThis.window = { Telegram: { WebApp: { openLink: (...args) => calls.push(args) } } }
  const link = 'https://kyc.neuro-vision.ru/scenario/encoded-key/11'
  assert.equal(openKycBrowser(link), true)
  assert.deepEqual(calls, [[link, { try_instant_view: false }]])
  assert.throws(() => openKycBrowser('https://other.example/session'))
})

test('browser handoff falls back when the Telegram bridge throws', () => {
  const calls = []
  globalThis.window = { Telegram: { WebApp: { openLink: () => { throw new Error('bridge unavailable') } } }, open: (...args) => { calls.push(args); return null } }
  const link = 'https://kyc.neuro-vision.ru/scenario/key/11'
  assert.equal(openKycBrowser(link), false)
  assert.deepEqual(calls, [[link, '_blank', 'noopener,noreferrer']])
})

test('failed widget download is removed and a subsequent attempt loads again', async () => {
  const scripts = []
  let removed = 0
  globalThis.window = {}
  globalThis.document = {
    getElementById: () => null,
    createElement: () => ({ remove: () => { removed++ } }),
    head: { appendChild: script => scripts.push(script) },
  }
  const first = loadKycWidget()
  assert.equal(loadKycWidget(), first)
  scripts[0].onerror()
  await assert.rejects(first)
  assert.equal(removed, 1)
  const second = loadKycWidget()
  window.KYCWidget = { setupKYC() {} }
  scripts[1].onload()
  assert.equal(await second, window.KYCWidget)
  assert.equal(scripts.length, 2)
})
