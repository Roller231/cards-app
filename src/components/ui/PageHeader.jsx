function PageHeader({ title, onBack }) {
  return (
    <div className="fixed top-0 left-1/2 -translate-x-1/2 w-full max-w-[430px] z-20" style={{ backgroundColor: '' }}>
      <div className="px-4 pt-4 pb-6">
        <div className="flex items-center">
          <button
            onClick={onBack}
            className="flex items-center justify-center transition-transform duration-150 active:scale-95"
            style={{
              width: 32,
              height: 32,
              borderRadius: 16,
              backgroundColor: '#F3F5F8',
              border: 'none',
              cursor: 'pointer',
              marginRight: 12,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M10 12L6 8L10 4"
                stroke="#111827"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <h1
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: '#111827',
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif',
            }}
          >
            {title}
          </h1>
        </div>
      </div>
    </div>
  )
}

export default PageHeader
