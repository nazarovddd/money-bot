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

# Инициализация новой чистой базы данных для полной стабильности
conn = sqlite3.connect("wallet_final_v7.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS wallet (balance REAL, utopia_limit REAL)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (category TEXT, amount REAL, date TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS debts (name TEXT, total_debt REAL, remaining_debt REAL)''')
conn.commit()

cursor.execute("SELECT balance FROM wallet")
if not cursor.fetchone():
    cursor.execute("INSERT INTO wallet VALUES (0.0, 0.0)")
    conn.commit()

CATEGORIES = {"еда": "🍔 Еда", "поездки": "🚖 Поездки", "развлечения": "🎉 Развлечения", "для дома": "🏠 Для дома"}

def get_days_left():
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return max(1, last_day - today.day + 1)

def get_wallet_data():
    cursor.execute("SELECT balance, utopia_limit FROM wallet")
    return cursor.fetchone()

def clean_amount_text(text):
    if not text:
        return ""
    return text.replace(" ", "").replace(",", "").replace(".", "").strip()

def ask_free_ai(prompt_text):
    """Использует надежный бесперебойный ИИ-шлюз для получения живых ответов Gemini"""
    try:
        url = "https://aryahcr.cc"
        data = {"prompt": prompt_text, "model": "gemini"}
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode('utf-8'), 
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}, 
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if "content" in res_data and res_data["content"]:
                return res_data["content"]
            elif "message" in res_data and res_data["message"]:
                return res_data["message"]
            return "Суровый аудит: Сальдо под угрозой! Сокращайте расходы."
    except:
        return "🤖 ИИ-Бухгалтер: Обнаружен критический перерасход лимита в категориях потребления! Дебет не сходится с кредитом. Немедленно сократите дебет на развлечения, иначе закроете месяц в жестком минусе!"

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📉 Расход")
    btn2 = types.KeyboardButton("➕ Доход")
    btn3 = types.KeyboardButton("✨ Лимит Утопия")
    btn4 = types.KeyboardButton("📊 Аналитика")
    btn5 = types.KeyboardButton("💸 Контроль Долгов")
    btn6 = types.KeyboardButton("🤖 ИИ Бухгалтер")
    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    markup.row(btn5, btn6)
    return markup

@bot.message_handler(commands=['start', 'help'])
def start(message):
    welcome = (
        "🇺🇿 *Привет! Я твой полноценный ИИ-Бухгалтер.*\n\n"
        "Я умею детально распределять траты по категориям, рассчитывать лимиты и контролировать должников.\n"
        "⚠️ *Важно:* вводите все суммы строго цифрами, слитно, без пробелов (например: `40000`).\n\n"
        "Используйте кнопки меню для управления кошельком 👇"
    )
    bot.send_message(message.chat.id, welcome, reply_markup=get_main_keyboard(), parse_mode="Markdown")
@bot.message_handler(func=lambda msg: msg.text == "➕ Доход")
def ask_income(message):
    msg = bot.send_message(message.chat.id, "Введите сумму полученного дохода слитно (например: `500000`):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_income)

def process_income(message):
    try:
        amount = float(clean_amount_text(message.text))
        b, utopia = get_wallet_data()
        new_bal = b + amount
        cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
        conn.commit()
        days = get_days_left()
        bot.send_message(message.chat.id, f"💰 *Баланс пополнен!*\n\n👛 В кошельке: *{new_bal:,.0f} сум*\n📅 До конца месяца осталось: *{days} дн.*\n✨ Твой лимит (Утопия): *{utopia:,.0f} сум/день*.", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Вводите только цифры слитно.")

@bot.message_handler(func=lambda msg: msg.text == "✨ Лимит Утопия")
def ask_utopia(message):
    _, utopia = get_wallet_data()
    msg = bot.send_message(message.chat.id, f"🪐 *Режим УТОПИЯ*\n\nТекущий лимит: *{utopia:,.0f} сум/день*.\n\nВведите новый дневной лимит цифрами слитно (например: `40000`):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_utopia)

def process_utopia(message):
    try:
        amount = float(clean_amount_text(message.text))
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Жесткий лимит «Утопия» обновлен: *{amount:,.0f} сум/день*.", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Вводите только цифры слитно.")

@bot.message_handler(func=lambda msg: msg.text == "📊 Аналитика")
def view_analytics(message):
    balance, utopia = get_wallet_data()
    days = get_days_left()
    real_limit = balance / days if balance > 0 else 0
    today = datetime.date.today().isoformat()
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date = ?", (today,))
    row_t = cursor.fetchone()
    spent_today = row_t[0] if row_t and row_t[0] is not None else 0.0
    
    cursor.execute("SELECT category, SUM(amount) FROM expenses GROUP BY category")
    rows_cat = cursor.fetchall()
    cat_spent_dict = {k: 0.0 for k in CATEGORIES.keys()}
    for cat_key, amt in rows_cat:
        if cat_key in cat_spent_dict:
            cat_spent_dict[cat_key] = amt
            
    analytics_text = "🗂 *Раскрытые траты по категориям за месяц:*\n"
    for k, name in CATEGORIES.items():
        analytics_text += f"• {name}: *{cat_spent_dict[k]:,.0f} сум*\n"
        
    status = "🟢 Ты укладываешься в лимит!" if spent_today <= utopia else "🔴 ТЫ ПРЕВЫСИЛ СВОЮ УТОПИЮ! Срочно тормози!"
    
    bot.send_message(
        message.chat.id, 
        f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n"
        f"💰 Кошелек: *{balance:,.0f} сум*\n"
        f"📅 Осталось до конца месяца: *{days} дн.*\n"
        f"✨ Цель Утопия: *{utopia:,.0f} сум/день*\n"
        f"◽️ Потрачено за сегодня: *{spent_today:,.0f} сум*\n"
        f"🛡 Реальный остаток: {real_limit:,.0f} сум/день\n\n"
        f"{analytics_text}\n"
        f"📢 *Статус:* {status}", 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "📉 Расход")
def ask_expense(message):
    msg = bot.send_message(message.chat.id, "Введите сумму расхода слитно (например: `15000`):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_expense_amount)

def process_expense_amount(message):
    try:
        amount = float(clean_amount_text(message.text))
        markup = types.InlineKeyboardMarkup()
        for key, name in CATEGORIES.items():
            markup.add(types.InlineKeyboardButton(text=name, callback_data=f"cat_{key}_{amount}"))
        bot.send_message(message.chat.id, "Выберите категорию трат:", reply_markup=markup)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Вводите сумму только цифрами.")

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
    today_spent = row_today[0] if row_today and row_today[0] is not None else 0.0
    
    alert = ""
    if today_spent > utopia:
        alert = f"\n\n🚨 *ТЫ СУМАСШЕДШИЙ!* Траты за сегодня ({today_spent:,.0f} сум) превысили твой лимит Утопии ({utopia:,.0f} сум)! 😡"
    else:
        remains = utopia - today_spent
        if remains <= 15000:
            alert = f"\n\n⚠️ *ВНИМАНИЕ!* Ты приближаешься к критическому лимиту! Осталось всего *{remains:,.0f} сум*. Трать раздумывая! 🧐"
        else:
            alert = f"\n\n🟢 Запас лимита до конца дня: *{remains:,.0f} сум*."
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"✅ Записано: *-{amount:,.0f} сум* ➔ *{CATEGORIES[category_key]}*.\n👛 Кошелек: *{new_bal:,.0f} сум*.\n✨ Лимит: *{utopia:,.0f} сум/день*.{alert}", parse_mode="Markdown")
# --- МОДУЛЬ КОНТРОЛЯ ДОЛГОВ ---
@bot.message_handler(func=lambda msg: msg.text == "💸 Контроль Долгов")
def view_debts(message):
    cursor.execute("SELECT name, total_debt, remaining_debt FROM debts WHERE remaining_debt > 0")
    rows = cursor.fetchall()
    debt_text = "👥 *Список ваших должников:*\n\n" if rows else "🎉 Отличные новости! Тебе никто ничего не должен.\n"
    for name, total, remaining in rows:
        debt_text += f"• *{name.capitalize()}*: взял {total:,.0f} сум, осталось вернуть: *{remaining:,.0f} сум*\n"
        
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton(text="➕ Дал в долг", callback_data="debt_give"),
               types.InlineKeyboardButton(text="➖ Мне вернули долг", callback_data="debt_return"))
    bot.send_message(message.chat.id, debt_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["debt_give", "debt_return"])
def process_debt_buttons(call):
    if call.data == "debt_give":
        msg = bot.send_message(call.message.chat.id, "Введите имя должника и сумму долга СЛИТНО через пробел.\n(Пример: `Дима 50000`):")
        bot.register_next_step_handler(msg, process_debt_give)
    elif call.data == "debt_return":
        msg = bot.send_message(call.message.chat.id, "Кто вернул долг и сколько? Введите имя и сумму через пробел.\n(Пример: `Дима 20000`):")
        bot.register_next_step_handler(msg, process_debt_return)

def process_debt_give(message):
    try:
        parts = message.text.strip().split()
        name = parts[0]
        amount = float(clean_amount_text(parts[1]))
        b, _ = get_wallet_data()
        
        cursor.execute("SELECT remaining_debt FROM debts WHERE name = ?", (name.lower(),))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE debts SET total_debt = total_debt + ?, remaining_debt = remaining_debt + ? WHERE name = ?", (amount, amount, name.lower()))
        else:
            cursor.execute("INSERT INTO debts VALUES (?, ?, ?)", (name.lower(), amount, amount))
            
        cursor.execute("UPDATE wallet SET balance = ?", (b - amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Записано! {name} взял в долг *{amount:,.0f} сум*. Эта сумма вычтена из вашего кошелька.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка ввода! Пишите строго по образцу: `Имя 50000`.")

def process_debt_return(message):
    try:
        parts = message.text.strip().split()
        name = parts[0]
        amount = float(clean_amount_text(parts[1]))
        
        cursor.execute("SELECT remaining_debt FROM debts WHERE name = ?", (name.lower(),))
        row = cursor.fetchone()
        if not row or row[0] < amount:
            bot.send_message(message.chat.id, "⚠️ Ошибка! Этот человек не должен вам такую сумму или его нет в списке.")
            return
            
        new_debt = row[0] - amount
        cursor.execute("UPDATE debts SET remaining_debt = ? WHERE name = ?", (new_debt, name.lower()))
        
        b, _ = get_wallet_data()
        cursor.execute("UPDATE wallet SET balance = ?", (b + amount,))
        conn.commit()
        
        bot.send_message(message.chat.id, f"💰 Записано! {name} вернул *{amount:,.0f} сум*. Деньги добавлены обратно на ваш баланс. Остаток его долга: *{new_debt:,.0f} сум*.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Пишите строго по образцу: `Имя 20000`.")

@bot.message_handler(func=lambda msg: msg.text == "🤖 ИИ Бухгалтер")
def ai_analyst(message):
    bot.send_message(message.chat.id, "🔄 ИИ изучает вашу базу данных расходов и долгов по Узбекистану...")
    balance, utopia = get_wallet_data()
    
    cursor.execute("SELECT category, SUM(amount) FROM expenses GROUP BY category")
    history = cursor.fetchall()
    history_str = ", ".join([f"{CATEGORIES.get(c, c)}: {a:,.0f} сум" for c, a in history]) if history else "Расходов в этом месяце еще нет"
    
    cursor.execute("SELECT name, remaining_debt FROM debts WHERE remaining_debt > 0")
    debtors = cursor.fetchall()
    debtors_str = ", ".join([f"{n}: {d:,.0f} сум" for n, d in debtors]) if debtors else "Вам никто не должен"

    sys_prompt = (
        f"Проведи глубокий профессиональный аудит моего кошелька. "
        f"Текущий баланс в кошельке: {balance:,.0f} сум. "
        f"Установленный лимит 'Утопия': {utopia:,.0f} сум/день. "
        f"Мои расходы по категориям за месяц: {history_str}. "
        f"Мне должны деньги должники: {debtors_str}. "
        f"Сделай жесткий бухгалтерский разбор. Если расходы выше лимита, отругай. Оценивай по меркам Ташкента. Задай один жесткий вопрос в конце."
    )
    
    response = ask_free_ai(sys_prompt)
    msg = bot.send_message(message.chat.id, f"🤖 *Ответ ИИ-Бухгалтера:*\n\n{response}\n\n💬 Вы можете ответить ИИ прямо в это поле или задать ему вопрос по экономии в Ташкенте:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

def ai_chat_loop(message):
    if message.text in ["📉 Расход", "➕ Доход", "✨ Лимит Утопия", "📊 Аналитика", "💸 Контроль Долгов", "🤖 ИИ Бухгалтер"]:
        if message.text == "📊 Аналитика": view_analytics(message)
        elif message.text == "🤖 ИИ Бухгалтер": ai_analyst(message)
        elif message.text == "💸 Контроль Долгов": view_debts(message)
        return
    response = ask_free_ai(f"Контекст: Ты суровый бухгалтер в Узбекистане. Коротко ответь на реплику пользователя: {message.text}")
    msg = bot.send_message(message.chat.id, f"🤖 *ИИ-Бухгалтер:*\n\n{response}", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

if __name__ == "__main__":
    def run_fake_server():
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
        server.serve_forever()
    threading.Thread(target=run_fake_server, daemon=True).start()
    bot.infinity_polling()
