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

# Стабильная инициализация базы данных
conn = sqlite3.connect("wallet_final_v4.db", check_same_thread=False)
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

def clean_amount_text(text):
    return text.replace(" ", "").replace(",", "").replace(".", "").strip()

def ask_free_ai(prompt_text):
    try:
        url = "https://pollinations.ai"
        data = {"messages": [{"role": "user", "content": prompt_text}], "model": "openai"}
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode('utf-8'), 
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}, 
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except:
        return "Суровый аудит: Ошибка связи с нейросетью. Сокращайте дебет вручную!"

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📉 Инструкция Расхода")
    btn2 = types.KeyboardButton("➕ Инструкция Дохода")
    btn3 = types.KeyboardButton("✨ Инструкция Утопии")
    btn4 = types.KeyboardButton("📊 Аналитика")
    btn5 = types.KeyboardButton("🤖 ИИ Бухгалтер")
    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    markup.row(btn5)
    return markup

@bot.message_handler(commands=['start', 'help'])
def start(message):
    welcome = (
        "🇺🇿 *Привет! Я твой новый неубиваемый ИИ-Бухгалтер!*\n\n"
        "Я больше никогда не зависну. Управляй кошельком быстрыми командами:\n\n"
        "➕ *Внести доход:* Пиши слово `доход` и сумму. Пример: `доход 500 000`\n"
        "✨ *Задать лимит:* Пиши слово `лимит` и сумму. Пример: `лимит 40 000`\n"
        "📉 *Внести расход:* Пиши сумму и категорию через пробел. "
        "Категории: `еда`, `поездки`, `развлечения`, `для дома`. Пример: `15000 еда` или `25000 поездки`"
    )
    bot.send_message(message.chat.id, welcome, reply_markup=get_main_keyboard(), parse_mode="Markdown")
@bot.message_handler(func=lambda msg: msg.text == "➕ Инструкция Дохода")
def inst_income(message):
    bot.send_message(message.chat.id, "💰 *Как внести доход:*\n\nПросто отправь мне сообщение в формате: `доход [сумма]`.\nПример: `доход 400 000` или `доход 500000`", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "✨ Инструкция Утопии")
def inst_utopia(message):
    bot.send_message(message.chat.id, "🪐 *Как установить лимит Утопии:*\n\nПросто отправь мне сообщение в формате: `лимит [сумма]`.\nПример: `лимит 40 000` или `лимит 40000`", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "📉 Инструкция Расхода")
def inst_expense(message):
    bot.send_message(message.chat.id, "🛍 *Как внести расход за 1 секунду:*\n\nОтправь сообщение: `[сумма] [категория]`.\n\nДоступные категории:\n• `еда` (🍔)\n• `поездки` (🚖)\n• `развлечения` (🎉)\n• `для дома` (🏠)\n\nПример: `15000 еда` или `30 000 развлечения`", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text.lower().startswith("доход"))
def process_income_direct(message):
    try:
        raw_val = message.text.lower().replace("доход", "")
        amount = float(clean_amount_text(raw_val))
        b, utopia = get_wallet_data()
        new_bal = b + amount
        cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
        conn.commit()
        days = get_days_left()
        bot.send_message(message.chat.id, f"💰 *Баланс успешно пополнен!*\n\n👛 Всего в кошельке: *{new_bal:,.0f} сум*\n📅 До конца месяца осталось: *{days} дн.*\n✨ Твой лимит (Утопия): *{utopia:,.0f} сум/день*.", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Пишите строго: `доход 400000`")

@bot.message_handler(func=lambda msg: msg.text.lower().startswith("лимит"))
def process_utopia_direct(message):
    try:
        raw_val = message.text.lower().replace("лимит", "")
        amount = float(clean_amount_text(raw_val))
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Жесткий лимит «Утопия» обновлен: *{amount:,.0f} сум/день*.", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Пишите строго: `лимит 40000`")

@bot.message_handler(func=lambda msg: msg.text == "📊 Аналитика")
def view_analytics(message):
    balance, utopia = get_wallet_data()
    days = get_days_left()
    real_limit = balance / days if balance > 0 else 0
    today = datetime.date.today().isoformat()
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_t = cursor.fetchone()
    spent_today = row_t[0] if row_t and row_t[0] is not None else 0.0
    status = "🟢 Ты укладываешься в лимит!" if spent_today <= utopia else "🔴 ТЫ ПРЕВЫСИЛ СВОЮ УТОПИЮ! Срочно тормози!"
    bot.send_message(message.chat.id, f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n💰 Кошелек: *{balance:,.0f} сум*\n📅 Осталось: *{days} дн.*\n✨ Лимит (Утопия): *{utopia:,.0f} сум/день*\n◽️ Потрачено сегодня: *{spent_today:,.0f} сум*\n🛡 Реальный остаток: {real_limit:,.0f} сум/день\n\n📢 *Статус:* {status}", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: any(cat in msg.text.lower() for cat in CATEGORIES.keys()))
def process_expense_direct(message):
    try:
        parts = message.text.lower().split()
        amount_raw = ""
        category_key = ""
        for part in parts:
            if part in CATEGORIES:
                category_key = part
            else:
                amount_raw += part
        amount = float(clean_amount_text(amount_raw))
        if not category_key or amount <= 0: raise ValueError
        
        b, utopia = get_wallet_data()
        new_bal = b - amount
        today = datetime.date.today().isoformat()
        cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
        cursor.execute("INSERT INTO expenses VALUES (?, ?, ?)", (category_key, amount, today))
        conn.commit()
        
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
        row_today = cursor.fetchone()
        today_spent = row_today[0] if row_today and row_today[0] is not None else 0.0
        
        alert = ""
        if today_spent > utopia:
            alert = f"\n\n🚨 *ТЫ СУМАСШЕДШИЙ!* Траты за сегодня ({today_spent:,.0f} сум) превысили твой лимит Утопии ({utopia:,.0f} сум)! 😡"
        else:
            remains = utopia - today_spent
            if remains <= 15000:
                alert = f"\n\n⚠️ *ВНИМАНИЕ!* Ты приближаешься к лимиту! Осталось всего *{remains:,.0f} сум*. Трать раздумывая! 🧐"
            else:
                alert = f"\n\n🟢 Запас лимита до конца дня: *{remains:,.0f} сум*."
        bot.send_message(message.chat.id, f"✅ Записано: *-{amount:,.0f} сум* ➔ *{CATEGORIES[category_key]}*.\n👛 Кошелек: *{new_bal:,.0f} сум*.\n✨ Утопия: *{utopia:,.0f} сум/день*.{alert}", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Не понял трату. Пишите, например: `15000 еда` или `20000 поездки`")

@bot.message_handler(func=lambda msg: msg.text == "🤖 ИИ Бухгалтер")
def ai_analyst(message):
    bot.send_message(message.chat.id, "🔄 ИИ изучает вашу базу данных расходов по Узбекистану...")
    balance, utopia = get_wallet_data()
    sys_prompt = f"Ты строгий главный бухгалтер в Ташкенте. Оцени бюджет. В кошельке: {balance} сум. Утопия: {utopia} сум/день. Напиши короткий жесткий аудит трат, используя слова дебет, кредит, сальдо. Задай один вопрос."
    response = ask_free_ai(sys_prompt)
    msg = bot.send_message(message.chat.id, f"🤖 *Ответ ИИ-Бухгалтера:*\n\n{response}\n\n💬 Вы можете ответить ИИ или задать вопрос. Для выхода нажмите любую кнопку меню.", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

def ai_chat_loop(message):
    if message.text in ["📉 Инструкция Расхода", "➕ Инструкция Дохода", "✨ Инструкция Утопии", "📊 Аналитика", "🤖 ИИ Бухгалтер"]:
        if message.text == "📊 Аналитика": view_analytics(message)
        elif message.text == "🤖 ИИ Бухгалтер": ai_analyst(message)
        return
    response = ask_free_ai(f"Ты бухгалтер в Узбекистане. Коротко ответь пользователю: {message.text}")
    msg = bot.send_message(message.chat.id, f"🤖 *ИИ-Бухгалтер:*\n\n{response}", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

if __name__ == "__main__":
    def run_fake_server():
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
        server.serve_forever()
    threading.Thread(target=run_fake_server, daemon=True).start()
    bot.infinity_polling()
