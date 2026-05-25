```python
import sqlite3
import datetime
import calendar
import urllib.request
import json
import os
import threading
import re
from decimal import Decimal
from http.server import SimpleHTTPRequestHandler, HTTPServer
import telebot
from telebot import types

# =========================
# ВСТАВЬ СВОЙ НОВЫЙ ТОКЕН
# =========================
TOKEN = "8102394026:AAEREm1tYAs9265zJ0aKSx9Z9l2jnw3kKMM"

bot = telebot.TeleBot(TOKEN)

# =========================
# БАЗА ДАННЫХ
# =========================
conn = sqlite3.connect("wallet_final_v4.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS wallet (
    balance REAL,
    utopia_limit REAL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS expenses (
    category TEXT,
    amount REAL,
    date TEXT
)
''')

conn.commit()

cursor.execute("SELECT balance FROM wallet")

if not cursor.fetchone():
    cursor.execute("INSERT INTO wallet VALUES (0.0, 0.0)")
    conn.commit()

# =========================
# КАТЕГОРИИ
# =========================
CATEGORIES = {
    "еда": "🍔 Еда",
    "поездки": "🚖 Поездки",
    "развлечения": "🎉 Развлечения",
    "для дома": "🏠 Для дома"
}

# =========================
# УМНЫЙ ПАРСЕР СУММ
# =========================
def parse_amount(text):
    s = text.strip()

    s = (
        s.replace('\xa0', '')
         .replace(' ', '')
         .replace("'", "")
    )

    if not s:
        raise ValueError("empty amount")

    # Если есть и точка и запятая
    if ',' in s and '.' in s:
        last_sep_pos = max(s.rfind(','), s.rfind('.'))

        int_part = re.sub(r'[.,]', '', s[:last_sep_pos])
        frac_part = re.sub(r'[.,]', '', s[last_sep_pos + 1:])

        if frac_part:
            s = f"{int_part}.{frac_part}"
        else:
            s = int_part

    # Только один разделитель
    elif ',' in s or '.' in s:
        sep = ',' if ',' in s else '.'
        parts = s.split(sep)

        # 500,000 -> 500000
        if (
            len(parts) == 2
            and len(parts[1]) == 3
            and parts[0].isdigit()
            and parts[1].isdigit()
        ):
            s = ''.join(parts)

        # 55,00 -> 55.00
        elif (
            len(parts) == 2
            and parts[0].isdigit()
            and parts[1].isdigit()
        ):
            s = parts[0] + '.' + parts[1]

        else:
            s = s.replace(sep, '')

    s = re.sub(r'[^0-9.\-]', '', s)

    return float(Decimal(s))

# =========================
# ОСТАЛОСЬ ДНЕЙ
# =========================
def get_days_left():
    today = datetime.date.today()

    last_day = calendar.monthrange(
        today.year,
        today.month
    )[1]

    return max(1, last_day - today.day + 1)

# =========================
# ДАННЫЕ КОШЕЛЬКА
# =========================
def get_wallet_data():
    cursor.execute(
        "SELECT balance, utopia_limit FROM wallet"
    )

    return cursor.fetchone()

# =========================
# FREE AI
# =========================
def ask_free_ai(prompt_text):
    try:
        url = "https://text.pollinations.ai/openai"

        data = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt_text
                }
            ],
            "model": "openai"
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode('utf-8')

    except Exception as e:
        return f"Ошибка связи с ИИ: {e}"

# =========================
# КЛАВИАТУРА
# =========================
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    btn1 = types.KeyboardButton(
        "📉 Инструкция Расхода"
    )

    btn2 = types.KeyboardButton(
        "➕ Инструкция Дохода"
    )

    btn3 = types.KeyboardButton(
        "✨ Инструкция Утопии"
    )

    btn4 = types.KeyboardButton(
        "📊 Аналитика"
    )

    btn5 = types.KeyboardButton(
        "🤖 ИИ Бухгалтер"
    )

    markup.row(btn1, btn2)
    markup.row(btn3, btn4)
    markup.row(btn5)

    return markup

# =========================
# START
# =========================
@bot.message_handler(commands=['start', 'help'])
def start(message):

    welcome = (
        "🇺🇿 *Привет! Я твой ИИ-Бухгалтер!*\n\n"

        "➕ Доход:\n"
        "`доход 500000`\n\n"

        "✨ Лимит:\n"
        "`лимит 40000`\n\n"

        "📉 Расход:\n"
        "`15000 еда`\n"
        "`55,00 поездки`\n"
        "`500 000 развлечения`"
    )

    bot.send_message(
        message.chat.id,
        welcome,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# =========================
# ИНСТРУКЦИИ
# =========================
@bot.message_handler(
    func=lambda msg: msg.text == "➕ Инструкция Дохода"
)
def inst_income(message):

    bot.send_message(
        message.chat.id,
        "💰 Пример:\n`доход 500000`\n`доход 500 000`\n`доход 55,00`",
        parse_mode="Markdown"
    )

@bot.message_handler(
    func=lambda msg: msg.text == "✨ Инструкция Утопии"
)
def inst_utopia(message):

    bot.send_message(
        message.chat.id,
        "🪐 Пример:\n`лимит 40000`\n`лимит 40 000`",
        parse_mode="Markdown"
    )

@bot.message_handler(
    func=lambda msg: msg.text == "📉 Инструкция Расхода"
)
def inst_expense(message):

    bot.send_message(
        message.chat.id,
        "🛍 Пример:\n`15000 еда`\n`500 000 поездки`\n`55,00 развлечения`",
        parse_mode="Markdown"
    )

# =========================
# ДОХОД
# =========================
@bot.message_handler(
    func=lambda msg: msg.text.lower().startswith("доход")
)
def process_income_direct(message):

    try:
        raw_val = (
            message.text
            .lower()
            .replace("доход", "")
        )

        amount = parse_amount(raw_val)

        balance, utopia = get_wallet_data()

        new_balance = balance + amount

        cursor.execute(
            "UPDATE wallet SET balance = ?",
            (new_balance,)
        )

        conn.commit()

        days = get_days_left()

        bot.send_message(
            message.chat.id,
            (
                f"💰 Баланс пополнен!\n\n"
                f"👛 Кошелек: {new_balance:,.2f} сум\n"
                f"📅 Осталось дней: {days}\n"
                f"✨ Утопия: {utopia:,.2f} сум/день"
            )
        )

    except Exception as e:

        bot.send_message(
            message.chat.id,
            f"⚠️ Ошибка: {e}"
        )

# =========================
# ЛИМИТ
# =========================
@bot.message_handler(
    func=lambda msg: msg.text.lower().startswith("лимит")
)
def process_utopia_direct(message):

    try:
        raw_val = (
            message.text
            .lower()
            .replace("лимит", "")
        )

        amount = parse_amount(raw_val)

        cursor.execute(
            "UPDATE wallet SET utopia_limit = ?",
            (amount,)
        )

        conn.commit()

        bot.send_message(
            message.chat.id,
            f"✅ Новый лимит: {amount:,.2f} сум/день"
        )

    except Exception as e:

        bot.send_message(
            message.chat.id,
            f"⚠️ Ошибка: {e}"
        )

# =========================
# АНАЛИТИКА
# =========================
@bot.message_handler(
    func=lambda msg: msg.text == "📊 Аналитика"
)
def view_analytics(message):

    balance, utopia = get_wallet_data()

    days = get_days_left()

    real_limit = (
        balance / days
        if balance > 0 else 0
    )

    today = datetime.date.today().isoformat()

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE date = ?",
        (today,)
    )

    row = cursor.fetchone()

    spent_today = (
        row[0]
        if row and row[0] is not None
        else 0.0
    )

    if spent_today <= utopia:
        status = "🟢 Всё нормально"
    else:
        status = "🔴 Лимит превышен"

    text = (
        f"📊 АНАЛИТИКА\n\n"

        f"💰 Баланс: {balance:,.2f} сум\n"
        f"📅 Осталось дней: {days}\n"
        f"✨ Лимит: {utopia:,.2f} сум\n"
        f"📉 Потрачено сегодня: {spent_today:,.2f} сум\n"
        f"🛡 Реальный лимит: {real_limit:,.2f} сум/день\n\n"

        f"{status}"
    )

    bot.send_message(
        message.chat.id,
        text
    )

# =========================
# РАСХОДЫ
# =========================
@bot.message_handler(
    func=lambda msg: any(
        cat in msg.text.lower()
        for cat in CATEGORIES.keys()
    )
)
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

        amount = parse_amount(amount_raw)

        if not category_key or amount <= 0:
            raise ValueError("Неверная сумма")

        balance, utopia = get_wallet_data()

        new_balance = balance - amount

        today = datetime.date.today().isoformat()

        cursor.execute(
            "UPDATE wallet SET balance = ?",
            (new_balance,)
        )

        cursor.execute(
            "INSERT INTO expenses VALUES (?, ?, ?)",
            (
                category_key,
                amount,
                today
            )
        )

        conn.commit()

        cursor.execute(
            "SELECT SUM(amount) FROM expenses WHERE date = ?",
            (today,)
        )

        row_today = cursor.fetchone()

        today_spent = (
            row_today[0]
            if row_today and row_today[0] is not None
            else 0.0
        )

        if today_spent > utopia:

            alert = (
                f"\n🚨 Лимит превышен!\n"
                f"Сегодня потрачено: "
                f"{today_spent:,.2f} сум"
            )

        else:

            remains = utopia - today_spent

            alert = (
                f"\n🟢 Остаток лимита: "
                f"{remains:,.2f} сум"
            )

        bot.send_message(
            message.chat.id,
            (
                f"✅ Расход записан\n\n"
                f"➖ {amount:,.2f} сум\n"
                f"📂 {CATEGORIES[category_key]}\n"
                f"👛 Баланс: {new_balance:,.2f} сум"
                f"{alert}"
            )
        )

    except Exception as e:

        bot.send_message(
            message.chat.id,
            f"⚠️ Ошибка: {e}"
        )

# =========================
# ИИ БУХГАЛТЕР
# =========================
@bot.message_handler(
    func=lambda msg: msg.text == "🤖 ИИ Бухгалтер"
)
def ai_analyst(message):

    bot.send_message(
        message.chat.id,
        "🔄 ИИ анализирует бюджет..."
    )

    balance, utopia = get_wallet_data()

    prompt = (
        f"Ты строгий бухгалтер в Ташкенте. "
        f"Баланс: {balance} сум. "
        f"Лимит: {utopia} сум/день. "
        f"Коротко оцени ситуацию."
    )

    response = ask_free_ai(prompt)

    msg = bot.send_message(
        message.chat.id,
        f"🤖 ИИ-Бухгалтер:\n\n{response}"
    )

    bot.register_next_step_handler(
        msg,
        ai_chat_loop
    )

# =========================
# AI CHAT LOOP
# =========================
def ai_chat_loop(message):

    menu_buttons = [
        "📉 Инструкция Расхода",
        "➕ Инструкция Дохода",
        "✨ Инструкция Утопии",
        "📊 Аналитика",
        "🤖 ИИ Бухгалтер"
    ]

    if message.text in menu_buttons:
        return

    response = ask_free_ai(
        f"Ты бухгалтер. Ответь коротко: {message.text}"
    )

    msg = bot.send_message(
        message.chat.id,
        f"🤖 ИИ:\n\n{response}"
    )

    bot.register_next_step_handler(
        msg,
        ai_chat_loop
    )

# =========================
# KEEP ALIVE SERVER
# =========================
if __name__ == "__main__":

    def run_fake_server():

        port = int(
            os.environ.get("PORT", 10000)
        )

        server = HTTPServer(
            ('0.0.0.0', port),
            SimpleHTTPRequestHandler
        )

        server.serve_forever()

    threading.Thread(
        target=run_fake_server,
        daemon=True
    ).start()

    print("БОТ ЗАПУЩЕН")

    bot.infinity_polling()
```
