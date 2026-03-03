function Card({ children, padding = '20px', className = '', style = {} }) {
  return (
    <div
      className={`bg-white w-full ${className}`}
      style={{
        borderRadius: 20,
        padding,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export default Card
