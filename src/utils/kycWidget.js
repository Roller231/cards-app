let widgetPromise

export function loadKycWidget() {
  if (window.KYCWidget?.setupKYC) return Promise.resolve(window.KYCWidget)
  if (widgetPromise) return widgetPromise
  widgetPromise = new Promise((resolve, reject) => {
    // Retry a failed download instead of retaining a dead script element.
    document.getElementById('nv-kyc-widget-script')?.remove()
    const script = document.createElement('script')
    script.id = 'nv-kyc-widget-script'
    script.src = 'https://kyc.neuro-vision.ru/lib/widget-lib.js'
    script.crossOrigin = 'anonymous'
    script.async = true
    const fail = () => {
      clearTimeout(timer)
      script.onload = script.onerror = null
      script.remove()
      reject(new Error('Не удалось открыть проверку в Telegram. Продолжите в браузере.'))
    }
    const timer = setTimeout(fail, 15000)
    script.onerror = fail
    script.onload = () => {
      if (!window.KYCWidget?.setupKYC) return fail()
      clearTimeout(timer)
      resolve(window.KYCWidget)
    }
    document.head.appendChild(script)
  }).catch(error => {
    widgetPromise = undefined
    throw error
  })
  return widgetPromise
}

export function kycSessionId(payload) {
  try {
    const result = typeof payload === 'string' ? JSON.parse(payload) : payload
    return result?.sessionId || result?.session_id || result?.id || null
  } catch {
    return null
  }
}

export function openKycBrowser(url) {
  const parsed = new URL(url)
  if (parsed.protocol !== 'https:' || parsed.hostname !== 'kyc.neuro-vision.ru') {
    throw new Error('Не удалось получить ссылку на проверку')
  }
  try {
    if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(url, { try_instant_view: false })
      return true
    }
  } catch { /* Try the regular browser action if the Telegram bridge fails. */ }
  return Boolean(window.open(url, '_blank', 'noopener,noreferrer'))
}

export async function copyKycLink(url) {
  try {
    await navigator.clipboard.writeText(url)
    return true
  } catch {
    const input = document.createElement('textarea')
    input.value = url
    input.readOnly = true
    input.style.cssText = 'position:fixed;top:0;left:0;opacity:0;font-size:16px'
    document.body.appendChild(input)
    input.select()
    input.setSelectionRange(0, input.value.length)
    try { return document.execCommand('copy') }
    catch { return false }
    finally { input.remove() }
  }
}
