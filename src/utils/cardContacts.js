export function cardContactsReady(user) {
  const email = String(user?.email || '').trim()
  const domain = email.split('@').pop().toLowerCase()
  return /^[^@\s]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/.test(email)
    && !['example.com', 'example.org', 'example.net'].includes(domain)
    && !/\.(test|invalid|example)$/.test(domain)
    && /^\+[1-9]\d{6,14}$/.test(String(user?.phone || '').replace(/[\s()-]/g, ''))
}
