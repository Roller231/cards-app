// Domains are case-insensitive. Preserve the mailbox, aliases and punctuation.
export function normalizeEmail(value) {
  const email = String(value ?? '').replace(/[\s\u200B-\u200D\uFEFF]+/gu, '')
  const at = email.lastIndexOf('@')
  return at < 0 ? email : email.slice(0, at + 1) + email.slice(at + 1).toLowerCase()
}

export const emailInputProps = {
  autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
  inputMode: 'email', autoComplete: 'email',
}
