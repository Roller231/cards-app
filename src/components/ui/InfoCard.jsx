function InfoCard({ title, value, style = {}, className = '' }) {
  return (
    <div
      className={className}
      style={{
        backgroundColor: '#F3F5F8',
        borderRadius: 12,
        padding: '12px 16px',
        ...style,
      }}
    >
      <div
        style={{
          fontSize: 16,
          fontWeight: 600,
          color: '#111827',
          fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
          marginBottom: 2,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontSize: 12,
          fontWeight: 400,
          color: '#6B7280',
          fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {title}
      </div>
    </div>
  )
}

export default InfoCard
