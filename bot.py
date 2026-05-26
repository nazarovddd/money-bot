import sqlite3
import datetime
import calendar
import urllib.request
import json
import os
import threading
import csv
import io
from http.server import SimpleHTTPRequestHandler, HTTPServer
import telebot
from telebot import types
 
# ──────────────────────────────────────────────
#  ТОКЕН: задайте переменную окружения BOT_TOKEN
#  Например: export BOT_TOKEN="ваш_токен"
# ──────────────────────────────────────────────
# Ищем переменную окружения по её названию
TOKEN = os.environ.get("BOT_TOKEN")

# Хорошая практика: добавить проверку, чтобы бот не падал с непонятной ошибкой
if not TOKEN:
    raise ValueError("8102394026:AAF5kNMBWYmOLQ7hfh4af2lTvQCJpfoCAdI")

bot = telebot.TeleBot(TOKEN)

# ──────────────────────────────────────────────
#  БАЗА ДАННЫХ
# ──────────────────────────────────────────────
DB_PATH = "wallet.db"
_local = threading.local()
 
def get_conn():
    """Отдельное соединение на каждый поток — защита от краша при параллельных запросах."""
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn
 
def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Таблица кошельков (отдельная строка на каждого пользователя)
    c.execute('''
        CREATE TABLE IF NOT EXISTS wallet (
            user_id     INTEGER PRIMARY KEY,
            balance     REAL    DEFAULT 0.0,
            utopia_limit REAL   DEFAULT 0.0
        )
    ''')
    # Расходы с user_id
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER,
            category TEXT,
            amount   REAL,
            note     TEXT DEFAULT "",
            date     TEXT
        )
    ''')
    # Доходы с user_id
    c.execute('''
        CREATE TABLE IF NOT EXISTS incomes (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER,
            amount   REAL,
            note     TEXT DEFAULT "",
            date     TEXT
        )
    ''')
    # Долги с user_id
    c.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            name          TEXT,
            total_debt    REAL,
            remaining_debt REAL
        )
    ''')
    conn.commit()
 
init_db()
 
# ──────────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ──────────────────────────────────────────────
CATEGORIES = {
    "еда":          "🍔 Еда",
    "поездки":      "🚖 Поездки",
    "развлечения":  "🎉 Развлечения",
    "для дома":     "🏠 Для дома",
    "здоровье":     "💊 Здоровье",
    "одежда":       "👕 Одежда",
    "другое":       "📦 Другое",
}
 
def get_days_left():
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return max(1, last_day - today.day + 1)
 
def get_month_start():
    return datetime.date.today().replace(day=1).isoformat()
 
def get_today():
    return datetime.date.today().isoformat()
 
def ensure_user(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO wallet (user_id) VALUES (?)", (user_id,))
    conn.commit()
 
def get_wallet(user_id: int):
    ensure_user(user_id)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT balance, utopia_limit FROM wallet WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    return row["balance"], row["utopia_limit"]
 
def set_balance(user_id: int, new_balance: float):
    conn = get_conn()
    conn.execute("UPDATE wallet SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
 
def set_utopia(user_id: int, limit: float):
    conn = get_conn()
    conn.execute("UPDATE wallet SET utopia_limit = ? WHERE user_id = ?", (limit, user_id))
    conn.commit()
 
def clean_amount(text: str) -> float:
    """Принимает '15 000', '15,000', '15000.50' и т.д."""
    if not text:
        raise ValueError
    cleaned = text.replace(" ", "").replace(",", ".")
    return float(cleaned)
 
def fmt(n: float) -> str:
    """Форматирование числа с пробелами: 1 500 000"""
    return f"{n:,.0f}".replace(",", " ")
 
# ──────────────────────────────────────────────
#  AI-БУХГАЛТЕР  (Gemini через бесплатный шлюз)
# ──────────────────────────────────────────────
def ask_ai(prompt: str) -> str:
    try:
        url = "https://aryahcr.cc"
        data = json.dumps({"prompt": prompt, "model": "gemini"}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("content") or res.get("message") or _ai_fallback()
    except Exception:
        return _ai_fallback()
 
def _ai_fallback() -> str:
    return (
        "🤖 ИИ-Бухгалтер временно недоступен.\n"
        "Совет дня: контролируй траты на развлечения — "
        "это самая «съедаемая» статья бюджета в Ташкенте. "
        "Попробуй правило 50/30/20: 50% на нужды, 30% на желания, 20% в накопления."
    )
 
# ──────────────────────────────────────────────
#  КЛАВИАТУРЫ
# ──────────────────────────────────────────────
def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📉 Расход", "➕ Доход")
    kb.row("✨ Лимит Утопия", "📊 Аналитика")
    kb.row("💸 Контроль Долгов", "📋 История")
    kb.row("📤 Экспорт CSV", "🤖 ИИ Бухгалтер")
    kb.row("🔄 Сброс баланса")
    return kb
 
MENU_BUTTONS = {
    "📉 Расход", "➕ Доход", "✨ Лимит Утопия", "📊 Аналитика",
    "💸 Контроль Долгов", "📋 История", "📤 Экспорт CSV",
    "🤖 ИИ Бухгалтер", "🔄 Сброс баланса"
}
 
# ──────────────────────────────────────────────
#  /start
# ──────────────────────────────────────────────
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    uid = message.from_user.id
    ensure_user(uid)
    text = (
        "👋 *Привет! Я твой личный ИИ-Бухгалтер.*\n\n"
        "🔹 Веду расходы и доходы по категориям\n"
        "🔹 Контролирую дневной лимит «Утопия»\n"
        "🔹 Слежу за должниками\n"
        "🔹 Строю аналитику за месяц\n"
        "🔹 Экспортирую данные в CSV\n"
        "🔹 Даю советы от ИИ по финансам\n\n"
        "💡 *Суммы вводи цифрами:* `15000` или `15 000` или `15000.50`\n\n"
        "Используй кнопки меню 👇"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_kb(), parse_mode="Markdown")
 
# ──────────────────────────────────────────────
#  ДОХОД
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "➕ Доход")
def ask_income(message):
    msg = bot.send_message(message.chat.id, "💰 Введите сумму дохода (например: `500000`):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, income_amount_step)
 
def income_amount_step(message):
    if message.text in MENU_BUTTONS:
        return route_menu(message)
    try:
        amount = clean_amount(message.text)
        msg = bot.send_message(message.chat.id, "📝 Добавьте заметку (источник дохода) или отправьте `-` чтобы пропустить:")
        bot.register_next_step_handler(msg, lambda m: income_save(m, amount))
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Введите сумму цифрами.")
 
def income_save(message, amount):
    if message.text in MENU_BUTTONS:
        return route_menu(message)
    uid = message.from_user.id
    note = "" if message.text.strip() == "-" else message.text.strip()
    b, utopia = get_wallet(uid)
    new_bal = b + amount
    set_balance(uid, new_bal)
    conn = get_conn()
    conn.execute(
        "INSERT INTO incomes (user_id, amount, note, date) VALUES (?, ?, ?, ?)",
        (uid, amount, note, get_today())
    )
    conn.commit()
    days = get_days_left()
    daily = new_bal / days if new_bal > 0 else 0
    bot.send_message(
        message.chat.id,
        f"✅ *Доход записан!*\n\n"
        f"➕ Поступило: *{fmt(amount)} сум*\n"
        f"👛 Баланс: *{fmt(new_bal)} сум*\n"
        f"📅 До конца месяца: *{days} дн.*\n"
        f"📊 Можно тратить в день: *{fmt(daily)} сум*",
        reply_markup=main_kb(), parse_mode="Markdown"
    )
 
# ──────────────────────────────────────────────
#  РАСХОД
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📉 Расход")
def ask_expense(message):
    msg = bot.send_message(message.chat.id, "💸 Введите сумму расхода (например: `15000`):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, expense_amount_step)
 
def expense_amount_step(message):
    if message.text in MENU_BUTTONS:
        return route_menu(message)
    try:
        amount = clean_amount(message.text)
        kb = types.InlineKeyboardMarkup(row_width=2)
        for key, name in CATEGORIES.items():
            kb.add(types.InlineKeyboardButton(name, callback_data=f"cat|{key}|{amount}"))
        bot.send_message(message.chat.id, "📂 Выберите категорию:", reply_markup=kb)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Введите сумму цифрами.")
 
@bot.callback_query_handler(func=lambda c: c.data.startswith("cat|"))
def expense_category_cb(call):
    _, cat_key, amount_str = call.data.split("|")
    amount = float(amount_str)
    uid = call.from_user.id
    b, utopia = get_wallet(uid)
    new_bal = b - amount
    today = get_today()
 
    set_balance(uid, new_bal)
    conn = get_conn()
    conn.execute(
        "INSERT INTO expenses (user_id, category, amount, date) VALUES (?, ?, ?, ?)",
        (uid, cat_key, amount, today)
    )
    conn.commit()
 
    # Сколько потрачено за сегодня
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE user_id=? AND date=?",
        (uid, today)
    )
    today_spent = c.fetchone()[0]
 
    if utopia > 0:
        remains = utopia - today_spent
        if today_spent > utopia:
            alert = f"\n\n🚨 *ЛИМИТ ПРЕВЫШЕН!* Потрачено {fmt(today_spent)} из {fmt(utopia)} сум — перерасход {fmt(-remains)} сум!"
        elif remains <= 15000:
            alert = f"\n\n⚠️ Осталось до лимита: *{fmt(remains)} сум* — будь осторожен!"
        else:
            alert = f"\n\n🟢 Запас до лимита: *{fmt(remains)} сум*"
    else:
        alert = "\n\n💡 Установи лимит «Утопия» для контроля трат."
 
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"✅ *Расход записан*\n\n"
            f"📂 {CATEGORIES[cat_key]}: *-{fmt(amount)} сум*\n"
            f"👛 Баланс: *{fmt(new_bal)} сум*"
            f"{alert}"
        ),
        parse_mode="Markdown"
    )
 
# ──────────────────────────────────────────────
#  ЛИМИТ УТОПИЯ
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "✨ Лимит Утопия")
def ask_utopia(message):
    _, utopia = get_wallet(message.from_user.id)
    msg = bot.send_message(
        message.chat.id,
        f"🪐 *Режим УТОПИЯ*\n\nТекущий лимит: *{fmt(utopia)} сум/день*\n\nВведите новый дневной лимит:",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, utopia_save)
 
def utopia_save(message):
    if message.text in MENU_BUTTONS:
        return route_menu(message)
    try:
        amount = clean_amount(message.text)
        set_utopia(message.from_user.id, amount)
        bot.send_message(
            message.chat.id,
            f"✅ Лимит «Утопия» обновлён: *{fmt(amount)} сум/день*",
            reply_markup=main_kb(), parse_mode="Markdown"
        )
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Введите сумму цифрами.")
 
# ──────────────────────────────────────────────
#  АНАЛИТИКА
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📊 Аналитика")
def view_analytics(message):
    uid = message.from_user.id
    balance, utopia = get_wallet(uid)
    days = get_days_left()
    today = get_today()
    month_start = get_month_start()
    conn = get_conn()
    c = conn.cursor()
 
    # Потрачено сегодня
    c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE user_id=? AND date=?",
        (uid, today)
    )
    spent_today = c.fetchone()[0]
 
    # Потрачено за месяц
    c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE user_id=? AND date>=?",
        (uid, month_start)
    )
    spent_month = c.fetchone()[0]
 
    # Доходы за месяц
    c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM incomes WHERE user_id=? AND date>=?",
        (uid, month_start)
    )
    income_month = c.fetchone()[0]
 
    # По категориям за месяц
    c.execute(
        "SELECT category, SUM(amount) FROM expenses WHERE user_id=? AND date>=? GROUP BY category",
        (uid, month_start)
    )
    cat_data = {row[0]: row[1] for row in c.fetchall()}
 
    daily_available = balance / days if balance > 0 else 0
 
    cat_lines = ""
    for key, name in CATEGORIES.items():
        amt = cat_data.get(key, 0)
        if amt > 0:
            cat_lines += f"  • {name}: *{fmt(amt)} сум*\n"
    if not cat_lines:
        cat_lines = "  Расходов пока нет\n"
 
    if utopia > 0:
        status = "🟢 Укладываешься в лимит!" if spent_today <= utopia else f"🔴 Превышен лимит на *{fmt(spent_today - utopia)} сум*!"
    else:
        status = "💡 Лимит «Утопия» не установлен"
 
    bot.send_message(
        message.chat.id,
        f"📊 *ФИНАНСОВАЯ АНАЛИТИКА*\n"
        f"_{datetime.date.today().strftime('%d.%m.%Y')}_\n\n"
        f"👛 Баланс: *{fmt(balance)} сум*\n"
        f"📅 До конца месяца: *{days} дн.*\n"
        f"🛡 Доступно в день: *{fmt(daily_available)} сум*\n"
        f"✨ Лимит «Утопия»: *{fmt(utopia)} сум/день*\n\n"
        f"📆 *За этот месяц:*\n"
        f"  ➕ Доходы: *{fmt(income_month)} сум*\n"
        f"  📉 Расходы: *{fmt(spent_month)} сум*\n"
        f"  💹 Экономия: *{fmt(income_month - spent_month)} сум*\n\n"
        f"🗂 *По категориям:*\n{cat_lines}\n"
        f"🕐 Сегодня потрачено: *{fmt(spent_today)} сум*\n"
        f"📢 Статус: {status}",
        reply_markup=main_kb(), parse_mode="Markdown"
    )
 
# ──────────────────────────────────────────────
#  ИСТОРИЯ (последние 15 операций)
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📋 История")
def view_history(message):
    uid = message.from_user.id
    conn = get_conn()
    c = conn.cursor()
 
    c.execute(
        "SELECT date, category, amount, note FROM expenses WHERE user_id=? ORDER BY id DESC LIMIT 15",
        (uid,)
    )
    expenses = c.fetchall()
 
    c.execute(
        "SELECT date, amount, note FROM incomes WHERE user_id=? ORDER BY id DESC LIMIT 5",
        (uid,)
    )
    incomes = c.fetchall()
 
    text = "📋 *Последние расходы:*\n"
    if expenses:
        for row in expenses:
            date, cat, amt, note = row
            cat_name = CATEGORIES.get(cat, cat)
            note_str = f" ({note})" if note else ""
            text += f"  `{date}` {cat_name} — *{fmt(amt)} сум*{note_str}\n"
    else:
        text += "  Расходов нет\n"
 
    text += "\n💰 *Последние доходы:*\n"
    if incomes:
        for row in incomes:
            date, amt, note = row
            note_str = f" ({note})" if note else ""
            text += f"  `{date}` ➕ *{fmt(amt)} сум*{note_str}\n"
    else:
        text += "  Доходов нет\n"
 
    bot.send_message(message.chat.id, text, reply_markup=main_kb(), parse_mode="Markdown")
 
# ──────────────────────────────────────────────
#  ЭКСПОРТ CSV
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📤 Экспорт CSV")
def export_csv(message):
    uid = message.from_user.id
    conn = get_conn()
    c = conn.cursor()
    month_start = get_month_start()
 
    c.execute(
        "SELECT date, category, amount, note FROM expenses WHERE user_id=? AND date>=? ORDER BY date",
        (uid, month_start)
    )
    expenses = c.fetchall()
 
    c.execute(
        "SELECT date, amount, note FROM incomes WHERE user_id=? AND date>=? ORDER BY date",
        (uid, month_start)
    )
    incomes = c.fetchall()
 
    output = io.StringIO()
    output.write("\ufeff")  # BOM для корректного открытия в Excel
    writer = csv.writer(output, delimiter=";")
 
    writer.writerow(["Тип", "Дата", "Категория", "Сумма (сум)", "Заметка"])
    for row in incomes:
        writer.writerow(["Доход", row[0], "—", row[1], row[2]])
    for row in expenses:
        writer.writerow(["Расход", row[0], CATEGORIES.get(row[1], row[1]), row[2], row[3]])
 
    csv_bytes = output.getvalue().encode("utf-8-sig")
    filename = f"budget_{datetime.date.today().strftime('%Y_%m')}.csv"
 
    bot.send_document(
        message.chat.id,
        (filename, io.BytesIO(csv_bytes)),
        caption=f"📤 Экспорт за {datetime.date.today().strftime('%B %Y')}",
        reply_markup=main_kb()
    )
 
# ──────────────────────────────────────────────
#  СБРОС БАЛАНСА
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔄 Сброс баланса")
def ask_reset(message):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Да, сбросить", callback_data="reset_yes"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="reset_no")
    )
    bot.send_message(
        message.chat.id,
        "⚠️ *Вы уверены?*\n\nЭто сбросит баланс и удалит все данные за текущий месяц.\nИстория долгов сохранится.",
        reply_markup=kb, parse_mode="Markdown"
    )
 
@bot.callback_query_handler(func=lambda c: c.data in ["reset_yes", "reset_no"])
def reset_cb(call):
    uid = call.from_user.id
    if call.data == "reset_yes":
        conn = get_conn()
        month_start = get_month_start()
        conn.execute("UPDATE wallet SET balance=0.0 WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM expenses WHERE user_id=? AND date>=?", (uid, month_start))
        conn.execute("DELETE FROM incomes WHERE user_id=? AND date>=?", (uid, month_start))
        conn.commit()
        bot.edit_message_text(
            "✅ Баланс сброшен. Начинай новый месяц с чистого листа!",
            call.message.chat.id, call.message.message_id
        )
    else:
        bot.edit_message_text("❌ Сброс отменён.", call.message.chat.id, call.message.message_id)
 
# ──────────────────────────────────────────────
#  КОНТРОЛЬ ДОЛГОВ
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "💸 Контроль Долгов")
def view_debts(message):
    uid = message.from_user.id
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT name, total_debt, remaining_debt FROM debts WHERE user_id=? AND remaining_debt > 0",
        (uid,)
    )
    rows = c.fetchall()
 
    if rows:
        total_owed = sum(r[2] for r in rows)
        text = f"👥 *Должники* (всего долгов: *{fmt(total_owed)} сум*):\n\n"
        for name, total, remaining in rows:
            paid = total - remaining
            pct = int(paid / total * 100) if total > 0 else 0
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            text += (
                f"👤 *{name.capitalize()}*\n"
                f"   Взял: {fmt(total)} сум\n"
                f"   Вернул: {fmt(paid)} сум ({pct}%)\n"
                f"   Осталось: *{fmt(remaining)} сум*\n"
                f"   [{bar}]\n\n"
            )
    else:
        text = "🎉 Отлично! Тебе никто ничего не должен.\n"
 
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("➕ Дал в долг", callback_data="debt_give"),
        types.InlineKeyboardButton("➖ Вернули долг", callback_data="debt_return")
    )
    kb.add(types.InlineKeyboardButton("🗑 Закрыть все долги", callback_data="debt_clear_all"))
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")
 
@bot.callback_query_handler(func=lambda c: c.data in ["debt_give", "debt_return", "debt_clear_all"])
def debt_buttons_cb(call):
    if call.data == "debt_give":
        msg = bot.send_message(
            call.message.chat.id,
            "Введите имя и сумму через пробел:\n`Дима 50000`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, debt_give_step)
    elif call.data == "debt_return":
        msg = bot.send_message(
            call.message.chat.id,
            "Кто вернул и сколько? Введите через пробел:\n`Дима 20000`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, debt_return_step)
    elif call.data == "debt_clear_all":
        uid = call.from_user.id
        conn = get_conn()
        conn.execute(
            "UPDATE debts SET remaining_debt=0 WHERE user_id=?", (uid,)
        )
        conn.commit()
        bot.edit_message_text(
            "✅ Все долги закрыты.", call.message.chat.id, call.message.message_id
        )
 
def debt_give_step(message):
    if message.text in MENU_BUTTONS:
        return route_menu(message)
    try:
        parts = message.text.strip().split()
        name = parts[0].lower()
        amount = clean_amount(parts[1])
        uid = message.from_user.id
        b, _ = get_wallet(uid)
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, remaining_debt FROM debts WHERE user_id=? AND name=?", (uid, name)
        )
        row = c.fetchone()
        if row:
            conn.execute(
                "UPDATE debts SET total_debt=total_debt+?, remaining_debt=remaining_debt+? WHERE id=?",
                (amount, amount, row[0])
            )
        else:
            conn.execute(
                "INSERT INTO debts (user_id, name, total_debt, remaining_debt) VALUES (?,?,?,?)",
                (uid, name, amount, amount)
            )
        set_balance(uid, b - amount)
        conn.commit()
        bot.send_message(
            message.chat.id,
            f"✅ *{name.capitalize()}* взял в долг *{fmt(amount)} сум*.\n"
            f"Сумма вычтена из кошелька.",
            reply_markup=main_kb(), parse_mode="Markdown"
        )
    except Exception:
        bot.send_message(message.chat.id, "⚠️ Ошибка. Пишите строго: `Имя 50000`", parse_mode="Markdown")
 
def debt_return_step(message):
    if message.text in MENU_BUTTONS:
        return route_menu(message)
    try:
        parts = message.text.strip().split()
        name = parts[0].lower()
        amount = clean_amount(parts[1])
        uid = message.from_user.id
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, remaining_debt FROM debts WHERE user_id=? AND name=?", (uid, name)
        )
        row = c.fetchone()
        if not row or row[1] < amount:
            bot.send_message(message.chat.id, "⚠️ Такого должника нет или сумма превышает долг.")
            return
        new_debt = row[1] - amount
        conn.execute("UPDATE debts SET remaining_debt=? WHERE id=?", (new_debt, row[0]))
        b, _ = get_wallet(uid)
        set_balance(uid, b + amount)
        conn.commit()
        bot.send_message(
            message.chat.id,
            f"💰 *{name.capitalize()}* вернул *{fmt(amount)} сум*.\n"
            f"Деньги добавлены на баланс.\n"
            f"Остаток долга: *{fmt(new_debt)} сум*",
            reply_markup=main_kb(), parse_mode="Markdown"
        )
    except Exception:
        bot.send_message(message.chat.id, "⚠️ Ошибка. Пишите строго: `Имя 20000`", parse_mode="Markdown")
 
# ──────────────────────────────────────────────
#  ИИ-БУХГАЛТЕР
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🤖 ИИ Бухгалтер")
def ai_analyst(message):
    uid = message.from_user.id
    bot.send_message(message.chat.id, "🔄 Анализирую ваши финансы...")
    balance, utopia = get_wallet(uid)
    month_start = get_month_start()
    conn = get_conn()
    c = conn.cursor()
 
    c.execute(
        "SELECT category, SUM(amount) FROM expenses WHERE user_id=? AND date>=? GROUP BY category",
        (uid, month_start)
    )
    cat_data = c.fetchall()
    history_str = ", ".join(
        [f"{CATEGORIES.get(cat, cat)}: {fmt(amt)} сум" for cat, amt in cat_data]
    ) if cat_data else "расходов нет"
 
    c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM incomes WHERE user_id=? AND date>=?",
        (uid, month_start)
    )
    income_total = c.fetchone()[0]
 
    c.execute(
        "SELECT name, remaining_debt FROM debts WHERE user_id=? AND remaining_debt>0",
        (uid,)
    )
    debtors = c.fetchall()
    debtors_str = ", ".join([f"{n}: {fmt(d)} сум" for n, d in debtors]) if debtors else "нет должников"
 
    prompt = (
        f"Ты строгий финансовый консультант в Ташкенте, Узбекистан. "
        f"Проведи краткий аудит кошелька клиента:\n"
        f"- Баланс: {fmt(balance)} сум\n"
        f"- Доходы за месяц: {fmt(income_total)} сум\n"
        f"- Лимит 'Утопия': {fmt(utopia)} сум/день\n"
        f"- Расходы по категориям: {history_str}\n"
        f"- Должники: {debtors_str}\n"
        f"Дай 3 конкретных совета по экономии с учётом цен в Ташкенте. "
        f"Будь конкретным и честным. В конце задай один острый вопрос."
    )
    response = ask_ai(prompt)
    msg = bot.send_message(
        message.chat.id,
        f"🤖 *ИИ-Бухгалтер:*\n\n{response}\n\n"
        f"💬 Можете задать вопрос по финансам:",
        reply_markup=main_kb(), parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ai_chat_loop)
 
def ai_chat_loop(message):
    if message.text in MENU_BUTTONS:
        return route_menu(message)
    response = ask_ai(
        f"Ты финансовый консультант в Узбекистане. "
        f"Коротко и конкретно ответь на вопрос пользователя про деньги и экономию: {message.text}"
    )
    msg = bot.send_message(
        message.chat.id,
        f"🤖 *ИИ-Бухгалтер:*\n\n{response}",
        reply_markup=main_kb(), parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, ai_chat_loop)
 
# ──────────────────────────────────────────────
#  РОУТЕР МЕНЮ (для обработки кнопок внутри шагов)
# ──────────────────────────────────────────────
def route_menu(message):
    handlers = {
        "📉 Расход":           ask_expense,
        "➕ Доход":            ask_income,
        "✨ Лимит Утопия":     ask_utopia,
        "📊 Аналитика":        view_analytics,
        "💸 Контроль Долгов":  view_debts,
        "📋 История":          view_history,
        "📤 Экспорт CSV":      export_csv,
        "🤖 ИИ Бухгалтер":    ai_analyst,
        "🔄 Сброс баланса":    ask_reset,
    }
    handler = handlers.get(message.text)
    if handler:
        handler(message)
 
# ──────────────────────────────────────────────
#  ЗАПУСК
# ──────────────────────────────────────────────
if __name__ == "__main__":
    def run_health_server():
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
        server.serve_forever()
 
    threading.Thread(target=run_health_server, daemon=True).start()
    print("🤖 Бот запущен!")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)
 
