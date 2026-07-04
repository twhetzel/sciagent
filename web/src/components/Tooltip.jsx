import { useId, useLayoutEffect, useRef, useState } from 'react'

export default function Tooltip({
  content,
  children,
  className = '',
  placement = 'top',
  maxWidth = '16rem',
}) {
  const id = useId()
  const triggerRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState(null)

  function show() {
    setOpen(true)
  }

  function hide() {
    setOpen(false)
    setCoords(null)
  }

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setCoords(null)
      return
    }

    function updatePosition() {
      const rect = triggerRef.current.getBoundingClientRect()
      setCoords({
        left: rect.left + rect.width / 2,
        top: placement === 'bottom' ? rect.bottom + 8 : rect.top - 8,
      })
    }

    updatePosition()
    window.addEventListener('scroll', updatePosition, true)
    window.addEventListener('resize', updatePosition)
    return () => {
      window.removeEventListener('scroll', updatePosition, true)
      window.removeEventListener('resize', updatePosition)
    }
  }, [open, placement])

  const bubbleStyle = coords
    ? {
        left: `${coords.left}px`,
        top: `${coords.top}px`,
        maxWidth,
      }
    : undefined

  return (
    <span
      className={`tooltip-wrap tooltip-wrap--${placement} ${className}`.trim()}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <span
        ref={triggerRef}
        className="tooltip-trigger"
        tabIndex={0}
        aria-describedby={open ? id : undefined}
      >
        {children}
      </span>
      <span
        id={id}
        role="tooltip"
        className={`tooltip-bubble tooltip-bubble--${placement}${open && coords ? ' tooltip-bubble--open tooltip-bubble--fixed' : ''}`}
        style={bubbleStyle}
      >
        {content}
      </span>
    </span>
  )
}
