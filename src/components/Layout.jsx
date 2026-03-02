function Layout({ children, background = 'white' }) {
  return (
    <div className="min-h-screen flex justify-center" style={{ background }}>
      <div className="w-full max-w-[430px] min-h-screen flex flex-col" style={{ background }}>
        {children}
      </div>
    </div>
  )
}

export default Layout
