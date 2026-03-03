function Input({ 
  label, 
  value, 
  onChange, 
  placeholder = '', 
  type = 'text',
  style = {},
  className = '',
  inputRef = null
}) {
  return (
    <div
      className={className}
      style={{
        backgroundColor: 'white',
        borderRadius: 12,
        padding: '14px 16px',
        ...style,
      }}
    >
      {label && (
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
      )}
      <input
        ref={inputRef}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        style={{
          border: 'none',
          outline: 'none',
          background: 'transparent',
          fontSize: 15,
          fontWeight: value ? 600 : 400,
          color: value ? '#111827' : '#6B7280',
          fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
          width: '100%',
        }}
      />
    </div>
  )
}

export default Input
