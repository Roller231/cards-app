function Button({ 
  children, 
  onClick, 
  variant = 'primary', 
  disabled = false,
  className = '',
  style = {},
  type = 'button',
  fullWidth = false
}) {
  const variants = {
    primary: {
      padding: '16px',
      backgroundColor: disabled ? '#D1D5DB' : '#DC4D35',
      borderRadius: 12,
      border: 'none',
      fontSize: 16,
      fontWeight: 600,
      color: '#FFFFFF',
      cursor: disabled ? 'not-allowed' : 'pointer',
    },
    secondary: {
      padding: '14px',
      backgroundColor: '#DC4D35',
      borderRadius: 12,
      border: 'none',
      fontSize: 16,
      fontWeight: 600,
      color: '#FFFFFF',
      cursor: 'pointer',
    },
    back: {
      width: 32,
      height: 32,
      borderRadius: 16,
      backgroundColor: '#F3F5F8',
      border: 'none',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
    icon: {
      width: 28,
      height: 28,
      borderRadius: 30,
      backgroundColor: 'transparent',
      border: 'none',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
    link: {
      fontSize: 14,
      fontWeight: 600,
      color: '#DC4D35',
      background: 'none',
      border: 'none',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
    },
  }

  const baseStyle = {
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
    ...variants[variant],
    ...style,
  }

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`transition-transform duration-150 active:scale-95 ${fullWidth ? 'w-full' : ''} ${className}`}
      style={baseStyle}
    >
      {children}
    </button>
  )
}

export default Button
