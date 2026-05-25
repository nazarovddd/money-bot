import sqlite3
import datetime
import calendar
import urllib.request
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
import telebot
from telebot import types

# СЮДА ВСТАВЬТЕ ВАШ ТОКЕН ВНУТРЬ КАВЫЧЕК:
TOKEN = "ВАШ_ТОКЕН_ТЕЛЕГРАМ_БОТА"

bot = telebot.TeleBot(TOKEN)

# Инициализация базы данных SQLite
conn = sqlite3.connect("wallet_v3.db", check_same_thread=False)
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
    """Автоматически считает количество дней до конца текущего месяца по календарю"""
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return max(1, last_day - today.day + 1)

def get_wallet_data():
    cursor.execute("SELECT balance, utopia_limit FROM wallet")
    return cursor.fetchone()

def ask_free_ai(prompt_text):
    try:
        url = "https://pollinations.ai"
        data = {"messages": [{"role": "user", "content": prompt_text}], "model": "openai"}
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except:
        return "Суровый аудит: Вы тратите слишком много! Сократите расходы на развлечения. Дебет не сходится с кредитом!"

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📉 Расход")
    btn2 = types.KeyboardButton("➕ Доход")
    btn3 = types.KeyboardButton("✨ Утопия")
    btn4 = types.KeyboardButton("📊 Аналитика")
    btn5 = types.KeyboardButton("🤖 ИИ Бухгалтер")
    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    markup.row(btn5)
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🇺🇿 Привет! Я твой личный бухгалтер. Управляй бюджетом с помощью кнопок:", reply_markup=get_main_keyboard())
@bot.message_handler(func=lambda msg: msg.text == "✨ Утопия")
def view_utopia(message):
    _, utopia = get_wallet_data()
    msg = bot.send_message(message.chat.id, f"🪐 *Режим УТОПИЯ*\n\nТекущий желаемый лимит: *{utopia:,.0f} сум/день*.\n\nВведи новую сумму цифрами для изменения:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, set_utopia)

def set_utopia(message):
    try:
        clean_text = message.text.replace(" ", "").replace(",", "")
        amount = float(clean_text)
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Лимит «Утопия» установлен: *{amount:,.0f} сум/день*.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Введите сумму только цифрами (например: 1000000).")

@bot.message_handler(func=lambda msg: msg.text == "📊 Аналитика")
def view_analytics(message):
    balance, utopia = get_wallet_data()
    days = get_days_left()
    real_limit = balance / days if balance > 0 else 0
    today = datetime.date.today().isoformat()
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_t = cursor.fetchone()
    spent_today = row_t[0] if row_t and row_t[0] else 0.0
    
    status = "🟢 Всё под контролем." if real_limit >= utopia else "🔴 Внимание! Срочно экономьте!"
    bot.send_message(message.chat.id, f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n💰 Баланс: *{balance:,.0f} сум*\n🛡 Лимит: *{real_limit:,.0f} сум/день* ({days} дн.)\n✨ Утопия: *{utopia:,.0f} сум/день*\n◽️ За сегодня ушло: {spent_today:,.0f} сум\n\n📢 *Статус:* {status}", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "➕ Доход")
def start_income(message):
    msg = bot.send_message(message.chat.id, "Введите сумму пополнения (в сумах):")
    bot.register_next_step_handler(msg, process_income)

def process_income(message):
    try:
        clean_text = message.text.replace(" ", "").replace(",", "")
        amount = float(clean_text)
        
        b, _ = get_wallet_data()
        new_bal = b + amount
        cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
        conn.commit()
        
        days = get_days_left()
        real_limit = new_bal / days if new_bal > 0 else 0
        
        bot.send_message(
            message.chat.id, 
            f"💰 *Баланс успешно пополнен!*\n\n"
            f"👛 Всего в кошельке: *{new_bal:,.0f} сум*\n"
            f"📅 До конца месяца осталось дней: *{days}*\n\n"
            f"🚀 Исходя из сегодняшней даты, ваш максимальный лимит: *{real_limit:,.0f} сум/день*.", 
            reply_markup=get_main_keyboard(), 
            parse_mode="Markdown"
        )
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Введите сумму только цифрами без букв и пробелов (например: 1000000).")

@bot.message_handler(func=lambda msg: msg.text == "📉 Расход")
def start_expense(message):
    msg = bot.send_message(message.chat.id, "Введите сумму расхода (в сумах):")
    bot.register_next_step_handler(msg, process_expense_amount)

def process_expense_amount(message):
    try:
        clean_text = message.text.replace(" ", "").replace(",", "")
        amount = float(clean_text)
        markup = types.InlineKeyboardMarkup()
        for key, name in CATEGORIES.items():
            markup.add(types.InlineKeyboardButton(text=name, callback_data=f"cat_{key}_{amount}"))
        bot.send_message(message.chat.id, "Выберите категорию трат:", reply_markup=markup)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Введите число цифрами.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def process_expense_category(call):
    parts = call.data.split("_")
    category_key = parts[1]
    amount = float(parts[2])
    
    b, u = get_wallet_data()
    new_bal = b - amount
    cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
    cursor.execute("INSERT INTO expenses VALUES (?, ?, ?)", (category_key, amount, datetime.date.today().isoformat()))
    conn.commit()
    
    days = get_days_left()
    real_limit = new_bal / days if new_bal > 0 else 0
    
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"✅ Расход записан: *-{amount:,.0f} сум* в категорию *{CATEGORIES[category_key]}*.\n👛 Остаток в кошельке: *{new_bal:,.0f} сум*.\n📉 Новый лимит на оставшиеся дни: *{real_limit:,.0f} сум/день*.", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "🤖 ИИ Бухгалтер")
def ai_analyst(message):
    bot.send_message(message.chat.id, "🔄 ИИ изучает вашу базу данных и анализирует рынок Узбекистана...")
    balance, utopia = get_wallet_data()
    
    sys_prompt = (
        f"Ты суровый главный бухгалтер в Узбекистане. Оцени бюджет пользователя. "
        f"В кошельке: {balance} сум. Утопия: {utopia} сум/день. Напиши строгий короткий аудит трат, учитывая цены в Ташкенте. "
        f"Используй слова дебет, кредит, сальдо. Задай один вопрос."
    )
    
    response = ask_free_ai(sys_prompt)
    msg = bot.send_message(message.chat.id, f"🤖 *Ответ ИИ-Бухгалтера:*\n\n{response}\n\n💬 Вы можете ответить ИИ-бухгалтеру прямо следующим сообщением:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

def ai_chat_loop(message):
    if message.text in ["📉 Расход", "➕ Доход", "✨ Утопия", "📊 Аналитика", "🤖 ИИ Бухгалтер"]:
        if message.text == "📉 Расход": start_expense(message)
        elif message.text == "➕ Доход": start_income(message)
        elif message.text == "✨ Утопия": view_utopia(message)
        elif message.text == "📊 Аналитика": view_analytics(message)
        elif message.text == "🤖 ИИ Бухгалтер": ai_analyst(message)
        return
    
    response = ask_free_ai(f"Ты бухгалтер в Узбекистане. Ответь коротко на реплику: {message.text}")
    msg = bot.send_message(message.chat.id, f"🤖 *ИИ-Бухгалтер:*\n\n{response}\n\n_(Для продолжения пишите сюда, для выхода нажмите кнопку меню)_", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

if __name__ == "__main__":
    def run_fake_server():
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
        server.serve_forever()
        
    threading.Thread(target=run_fake_server, daemon=True).start()
    bot.infinity_polling()
