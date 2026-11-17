import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeEmail, emailInputProps } from '../src/utils/email.js'

test('normalizes pasted whitespace and mixed-case domains without changing aliases', () => {
  assert.equal(normalizeEmail(' \tCustomer+Cards @ iCloud.COM\n'), 'Customer+Cards@icloud.com')
  assert.equal(normalizeEmail('\u200BFirst.Last+pay@GMAIL.COM\uFEFF'), 'First.Last+pay@gmail.com')
  assert.equal(normalizeEmail('Customer@gmail.com'), 'Customer@gmail.com')
})

test('is idempotent during typing, deletion and incomplete addresses', () => {
  for (const value of ['', null, 'M', 'Mail@', '@ICLOUD.COM', 'not-an-email', 'a@@GMAIL.COM']) {
    assert.equal(normalizeEmail(normalizeEmail(value)), normalizeEmail(value))
  }
  assert.equal(normalizeEmail('M'), 'M')
  assert.equal(normalizeEmail('Mail@'), 'Mail@')
})

test('disables phone keyboard capitalization and autocorrection', () => {
  assert.equal(emailInputProps.autoCapitalize, 'none')
  assert.equal(emailInputProps.autoCorrect, 'off')
  assert.equal(emailInputProps.spellCheck, false)
  assert.equal(emailInputProps.inputMode, 'email')
})
