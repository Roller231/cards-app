function Section({ children, className = '', style = {} }) {
  return (
    <div className={`page-block px-4 pt-4 ${className}`} style={style}>
      {children}
    </div>
  )
}

export default Section
