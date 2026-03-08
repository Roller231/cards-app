function WelcomePage({ onStart }) {
  return (
    <div
      className="flex-1 flex flex-col overflow-hidden"
      style={{ minHeight: '100dvh', maxHeight: '100dvh' }}
    >
      <div className="w-full overflow-hidden" style={{ flexShrink: 0 }}>
        <img
          src="/images/cardMain.png"
          alt="Виртуальные карты"
          draggable={false}
          style={{ width: '100%', height: 'auto', display: 'block' }}
        />
      </div>

      <div
        className="flex-1 flex flex-col"
        style={{
          paddingLeft: 24,
          paddingRight: 24,
          paddingTop: 'clamp(10px, 2vh, 22px)',
          paddingBottom: 'clamp(10px, 2vh, 24px)',
        }}
      >
        <h1
          className="font-bold tracking-tight text-gray-900"
          style={{ fontSize: 'clamp(30px, 5.5vw, 40px)', lineHeight: 1.12 }}
        >
          Виртуальные
          <br />
          карты Pronto Pay
        </h1>

        <p className="leading-relaxed text-gray-500" style={{ marginTop: 'clamp(8px, 1.6vh, 14px)', fontSize: 14 }}>
          Оплачивайте покупки в интернете, подписки и сервисы без ограничений.
          Платите за границей через ApplePay и GooglePay
        </p>

        <div className="flex flex-col gap-3" style={{ marginTop: 'auto' }}>
          <button
            type="button"
            onClick={onStart}
            style={{
              backgroundColor: '#DC4D35',
            }}
            className="w-full rounded-2xl py-[16px] text-[16px] font-semibold text-white cursor-pointer transition-transform duration-150 active:scale-95 hover:opacity-90"
          >
            Начать
          </button>

          <p className="text-center text-xs leading-relaxed text-gray-400 px-2">
            Продолжая, вы соглашаетесь с нашей{' '}
            <a href="#" className="underline" style={{ color: '#DC4D35' }}>
              Политикой конфиденциальности
            </a>{' '}
            и{' '}
            <a href="#" className="underline" style={{ color: '#DC4D35' }}>
              Условиями использования
            </a>
            .
          </p>
        </div>
      </div>
    </div>
  )
}

export default WelcomePage
