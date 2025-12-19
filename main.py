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
REPORT_THREAD_ID = 8  # тема "ОТЧЕТЫ"

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
    date TEXT
)
""")
conn.commit()

# ================= UTILS =================
def extract_phones(text: str):
    return re.findall(r"\+77\d{9}", text or "")

def extract_username(text: str):
    users = re.findall(r"@[\w\d_]+", text or "")
    return users[-1] if users else None

def calc_price(count: int):
    if count >= 5:
        return count * 6
    return count * 5.5

# ================= SAVE MESSAGES =================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
@dp.edited_message(F.chat.type.in_({"group", "supergroup"}))
async def save_message(msg: types.Message):
    if msg.message_thread_id != REPORT_THREAD_ID:
        return
    if not msg.text:
        return
    if "слетел" in msg.text.lower():
        return

    phones = extract_phones(msg.text)
    username = extract_username(msg.text)

    if not phones or not username:
        return

    date = datetime.now().strftime("%Y-%m-%d")

    for phone in phones:
        cursor.execute("""
            INSERT INTO messages (chat_id, thread_id, phone, username, date)
            VALUES (?, ?, ?, ?, ?)
        """, (
            msg.chat.id,
            msg.message_thread_id,
            phone,
            username,
            date
        ))

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
@dp.callback_query(F.data.in_(["date_today", "date_yesterday"]))
async def set_quick_date(call: types.CallbackQuery, state: FSMContext):
    date = datetime.now() if call.data == "date_today" else datetime.now() - timedelta(days=1)
    date = date.strftime("%Y-%m-%d")

    await state.update_data(date=date)
    await state.set_state(ReportState.waiting_numbers)
    await call.message.edit_text(
        f"📅 Дата: {date}\n\nОтправь номера (+77...)"
    )

@dp.callback_query(F.data == "date_custom")
async def custom_date_request(call: types.CallbackQuery):
    await call.message.edit_text("Отправь дату в формате YYYY-MM-DD")

# ================= CUSTOM DATE =================
@dp.message(ReportState.waiting_date)
async def set_custom_date(msg: types.Message, state: FSMContext):
    try:
        datetime.strptime(msg.text, "%Y-%m-%d")
    except ValueError:
        await msg.answer("❌ Неверный формат даты")
        return

    await state.update_data(date=msg.text)
    await state.set_state(ReportState.waiting_numbers)
    await msg.answer("Теперь отправь номера (+77...)")

# ================= BUILD REPORT =================
@dp.message(ReportState.waiting_numbers)
async def build_report(msg: types.Message, state: FSMContext):
    numbers = extract_phones(msg.text)
    if not numbers:
        await msg.answer("❌ Номера не найдены")
        return

    data = await state.get_data()
    date = data["date"]

    cursor.execute(f"""
        SELECT username, phone FROM messages
        WHERE date = ? AND phone IN ({','.join('?' * len(numbers))})
    """, (date, *numbers))

    rows = cursor.fetchall()
    if not rows:
        await msg.answer("❌ Нет данных за эту дату")
        await state.clear()
        return

    users = {}
    for user, phone in rows:
        users.setdefault(user, set()).add(phone)

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
