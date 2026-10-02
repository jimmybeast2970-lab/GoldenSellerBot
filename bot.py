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
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "1897213917").
PAYMENT_UPI = os.getenv("PAYMENT_UPI", "YOUR-UPI@upi").strip()
ORDER_CONFIRM_FEE = int(os.getenv("ORDER_CONFIRM_FEE", "51").strip() or "51")
DB_PATH = os.getenv("DB_PATH", "golden_seller.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row


def now():
    return datetime.now(timezone.utc).isoformat()


def column_exists(table, column):
    return any(r["name"] == column for r in db.execute(f"PRAGMA table_info({table})").fetchall())


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
        confirmed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS recharge_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        screenshot_file_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        reviewed_at TEXT,
        reviewed_by INTEGER
    );

    CREATE TABLE IF NOT EXISTS wallet_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        type TEXT NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
    );
    """)

    if not column_exists("sellers", "wallet"):
        db.execute("ALTER TABLE sellers ADD COLUMN wallet INTEGER DEFAULT 0")
    db.commit()


class Register(StatesGroup):
    name = State()
    phone = State()
    address = State()
    bank = State()
    account = State()
    ifsc = State()
    upi = State()


class EditProfile(StatesGroup):
    value = State()


class NewOrder(StatesGroup):
    details = State()
    amount = State()


class Recharge(StatesGroup):
    amount = State()
    screenshot = State()


class AdminWallet(StatesGroup):
    amount = State()


class Broadcast(StatesGroup):
    message = State()


def seller_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 नया Order", callback_data="new_order"),
         InlineKeyboardButton(text="📋 My Orders", callback_data="my_orders")],
        [InlineKeyboardButton(text="💰 Wallet", callback_data="wallet"),
         InlineKeyboardButton(text="➕ Add Money", callback_data="recharge")],
        [InlineKeyboardButton(text="👤 Profile", callback_data="profile"),
         InlineKeyboardButton(text="✏️ Edit Profile", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🏆 Rank", callback_data="rank"),
         InlineKeyboardButton(text="📈 Margin", callback_data="margin")],
        [InlineKeyboardButton(text="📖 Guide", callback_data="guide"),
         InlineKeyboardButton(text="🔎 AWB Search", callback_data="awb")],
        [InlineKeyboardButton(text="🗑️ Delete Profile", callback_data="delete_profile")]
    ])


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Sellers", callback_data="admin_sellers"),
         InlineKeyboardButton(text="💳 Recharge Requests", callback_data="admin_recharges")],
        [InlineKeyboardButton(text="📦 Orders", callback_data="admin_orders"),
         InlineKeyboardButton(text="📊 Reports", callback_data="admin_reports")],
        [InlineKeyboardButton(text="💰 Wallet Manage", callback_data="admin_wallet_list"),
         InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📥 CSV", callback_data="admin_csv")]
    ])


def get_seller(tg_id):
    return db.execute(
        "SELECT * FROM sellers WHERE telegram_id=?", (tg_id,)
    ).fetchone()


def admin_only(uid):
    return ADMIN_ID and uid == ADMIN_ID


async def send_admin(text, reply_markup=None):
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, text, reply_markup=reply_markup)


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    if admin_only(message.from_user.id):
        await message.answer("👑 <b>Golden Seller Admin Panel</b>", reply_markup=admin_menu())
        return

    seller = get_seller(message.from_user.id)
    if seller and seller["active"]:
        await message.answer(
            f"नमस्ते <b>{seller['name']}</b> 👋\n"
            f"💰 Wallet: ₹{seller['wallet'] or 0:,}",
            reply_markup=seller_menu()
        )
    else:
        await message.answer(
            "👋 <b>Golden Seller</b>\n\nपहले Seller Registration पूरा करें।",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Seller Registration", callback_data="register")]
            ])
        )


@dp.callback_query(F.data == "register")
async def register_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(Register.name)
    await c.message.answer("1/7️⃣ पूरा नाम लिखें:")


@dp.message(Register.name)
async def reg_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip(), username=m.from_user.username or "")
    await state.set_state(Register.phone)
    await m.answer("2/7️⃣ Mobile Number लिखें:")


@dp.message(Register.phone)
async def reg_phone(m: Message, state: FSMContext):
    await state.update_data(phone=m.text.strip())
    await state.set_state(Register.address)
    await m.answer("3/7️⃣ पूरा Address लिखें:")


@dp.message(Register.address)
async def reg_address(m: Message, state: FSMContext):
    await state.update_data(address=m.text.strip())
    await state.set_state(Register.bank)
    await m.answer("4/7️⃣ Bank Name लिखें:")


@dp.message(Register.bank)
async def reg_bank(m: Message, state: FSMContext):
    await state.update_data(bank_name=m.text.strip())
    await state.set_state(Register.account)
    await m.answer("5/7️⃣ Bank Account Number लिखें:")


@dp.message(Register.account)
async def reg_account(m: Message, state: FSMContext):
    await state.update_data(account_no=m.text.strip())
    await state.set_state(Register.ifsc)
    await m.answer("6/7️⃣ IFSC Code लिखें:")


@dp.message(Register.ifsc)
async def reg_ifsc(m: Message, state: FSMContext):
    await state.update_data(ifsc=m.text.strip())
    await state.set_state(Register.upi)
    await m.answer("7/7️⃣ UPI ID लिखें (नहीं है तो - लिखें):")


@dp.message(Register.upi)
async def reg_upi(m: Message, state: FSMContext):
    data = await state.update_data(upi=m.text.strip())
    db.execute("""
        INSERT INTO sellers
        (telegram_id,username,name,phone,address,bank_name,account_no,ifsc,upi,created_at,active,wallet)
        VALUES (?,?,?,?,?,?,?,?,?,?,1,0)
        ON CONFLICT(telegram_id) DO UPDATE SET
        username=excluded.username,name=excluded.name,phone=excluded.phone,
        address=excluded.address,bank_name=excluded.bank_name,
        account_no=excluded.account_no,ifsc=excluded.ifsc,upi=excluded.upi,active=1
    """, (
        m.from_user.id, data.get("username", ""), data["name"], data["phone"],
        data["address"], data["bank_name"], data["account_no"],
        data["ifsc"], data["upi"], now()
    ))
    db.commit()
    await state.clear()
    await m.answer("✅ Registration complete.", reply_markup=seller_menu())
    await send_admin(
        f"👤 <b>नया Seller</b>\n\n"
        f"Name: {data['name']}\nPhone: {data['phone']}\n"
        f"Telegram ID: <code>{m.from_user.id}</code>"
    )


@dp.callback_query(F.data == "wallet")
async def wallet(c: CallbackQuery):
    await c.answer()
    s = get_seller(c.from_user.id)
    if s:
        await c.message.answer(
            f"💰 <b>Your Wallet</b>\n\n"
            f"Available Balance: <b>₹{s['wallet'] or 0:,}</b>",
            reply_markup=seller_menu()
        )


@dp.callback_query(F.data == "recharge")
async def recharge_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if not get_seller(c.from_user.id):
        return
    await state.set_state(Recharge.amount)
    await c.message.answer(
        f"➕ <b>Wallet Recharge</b>\n\n"
        f"UPI: <code>{PAYMENT_UPI}</code>\n\n"
        "जितने रुपये का payment किया है वह amount लिखें:"
    )


@dp.message(Recharge.amount)
async def recharge_amount(m: Message, state: FSMContext):
    try:
        amount = int(m.text.replace(",", "").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await m.answer("सही amount लिखें, जैसे 500")
        return
    await state.update_data(amount=amount)
    await state.set_state(Recharge.screenshot)
    await m.answer(
        f"₹{amount:,} का payment करें और फिर <b>Payment Screenshot</b> भेजें।"
    )


@dp.message(Recharge.screenshot, F.photo)
async def recharge_screenshot(m: Message, state: FSMContext):
    data = await state.get_data()
    s = get_seller(m.from_user.id)
    photo_id = m.photo[-1].file_id
    cur = db.execute("""
        INSERT INTO recharge_requests
        (seller_id,amount,screenshot_file_id,status,created_at)
        VALUES(?,?,?,'PENDING',?)
    """, (s["id"], data["amount"], photo_id, now()))
    db.commit()
    rid = cur.lastrowid
    await state.clear()

    await m.answer(
        f"✅ Recharge Request #{rid} भेज दी गई है।\n"
        "Admin verification के बाद wallet में amount add होगा।",
        reply_markup=seller_menu()
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Approve", callback_data=f"ra:{rid}"),
         InlineKeyboardButton(text="❌ Reject", callback_data=f"rr:{rid}")]
    ])
    await bot.send_photo(
        ADMIN_ID, photo_id,
        caption=(
            f"💳 <b>Recharge Request #{rid}</b>\n\n"
            f"Seller: {s['name']}\nPhone: {s['phone']}\n"
            f"Telegram ID: <code>{s['telegram_id']}</code>\n"
            f"Amount: <b>₹{data['amount']:,}</b>"
        ),
        reply_markup=kb
    )


@dp.message(Recharge.screenshot)
async def recharge_not_photo(m: Message):
    await m.answer("कृपया payment का screenshot/photo भेजें।")


@dp.callback_query(F.data.startswith("ra:"))
async def recharge_approve(c: CallbackQuery):
    await c.answer()
    if not admin_only(c.from_user.id):
        return
    rid = int(c.data.split(":")[1])
    req = db.execute(
        "SELECT * FROM recharge_requests WHERE id=?", (rid,)
    ).fetchone()
    if not req or req["status"] != "PENDING":
        await c.message.answer("यह request पहले ही process हो चुकी है।")
        return

    db.execute(
        "UPDATE sellers SET wallet=COALESCE(wallet,0)+? WHERE id=?",
        (req["amount"], req["seller_id"])
    )
    db.execute(
        "INSERT INTO wallet_transactions(seller_id,amount,type,note,created_at) VALUES(?,?,?,?,?)",
        (req["seller_id"], req["amount"], "CREDIT", f"Recharge #{rid}", now())
    )
    db.execute(
        "UPDATE recharge_requests SET status='APPROVED',reviewed_at=?,reviewed_by=? WHERE id=?",
        (now(), ADMIN_ID, rid)
    )
    db.commit()

    s = db.execute("SELECT * FROM sellers WHERE id=?", (req["seller_id"],)).fetchone()
    await c.message.edit_caption(
        caption=f"✅ Recharge #{rid} APPROVED\nSeller: {s['name']}\nAmount: ₹{req['amount']:,}"
    )
    await bot.send_message(
        s["telegram_id"],
        f"✅ <b>Recharge Approved</b>\n₹{req['amount']:,} wallet में add हो गए।\n"
        f"💰 New Balance: ₹{s['wallet']:,}",
        reply_markup=seller_menu()
    )


@dp.callback_query(F.data.startswith("rr:"))
async def recharge_reject(c: CallbackQuery):
    await c.answer()
    if not admin_only(c.from_user.id):
        return
    rid = int(c.data.split(":")[1])
    req = db.execute(
        "SELECT * FROM recharge_requests WHERE id=?", (rid,)
    ).fetchone()
    if not req or req["status"] != "PENDING":
        await c.message.answer("यह request पहले ही process हो चुकी है।")
        return
    db.execute(
        "UPDATE recharge_requests SET status='REJECTED',reviewed_at=?,reviewed_by=? WHERE id=?",
        (now(), ADMIN_ID, rid)
    )
    db.commit()
    s = db.execute("SELECT * FROM sellers WHERE id=?", (req["seller_id"],)).fetchone()
    await c.message.edit_caption(
        caption=f"❌ Recharge #{rid} REJECTED\nSeller: {s['name']}\nAmount: ₹{req['amount']:,}"
    )
    await bot.send_message(
        s["telegram_id"],
        f"❌ Recharge Request #{rid} reject हो गई।",
        reply_markup=seller_menu()
    )


@dp.callback_query(F.data == "new_order")
async def new_order(c: CallbackQuery, state: FSMContext):
    await c.answer()
    s = get_seller(c.from_user.id)
    if not s or not s["active"]:
        return
    if (s["wallet"] or 0) < ORDER_CONFIRM_FEE:
        await c.message.answer(
            f"❌ Wallet balance कम है।\n\n"
            f"Order confirmation fee: ₹{ORDER_CONFIRM_FEE}\n"
            f"Current balance: ₹{s['wallet'] or 0}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Add Money", callback_data="recharge")],
                [InlineKeyboardButton(text="🔙 Menu", callback_data="back")]
            ])
        )
        return
    await state.set_state(NewOrder.details)
    await c.message.answer("📦 Order की details लिखें:")


@dp.message(NewOrder.details)
async def order_details(m: Message, state: FSMContext):
    await state.update_data(details=m.text.strip())
    await state.set_state(NewOrder.amount)
    await m.answer("💰 Order amount ₹ में लिखें:")


@dp.message(NewOrder.amount)
async def order_amount(m: Message, state: FSMContext):
    try:
        amount = float(m.text.replace(",", "").strip())
        if amount < 0:
            raise ValueError
    except ValueError:
        await m.answer("सही amount लिखें, जैसे 12500")
        return

    s = get_seller(m.from_user.id)
    if not s or (s["wallet"] or 0) < ORDER_CONFIRM_FEE:
        await state.clear()
        await m.answer("❌ Wallet balance पर्याप्त नहीं है।")
        return

    data = await state.get_data()
    cur = db.execute(
        "INSERT INTO orders(seller_id,details,amount,status,created_at) VALUES(?,?,?,?,?)",
        (s["id"], data["details"], amount, "CONFIRMED", now())
    )
    order_id = cur.lastrowid

    db.execute(
        "UPDATE sellers SET wallet=wallet-? WHERE id=? AND wallet>=?",
        (ORDER_CONFIRM_FEE, s["id"], ORDER_CONFIRM_FEE)
    )
    db.execute(
        "INSERT INTO wallet_transactions(seller_id,amount,type,note,created_at) VALUES(?,?,?,?,?)",
        (s["id"], -ORDER_CONFIRM_FEE, "DEBIT", f"Order #{order_id} confirmation fee", now())
    )
    db.execute(
        "UPDATE orders SET confirmed_at=? WHERE id=?", (now(), order_id)
    )
    db.commit()
    await state.clear()

    new_balance = db.execute(
        "SELECT wallet FROM sellers WHERE id=?", (s["id"],)
    ).fetchone()["wallet"]

    await m.answer(
        f"✅ <b>Order #{order_id} CONFIRMED</b>\n"
        f"Order Amount: ₹{amount:,.2f}\n"
        f"Confirmation Fee: ₹{ORDER_CONFIRM_FEE}\n"
        f"💰 Wallet Balance: ₹{new_balance:,}",
        reply_markup=seller_menu()
    )
    await send_admin(
        f"📦 <b>NEW ORDER #{order_id}</b>\n"
        f"Seller: {s['name']}\nAmount: ₹{amount:,.2f}\n"
        f"Details: {data['details']}"
    )


@dp.callback_query(F.data == "my_orders")
async def my_orders(c: CallbackQuery):
    await c.answer()
    s = get_seller(c.from_user.id)
    if not s:
        return
    rows = db.execute(
        "SELECT * FROM orders WHERE seller_id=? ORDER BY id DESC LIMIT 30",
        (s["id"],)
    ).fetchall()
    if not rows:
        await c.message.answer("📋 अभी कोई Order नहीं है।", reply_markup=seller_menu())
        return
    text = ["📋 <b>My Orders</b>\n"]
    for r in rows:
        text.append(
            f"#{r['id']} | ₹{r['amount']:,.2f} | {r['status']} | {r['created_at'][:10]}"
        )
    await c.message.answer("\n".join(text), reply_markup=seller_menu())


@dp.callback_query(F.data == "profile")
async def profile(c: CallbackQuery):
    await c.answer()
    s = get_seller(c.from_user.id)
    if not s:
        return
    await c.message.answer(
        f"👤 <b>Seller Profile</b>\n\n"
        f"Name: {s['name']}\n📱 {s['phone']}\n🏠 {s['address']}\n"
        f"🏦 Bank: {s['bank_name']}\n"
        f"💳 Account: <code>{s['account_no']}</code>\n"
        f"IFSC: <code>{s['ifsc']}</code>\n"
        f"UPI: <code>{s['upi']}</code>\n"
        f"💰 Wallet: ₹{s['wallet'] or 0:,}",
        reply_markup=seller_menu()
    )


@dp.callback_query(F.data == "edit_profile")
async def edit_profile(c: CallbackQuery):
    await c.answer()
    await c.message.answer(
        "✏️ <b>Edit Profile</b>\n\n"
        "अभी profile को जल्दी update करने के लिए नीचे दिए command इस्तेमाल करें:\n"
        "/editname\n/editphone\n/editaddress\n/editbank\n/editaccount\n/editifsc\n/editupi"
    )


async def edit_start(m: Message, state: FSMContext, field, title):
    s = get_seller(m.from_user.id)
    if not s:
        return
    await state.update_data(edit_field=field)
    await state.set_state(EditProfile.value)
    await m.answer(f"✏️ नया {title} लिखें:")


@dp.message(Command("editname"))
async def editname(m: Message, state: FSMContext):
    await edit_start(m, state, "name", "Name")


@dp.message(Command("editphone"))
async def editphone(m: Message, state: FSMContext):
    await edit_start(m, state, "phone", "Mobile")


@dp.message(Command("editaddress"))
async def editaddress(m: Message, state: FSMContext):
    await edit_start(m, state, "address", "Address")


@dp.message(Command("editbank"))
async def editbank(m: Message, state: FSMContext):
    await edit_start(m, state, "bank_name", "Bank Name")


@dp.message(Command("editaccount"))
async def editaccount(m: Message, state: FSMContext):
    await edit_start(m, state, "account_no", "Account Number")


@dp.message(Command("editifsc"))
async def editifsc(m: Message, state: FSMContext):
    await edit_start(m, state, "ifsc", "IFSC")


@dp.message(Command("editupi"))
async def editupi(m: Message, state: FSMContext):
    await edit_start(m, state, "upi", "UPI ID")


@dp.message(EditProfile.value)
async def edit_value(m: Message, state: FSMContext):
    data = await state.get_data()
    field = data["edit_field"]
    if field not in {"name", "phone", "address", "bank_name", "account_no", "ifsc", "upi"}:
        await state.clear()
        return
    db.execute(f"UPDATE sellers SET {field}=? WHERE telegram_id=?", (m.text.strip(), m.from_user.id))
    db.commit()
    await state.clear()
    await m.answer("✅ Profile updated.", reply_markup=seller_menu())


