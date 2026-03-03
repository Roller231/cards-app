function FormField({ 
  label, 
  children, 
  onClick,
  style = {},
  className = ''
}) {
  return (
    <div
      onClick={onClick}
      className={className}
      style={{
        backgroundColor: 'white',
        borderRadius: 12,
        padding: '14px 16px',
        cursor: onClick ? 'text' : 'default',
        ...style,
      }}
    >
      <label
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: '#6B7280',
          fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
          display: 'block',
          marginBottom: 8,
        }}
      >
        {label}
      </label>
      {children}
    </div>
  )
}

export default FormField
