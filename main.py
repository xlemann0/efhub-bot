import logging
import sqlite3
import time
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

BOT_TOKEN = "8761736244:AAHJrJUOHz6ujzlkOdgqzyGqPlSyYzMHztI"
OWNER_ID = 5874144878
CHANNEL_USERNAME = "@eFhubTime_Shop"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= DATABASE =================
def db_connect():
    return sqlite3.connect("bot_database.db")

def setup_database():
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_message_id INTEGER,
            ad_type TEXT,
            caption TEXT,
            photo TEXT,
            status TEXT DEFAULT 'active',
            created_at REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS bot_admins (user_id INTEGER PRIMARY KEY)")
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (channel_username TEXT PRIMARY KEY)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS template_admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_text TEXT
        )
    """)
    
    conn.commit()
    cursor.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (OWNER_ID,))
    
    default_data = {
        "rules": "📜 Botimiz qoidalari tez orada kiritiladi.",
        "prices": "💰 E'lon narxlari: 10 tadan keyin har bir e'lon 5.000 so'm.",
        "payment_card": "💳 8600 0000 0000 0000\n👤 F.I.O: Admin Ismi Familiyasi",
        "buy_default_photo": "",
        "sotish_default_photo": ""
    }
    for key, val in default_data.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

setup_database()

def get_setting(key):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else ""

def update_setting(key, value):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM bot_admins WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def get_garants_text():
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_text FROM template_admins")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return "    ▪️ Hozircha shablon adminlar yo'q"
    return "\n".join([f"    ▪️ {row[0]}" for row in rows])

# FSM holatlari
class ElonState(StatesGroup):
    photo = State()
    google = State()
    obmen_choice = State()
    price_type = State()
    price = State()
    comment = State()
    buy_budget = State()
    buy_google = State()
    buy_comment = State()
    confirm = State()

class AdminState(StatesGroup):
    waiting_for_text = State()
    current_key = State()
    add_admin_id = State()
    add_channel_username = State()
    set_buy_photo = State()
    set_sotish_photo = State()
    add_template_admin = State()

class EditPriceState(StatesGroup):
    new_price = State()
    ad_id = State()

# Klaviaturalar
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📢 E’lon berish")
    builder.button(text="📁 E’lonlarim")
    builder.button(text="👨‍💻 Adminlar")
    builder.button(text="📜 Qoidalar")
    builder.button(text="💰 E’lon narxlari")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def admin_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="💳 To'lov karta va F.I.O ni sozlash", callback_data="edit_payment_card"))
    builder.row(types.InlineKeyboardButton(text="➕ Bot adminini qo'shish", callback_data="add_bot_admin"))
    builder.row(types.InlineKeyboardButton(text="👥 Shablon admin qo'shish", callback_data="add_template_admin"))
    builder.row(types.InlineKeyboardButton(text="📢 Majburiy obuna kanali qo'shish", callback_data="add_force_channel"))
    builder.row(types.InlineKeyboardButton(text="📜 Qoidalarni tahrirlash", callback_data="edit_rules"))
    builder.row(types.InlineKeyboardButton(text="🖼 Sotish e'loni namuna rasmini sozlash", callback_data="set_sotish_photo"))
    builder.row(types.InlineKeyboardButton(text="🖼 Olish e'loni uchun shablon rasm sozlash", callback_data="set_buy_photo"))
    builder.row(types.InlineKeyboardButton(text="👥 Kunlik aktivlar statistikasi", callback_data="daily_stats"))
    return builder.as_markup()

def yes_no_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha", callback_data="yes")
    builder.button(text="❌ Yo'q", callback_data="no")
    builder.row(types.InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="cancel"))
    builder.adjust(2, 1)
    return builder.as_markup()

def confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Yuborish ✅", callback_data="send_to_channel")
    builder.button(text="Bekor qilish ❌", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()

async def check_subscription(user_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT channel_username FROM channels")
    channels = cursor.fetchall()
    conn.close()
    
    if not channels:
        return True
        
    for ch in channels:
        ch_username = ch[0]
        try:
            member = await bot.get_chat_member(chat_id=ch_username, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            pass
    return True

@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if not await check_subscription(user_id):
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("SELECT channel_username FROM channels")
        channels = cursor.fetchall()
        conn.close()
        
        builder = InlineKeyboardBuilder()
        for ch in channels:
            ch_name = ch[0]
            builder.row(types.InlineKeyboardButton(text=f"Obuna bo'lish ➕ {ch_name}", url=f"https://t.me/{ch_name.replace('@', '')}"))
        builder.row(types.InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub"))
        
        return await message.answer("Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:", reply_markup=builder.as_markup())
        
    user = message.from_user
    user_link = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"
    
    caption = (
        f"Assalomu alaykum {user_link}\n\n"
        f"@eFhubTime_Shop ning avto elon botiga xush kelibsiz! 🚀\n\n"
        f"<b>Rasmiy sahifalarimiz:</b>\n"
        f"@eFhub_Time va @eFhubTime_Shop"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍💻 Dasturchi", url="https://t.me/mekhanizatsiya")
    
    await message.answer(caption, parse_mode="HTML", reply_markup=builder.as_markup())
    await message.answer("Mijoz uchun menyu:", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery, state: FSMContext):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        await start_handler(call.message, state)
    else:
        await call.answer("Hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Sizda bu buyruqdan foydalanish huquqi yo'q.")
    await state.clear()
    await message.answer("🔧 <b>Admin paneliga xush kelibsiz!</b>", parse_mode="HTML", reply_markup=admin_main_menu())

@dp.callback_query(lambda c: c.data in ["edit_payment_card", "edit_rules", "add_bot_admin", "add_template_admin", "add_force_channel", "set_buy_photo", "set_sotish_photo", "daily_stats"])
async def admin_actions(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    if call.data == "edit_payment_card":
        await state.update_data(current_key="payment_card")
        await state.set_state(AdminState.waiting_for_text)
        await call.message.edit_text("💳 Yangi to'lov karta raqami va egasining F.I.O sini yuboring:")
    elif call.data == "edit_rules":
        await state.update_data(current_key="rules")
        await state.set_state(AdminState.waiting_for_text)
        await call.message.edit_text("📜 Yangi Qoidalar matnini yuboring:")
    elif call.data == "add_bot_admin":
        await state.set_state(AdminState.add_admin_id)
        await call.message.edit_text("➕ Yangi adminning Telegram ID raqamini yuboring:")
    elif call.data == "add_template_admin":
        await state.set_state(AdminState.add_template_admin)
        await call.message.edit_text("👥 Shablon admin ma'lumotini yuboring (masalan: <code>@username - Ism</code>):", parse_mode="HTML")
    elif call.data == "add_force_channel":
        await state.set_state(AdminState.add_channel_username)
        await call.message.edit_text("📢 Majburiy obuna kanalining username'ini yuboring (masalan: @kanal_nomi):")
    elif call.data == "set_buy_photo":
        await state.set_state(AdminState.set_buy_photo)
        await call.message.edit_text("🖼 Olish e'loni uchun ishlatiladigan doimiy rasmni yuboring:")
    elif call.data == "set_sotish_photo":
        await state.set_state(AdminState.set_sotish_photo)
        await call.message.edit_text("🖼 Sotish e'loni uchun **namuna (shablon)** rasmini yuboring:")
    elif call.data == "daily_stats":
        conn = db_connect()
        cursor = conn.cursor()
        day_ago = time.time() - 86400
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM ads WHERE created_at > ?", (day_ago,))
        active_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM ads WHERE created_at > ?", (day_ago,))
        total_ads = cursor.fetchone()[0]
        conn.close()
        
        builder = InlineKeyboardBuilder().button(text="⬅️ Orqaga", callback_data="back_to_admin")
        await call.message.edit_text(
            f"📊 <b>So'nggi 24 soatlik statistika:</b>\n\n"
            f"👤 Faol e'lon beruvchilar: {active_users} ta\n"
            f"📝 Yuborilgan e'lonlar: {total_ads} ta",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )

@dp.callback_query(lambda c: c.data == "back_to_admin")
async def back_to_admin(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🔧 <b>Admin paneliga xush kelibsiz!</b>", parse_mode="HTML", reply_markup=admin_main_menu())

@dp.message(AdminState.waiting_for_text)
async def save_admin_text(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    update_setting(data.get("current_key"), message.text)
    await state.clear()
    await message.answer("Ma'lumot muvaffaqiyatli yangilandi! ✅", reply_markup=main_menu())

@dp.message(AdminState.add_template_admin)
async def process_add_template_admin(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    admin_info = message.text.strip()
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO template_admins (admin_text) VALUES (?)", (admin_info,))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer("Shablon admin muvaffaqiyatli qo'shildi! ✅", reply_markup=main_menu())

@dp.message(AdminState.add_admin_id)
async def process_add_admin(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        new_admin_id = int(message.text.strip())
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        conn.close()
        await state.clear()
        await message.answer("Yangi bot admini qo'shildi! ✅", reply_markup=main_menu())
    except ValueError:
        await message.answer("Iltimos, to'g'ri raqamli Telegram ID kiriting:")

@dp.message(AdminState.add_channel_username)
async def process_add_channel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    ch_name = message.text.strip()
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO channels (channel_username) VALUES (?)", (ch_name,))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer("Majburiy obuna kanali qo'shildi! ✅", reply_markup=main_menu())

@dp.message(AdminState.set_buy_photo)
async def process_set_buy_photo(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.photo:
        return await message.answer("Iltimos rasm yuboring!")
    file_id = message.photo[-1].file_id
    update_setting("buy_default_photo", file_id)
    await state.clear()
    await message.answer("Olish e'loni uchun shablon rasm saqlandi! ✅", reply_markup=main_menu())

@dp.message(AdminState.set_sotish_photo)
async def process_set_sotish_photo(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.photo:
        return await message.answer("Iltimos rasm yuboring!")
    file_id = message.photo[-1].file_id
    update_setting("sotish_default_photo", file_id)
    await state.clear()
    await message.answer("Sotish e'loni uchun namuna rasm muvaffaqiyatli saqlandi! ✅", reply_markup=main_menu())

@dp.message(lambda m: m.text == "👨‍💻 Adminlar")
async def show_admins(message: types.Message):
    garants_text = get_garants_text()
    await message.answer(f"👨‍💻 <b>Shablon adminlar va garantlar:</b>\n\n{garants_text}", parse_mode="HTML")

@dp.message(lambda m: m.text == "📜 Qoidalar")
async def show_rules(message: types.Message):
    await message.answer(get_setting("rules"))

@dp.message(lambda m: m.text == "💰 E’lon narxlari")
async def show_prices(message: types.Message):
    await message.answer(get_setting("prices"))

@dp.message(lambda m: m.text == "📁 E’lonlarim")
async def show_my_ads(message: types.Message):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, caption, status FROM ads WHERE user_id = ? AND status = 'active'", (message.from_user.id,))
    ads = cursor.fetchall()
    conn.close()
    
    if not ads:
        return await message.answer("Sizda hozircha faol e'lonlar mavjud emas. 📭")
    
    await message.answer("📋 Sizning faol e'lonlaringiz:")
    for ad in ads:
        ad_id, caption, status = ad
        builder = InlineKeyboardBuilder()
        builder.button(text="📉 Narxni tushirish", callback_data=f"edit_price_{ad_id}")
        builder.button(text="❌ Sotildi", callback_data=f"sold_{ad_id}")
        builder.adjust(2)
        
        short_text = caption[:100] + "..." if len(caption) > 100 else caption
        await message.answer(f"🆔 <b>E'lon ID:</b> #{ad_id}\n\n{short_text}", parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data.startswith("edit_price_"))
async def ask_new_price(call: types.CallbackQuery, state: FSMContext):
    ad_id = call.data.split("_")[2]
    await state.update_data(ad_id=ad_id)
    await state.set_state(EditPriceState.new_price)
    await call.message.answer("💵 Yangi tushirilgan narxni kiriting (masalan: 199.000):")

@dp.message(EditPriceState.new_price)
async def process_new_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data.get("ad_id")
    new_price = message.text
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT channel_message_id, caption, photo FROM ads WHERE id = ?", (ad_id,))
    ad = cursor.fetchone()
    
    if ad:
        msg_id, old_caption, photo = ad
        lines = old_caption.split("\n")
        updated_lines = []
        
        for line in lines:
            if "Narx:" in line or "BUDJET:" in line:
                prefix = "💴 Narx: " if "Narx:" in line else "💴 BUDJET: "
                if "~~" in line:
                    parts = line.split("~~")
                    old_base_price = parts[-1].strip().replace(" so'm", "")
                    updated_lines.append(f"{prefix}~~{old_base_price}~~ {new_price} so'm")
                else:
                    old_val = line.replace(prefix, "").replace(" so'm", "").strip()
                    updated_lines.append(f"{prefix}~~{old_val}~~ {new_price} so'm")
            else:
                updated_lines.append(line)
        
        updated_caption = "\n".join(updated_lines)
        
        try:
            if photo:
                await bot.edit_message_caption(chat_id=CHANNEL_USERNAME, message_id=msg_id, caption=updated_caption, parse_mode="HTML")
            else:
                await bot.edit_message_text(chat_id=CHANNEL_USERNAME, message_id=msg_id, text=updated_caption, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Asl xabarni tahrirlashda xato: {e}")

        fast_caption = f"#FAST ⚡️\n\n{new_price} so'm"
        
        try:
            new_msg = await bot.send_message(
                chat_id=CHANNEL_USERNAME, 
                text=fast_caption, 
                parse_mode="HTML", 
                reply_to_message_id=msg_id
            )
            
            cursor.execute("UPDATE ads SET caption = ?, channel_message_id = ? WHERE id = ?", (updated_caption, new_msg.message_id, ad_id))
            conn.commit()
        except Exception as e:
            logging.error(f"Fast xabar yuborishda xato: {e}")
            
    conn.close()
    await state.clear()
    await message.answer("E'lon narxi tushirildi va kanalda faqat #FAST hamda yangi narx reply qilindi! ✅", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data.startswith("sold_"))
async def mark_as_sold(call: types.CallbackQuery):
    ad_id = call.data.split("_")[1]
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT channel_message_id, caption, photo FROM ads WHERE id = ?", (ad_id,))
    ad = cursor.fetchone()
    
    if ad:
        msg_id, old_caption, photo = ad
        lines = old_caption.split("\n")
        updated_lines = []
        
        for line in lines:
            if "Narx:" in line or "BUDJET:" in line:
                prefix = "💴 Narx: " if "Narx:" in line else "💴 BUDJET: "
                updated_lines.append(f"{prefix}#SOTILDI")
            else:
                updated_lines.append(line)
                
        new_caption = "\n".join(updated_lines)
        cursor.execute("UPDATE ads SET status = 'closed', caption = ? WHERE id = ?", (new_caption, ad_id))
        conn.commit()
        
        try:
            if photo:
                await bot.edit_message_caption(chat_id=CHANNEL_USERNAME, message_id=msg_id, caption=new_caption, parse_mode="HTML")
            else:
                await bot.edit_message_text(chat_id=CHANNEL_USERNAME, message_id=msg_id, text=new_caption, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Xato: {e}")
            
    conn.close()
    await call.message.edit_text("E'lon 'Sotildi' deb belgilandi va kanaldagi narx o'rniga #SOTILDI yozildi! ✅")

@dp.message(lambda m: m.text == "📢 E’lon berish")
async def elon_berish(message: types.Message):
    user_id = message.from_user.id
    if not await check_subscription(user_id):
        return await message.answer("Avval kanallarga obuna bo'ling! ⚠️")
        
    conn = db_connect()
    cursor = conn.cursor()
    current_time = time.time()
    day_ago = current_time - 86400
    
    cursor.execute("SELECT COUNT(*) FROM ads WHERE user_id = ? AND created_at > ?", (user_id, day_ago))
    count = cursor.fetchone()[0]
    
    if count >= 10:
        cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        balance = res[0] if res else 0
        
        if balance >= 5000:
            cursor.execute("UPDATE balances SET balance = balance - 5000 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            
            builder = InlineKeyboardBuilder()
            builder.button(text="🛍 Sotish e'loni", callback_data="sotish")
            builder.button(text="🛒 Olish e'loni", callback_data="olish")
            builder.adjust(2)
            return await message.answer("⚠️ Kunlik 10 ta limit tugadi. Balansingizdan 5.000 so'm yechilib, ruxsat berildi. ✅", reply_markup=builder.as_markup())
        else:
            card_info = get_setting("payment_card")
            conn.close()
            builder = InlineKeyboardBuilder().button(text="✅ To'ladim (Tekshirish)", callback_data="check_payment")
            return await message.answer(
                f"⚠️ <b>24 soatlik 10 ta e'lon limiti tugadi!</b>\n\n"
                f"Keyingi e'lonlar uchun to'lov sharti: <b>5.000 so'm</b>\n\n"
                f"<b>To'lov uchun karta va egasi:</b>\n{card_info}\n\n"
                f"Pulni o'tkazib, quyidagi tugmani bosing:",
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
            
    conn.close()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🛍 Sotish e'loni", callback_data="sotish")
    builder.button(text="🛒 Olish e'loni", callback_data="olish")
    builder.adjust(2)
    await message.answer("Qanday turdagi elon joylamoqchisiz?", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data == "check_payment")
async def check_payment_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO balances (user_id, balance) VALUES (?, 5000) ON CONFLICT(user_id) DO UPDATE SET balance = balance + 5000", (user_id,))
    conn.commit()
    conn.close()
    await call.message.edit_text("To'lovingiz qabul qilindi va balans to'ldirildi! ✅\nEndi qaytadan '📢 E’lon berish' tugmasini bosing.")

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_handler(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("Jarayon bekor qilindi. ❌", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data == "sotish")
async def start_sotish_process(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(elon_type="sotish")
    sotish_photo = get_setting("sotish_default_photo")
    
    if sotish_photo:
        await call.message.answer_photo(
            photo=sotish_photo, 
            caption="💡 **E'tibor bering!** Akkount rasmini xuddi shu ko'rinishda (namunadagidek) skrinshot qilib yuborishingiz kerak."
        )
    
    await state.set_state(ElonState.photo)
    await call.message.answer("📸 Endi o'z akkountingizning rasmini yuboring:")

@dp.message(ElonState.photo)
async def process_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        return await message.answer("Iltimos rasm yuboring! ⚠️")
    await state.update_data(photo=message.photo[-1].file_id)
    await state.set_state(ElonState.google)
    await message.answer("🔐 Akkountingizga Google yoki Game Center ulanganmi?", reply_markup=yes_no_keyboard())

@dp.callback_query(lambda c: c.data in ["yes", "no"], StateFilter(ElonState.google))
async def process_google(call: types.CallbackQuery, state: FSMContext):
    status = "Ulangan" if call.data == "yes" else "Toza"
    await state.update_data(google=status)
    await state.set_state(ElonState.obmen_choice)
    await call.message.edit_text("♻️ Ushbu akkountingizga obmen ko'rasizmi?", reply_markup=yes_no_keyboard())

@dp.callback_query(lambda c: c.data in ["yes", "no"], StateFilter(ElonState.obmen_choice))
async def process_obmen(call: types.CallbackQuery, state: FSMContext):
    obmen_status = "Bor" if call.data == "yes" else "Yoq"
    await state.update_data(obmen=obmen_status)
    await state.set_state(ElonState.price_type)
    
    builder = InlineKeyboardBuilder().button(text="📝 Narxini kiritish", callback_data="enter_price")
    await call.message.edit_text("📋 Akkount narxini kiriting:", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data == "enter_price", StateFilter(ElonState.price_type))
async def request_price(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ElonState.price)
    await call.message.answer("💵 Akkount narxini yuboring (masalan: 299.000):")

@dp.message(ElonState.price)
async def process_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await state.set_state(ElonState.comment)
    await message.answer("📝 Qo'shimcha izoh yozishingiz mumkin:")

@dp.message(ElonState.comment)
async def process_sotish_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=message.text)
    data = await state.get_data()
    garants_text = get_garants_text()
    
    # Foydalanuvchining bosiladigan havolasi (profil linki)
    user = message.from_user
    contact_link = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"
    
    caption = (
        f"#SOTILADI\n\n"
        f"💴 Narx: {data.get('price')} so'm\n"
        f"♻️ Obmen ko'rish: {data.get('obmen')}\n"
        f"⚠️ Google & Game Center: {data.get('google')}\n"
        f"☎️ Murojaat: {contact_link}\n\n"
        f"📋 Ma'lumot:\n{data.get('comment')}\n\n"
        f"♻️OLDI SOTDI GARANT ADMINLAR\n"
        f"{garants_text}\n\n"
        f"🔻ELON BERISH UCHUN BOTIMIZ\n"
        f"      @eFhubShop_Bot"
    )
    await state.update_data(final_text=caption)
    await state.set_state(ElonState.confirm)
    
    if data.get("photo"):
        await message.answer_photo(photo=data.get("photo"), caption=caption, parse_mode="HTML")
    else:
        await message.answer(caption, parse_mode="HTML")
    await message.answer("✅ E'lon yuborishga tayyor!", reply_markup=confirm_keyboard())

@dp.callback_query(lambda c: c.data == "olish")
async def start_olish_process(call: types.CallbackQuery, state: FSMContext):
    buy_photo = get_setting("buy_default_photo")
    await state.update_data(elon_type="olish", photo=buy_photo if buy_photo else None)
    await state.set_state(ElonState.buy_budget)
    await call.message.answer("💵 E'lon uchun byudjetingizni yuboring (masalan: 500.000):")

@dp.message(ElonState.buy_budget)
async def process_buy_budget(message: types.Message, state: FSMContext):
    await state.update_data(budget=message.text)
    await state.set_state(ElonState.buy_google)
    await message.answer("🔐 Google yoki Game Center akkount ko'rasizmi?", reply_markup=yes_no_keyboard())

@dp.callback_query(lambda c: c.data in ["yes", "no"], StateFilter(ElonState.buy_google))
async def process_buy_google(call: types.CallbackQuery, state: FSMContext):
    google_status = "FAQAT_TOZA" if call.data == "no" else "ULANGAN"
    await state.update_data(buy_google=google_status)
    await state.set_state(ElonState.buy_comment)
    await call.message.edit_text("📝 Qanday akkaunt kerakligini to'liq yozing:")

@dp.message(ElonState.buy_comment)
async def process_buy_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=message.text)
    data = await state.get_data()
    garants_text = get_garants_text()
    tag = "#OLINADI #FAQAT_TOZA" if data.get('buy_google') == "FAQAT_TOZA" else "#OLINADI"
    
    # Foydalanuvchining bosiladigan havolasi (profil linki)
    user = message.from_user
    contact_link = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"
    
    caption = (
        f"{tag}\n\n"
        f"💴 BUDJET: {data.get('budget')} so'm\n"
        f"📋 Ma'lumot:\n{data.get('comment')}\n\n"
        f"☎️ Murojaat: {contact_link}\n\n"
        f"♻️OLDI SOTDI GARANT ADMINLAR\n"
        f"{garants_text}\n\n"
        f"🔻ELON BERISH UCHUN BOTIMIZ\n"
        f"      @eFhubShop_Bot"
    )
    await state.update_data(final_text=caption)
    await state.set_state(ElonState.confirm)
    
    if data.get("photo"):
        await message.answer_photo(photo=data.get("photo"), caption=caption, parse_mode="HTML")
    else:
        await message.answer(caption, parse_mode="HTML")
    await message.answer("✅ E'lon yuborishga tayyor!", reply_markup=confirm_keyboard())

@dp.callback_query(lambda c: c.data == "send_to_channel", StateFilter(ElonState.confirm))
async def send_to_channel_handler(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    final_text = data.get("final_text")
    photo = data.get("photo")
    user_id = call.from_user.id
    
    try:
        if photo:
            sent_message = await bot.send_photo(chat_id=CHANNEL_USERNAME, photo=photo, caption=final_text, parse_mode="HTML")
        else:
            sent_message = await bot.send_message(chat_id=CHANNEL_USERNAME, text=final_text, parse_mode="HTML")
            
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ads (user_id, channel_message_id, ad_type, caption, photo, status, created_at) VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (user_id, sent_message.message_id, data.get("elon_type"), final_text, photo, time.time())
        )
        conn.commit()
        conn.close()
            
        channel_name_trimmed = CHANNEL_USERNAME.replace("@", "")
        post_link = f"https://t.me/{channel_name_trimmed}/{sent_message.message_id}"
        
        builder = InlineKeyboardBuilder().button(text="E’lonimni ko'rish 👁", url=post_link)
        
        await call.message.delete()
        await call.message.answer("E'loningiz muvaffaqiyatli kanalga joylandi! ✅", reply_markup=main_menu())
        await call.message.answer("Quyidagi tugma orqali e'loningizni ko'rishingiz mumkin:", reply_markup=builder.as_markup())
        
    except Exception as e:
        await call.message.answer(f"Xatolik yuz berdi! Bot kanalga admin qilinganligini tekshiring.\nXato: {e}", reply_markup=main_menu())
        
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
