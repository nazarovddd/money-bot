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

TOKEN = "8102394026:AAEREm1tYAs9265zJ0aKSx9Z9l2jnw3kKMM"

bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("wallet.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS wallet (balance REAL, utopia_limit REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS expenses (category TEXT, amount REAL, date TEXT)")
conn.commit()

cursor.execute("SELECT balance FROM wallet")

if not cursor.fetchone():
    cursor.execute("INSERT INTO wallet VALUES (0.0, 0.0)")
    conn.commit()

CATEGORIES = {
    "еда": "🍔 Еда",
    "поездки": "🚖 Поездки",
    "развлечения": "🎉 Развлечения",
    "для дома": "🏠 Для дома"
}

def parse_amount(text):
    s = text.strip()
    s = s.replace(" ", "").replace("\xa0", "").replace("'", "")

    if "," in s and "." in s:
        last_sep = max(s.rfind(","), s.rfind("."))
        int_part = re.sub(r"[.,]", "", s[:last_sep])
        frac_part = re.sub(r"[.,]", "", s[last_sep + 1:])
        s = f"{int_part}.{frac_part}"

    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)

        if len(parts) == 2 and len(parts[1]) == 3:
            s = "".join(parts)
        elif len(parts) == 2:
            s = parts[0] + "." + parts[1]
        else:
            s = s.replace(sep, "")

    s = re.sub(r"[^0-9.\-]", "", s)

    return float(Decimal(s))

def get_wallet_data():
    cursor.execute("SELECT balance, utopia_limit FROM wallet")
    return cursor.fetchone()

def get_days_left():
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return max(1, last_day - today.day + 1)

def ask_ai(prompt_text):
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
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8")

    except Exception as e:
        return f"Ошибка ИИ: {e}"

def keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row(
        types.KeyboardButton("📉 Расход"),
        types.KeyboardButton("➕ Доход")
    )

    kb.row(
        types.KeyboardButton("✨ Лимит"),
        types.KeyboardButton("📊 Аналитика")
    )

    kb.row(
        types.KeyboardButton("🤖 ИИ")
    )

    return kb

@bot.message_handler(commands=["start"])
def start(message):

    text = (
        "🇺🇿 ИИ-Бухгалтер запущен\n\n"
        "Доход:\n"
        "доход 500000\n\n"
        "Лимит:\n"
        "лимит 40000\n\n"
        "Расход:\n"
        "15000 еда\n"
        "55,00 поездки\n"
        "500 000 развлечения"
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard()
    )

@bot.message_handler(func=lambda m: m.text.lower().startswith("доход"))
def income(message):

    try:
        raw = message.text.lower().replace("доход", "")
        amount = parse_amount(raw)

        balance, utopia = get_wallet_data()

        new_balance = balance + amount

        cursor.execute(
            "UPDATE wallet SET balance=?",
            (new_balance,)
        )

        conn.commit()

        bot.send_message(
            message.chat.id,
            f"💰 Доход добавлен\n\nБаланс: {new_balance:,.2f} сум"
        )

    except Exception as e:

        bot.send_message(
            message.chat.id,
            f"Ошибка: {e}"
        )

@bot.message_handler(func=lambda m: m.text.lower().startswith("лимит"))
def limit(message):

    try:
        raw = message.text.lower().replace("лимит", "")
        amount = parse_amount(raw)

        cursor.execute(
            "UPDATE wallet SET utopia_limit=?",
            (amount,)
        )

        conn.commit()

        bot.send_message(
            message.chat.id,
            f"✨ Новый лимит: {amount:,.2f} сум"
        )

    except Exception as e:

        bot.send_message(
            message.chat.id,
            f"Ошибка: {e}"
        )

@bot.message_handler(func=lambda m: any(cat in m.text.lower() for cat in CATEGORIES))
def expense(message):

    try:
        parts = message.text.lower().split()

        amount_raw = ""
        category = ""

        for part in parts:

            if part in CATEGORIES:
                category = part
            else:
                amount_raw += part

        amount = parse_amount(amount_raw)

        balance, utopia = get_wallet_data()

        new_balance = balance - amount

        today = datetime.date.today().isoformat()

        cursor.execute(
            "UPDATE wallet SET balance=?",
            (new_balance,)
        )

        cursor.execute(
            "INSERT INTO expenses VALUES (?, ?, ?)",
            (category, amount, today)
        )

        conn.commit()

        bot.send_message(
            message.chat.id,
            f"✅ Расход записан\n\n"
            f"➖ {amount:,.2f} сум\n"
            f"{CATEGORIES[category]}\n"
            f"👛 Баланс: {new_balance:,.2f} сум"
        )

    except Exception as e:

        bot.send_message(
            message.chat.id,
            f"Ошибка: {e}"
        )

@bot.message_handler(func=lambda m: m.text == "📊 Аналитика")
def analytics(message):

    balance, utopia = get_wallet_data()

    days = get_days_left()

    today = datetime.date.today().isoformat()

    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE date=?",
        (today,)
    )

    row = cursor.fetchone()

    spent_today = row[0] if row[0] else 0

    real_limit = balance / days if balance > 0 else 0

    bot.send_message(
        message.chat.id,
        f"📊 Аналитика\n\n"
        f"💰 Баланс: {balance:,.2f}\n"
        f"✨ Лимит: {utopia:,.2f}\n"
        f"📉 Потрачено сегодня: {spent_today:,.2f}\n"
        f"🛡 Реальный лимит: {real_limit:,.2f}"
    )

@bot.message_handler(func=lambda m: m.text == "🤖 ИИ")
def ai(message):

    balance, utopia = get_wallet_data()

    response = ask_ai(
        f"Ты строгий бухгалтер. "
        f"Баланс {balance}. "
        f"Лимит {utopia}. "
        f"Коротко оцени ситуацию."
    )

    bot.send_message(
        message.chat.id,
        f"🤖 ИИ:\n\n{response}"
    )

def keep_alive():

    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(
        ("0.0.0.0", port),
        SimpleHTTPRequestHandler
    )

    server.serve_forever()

threading.Thread(
    target=keep_alive,
    daemon=True
).start()

while True:
    try:
        print("Бот работает...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(e)
