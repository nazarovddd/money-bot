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

# Стабильная инициализация финальной базы данных версии v8
conn = sqlite3.connect("wallet_final_v8.db", check_same_thread=False)
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
    if not text: return ""
    return text.lower().replace("доход", "").replace("лимит", "").replace(" ", "").replace(",", "").replace(".", "").strip()

def ask_free_ai(prompt_text):
    try:
        url = "https://aryahcr.cc"
        data = {"prompt": prompt_text, "model": "gemini"}
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}, method='POST')
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if "content" in res_data and res_data["content"]: return res_data["content"]
            if "message" in res_data and res_data["message"]: return res_data["message"]
        return "Суровый аудит: Сальдо под угрозой! Сокращайте расходы."
    except:
        return "🤖 ИИ-Бухгалтер: Дебет не сходится с кредитом! Финансовая нейросеть Ташкента рекомендует немедленно сократить нецелевые расходы на развлечения и фастфуд, чтобы закрыть баланс месяца без дефицита. Какие меры по оптимизации сальдо вы планируете предпринять?"

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📊 Аналитика")
    btn2 = types.KeyboardButton("💸 Контроль Долгов")
    btn3 = types.KeyboardButton("🤖 ИИ Бухгалтер")
    markup.row(btn1, btn2)
    markup.row(btn3)
    return markup

@bot.message_handler(commands=['start', 'help'])
def start(message):
    welcome = (
        "🇺🇿 *Привет! Я твой новый НЕУБИВАЕМЫЙ ИИ-Бухгалтер.*\n\n"
        "Я больше никогда не зависну на кнопках. Теперь ты управляешь мной быстрыми текстовыми командами:\n\n"
        "➕ *Внести доход:* Напиши слово `доход` и сумму. Пример: `доход 500000`\n"
        "✨ *Установить лимит:* Напиши слово `лимит` и сумму. Пример: `лимит 40000`\n"
        "📉 *Внести расход за 1 секунду:* Напиши сумму и категорию через пробел.\n"
        "Доступные категории: `еда`, `поездки`, `развлечения`, `для дома`.\n"
        "Пример: `15000 еда` или `35000 развлечения`"
    )
    bot.send_message(message.chat.id, welcome, reply_markup=get_main_keyboard(), parse_mode="Markdown")
@bot.message_handler(func=lambda msg: msg.text.lower().startswith("доход"))
def process_income_direct(message):
    try:
        amount = float(clean_amount_text(message.text))
        b, utopia = get_wallet_data()
        new_bal = b + amount
        cursor.execute("UPDATE wallet SET balance = ?", (new_bal,))
        conn.commit()
        days = get_days_left()
        bot.send_message(message.chat.id, f"💰 *Баланс успешно пополнен!*\n\n👛 Всего в кошельке: *{new_bal:,.0f} сум*\n📅 До конца месяца осталось: *{days} дн.*\n✨ Твой лимит (Утопия): *{utopia:,.0f} сум/день*.", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Пишите строго в формате: `доход 500000`")

@bot.message_handler(func=lambda msg: msg.text.lower().startswith("лимит"))
def process_utopia_direct(message):
    try:
        amount = float(clean_amount_text(message.text))
        cursor.execute("UPDATE wallet SET utopia_limit = ?", (amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Жесткий лимит «Утопия» обновлен: *{amount:,.0f} сум/день*.", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Пишите строго в формате: `лимит 40000`")

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
    bot.send_message(message.chat.id, f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n\n💰 Кошелек: *{balance:,.0f} сум*\n📅 Осталось до конца месяца: *{days} дн.*\n✨ Цель Утопия: *{utopia:,.0f} сум/день*\n◽️ Потрачено за сегодня: *{spent_today:,.0f} сум*\n🛡 Реальный остаток: {real_limit:,.0f} сум/день\n\n{analytics_text}\n📢 *Статус:* {status}", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: any(cat in msg.text.lower() for cat in CATEGORIES.keys()))
def process_expense_direct(message):
    try:
        parts = message.text.lower().split()
        amount_raw = ""
        category_key = ""
        for part in parts:
            if part in CATEGORIES: category_key = part
            else: amount_raw += part
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
            if remains <= 15000: alert = f"\n\n⚠️ *ВНИМАНИЕ!* Ты приближаешься к лимиту! Осталось всего *{remains:,.0f} сум*. Трать раздумывая! 🧐"
            else: alert = f"\n\n🟢 Запас лимита до конца дня: *{remains:,.0f} сум*."
        bot.send_message(message.chat.id, f"✅ Записано: *-{amount:,.0f} сум* ➔ *{CATEGORIES[category_key]}*.\n👛 Кошелек: *{new_bal:,.0f} сум*.\n✨ Утопия: *{utopia:,.0f} сум/день*.{alert}", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Не понял расход. Пишите, например: `15000 еда` или `25000 поездки`")
# --- МОДУЛЬ КОНТРОЛЯ ДОЛГОВ ---
@bot.message_handler(func=lambda msg: msg.text == "💸 Контроль Долгов")
def view_debts(message):
    cursor.execute("SELECT name, total_debt, remaining_debt FROM debts WHERE remaining_debt > 0")
    rows = cursor.fetchall()
    debt_text = "👥 *Список ваших должников:*\n\n" if rows else "🎉 Отличные новости! Тебе никто ничего не должен.\n"
    for name, total, remaining in rows:
        debt_text += f"• *{name.capitalize()}*: взял {total:,.0f} сум, осталось вернуть: *{remaining:,.0f} сум*\n"
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton(text="➕ Дал в долг", callback_data="debt_give"), types.InlineKeyboardButton(text="➖ Мне вернули долг", callback_data="debt_return"))
    bot.send_message(message.chat.id, debt_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["debt_give", "debt_return"])
def process_debt_buttons(call):
    if call.data == "debt_give":
        msg = bot.send_message(call.message.chat.id, "Введите имя должника и сумму долга через пробел слитно.\n(Пример: `Дима 50000`):")
        bot.register_next_step_handler(msg, process_debt_give)
    elif call.data == "debt_return":
        msg = bot.send_message(call.message.chat.id, "Кто вернул долг и сколько? Введите имя и сумму через пробел слитно.\n(Пример: `Дима 20000`):")
        bot.register_next_step_handler(msg, process_debt_return)

def process_debt_give(message):
    try:
        parts = message.text.strip().split()
        name = parts[0]
        amount = float(clean_amount_text(parts[1]))
        b, _ = get_wallet_data()
        cursor.execute("SELECT remaining_debt FROM debts WHERE name = ?", (name.lower(),))
        row = cursor.fetchone()
        if row: cursor.execute("UPDATE debts SET total_debt = total_debt + ?, remaining_debt = remaining_debt + ? WHERE name = ?", (amount, amount, name.lower()))
        else: cursor.execute("INSERT INTO debts VALUES (?, ?, ?)", (name.lower(), amount, amount))
        cursor.execute("UPDATE wallet SET balance = ?", (b - amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Записано! {name} взял в долг *{amount:,.0f} сум*. Деньги вычтены из кошелька.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Образец: `Дима 50000`")

def process_debt_return(message):
    try:
        parts = message.text.strip().split()
        name = parts[0]
        amount = float(clean_amount_text(parts[1]))
        cursor.execute("SELECT remaining_debt FROM debts WHERE name = ?", (name.lower(),))
        row = cursor.fetchone()
        if not row or row[0] < amount:
            bot.send_message(message.chat.id, "⚠️ Ошибка! Сумма больше долга или человека нет в базе.")
            return
        new_debt = row[0] - amount
        cursor.execute("UPDATE debts SET remaining_debt = ? WHERE name = ?", (new_debt, name.lower()))
        b, _ = get_wallet_data()
        cursor.execute("UPDATE wallet SET balance = ?", (b + amount,))
        conn.commit()
        bot.send_message(message.chat.id, f"💰 Записано! {name} вернул *{amount:,.0f} сум*. Деньги возвращены в ваш баланс. Остаток долга: *{new_debt:,.0f} сум*.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ Ошибка! Образец: `Дима 20000`")

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
    sys_prompt = f"Проведи глубокий профессиональный аудит моего кошелька. Текущий баланс: {balance:,.0f} сум. Лимит 'Утопия': {utopia:,.0f} сум/день. Траты за месяц: {history_str}. Должники: {debtors_str}. Сделай жесткий бухгалтерский разбор. Если расходы выше лимита, отругай. Оценивай по меркам Ташкента. Задай один жесткий вопрос в конце."
    response = ask_free_ai(sys_prompt)
    msg = bot.send_message(message.chat.id, f"🤖 *Ответ ИИ-Бухгалтера:*\n\n{response}\n\n💬 Вы можете ответить ИИ прямо в это поле или задать ему вопрос по экономии в Ташкенте:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, ai_chat_loop)

def ai_chat_loop(message):
    if message.text in ["📊 Аналитика", "💸 Контроль Долгов", "🤖 ИИ Бухгалтер"]:
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
