import { useEffect, useRef } from 'react'

export const useDragScroll = () => {
  const scrollRef = useRef(null)
  const isDragging = useRef(false)
  const startX = useRef(0)
  const scrollLeft = useRef(0)

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return

    const handleMouseDown = (e) => {
      isDragging.current = true
      startX.current = e.pageX - element.offsetLeft
      scrollLeft.current = element.scrollLeft
    }

    const handleMouseLeave = () => {
      isDragging.current = false
    }

    const handleMouseUp = () => {
      isDragging.current = false
    }

    const handleMouseMove = (e) => {
      if (!isDragging.current) return
      e.preventDefault()
      const x = e.pageX - element.offsetLeft
      const walk = (x - startX.current) * 2
      element.scrollLeft = scrollLeft.current - walk
    }

    element.addEventListener('mousedown', handleMouseDown)
    element.addEventListener('mouseleave', handleMouseLeave)
    element.addEventListener('mouseup', handleMouseUp)
    element.addEventListener('mousemove', handleMouseMove)

    return () => {
      element.removeEventListener('mousedown', handleMouseDown)
      element.removeEventListener('mouseleave', handleMouseLeave)
      element.removeEventListener('mouseup', handleMouseUp)
      element.removeEventListener('mousemove', handleMouseMove)
    }
  }, [])

  return scrollRef
}
