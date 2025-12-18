import re
import asyncio
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

API_TOKEN = "8544825319:AAH5p7uWc01O5yoH84wNBMrrfGELjifkhzQ"

REPORT_THREAD_ID = 8  # ID темы "ОТЧЕТЫ"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================= FSM =================
class ReportState(StatesGroup):
    waiting_date = State()
    waiting_numbers = State()

# ================= SQLITE =================
conn = sqlite3.connect("group_reports.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    chat_id INTEGER,
    thread_id INTEGER,
    phone TEXT,
    username TEXT,
    message_id INTEGER,
    date TEXT,
    PRIMARY KEY (chat_id, thread_id, phone)
)
""")
conn.commit()

# ================= UTILS =================
def extract_phones(text: str):
    return re.findall(r"\+77\d{9}", text or "")

def extract_username_from_text(text: str):
    match = re.search(r"@[\w\d_]+", text or "")
    return match.group(0) if match else None

def is_valid_report_message(text: str):
    t = (text or "").lower()
    if "слетел" in t:
        return False
    if "встал" not in t:
        return False
    if not extract_phones(text):
        return False
    if not extract_username_from_text(text):
        return False
    return True

def calc_price(count: int):
    if count == 0:
        return 0
    if count >= 5:
        return count * 6
    return count * 5.5

# ================= SAVE + EDIT =================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
@dp.edited_message(F.chat.type.in_({"group", "supergroup"}))
async def save_or_update_message(msg: types.Message):
    if msg.message_thread_id != REPORT_THREAD_ID:
        return
    if not msg.text:
        return
    if not is_valid_report_message(msg.text):
        return

    phones = extract_phones(msg.text)
    username = extract_username_from_text(msg.text)
    date = datetime.now().strftime("%Y-%m-%d")

    chat_id = msg.chat.id
    thread_id = msg.message_thread_id or 0

    cursor.execute("""
        DELETE FROM messages
        WHERE chat_id = ? AND thread_id = ? AND message_id = ?
    """, (chat_id, thread_id, msg.message_id))

    for phone in set(phones):
        cursor.execute("""
            INSERT OR IGNORE INTO messages
            (chat_id, thread_id, phone, username, message_id, date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (chat_id, thread_id, phone, username, msg.message_id, date))

    conn.commit()

# ================= START =================
@dp.message(CommandStart())
async def start(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔘 Сделать отчёт", callback_data="make_report")]
    ])
    await msg.answer("Выбери действие:", reply_markup=kb)

# ================= MAKE REPORT =================
@dp.callback_query(F.data == "make_report")
async def choose_date(call: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="date_today")],
        [InlineKeyboardButton(text="📅 Вчера", callback_data="date_yesterday")],
        [InlineKeyboardButton(text="📅 Другая дата", callback_data="date_custom")]
    ])
    await call.message.edit_text("Выбери дату отчёта:", reply_markup=kb)
    await state.set_state(ReportState.waiting_date)

# ================= DATE SELECT =================
@dp.callback_query(F.data.in_(["date_today", "date_yesterday", "date_custom"]))
async def set_date(call: types.CallbackQuery, state: FSMContext):
    if call.data == "date_today":
        date = datetime.now().strftime("%Y-%m-%d")
    elif call.data == "date_yesterday":
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        await call.message.edit_text("Отправь дату в формате YYYY-MM-DD")
        return

    await state.update_data(date=date)
    await state.set_state(ReportState.waiting_numbers)
    await call.message.edit_text(
        f"Дата выбрана: {date}\n\n"
        "Теперь отправь номера телефонов\n"
        "(через пробел или с новой строки)"
    )

# ================= CUSTOM DATE =================
@dp.message(ReportState.waiting_date)
async def custom_date(msg: types.Message, state: FSMContext):
    try:
        datetime.strptime(msg.text, "%Y-%m-%d")
    except ValueError:
        await msg.answer("❌ Неверный формат. Нужно YYYY-MM-DD")
        return

    await state.update_data(date=msg.text)
    await state.set_state(ReportState.waiting_numbers)
    await msg.answer("Теперь отправь номера телефонов")

# ================= BUILD REPORT =================
@dp.message(ReportState.waiting_numbers)
async def build_report(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    date = data["date"]

    numbers = extract_phones(msg.text)
    if not numbers:
        await msg.answer("❌ Я не нашёл номера +77...")
        return

    cursor.execute(f"""
        SELECT username, phone FROM messages
        WHERE date = ? AND phone IN ({','.join('?' * len(numbers))})
    """, (date, *numbers))

    rows = cursor.fetchall()
    if not rows:
        await msg.answer("❌ Нет данных")
        await state.clear()
        return

    users = {}
    for username, phone in rows:
        users.setdefault(username, set()).add(phone)

    report = f"ОТЧЕТ БХ ({date})\n\n"
    total = 0

    for user in sorted(users):
        report += f"{user}\n"
        for phone in sorted(users[user]):
            report += f"{phone}\n"
        price = calc_price(len(users[user]))
        total += price
        report += f"Сумма: {price}$\n\n"

    report += f"💰 ИТОГО: {total}$\n"
    report += "Обменники @odmenikk, @kill_monger_3 и @swhexs"

    await msg.answer(report)
    await state.clear()

# ================= MAIN =================
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
