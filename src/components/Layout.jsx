function Layout({ children }) {
  return (
    <div className="min-h-screen bg-white flex justify-center">
      <div className="w-full max-w-[430px] min-h-screen flex flex-col bg-white">
        {children}
      </div>
    </div>
  )
}

export default Layout
