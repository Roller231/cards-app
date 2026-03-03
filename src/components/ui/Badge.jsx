function Badge({ children, variant = 'green', style = {}, className = '' }) {
  const variants = {
    green: {
      backgroundColor: '#10B981',
    },
    blue: {
      backgroundColor: '#3B82F6',
    },
    dark: {
      backgroundColor: '#1A1F36',
    },
  }

  return (
    <div
      className={className}
      style={{
        padding: '6px 12px',
        borderRadius: 8,
        fontSize: 12,
        fontWeight: 400,
        color: '#FFFFFF',
        fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
        ...variants[variant],
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export default Badge
