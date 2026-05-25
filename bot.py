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

# Инициализация базы данных SQLite (используем стабильное имя)
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
    """Автоматически считает количество дней до конца текущего месяца по календарю"""
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)
    return max(1, last_day - today.day + 1)

def get_wallet_data():
    cursor.execute("SELECT balance, utopia_limit FROM wallet")
    return cursor.fetchone()

def clean_amount_text(text):
    """Очищает любой ввод пользователя от пробелов, запятых, точек и слова 'лимит'"""
    if not text:
        return ""
    return text.lower().replace("лимит", "").replace(" ", "").replace(",", "").replace(".", "").strip()

def ask_free_ai(prompt_text):
    """Отправляет запрос ИИ со специальными заголовками браузера для обхода блокировок"""
    try:
        url = "https://pollinations.ai"
        data = {"messages": [{"role": "user", "content": prompt_text}], "model": "openai"}
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode('utf-8'), 
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }, 
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        return "Суровый аудит: Обнаружена ошибка дебита! Финансовая нейросеть перегружена. Сокращайте баланс на развлечения вручную, сальдо под угрозой!"

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

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "🇺🇿 *Шпаргалка по управлению ИИ-Бухгалтером:*\n\n"
        "📉 *Расход* — Записать трату. Введите сумму, а затем выберите категорию.\n\n"
        "➕ *Доход* — Пополнить кошелек. Сумма добавится к общему балансу.\n\n"
        "✨ *Утопия* — Задать ваш жесткий лимит на день. Можно писать просто цифры.\n\n"
        "📊 *Аналитика* — Посмотреть баланс, траты за сегодня и математический остаток.\n\n"
        "🤖 *ИИ Бухгалтер* — Включает аудит вашей базы данных нейросетью.\n\n"
        "💡 *Правило ввода цифр:* Вы можете писать суммы в любом удобном виде: "
        "`40 000`, `40000` или `40,000` — бот всё поймет!"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")
@bot.message_handler(func=lambda msg: msg.text == "✨ Утопия")
def view_utopia(message):
    _, utopia = get_wallet_data()
    msg = bot.send_message(
        message.chat.id, 
        f"🪐 *Режим УТОПИЯ*\n\n"
        f"Текущий жесткий лимит: *{utopia:,.0f} сум/день*.\n\n"
        f"Введи новую сумму цифрами, которую ты запрещаешь себе превышать в день\n"
        f"(Например: `40000` или `40 000`):", 
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, set_utopia)

def set_utopia(message):
    try:
        clean_text = clean_amount_text(message.text)
        amount = float(clean_text)
        
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        
        bot.send_message(
            message.chat.id, 
            f"✅ Жесткий лимит «Утопия» успешно обновлен в базе: *{amount:,.0f} сум/день*.", 
            reply_markup=get_main_keyboard(), 
            parse_mode="Markdown"
        )
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Не удалось распознать сумму. Нажмите кнопку '✨ Утопия' заново и введите только число.")

@bot.message_handler(func=lambda msg: msg.text == "📊 Аналитика")
def view_analytics(message):
    balance, utopia = get_wallet_data()
    days = get_days_left()
    real_limit = balance / days if balance > 0 else 0
    today = datetime.date.today().isoformat()
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_t = cursor.fetchone()
    spent_today = row_t[0] if row_t and row_t[0] is not None else 0.0
    
    status = "🟢 Ты красавчик, укладываешься в лимит!" if spent_today <= utopia else "🔴 ТЫ ПРЕВЫСИЛ СВОЮ УТОПИЮ! Срочно тормози!"
    bot.send_message(message.chat.id, f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n💰 Всего в кошельке: *{balance:,.0f} сум*\n📅 До конца месяца осталось: *{days} дн.*\n\n✨ Твой лимит (Утопия): *{utopia:,.0f} сум/день*\n◽️ Потрачено за сегодня: *{spent_today:,.0f} сум*\n🛡 Реальный остаток: {real_limit:,.0f} сум/день\n\n📢 *Статус дел:* {status}", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "➕ Доход")
def start_income(message):
    msg = bot.send_message(message.chat.id, "Введите сумму пополнения (в сумах):")
    bot.register_next_step_handler(msg, process_income)

def process_income(message):
    try:
        clean_text = clean_amount_text(message.text)
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
        clean_text = clean_amount_text(message.text)
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
    category_key = parts[1]  # Исправлено извлечение ключа категории
    amount = float(parts[2])  # Исправлено извлечение суммы
    
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
        alert = f"\n\n🚨 *ТЫ СУМАСШЕДШИЙ!* Траты за сегодня ({today_spent:,.0f} сум) превысили твой жесткий лимит Утопии ({utopia:,.0f} сум)! Живо закрой кошелек! 😡"
    else:
        remains = utopia - today_spent
        if remains <= 15000 and remains > 0:
            alert = f"\n\n⚠️ *ВНИМАНИЕ!* Ты стремительно приближаешься к критическому лимиту на сегодня! Осталось всего *{remains:,.0f} сум*. Дальнейшие траты делай обдуманно и трать раздумывая! 🧐"
        else:
            alert = f"\n\n🟢 Твой запас лимита до конца дня: *{remains:,.0f} сум*. Всё в норме."
        
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
    
    cursor.execute("SELECT category, amount, date FROM expenses ORDER BY rowid DESC LIMIT 10")
    history = cursor.fetchall()
    history_str = ", ".join([f"{CATEGORIES.get(c, c)}: {a:,.0f}" for c, a, d in history]) if history else "Трат пока нет"

    sys_prompt = (
        f"Ты строгий главный бухгалтер в Ташкенте. Проведи аудит кошелька. "
        f"Баланс: {balance:,.0f} сум. Дневной лимит: {utopia:,.0f} сум. "
        f"Последние траты: {history_str}. Ответь на русском языке. Используй бухгалтерские термины (сальдо, дебет, кредит), "
        f"ругай за перерасход лимита, оценивай цены по меркам Узбекистана (сум) и в конце задай один жесткий вопрос пользователю."
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
    
    response = ask_free_ai(f"Контекст: Ты суровый бухгалтер в Узбекистане. Коротко ответь на реплику пользователя: {message.text}")
    msg = bot.send_message(message.chat.id, f"🤖 *ИИ-Бухгалтер:*\n\n{response}\n\n_(Для продолжения пишите сюда, для выхода нажмите кнопку меню)_", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

if __name__ == "__main__":
    def run_fake_server():
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
        server.serve_forever()
        
    threading.Thread(target=run_fake_server, daemon=True).start()
    bot.infinity_polling()
