let lockCount = 0
let restorePage

// Lock the document, not touch events: the provider's camera, controls and
// scrollable instructions are mounted beside our root and must remain usable.
export function lockBackgroundScroll() {
  if (lockCount === 0) {
    const body = document.body
    const html = document.documentElement
    const root = document.getElementById('root')
    const x = window.scrollX
    const y = window.scrollY
    const bodyProps = ['position', 'top', 'left', 'width', 'overflow', 'overscrollBehavior', 'paddingRight']
    const savedBody = Object.fromEntries(bodyProps.map(key => [key, body.style[key]]))
    const savedHtml = { overflow: html.style.overflow, overscrollBehavior: html.style.overscrollBehavior }
    const wasInert = root?.inert
    const scrollbar = Math.max(0, window.innerWidth - html.clientWidth)
    if (scrollbar) body.style.paddingRight = `${(parseFloat(getComputedStyle(body).paddingRight) || 0) + scrollbar}px`
    Object.assign(body.style, { position: 'fixed', top: `${-y}px`, left: `${-x}px`, width: '100%', overflow: 'hidden', overscrollBehavior: 'none' })
    Object.assign(html.style, { overflow: 'hidden', overscrollBehavior: 'none' })
    if (root) root.inert = true
    restorePage = () => {
      Object.assign(body.style, savedBody)
      Object.assign(html.style, savedHtml)
      if (root) root.inert = wasInert
      window.scrollTo(x, y)
    }
  }
  lockCount += 1
  let released = false
  return () => {
    if (released) return
    released = true
    lockCount -= 1
    if (lockCount === 0) {
      restorePage?.()
      restorePage = undefined
    }
  }
}
