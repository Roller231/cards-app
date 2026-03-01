function HomePage() {
  return (
    <div className="flex-1 flex flex-col bg-gray-50">
      <div className="px-6 pt-6 pb-4 bg-white">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-600">Общий баланс</span>
          <button className="w-6 h-6 rounded-full border border-gray-300 flex items-center justify-center">
            <span className="text-gray-600 text-sm">?</span>
          </button>
        </div>
        <div className="text-4xl font-bold text-gray-900">0 $</div>
      </div>

      <div className="px-6 pt-6 pb-4 bg-white mt-2">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900">Мои карты</h2>
          <button className="text-sm font-medium" style={{ color: '#DC4D35' }}>
            + Оформить карту
          </button>
        </div>
        <p className="text-sm text-gray-400">У вас пока нет карт</p>
      </div>

      <div className="px-6 pt-6 pb-4 bg-white mt-2">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center">
              <div className="w-6 h-6 bg-gradient-to-br from-orange-400 to-yellow-400 rounded"></div>
            </div>
            <div>
              <div className="text-sm font-medium text-gray-900">Online</div>
              <div className="text-xs text-gray-400">Для оплаты покупок и сервисов в интернете</div>
            </div>
          </div>
          <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gradient-to-br from-orange-400 to-yellow-400 rounded-full"></div>
                <div className="w-2 h-2 bg-gray-300 rounded-full"></div>
              </div>
            </div>
            <div>
              <div className="text-sm font-medium text-gray-900">Online + Apple Pay + Google Pay</div>
              <div className="text-xs text-gray-400">Оплата в магазинах через Apple Pay, Google Pay и онлайн-сервисов на сайтах</div>
            </div>
          </div>
          <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      <div className="px-6 pt-6 pb-4 bg-white mt-2 flex-1">
        <h2 className="text-lg font-bold text-gray-900 mb-4">История</h2>
        <div className="flex flex-col items-center justify-center py-12">
          <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mb-3">
            <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-sm text-gray-400">Нет операций</p>
        </div>
      </div>

      <div className="px-6 py-4 bg-white border-t border-gray-100">
        <button
          type="button"
          style={{ backgroundColor: '#DC4D35' }}
          className="w-full rounded-2xl py-4 text-base font-semibold text-white transition-transform duration-150 active:scale-95"
        >
          + Выпустить карту
        </button>
      </div>
    </div>
  )
}

export default HomePage
