import sqlite3
import datetime
import calendar
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from duckduckgo_search import DDGS  # Бесплатный ИИ

# СЮДА ВСТАВЬТЕ ВАШ ТОКЕН ВНУТРЬ КАВЫЧЕК:
TOKEN = "8102394026:AAEREm1tYAs9265zJ0aKSx9Z9l2jnw3kKMM"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Состояния FSM для последовательного ввода данных
class FinanceStates(StatesGroup):
    waiting_for_expense_amount = State()
    waiting_for_category = State()
    waiting_for_income = State()
    waiting_for_utopia = State()
    waiting_for_ai_chat = State()

# Инициализация базы данных SQLite
conn = sqlite3.connect("wallet_v2.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS wallet (balance REAL, utopia_limit REAL)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (category TEXT, amount REAL, date TEXT)''')
conn.commit()

# Проверка первичной записи в таблице кошелька
cursor.execute("SELECT balance FROM wallet")
if not cursor.fetchone():
    cursor.execute("INSERT INTO wallet VALUES (0.0, 0.0)")
    conn.commit()

# Категории трат
CATEGORIES = {
    "еда": "🍔 Еда", 
    "поездки": "🚖 Поездки", 
    "развлечения": "🎉 Развлечения", 
    "для дома": "🏠 Для дома"
}

# --- Вспомогательные функции ---
def get_days_left():
    """Считает сколько дней осталось до конца текущего месяца (включая сегодня)"""
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)
    return max(1, last_day - today.day + 1)

def get_wallet_data():
    """Получает баланс кошелька и лимит 'Утопия' из базы данных"""
    cursor.execute("SELECT balance, utopia_limit FROM wallet")
    return cursor.fetchone()

# --- Главное меню (Клавиатура Telegram) ---
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📉 Расход"), KeyboardButton(text="➕ Доход")],
    [KeyboardButton(text="✨ Утопия"), KeyboardButton(text="📊 Аналитика")],
    [KeyboardButton(text="🤖 ИИ Бухгалтер")]
], resize_keyboard=True)

# Инлайн-кнопки для выбора категории расходов
inline_categories = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🍔 Еда", callback_data="cat_еда"), 
     InlineKeyboardButton(text="🚖 Поездки", callback_data="cat_поездки")],
    [InlineKeyboardButton(text="🎉 Развлечения", callback_data="cat_развлечения"), 
     InlineKeyboardButton(text="🏠 Для дома", callback_data="cat_для дома")]
])

# --- Приветственный хэндлер ---
@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "🇺🇿 Привет! Я твой личный финансовый контролер и бухгалтер.\n"
        "Я помогу тебе экономить деньги, следить за бюджетом и автоматически "
        "рассчитаю твой дневной лимит исходя из календаря.\n\n"
        "Используй кнопки меню ниже для управления кошельком 👇", 
        reply_markup=main_kb
    )

# --- Блок: Режим «Утопия» ---
@dp.message(F.text == "✨ Утопия")
async def view_utopia(message: Message, state: FSMContext):
    _, utopia = get_wallet_data()
    await message.answer(
        f"🪐 *Режим УТОПИЯ*\n\n"
        f"Текущий идеальный лимит трат: *{utopia:,.0f} сум/день*.\n\n"
        f"Если хочешь изменить его, введи новую сумму цифрами в ответ на это сообщение.\n"
        f"Если менять не нужно, просто выбери любую другую кнопку меню.", 
        parse_mode="Markdown"
    )
    await state.set_state(FinanceStates.waiting_for_utopia)

@dp.message(FinanceStates.waiting_for_utopia)
async def set_utopia(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        await message.answer(
            f"✅ Идеальный лимит «Утопия» успешно установлен на: *{amount:,.0f} сум/день*.", 
            reply_markup=main_kb, 
            parse_mode="Markdown"
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введи корректное число без букв и пробелов.")
# --- Блок: Аналитика трат ---
@dp.message(F.text == "📊 Аналитика")
async def view_analytics(message: Message):
    balance, utopia = get_wallet_data()
    days = get_days_left()
    real_limit = balance / days if balance > 0 else 0
    
    today = datetime.date.today().isoformat()
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    month_ago = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    
    # Сбор статистики из базы за разные периоды
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_today = cursor.fetchone()
    spent_today = row_today if row_today else 0.0
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date >= ?", (week_ago,))
    row_week = cursor.fetchone()
    spent_week = row_week if row_week else 0.0
    
    cursor.execute("SELECT category, SUM(amount) FROM expenses WHERE date >= ? GROUP BY category", (month_ago,))
    month_categories = cursor.fetchall()
    
    cat_text = ""
    spent_month = 0.0
    for cat_key, amt in month_categories:
        cat_text += f"• {CATEGORIES.get(cat_key, cat_key)}: {amt:,.0f} сум\n"
        spent_month += amt
        
    # Сравнение с Утопией
    if real_limit >= utopia:
        status = "🟢 Всё под контролем. Ваш текущий лимит позволяет жить в рамках 'Утопии'!"
    else:
        status = f"🔴 Внимание! Реальный лимит ниже вашей Утопии на {(utopia - real_limit):,.0f} сум. Рекомендуется затянуть пояс!"
    
    await message.answer(
        f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n"
        f"💰 В кошельке сейчас: *{balance:,.0f} сум*\n"
        f"📅 До конца месяца осталось дней: *{days}*\n"
        f"🛡 Твой реальный лимит: *{real_limit:,.0f} сум/день*\n"
        f"✨ Твоя цель (Утопия): *{utopia:,.0f} сум/день*\n\n"
        f"📉 *Периоды расходов:*\n"
        f"◽️ За сегодня: {spent_today:,.0f} сум\n"
        f"◽️ За последние 7 дней: {spent_week:,.0f} сум\n"
        f"◽️ За последние 30 дней: {spent_month:,.0f} сум\n\n"
        f"🗂 *Траты по крупным категориям (30 дней):*\n{cat_text if cat_text else 'Трат пока не зафиксировано.'}\n"
        f"📢 *Статус дел:* {status}",
        parse_mode="Markdown"
    )

# --- Блок: Запись доходов ---
@dp.message(F.text == "➕ Доход")
async def start_income(message: Message, state: FSMContext):
    await message.answer("Введите сумму пополнения кошелька (в сумах):")
    await state.set_state(FinanceStates.waiting_for_income)

@dp.message(FinanceStates.waiting_for_income)
async def process_income(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        balance, utopia = get_wallet_data()
        new_bal = balance + amount
        
        cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
        conn.commit()
        
        days = get_days_left()
        new_limit = new_bal / days
        
        await message.answer(
            f"💰 *Баланс успешно пополнен!*\n\n"
            f"➕ Добавлено: +{amount:,.0f} сум\n"
            f"👛 Общий остаток: {new_bal:,.0f} сум\n"
            f"🔄 Пересчитанный лимит на остаток месяца: *{new_limit:,.0f} сум/день*.",
            reply_markup=main_kb, 
            parse_mode="Markdown"
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Введите корректное число.")

# --- Блок: Запись расходов (Вариант Б - Кнопки) ---
@dp.message(F.text == "📉 Расход")
async def start_expense(message: Message, state: FSMContext):
    await message.answer("Введите сумму расхода (в сумах):")
    await state.set_state(FinanceStates.waiting_for_expense_amount)

@dp.message(FinanceStates.waiting_for_expense_amount)
async def process_expense_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        await state.update_data(amount=amount)
        await message.answer("Выберите категорию трат:", reply_markup=inline_categories)
        await state.set_state(FinanceStates.waiting_for_category)
    except ValueError:
        await message.answer("⚠️ Введите число цифрами.")

@dp.callback_query(F.data.startswith("cat_"), FinanceStates.waiting_for_category)
async def process_expense_category(callback: CallbackQuery, state: FSMContext):
    category_key = callback.data.split("_")[-1]
    data = await state.get_data()
    amount = data['amount']
    
    balance, utopia = get_wallet_data()
    new_bal = balance - amount
    cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
    
    today = datetime.date.today().isoformat()
    cursor.execute("INSERT INTO expenses VALUES (?, ?, ?)", (category_key, amount, today))
    conn.commit()
    
    # Динамический пересчет лимита
    days = get_days_left()
    new_limit = new_bal / days if new_bal > 0 else 0
    
    # Считаем сколько всего потрачено за сегодня, чтобы проверить превышение
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_today = cursor.fetchone()
    today_spent = row_today if row_today else 0.0
    
    alert = ""
    # Если за день потрачено больше, чем рассчитанный на день лимит
    if today_spent > (balance / days if balance > 0 else 0):
        alert = f"\n\n🚨 *ВНИМАНИЕ! ТЫ ПРЕВЫСИЛ СВОЙ ЛИМИТ!* За сегодня потрачено уже {today_spent:,.0f} сум! Хватит транжирить деньги, до конца месяца осталось {days} дней! 😡"
        
    await callback.message.edit_text(
        f"✅ Расход записан: *-{amount:,.0f} сум* в категорию *{CATEGORIES[category_key]}*.\n\n"
        f"👛 Остаток в кошельке: {new_bal:,.0f} сум\n"
        f"📉 Твой новый динамический лимит: *{new_limit:,.0f} сум/день*.{alert}", 
        parse_mode="Markdown"
    )
    await state.clear()

# --- Блок: Бесплатный ИИ Бухгалтер (Узбекистан) ---
@dp.message(F.text == "🤖 ИИ Бухгалтер")
async def ai_analyst(message: Message, state: FSMContext):
    await message.answer("🔄 Профессиональный ИИ-Бухгалтер изучает базу данных ваших расходов и анализирует текущий рынок в Узбекистане...")
    
    balance, utopia = get_wallet_data()
    cursor.execute("SELECT category, amount, date FROM expenses ORDER BY date DESC LIMIT 30")
    history = cursor.fetchall()
    
    history_str = "\n".join([f"- {date}: категория '{CATEGORIES.get(cat, cat)}' на сумму {amt:,.0f} сум" for cat, amt, date in history])
    
    # Промпт для настройки характера ИИ трат в Узбекистане
    sys_prompt = (
        "Ты — опытный, профессиональный главный бухгалтер и суровый финансовый аудитор в Узбекистане. "
        "Твоя задача — проанализировать расходы пользователя, сопоставить их с текущими реальными ценами и рынком Узбекистана "
        "(цены на продукты на базарах Чорсу/Алайский, супермаркетах Корзинка/Макро, тарифы такси Yandex Go в Ташкенте, аренда жилья и коммуналка). "
        "Говори строго на русском языке, используй профессиональный, но понятный тон. "
        "Если финансовое сальдо отрицательное или реальный лимит хуже 'Утопии', то сделай пользователю строгий выговор и укажи, из-за каких именно категорий расходы пошли на дно. "
        "Используй бухгалтерские термины: 'дебет', 'кредит', 'активы', 'сальдо', 'баланс'. "
        "В конце анализа обязательно задай пользователю ОДИН жесткий уточняющий вопрос о целесообразности его трат. "
        f"Данные пользователя для аудита: Баланс кошелька: {balance} сум. Желаемая цель трат (Утопия): {utopia} сум/день. "
        f"История последних трат:\n{history_str if history_str else 'Трат еще нет.'}\n"
        "Выдай профессиональный финансовый аудит."
    )
    
    try:
        with DDGS() as ddgs:
            # Бесплатный запрос к ИИ через DuckDuckGo
            response = ddgs.chat(keywords=sys_prompt, model="gpt-4o")
            await message.answer(f"🤖 *Заключение Главбуха:*\n\n{response}", parse_mode="Markdown")
            await message.answer("💬 Вы можете ответить ИИ-бухгалтеру здесь или задать ему вопрос по вашим деньгам. Чтобы выйти из чата с ИИ, просто нажмите любую кнопку в меню.")
            await state.set_state(FinanceStates.waiting_for_ai_chat)
    except Exception as e:
        await message.answer("❌ Не удалось связаться с сервером ИИ. Попробуйте нажать кнопку еще раз.")

@dp.message(FinanceStates.waiting_for_ai_chat)
async def ai_chat_loop(message: Message, state: FSMContext):
    # Если пользователь решил нажать кнопку меню вместо продолжения чата с ИИ
    if message.text in ["📉 Расход", "➕ Доход", "✨ Утопия", "📊 Аналитика", "🤖 ИИ Бухгалтер"]:
        await state.clear()
        if message.text == "📉 Расход": await start_expense(message, state)
        elif message.text == "➕ Доход": await start_income(message, state)
        elif message.text == "✨ Утопия": await view_utopia(message, state)
        elif message.text == "📊 Аналитика": await view_analytics(message)
        elif message.text == "🤖 ИИ Бухгалтер": await ai_analyst(message, state)
        return
        
    try:
        with DDGS() as ddgs:
            response = ddgs.chat(
                keywords=f"Контекст: Ты суровый бухгалтер в Узбекистане, анализирующий личный бюджет. Ответь пользователю на его реплику: {message.text}", 
                model="gpt-4o"
            )
            await message.answer(f"🤖 *ИИ-Бухгалтер:*\n\n{response}\n\n_(Для выхода в главное меню нажмите любую кнопку внизу)_", parse_mode="Markdown")
    except Exception as e:
        await message.answer("❌ Ошибка ИИ-модуля. Повторите запрос.")

if __name__ == "__main__":
    dp.run_polling(bot)
