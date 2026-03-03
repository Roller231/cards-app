const baseFont = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif'

export function H1({ children, style = {}, className = '' }) {
  return (
    <h1
      className={className}
      style={{
        fontSize: 22,
        fontWeight: 700,
        color: '#111827',
        fontFamily: baseFont,
        ...style,
      }}
    >
      {children}
    </h1>
  )
}

export function H2({ children, style = {}, className = '' }) {
  return (
    <h2
      className={className}
      style={{
        fontSize: 24,
        fontWeight: 700,
        color: '#111827',
        fontFamily: baseFont,
        ...style,
      }}
    >
      {children}
    </h2>
  )
}

export function H3({ children, style = {}, className = '' }) {
  return (
    <h3
      className={className}
      style={{
        fontSize: 16,
        fontWeight: 600,
        color: '#111827',
        fontFamily: baseFont,
        marginBottom: 2,
        ...style,
      }}
    >
      {children}
    </h3>
  )
}

export function H4({ children, style = {}, className = '' }) {
  return (
    <h4
      className={className}
      style={{
        fontSize: 17,
        fontWeight: 700,
        color: '#111827',
        fontFamily: baseFont,
        ...style,
      }}
    >
      {children}
    </h4>
  )
}

export function Label({ children, style = {}, className = '' }) {
  return (
    <label
      className={className}
      style={{
        fontSize: 13,
        fontWeight: 600,
        color: '#6B7280',
        fontFamily: baseFont,
        display: 'block',
        ...style,
      }}
    >
      {children}
    </label>
  )
}

export function Text({ children, style = {}, className = '', semibold = false, gray = false }) {
  return (
    <span
      className={className}
      style={{
        fontSize: 16,
        fontWeight: semibold ? 600 : 400,
        color: gray ? '#6B7280' : '#111827',
        fontFamily: baseFont,
        ...style,
      }}
    >
      {children}
    </span>
  )
}

export function Description({ children, style = {}, className = '' }) {
  return (
    <p
      className={className}
      style={{
        fontSize: 12,
        fontWeight: 400,
        color: '#6B7280',
        fontFamily: baseFont,
        lineHeight: '16px',
        ...style,
      }}
    >
      {children}
    </p>
  )
}
