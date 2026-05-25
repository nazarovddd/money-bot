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
TOKEN = "8102394026:AAEREm1tYAs9265zJ0aKSx9Z9l2jnw3kKMM"

bot = telebot.TeleBot(TOKEN)

# Инициализация абсолютно новой чистой базы данных
conn = sqlite3.connect("wallet_final.db", check_same_thread=False)
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
    return max(1, last_day[1] - today.day + 1)

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
        return "Суровый аудит: Вы тратите слишком много! Сократите расходы. Дебет не сходится с кредитом!"

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
    msg = bot.send_message(message.chat.id, f"🪐 *Режим УТОПИЯ*\n\nТекущий жесткий лимит: *{utopia:,.0f} сум/день*.\n\nВведи новую сумму цифрами, которую ты запрещаешь себе превышать в день:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, set_utopia)

def set_utopia(message):
    try:
        clean_text = message.text.replace(" ", "").replace(",", "")
        amount = float(clean_text)
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Жесткий лимит «Утопия» успешно обновлен в базе: *{amount:,.0f} сум/день*.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Введите сумму только цифрами (например: 40000).")

@bot.message_handler(func=lambda msg: msg.text == "📊 Аналитика")
def view_analytics(message):
    balance, utopia = get_wallet_data()
    days = get_days_left()
    real_limit = balance / days if balance > 0 else 0
    today = datetime.date.today().isoformat()
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_t = cursor.fetchone()
    spent_today = row_t[0] if row_t and row_t[0] else 0.0
    
    status = "🟢 Ты красавчик, укладываешься в лимит!" if spent_today <= utopia else "🔴 ТЫ ПРЕВЫСИЛ СВОЮ УТОПИЮ! Срочно тормози!"
    bot.send_message(message.chat.id, f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n💰 Всего в кошельке: *{balance:,.0f} сум*\n📅 До конца месяца осталось: *{days} дн.*\n\n✨ Твой лимит (Утопия): *{utopia:,.0f} сум/день*\n◽️ Потрачено за сегодня: *{spent_today:,.0f} сум*\n🛡 Реальный математический остаток: {real_limit:,.0f} сум/день\n\n📢 *Статус дел:* {status}", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "➕ Доход")
def start_income(message):
    msg = bot.send_message(message.chat.id, "Введите сумму пополнения (в сумах):")
    bot.register_next_step_handler(msg, process_income)

def process_income(message):
    try:
        clean_text = message.text.replace(" ", "").replace(",", "")
        amount = float(clean_text)
        
        b, utopia = get_wallet_data()
        new_bal = b + amount
        cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
        conn.commit()
        
        days = get_days_left()
        
        bot.send_message(
            message.chat.id, 
            f"💰 *Баланс успешно пополнен!*\n\n"
            f"👛 Всего в кошельке: *{new_bal:,.0f} сум*\n"
            f"📅 Оставшиеся дни месяца: *{days}*\n"
            f"✨ Твой установленный лимит: *{utopia:,.0f} сум/день*.", 
            reply_markup=get_main_keyboard(), 
            parse_mode="Markdown"
        )
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Введите сумму только цифрами.")

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
    
    b, utopia = get_wallet_data()
    new_bal = b - amount
    
    today = datetime.date.today().isoformat()
    cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
    cursor.execute("INSERT INTO expenses VALUES (?, ?, ?)", (category_key, amount, today))
    conn.commit()
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_today = cursor.fetchone()
    today_spent = row_today[0] if row_today and row_today[0] else 0.0
    
    alert = ""
    if today_spent > utopia:
        alert = f"\n\n🚨 *ТЫ СУМАСШЕДШИЙ!* Траты за сегодня ({today_spent:,.0f} сум) превысили твой жесткий лимит Утопии ({utopia:,.0f} сум)! Живо закрой кошелек! 😡"
    else:
        remains = utopia - today_spent
        alert = f"\n\n🟢 До превышения лимита на сегодня осталось: *{remains:,.0f} сум*."
        
    bot.edit_message_text(
        chat_id=call.message.chat.id, 
        message_id=call.message.message_id, 
        text=f"✅ Расход записан: *-{amount:,.0f} сум* в категорию *{CATEGORIES[category_key]}*.\n"
             f"👛 Остаток в кошельке: *{new_bal:,.0f} сум*.\n"
             f"✨ Твой лимит (Утопия): *{utopia:,.0f} сум/день*.{alert}", 
        parse_mode="Markdown"
    )

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
