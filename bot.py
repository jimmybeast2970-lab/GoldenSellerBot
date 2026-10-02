import asyncio
import csv
import io
import logging
import os
import sqlite3
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup,
    LabeledPrice, Message, PreCheckoutQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PAYMENT_STARS = int(os.getenv("PAYMENT_STARS", "100"))
DB_PATH = os.getenv("DB_PATH", "golden_seller.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env")

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row

def init_db():
    db.executescript("""
    CREATE TABLE IF NOT EXISTS sellers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE NOT NULL,
        username TEXT,
        name TEXT NOT NULL,
        phone TEXT,
        address TEXT,
        bank_name TEXT,
        account_no TEXT,
        ifsc TEXT,
        upi TEXT,
        created_at TEXT NOT NULL,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        details TEXT NOT NULL,
        amount REAL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'PENDING_PAYMENT',
        stars INTEGER DEFAULT 0,
        telegram_charge_id TEXT,
        created_at TEXT NOT NULL,
        confirmed_at TEXT,
        FOREIGN KEY(seller_id) REFERENCES sellers(id)
    );
    """)
    db.commit()

class Register(StatesGroup):
    name = State()
    phone = State()
    address = State()
    bank = State()
    account = State()
    ifsc = State()
    upi = State()

class NewOrder(StatesGroup):
    details = State()
    amount = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 नया Order", callback_data="new_order")],
        [InlineKeyboardButton(text="👤 मेरी Profile", callback_data="profile"),
         InlineKeyboardButton(text="📋 मेरे Orders", callback_data="my_orders")],
        [InlineKeyboardButton(text="ℹ️ Help", callback_data="help")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 आज की Report", callback_data="admin_today"),
         InlineKeyboardButton(text="📅 महीने की Report", callback_data="admin_month")],
        [InlineKeyboardButton(text="👥 Seller List", callback_data="admin_sellers")],
        [InlineKeyboardButton(text="📥 CSV Report", callback_data="admin_csv")]
    ])

def get_seller(tg_id):
    return db.execute("SELECT * FROM sellers WHERE telegram_id=?", (tg_id,)).fetchone()

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 <b>Admin Panel</b>\n\nBot तैयार है।", reply_markup=admin_menu())
        return
    seller = get_seller(message.from_user.id)
    if seller:
        await message.answer(f"नमस्ते <b>{seller['name']}</b> 👋\nआपका Seller account active है।", reply_markup=main_menu())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Seller Registration", callback_data="register")]
        ])
        await message.answer("👋 <b>Golden Seller</b>\n\nOrder देने से पहले Seller Registration पूरा करें।", reply_markup=kb)

@dp.callback_query(F.data == "register")
async def register_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(Register.name)
    await c.message.answer("1/7️⃣ Seller का <b>पूरा नाम</b> लिखें:")

@dp.message(Register.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip(), username=message.from_user.username or "")
    await state.set_state(Register.phone)
    await message.answer("2/7️⃣ Mobile Number लिखें:")

@dp.message(Register.phone)
async def reg_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(Register.address)
    await message.answer("3/7️⃣ पूरा Address लिखें:")

@dp.message(Register.address)
async def reg_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(Register.bank)
    await message.answer("4/7️⃣ Bank Name लिखें:")

@dp.message(Register.bank)
async def reg_bank(message: Message, state: FSMContext):
    await state.update_data(bank_name=message.text.strip())
    await state.set_state(Register.account)
    await message.answer("5/7️⃣ Bank Account Number लिखें:")

@dp.message(Register.account)
async def reg_account(message: Message, state: FSMContext):
    await state.update_data(account_no=message.text.strip())
    await state.set_state(Register.ifsc)
    await message.answer("6/7️⃣ IFSC Code लिखें:")

@dp.message(Register.ifsc)
async def reg_ifsc(message: Message, state: FSMContext):
    await state.update_data(ifsc=message.text.strip())
    await state.set_state(Register.upi)
    await message.answer("7/7️⃣ UPI ID लिखें (अगर नहीं है तो <code>-</code> लिखें):")

@dp.message(Register.upi)
async def reg_upi(message: Message, state: FSMContext):
    data = await state.update_data(upi=message.text.strip())
    db.execute("""
        INSERT INTO sellers(telegram_id, username, name, phone, address, bank_name, account_no, ifsc, upi, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(telegram_id) DO UPDATE SET
          username=excluded.username,name=excluded.name,phone=excluded.phone,address=excluded.address,
          bank_name=excluded.bank_name,account_no=excluded.account_no,ifsc=excluded.ifsc,upi=excluded.upi,active=1
    """, (
        message.from_user.id, data.get("username",""), data["name"], data["phone"],
        data["address"], data["bank_name"], data["account_no"], data["ifsc"], data["upi"],
        datetime.now(timezone.utc).isoformat()
    ))
    db.commit()
    await state.clear()
    await message.answer("✅ <b>Registration complete.</b>", reply_markup=main_menu())
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, f"👤 नया Seller registered: <b>{data['name']}</b>\nTelegram ID: <code>{message.from_user.id}</code>")

@dp.callback_query(F.data == "new_order")
async def new_order(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if not get_seller(c.from_user.id):
        await c.message.answer("पहले Seller Registration पूरा करें।")
        return
    await state.set_state(NewOrder.details)
    await c.message.answer("📦 Order की details लिखें (product/quantity आदि):")

@dp.message(NewOrder.details)
async def order_details(message: Message, state: FSMContext):
    await state.update_data(details=message.text.strip())
    await state.set_state(NewOrder.amount)
    await message.answer("💰 Order amount लिखें (₹ में), जैसे <code>12500</code>:")

@dp.message(NewOrder.amount)
async def order_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "").strip())
        if amount < 0:
            raise ValueError
    except ValueError:
        await message.answer("कृपया सही amount लिखें, जैसे 12500")
        return

    seller = get_seller(message.from_user.id)
    data = await state.update_data(amount=amount)
    cur = db.execute(
        "INSERT INTO orders(seller_id,details,amount,created_at) VALUES(?,?,?,?)",
        (seller["id"], data["details"], amount, datetime.now(timezone.utc).isoformat())
    )
    db.commit()
    order_id = cur.lastrowid
    await state.clear()

    payload = f"order:{order_id}"
    await message.answer_invoice(
        title=f"Order #{order_id} confirmation",
        description=f"Order confirmation fee for Order #{order_id}",
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label="Order confirmation", amount=PAYMENT_STARS)]
    )
    await message.answer(f"⭐ Payment required: <b>{PAYMENT_STARS} Stars</b>\nPayment successful होने पर Order automatically confirm होगा.")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    if not query.invoice_payload.startswith("order:"):
        await query.answer(ok=False, error_message="Invalid order.")
        return
    order_id = int(query.invoice_payload.split(":")[1])
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order or order["status"] != "PENDING_PAYMENT":
        await query.answer(ok=False, error_message="Order unavailable or already paid.")
        return
    if query.from_user.id != db.execute(
        "SELECT telegram_id FROM sellers WHERE id=?", (order["seller_id"],)
    ).fetchone()[0]:
        await query.answer(ok=False, error_message="This order belongs to another seller.")
        return
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    sp = message.successful_payment
    order_id = int(sp.invoice_payload.split(":")[1])
    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        UPDATE orders SET status='CONFIRMED', stars=?, telegram_charge_id=?, confirmed_at=?
        WHERE id=? AND status='PENDING_PAYMENT'
    """, (sp.total_amount, sp.telegram_payment_charge_id, now, order_id))
    db.commit()
    order = db.execute("""
        SELECT o.*, s.name, s.telegram_id FROM orders o JOIN sellers s ON s.id=o.seller_id WHERE o.id=?
    """, (order_id,)).fetchone()
    await message.answer(f"✅ <b>Order #{order_id} CONFIRMED</b>\nPayment: ⭐ {sp.total_amount}\n\nआपका Order confirm हो गया।", reply_markup=main_menu())
    if ADMIN_ID:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>NEW CONFIRMED ORDER</b>\n\n"
            f"Order: <b>#{order_id}</b>\nSeller: <b>{order['name']}</b>\n"
            f"Order amount: ₹{order['amount']:,.2f}\nPayment: ⭐ {sp.total_amount}\n"
            f"Details: {order['details']}"
        )

@dp.callback_query(F.data == "profile")
async def profile(c: CallbackQuery):
    await c.answer()
    s = get_seller(c.from_user.id)
    if not s:
        await c.message.answer("Registration नहीं मिली।")
        return
    text = (
        f"👤 <b>{s['name']}</b>\n📱 {s['phone']}\n🏠 {s['address']}\n\n"
        f"🏦 Bank: {s['bank_name']}\n💳 Account: <code>{s['account_no']}</code>\n"
        f"IFSC: <code>{s['ifsc']}</code>\nUPI: <code>{s['upi']}</code>"
    )
    await c.message.answer(text, reply_markup=main_menu())

@dp.callback_query(F.data == "my_orders")
async def my_orders(c: CallbackQuery):
    await c.answer()
    s = get_seller(c.from_user.id)
    if not s:
        await c.message.answer("Registration नहीं मिली।")
        return
    rows = db.execute("SELECT * FROM orders WHERE seller_id=? ORDER BY id DESC LIMIT 20", (s["id"],)).fetchall()
    if not rows:
        await c.message.answer("अभी कोई Order नहीं है।", reply_markup=main_menu())
        return
    lines = ["📋 <b>आपके Latest Orders</b>"]
    for r in rows:
        lines.append(f"#{r['id']} | ₹{r['amount']:,.2f} | {r['status']} | {r['created_at'][:10]}")
    await c.message.answer("\n".join(lines), reply_markup=main_menu())

@dp.callback_query(F.data == "help")
async def help_cb(c: CallbackQuery):
    await c.answer()
    await c.message.answer("Order देने के लिए <b>📦 नया Order</b> दबाएँ।\nहर Order confirm करने से पहले Stars payment जरूरी है.", reply_markup=main_menu())

def admin_only(user_id):
    return ADMIN_ID and user_id == ADMIN_ID

@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not admin_only(message.from_user.id):
        return
    await message.answer("👑 Admin Panel", reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_today")
async def admin_today(c: CallbackQuery):
    await c.answer()
    if not admin_only(c.from_user.id): return
    day = datetime.now(timezone.utc).date().isoformat()
    rows = db.execute("""
        SELECT s.name, COUNT(o.id) cnt, COALESCE(SUM(o.amount),0) total
        FROM sellers s LEFT JOIN orders o ON o.seller_id=s.id AND substr(o.created_at,1,10)=?
        GROUP BY s.id ORDER BY cnt DESC
    """, (day,)).fetchall()
    total_cnt = sum(r["cnt"] for r in rows)
    total_amt = sum(r["total"] for r in rows)
    text = [f"📊 <b>Today ({day})</b>"]
    for r in rows:
        if r["cnt"]: text.append(f"{r['name']} — {r['cnt']} orders — ₹{r['total']:,.2f}")
    text.append(f"\n<b>Total:</b> {total_cnt} orders — ₹{total_amt:,.2f}")
    await c.message.answer("\n".join(text), reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_month")
async def admin_month(c: CallbackQuery):
    await c.answer()
    if not admin_only(c.from_user.id): return
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = db.execute("""
        SELECT s.name, COUNT(o.id) cnt, COALESCE(SUM(o.amount),0) total
        FROM sellers s LEFT JOIN orders o ON o.seller_id=s.id AND substr(o.created_at,1,7)=?
        GROUP BY s.id ORDER BY cnt DESC
    """, (month,)).fetchall()
    text = [f"📅 <b>Month ({month})</b>"]
    total_cnt = total_amt = 0
    for r in rows:
        if r["cnt"]:
            text.append(f"{r['name']} — {r['cnt']} orders — ₹{r['total']:,.2f}")
            total_cnt += r["cnt"]; total_amt += r["total"]
    text.append(f"\n<b>Total:</b> {total_cnt} orders — ₹{total_amt:,.2f}")
    await c.message.answer("\n".join(text), reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_sellers")
async def admin_sellers(c: CallbackQuery):
    await c.answer()
    if not admin_only(c.from_user.id): return
    rows = db.execute("SELECT name, phone, telegram_id, active FROM sellers ORDER BY name").fetchall()
    if not rows:
        await c.message.answer("No sellers.")
        return
    text = ["👥 <b>Sellers</b>"]
    for r in rows:
        text.append(f"• {r['name']} | {r['phone']} | {'Active' if r['active'] else 'Blocked'}")
    await c.message.answer("\n".join(text), reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_csv")
async def admin_csv(c: CallbackQuery):
    await c.answer()
    if not admin_only(c.from_user.id): return
    rows = db.execute("""
        SELECT o.id order_id, s.name seller, s.phone, o.details, o.amount, o.status,
               o.stars, o.created_at, o.confirmed_at
        FROM orders o JOIN sellers s ON s.id=o.seller_id ORDER BY o.id DESC
    """).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order ID","Seller","Phone","Details","Order Amount INR","Status","Stars","Created","Confirmed"])
    for r in rows:
        writer.writerow(list(r))
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    data.name = "golden_seller_orders.csv"
    await c.message.answer_document(data, caption="📥 Orders CSV Report", reply_markup=admin_menu())

async def main():
    init_db()
    print("GoldenSellerBot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
