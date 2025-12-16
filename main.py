import re
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart

API_TOKEN = "8544825319:AAH5p7uWc01O5yoH84wNBMrrfGELjifkhzQ"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

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

def calc_price(count: int):
    if count == 0:
        return 0
    if count >= 5:
        return count * 6
    return count * 5.5

async def is_admin(chat_id: int, user_id: int):
    admins = await bot.get_chat_administrators(chat_id)
    return any(a.user.id == user_id for a in admins)

# ================= SAVE MESSAGES =================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def save_group_message(msg: types.Message):
    if not msg.text:
        return

    phones = extract_phones(msg.text)
    if not phones:
        return

    chat_id = msg.chat.id
    thread_id = msg.message_thread_id or 0
    username = f"@{msg.from_user.username}" if msg.from_user.username else "без_юза"
    date = datetime.now().strftime("%Y-%m-%d")

    for phone in phones:
        cursor.execute("""
        INSERT OR REPLACE INTO messages
        (chat_id, thread_id, phone, username, message_id, date)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (chat_id, thread_id, phone, username, msg.message_id, date))

    conn.commit()

# ================= UPDATE EDITED MESSAGES =================
@dp.message(F.chat.type.in_({"group", "supergroup"}), F.content_type.in_(["text"]))
async def update_edited_message(msg: types.Message):
    if not msg.text:
        return

    phones = extract_phones(msg.text)
    chat_id = msg.chat.id
    thread_id = msg.message_thread_id or 0
    username = f"@{msg.from_user.username}" if msg.from_user.username else "без_юза"
    date = datetime.now().strftime("%Y-%m-%d")

    # Удаляем старые номера этого сообщения
    cursor.execute("""
        DELETE FROM messages
        WHERE chat_id = ? AND thread_id = ? AND message_id = ?
    """, (chat_id, thread_id, msg.message_id))

    # Добавляем новые номера
    for phone in phones:
        cursor.execute("""
            INSERT OR REPLACE INTO messages
            (chat_id, thread_id, phone, username, message_id, date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (chat_id, thread_id, phone, username, msg.message_id, date))

    conn.commit()

# ================= START =================
@dp.message(CommandStart())
async def start(msg: types.Message):
    await msg.answer(
        "Привет! Я собираю номера телефонов из групп.\n\n"
        "Чтобы получить отчет, отправь команду в личку боту:\n"
        "/day_report YYYY-MM-DD +77012345678 +77098765432 ...\n\n"
        "⚠️ Работает только для админов групп, где я был."
    )

# ================= DAY REPORT =================
@dp.message(F.text.startswith("/day_report"))
async def day_report(msg: types.Message):
    if msg.chat.type != "private":
        await msg.reply("Отчёт делается только в личку боту.")
        return

    parts = msg.text.split()
    if len(parts) < 3:
        await msg.reply("Используй:\n/day_report YYYY-MM-DD +77012345678 ...")
        return

    date = parts[1]
    numbers = parts[2:]

    # Получаем username и номера
    cursor.execute(f"""
        SELECT username, phone FROM messages
        WHERE date = ? AND phone IN ({','.join('?'*len(numbers))})
    """, (date, *numbers))

    rows = cursor.fetchall()
    if not rows:
        await msg.reply("❌ Данных по этим номерам за указанную дату нет.")
        return

    # Группируем по пользователю
    users = {}
    for username, phone in rows:
        users.setdefault(username, []).append(phone)

    # Формируем отчет с сортировкой и подсчетом суммы
    report = f"ОТЧЕТ БХ ({date})\n\n"
    total_sum = 0
    for username in sorted(users.keys(), key=lambda x: x.lower()):
        report += f"{username}\n"
        for phone in sorted(users[username]):
            report += f"{phone}\n"
        price = calc_price(len(users[username]))
        total_sum += price
        report += f"Сумма: {price}$\n\n"

    report += f"💰 ИТОГО: {total_sum}$\n"
    report += "Обменники @odmenikk, @kill_monger_3 и @swhexs"

    await msg.answer(report)

# ================= MAIN =================
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
