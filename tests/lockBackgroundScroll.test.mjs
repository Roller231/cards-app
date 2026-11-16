import test from 'node:test'
import assert from 'node:assert/strict'
import { lockBackgroundScroll } from '../src/utils/lockBackgroundScroll.js'

test('verification freezes the page and restores its position only after the last close', () => {
  const root = { inert: false }
  const style = { position: '', top: '', left: '', width: '', overflow: '', overscrollBehavior: '', paddingRight: '' }
  const htmlStyle = { overflow: '', overscrollBehavior: '' }
  const restored = []
  globalThis.window = { scrollX: 0, scrollY: 420, innerWidth: 390, scrollTo: (...p) => restored.push(p) }
  globalThis.document = { body: { style }, documentElement: { style: htmlStyle, clientWidth: 390 }, getElementById: () => root }
  const closeFirst = lockBackgroundScroll()
  assert.equal(style.position, 'fixed')
  assert.equal(style.top, '-420px')
  assert.equal(htmlStyle.overflow, 'hidden')
  assert.equal(root.inert, true)
  const closeSecond = lockBackgroundScroll()
  closeFirst()
  assert.equal(style.position, 'fixed')
  assert.equal(restored.length, 0)
  closeSecond()
  closeSecond()
  assert.equal(style.position, '')
  assert.equal(style.top, '')
  assert.equal(root.inert, false)
  assert.deepEqual(restored, [[0, 420]])
})
