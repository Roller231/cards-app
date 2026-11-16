import assert from 'node:assert/strict'
import test from 'node:test'
import { formatOperationDate, parseOperationDate } from '../src/utils/operationDates.js'

test('naive backend dates are interpreted as UTC', () => {
  assert.equal(parseOperationDate('2026-10-28T19:58:47').toISOString(), '2026-10-28T19:58:47.000Z')
})

test('explicit timezone offsets are preserved across midnight', () => {
  assert.equal(parseOperationDate('2026-11-13T00:30:00+03:00').toISOString(), '2026-11-12T21:30:00.000Z')
  assert.equal(parseOperationDate('2026-11-11T11:13:21Z').toISOString(), '2026-11-11T11:13:21.000Z')
})

test('missing and invalid dates do not show Invalid Date', () => {
  for (const value of [null, '', 'not-a-date']) {
    assert.equal(parseOperationDate(value), null)
    assert.equal(formatOperationDate(value), '')
  }
})
