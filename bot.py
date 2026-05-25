import sqlite3
import datetime
import calendar
import urllib.request
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# СЮДА ВСТАВЬТЕ ВАШ ТОКЕН ВНУТРЬ КАВЫЧЕК:
TOKEN = "8102394026:AAEREm1tYAs9265zJ0aKSx9Z9l2jnw3kKMM"

bot = Bot(token=TOKEN)
dp = Dispatcher()

class FinanceStates(StatesGroup):
    waiting_for_expense_amount = State()
    waiting_for_category = State()
    waiting_for_income = State()
    waiting_for_utopia = State()
    waiting_for_ai_chat = State()

conn = sqlite3.connect("wallet_v2.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS wallet (balance REAL, utopia_limit REAL)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (category TEXT, amount REAL, date TEXT)''')
conn.commit()

cursor.execute("SELECT balance FROM wallet")
if not cursor.fetchone():
    cursor.execute("INSERT INTO wallet VALUES (0.0, 0.0)")
    conn.commit()

CATEGORIES = {"еда": "🍔 Еда", "поездки": "🚖 Поездки", "развлечения": "🎉 Развлечения", "для дома": "🏠 Для дома"}

def get_days_left():
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)
    return max(1, last_day - today.day + 1)

def get_wallet_data():
    cursor.execute("SELECT balance, utopia_limit FROM wallet")
    return cursor.fetchone()

main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📉 Расход"), KeyboardButton(text="➕ Доход")],
    [KeyboardButton(text="✨ Утопия"), KeyboardButton(text="📊 Аналитика")],
    [KeyboardButton(text="🤖 ИИ Бухгалтер")]
], resize_keyboard=True)

inline_categories = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🍔 Еда", callback_data="cat_еда"), InlineKeyboardButton(text="🚖 Поездки", callback_data="cat_поездки")],
    [InlineKeyboardButton(text="🎉 Развлечения", callback_data="cat_развлечения"), InlineKeyboardButton(text="🏠 Для дома", callback_data="cat_для дома")]
])

@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer("🇺🇿 Привет! Я твой личный бухгалтер. Управляй бюджетом с помощью кнопок:", reply_markup=main_kb)

@dp.message(F.text == "✨ Утопия")
async def view_utopia(message: Message, state: FSMContext):
    _, utopia = get_wallet_data()
    await message.answer(f"🪐 *Режим УТОПИЯ*\n\nТекущий желаемый лимит: *{utopia:,.0f} сум/день*.\n\nВведи новую сумму цифрами для изменения:", parse_mode="Markdown")
    await state.set_state(FinanceStates.waiting_for_utopia)

@dp.message(FinanceStates.waiting_for_utopia)
async def set_utopia(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        await message.answer(f"✅ Лимит «Утопия» установлен: *{amount:,.0f} сум/день*.", reply_markup=main_kb, parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("Введите корректное число.")
def ask_free_ai(prompt_text):
    """Функция делает легкий прямой веб-запрос к бесплатному ИИ без использования тяжелых библиотек"""
    try:
        url = "https://pollinations.ai"
        data = {"messages": [{"role": "user", "content": prompt_text}], "model": "openai"}
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except:
        return "Суровый аудит: Вы тратите слишком много! Сократите расходы на развлечения и фастфуд. Дебет не сходится с кредитом!"

@dp.message(F.text == "📊 Аналитика")
async def view_analytics(message: Message):
    balance, utopia = get_wallet_data()
    days = get_days_left()
    real_limit = balance / days if balance > 0 else 0
    today = datetime.date.today().isoformat()
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_t = cursor.fetchone()
    spent_today = row_t[0] if row_t and row_t[0] else 0.0
    
    status = "🟢 Всё под контролем." if real_limit >= utopia else "🔴 Внимание! Срочно экономьте!"
    await message.answer(
        f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n💰 Баланс: *{balance:,.0f} сум*\n🛡 Лимит: *{real_limit:,.0f} сум/день* ({days} дн.)\n✨ Утопия: *{utopia:,.0f} сум/день*\n◽️ За сегодня ушло: {spent_today:,.0f} сум\n\n📢 *Статус:* {status}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "➕ Доход")
async def start_income(message: Message, state: FSMContext):
    await message.answer("Введите сумму пополнения (в сумах):")
    await state.set_state(FinanceStates.waiting_for_income)

@dp.message(FinanceStates.waiting_for_income)
async def process_income(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        b, _ = get_wallet_data()
        cursor.execute("UPDATE wallet SET balance = ?", (b + amount,))
        conn.commit()
        await message.answer(f"💰 Баланс успешно пополнен на *+{amount:,.0f} сум*.", parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("Введите число.")

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
        await message.answer("Введите число цифрами.")

@dp.callback_query(F.data.startswith("cat_"), FinanceStates.waiting_for_category)
async def process_expense_category(callback: CallbackQuery, state: FSMContext):
    category_key = callback.data.split("_")[-1]
    data = await state.get_data()
    amount = data['amount']
    
    b, u = get_wallet_data()
    new_bal = b - amount
    cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
    cursor.execute("INSERT INTO expenses VALUES (?, ?, ?)", (category_key, amount, datetime.date.today().isoformat()))
    conn.commit()
    
    await callback.message.edit_text(f"✅ Расход записан: *-{amount:,.0f} сум* в категорию *{CATEGORIES[category_key]}*.\n👛 Остаток: {new_bal:,.0f} сум.", parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🤖 ИИ Бухгалтер")
async def ai_analyst(message: Message, state: FSMContext):
    await message.answer("🔄 ИИ изучает вашу базу данных и анализирует рынок Узбекистана...")
    balance, utopia = get_wallet_data()
    
    sys_prompt = (
        f"Ты суровый главный бухгалтер в Узбекистане. Оцени бюджет пользователя. "
        f"В кошельке: {balance} сум. Утопия: {utopia} сум/день. Напиши строгий аудит трат, учитывая цены в Ташкенте. "
        f"Используй слова дебет, кредит, сальдо. Ответь коротко и задай один вопрос."
    )
    
    response = ask_free_ai(sys_prompt)
    await message.answer(f"🤖 *Ответ ИИ-Бухгалтера:*\n\n{response}", parse_mode="Markdown")
    await state.set_state(FinanceStates.waiting_for_ai_chat)

@dp.message(FinanceStates.waiting_for_ai_chat)
async def ai_chat_loop(message: Message, state: FSMContext):
    if message.text in ["📉 Расход", "➕ Доход", "✨ Утопия", "📊 Аналитика", "🤖 ИИ Бухгалтер"]:
        await state.clear()
        if message.text == "📉 Расход": await start_expense(message, state)
        elif message.text == "➕ Доход": await start_income(message, state)
        elif message.text == "✨ Утопия": await view_utopia(message, state)
        elif message.text == "📊 Аналитика": await view_analytics(message)
        elif message.text == "🤖 ИИ Бухгалтер": await ai_analyst(message, state)
        return
    
    response = ask_free_ai(f"Ты бухгалтер в Узбекистане. Ответь на реплику: {message.text}")
    await message.answer(f"🤖 *ИИ-Бухгалтер:*\n\n{response}\n\n_(Для выхода нажмите любую кнопку меню)_", parse_mode="Markdown")

if __name__ == "__main__":
    dp.run_polling(bot)
