#!/usr/bin/env python3
"""
CODECRYPT Shop Bot – Supabase (PostgreSQL) Version
Permanent database – no more data loss.
"""
import aiohttp
from aiohttp import web
import asyncio
import logging
import os
import asyncpg
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram import F
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- Database Connection ----------
DATABASE_URL = os.getenv("DATABASE_URL")

async def init_db():
    """Create tables if they don't exist."""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            referred_by BIGINT,
            registered_at TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT,
            price INTEGER,
            file_link TEXT,
            active BOOLEAN DEFAULT TRUE
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            product_id INTEGER,
            amount INTEGER,
            affiliate_id BIGINT,
            created_at TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount INTEGER,
            status TEXT,
            requested_at TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)
    await conn.close()

# ---------- Database Helpers ----------
async def get_user(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return row

async def create_user(user_id, username, referred_by=None):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO users (user_id, username, referred_by, registered_at) VALUES ($1, $2, $3, $4)",
        user_id, username, referred_by, datetime.now()
    )
    await conn.close()

async def get_products():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT id, name, price, file_link FROM products WHERE active = TRUE")
    await conn.close()
    return rows

async def get_product(product_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT id, name, price, file_link FROM products WHERE id = $1 AND active = TRUE", product_id)
    await conn.close()
    return row

async def add_sale(user_id, product_id, amount, affiliate_id=None):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO sales (user_id, product_id, amount, affiliate_id, created_at) VALUES ($1, $2, $3, $4, $5)",
        user_id, product_id, amount, affiliate_id, datetime.now()
    )
    await conn.close()

async def add_balance(user_id, amount):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, user_id)
    await conn.close()

async def get_balance(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return row["balance"] if row else 0

# ---------- Bot Commands (unchanged logic, just using asyncpg) ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referred_by = int(args[1].split("_")[1])
        except:
            pass

    user = await get_user(message.from_user.id)
    if not user:
        try:
            await create_user(message.from_user.id, message.from_user.username, referred_by)
        except asyncpg.exceptions.UniqueViolationError:
            # User was inserted by another request; just continue
            pass
        await message.answer(
            f"🎧 Welcome to **CODECRYPT Shop**!\n\n"
            f"**Commands:**\n"
            f"/start – Register & get your referral link\n"
            f"/buy – See available products\n"
            f"/pay <id> – Buy a product (e.g., /pay 1)\n"
            f"/affiliate – Your referral link and balance\n"
            f"/balance – Check your Stars balance\n"
            f"/withdraw – Request payout\n\n"
            f"🌟 **Your referral link:**\n"
            f"`https://t.me/CodeCryptAssistantBot_bot?start=ref_{message.from_user.id}`\n"
            f"Share it – you earn **30% commission** on every sale!\n\n"
            f"Type `/help` anytime to see this again."
        )
    else:
        await message.answer(
            f"Welcome back! Use /buy to shop.\n"
            f"Your balance: {await get_balance(message.from_user.id)} Stars"
        )

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    products = await get_products()
    if not products:
        await message.answer("No products available at the moment.")
        return
    text = "📦 **Products:**\n\n"
    for p in products:
        text += f"`{p['id']}`. {p['name']} — {p['price']} Stars\n"
    text += "\nType `/pay <product_id>` to buy."
    await message.answer(text)

@dp.message(Command("pay"))
async def cmd_pay(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /pay <product_id>\nExample: /pay 1")
        return
    try:
        product_id = int(args[1])
    except:
        await message.answer("Invalid product ID.")
        return
    product = await get_product(product_id)
    if not product:
        await message.answer("Product not found.")
        return
    pid, name, price, file_link = product['id'], product['name'], product['price'], product['file_link']

    await message.answer_invoice(
        title=name,
        description="You will receive the download link immediately after payment.",
        payload=f"product_{pid}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Price", amount=price)],
        start_parameter=f"buy_{pid}"
    )

@dp.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    product_id = int(payload.split("_")[1])
    product = await get_product(product_id)
    if not product:
        await message.answer("Product not found, but payment recorded. Contact admin.")
        return
    pid, name, price, file_link = product['id'], product['name'], product['price'], product['file_link']

    user = await get_user(message.from_user.id)
    affiliate_id = user['referred_by'] if user else None
    if affiliate_id:
        commission = int(price * 0.3)
        await add_balance(affiliate_id, commission)
        try:
            await bot.send_message(affiliate_id,
                                   f"🎉 You earned {commission} Stars commission!\n"
                                   f"User @{message.from_user.username} bought {name} using your link.")
        except:
            pass

    await add_sale(message.from_user.id, product_id, price, affiliate_id)

    await message.answer(
        f"✅ **Payment received!**\n\n"
        f"You purchased: **{name}**\n"
        f"Download: {file_link}\n\n"
        f"Thank you for supporting CODECRYPT! 🙌"
    )

    await bot.send_message(
        ADMIN_ID,
        f"💰 **New Sale!**\n"
        f"User: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"Product: {name}\n"
        f"Amount: {price} Stars\n"
        f"Affiliate: {'@' + str(affiliate_id) if affiliate_id else 'None'}"
    )

@dp.message(Command("affiliate"))
async def cmd_affiliate(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Please /start first.")
        return
    link = f"https://t.me/CodeCryptAssistantBot_bot?start=ref_{message.from_user.id}"
    balance = await get_balance(message.from_user.id)
    await message.answer(
        f"🌟 **Your Affiliate Link**\n"
        f"`{link}`\n\n"
        f"💰 **Current Balance:** {balance} Stars\n\n"
        f"Share your link — when someone buys, you get **30% commission**!\n"
        f"Use /withdraw to cash out your Stars."
    )

@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    bal = await get_balance(message.from_user.id)
    await message.answer(f"Your balance: {bal} Stars")

@dp.message(Command("withdraw"))
async def cmd_withdraw(message: types.Message):
    bal = await get_balance(message.from_user.id)
    if bal < 10:
        await message.answer("Minimum withdrawal is 10 Stars. Keep earning!")
        return
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO withdrawals (user_id, amount, status, requested_at) VALUES ($1, $2, $3, $4)",
        message.from_user.id, bal, "pending", datetime.now()
    )
    await conn.close()
    await message.answer(f"Withdrawal of {bal} Stars requested. Admin will process soon.")

# ---------- Admin Commands ----------
@dp.message(Command("add_product"))
async def cmd_add_product(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        await message.answer("Usage: /add_product <name> <price> <file_link>")
        return
    name = args[1]
    try:
        price = int(args[2])
    except:
        await message.answer("Price must be a number.")
        return
    file_link = args[3]
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO products (name, price, file_link) VALUES ($1, $2, $3)", name, price, file_link)
    await conn.close()
    await message.answer(f"Product '{name}' added with price {price} Stars.")

@dp.message(Command("list_products"))
async def cmd_list_products(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    products = await get_products()
    if not products:
        await message.answer("No products.")
        return
    text = "📋 **Products:**\n"
    for p in products:
        text += f"`{p['id']}`. {p['name']} — {p['price']} Stars\n"
    await message.answer(text)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = await asyncpg.connect(DATABASE_URL)
    users = await conn.fetchval("SELECT COUNT(*) FROM users")
    total_sales = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM sales")
    affiliate_sales = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM sales WHERE affiliate_id IS NOT NULL")
    await conn.close()
    await message.answer(
        f"📊 **Stats**\n"
        f"Total users: {users}\n"
        f"Total sales: {total_sales} Stars\n"
        f"Affiliate sales: {affiliate_sales} Stars"
    )
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🤖 **CodeCrypt Bot – How to Use**\n\n"
        "📌 **Commands:**\n"
        "`/start` – Register and get your referral link\n"
        "`/buy` – See available products\n"
        "`/pay <id>` – Buy a product (e.g., `/pay 1`)\n"
        "`/affiliate` – View your referral link and balance\n"
        "`/balance` – Check your Stars balance\n"
        "`/withdraw` – Request payout of your balance\n\n"
        "🛒 **How to Buy:**\n"
        "1. Send `/buy` to see products\n"
        "2. Pick a product ID (e.g., `1`)\n"
        "3. Send `/pay 1` to purchase\n"
        "4. Pay with Telegram Stars\n"
        "5. Download link will be sent immediately\n\n"
        "💸 **Affiliate Program:**\n"
        "Share your referral link from `/affiliate`. When someone buys using your link, you earn 30% commission in Stars.\n\n"
        "Need more help? DM @CodeCryptOfficial"
    )
# ---------- Run ----------
async def start_web_server():
    app = web.Application()
    async def health(request):
        return web.Response(text="OK")
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server running on port {port}")
    # Keep the server running forever
    await asyncio.Event().wait()
@dp.message()
async def handle_text(message: types.Message):
    text = message.text.lower().strip()
    
    if text in ["start", "help", "buy", "affiliate", "balance"]:
        if text == "start":
            await cmd_start(message)
        elif text == "help":
            await cmd_help(message)
        elif text == "buy":
            await cmd_buy(message)
        elif text == "affiliate":
            await cmd_affiliate(message)
        elif text == "balance":
            await cmd_balance(message)
    elif text.startswith("pay") and len(text.split()) == 2:
        # Example: "pay 1"
        parts = text.split()
        product_id = parts[1]
        # Create a fake command message to reuse cmd_pay logic
        class FakeMessage:
            def __init__(self, original, text):
                self.from_user = original.from_user
                self.chat = original.chat
                self.text = f"/pay {product_id}"
        fake_msg = FakeMessage(message, f"/pay {product_id}")
        await cmd_pay(fake_msg)
    else:
        await message.answer(
            "❓ I didn't understand that. Type `/help` to see available commands."
        )
async def main():
    # Start both the bot polling and the web server at the same time
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
