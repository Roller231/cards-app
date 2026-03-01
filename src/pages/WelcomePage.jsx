function WelcomePage({ onStart }) {
  return (
    <div className="flex-1 flex flex-col overflow-x-hidden touch-pan-y">
      <div className="w-full overflow-hidden">
        <div className="w-full h-[430px]">
          <img
            src="/images/cardMain.png"
            alt="Виртуальные карты"
            className="w-full h-full block object-cover object-[center_85%]"
            draggable={false}
          />
        </div>
      </div>

      <div className="flex-1 flex flex-col px-6 pt-8 pb-10">
        <h1 className="text-[40px] leading-[1.12] font-bold tracking-tight text-gray-900">
          Виртуальные
          <br />
          карты Pronto Pay
        </h1>

        <p className="mt-4 text-[14px] leading-relaxed text-gray-500" >
          Оплачивайте покупки в интернете, подписки и сервисы без ограничений.
          Платите за границей через ApplePay и GooglePay
        </p>

        <div className="mt-10 flex flex-col gap-4">
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
