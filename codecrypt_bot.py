#!/usr/bin/env python3
"""
CODECRYPT Shop Bot – Full Affiliate System + Stars Payments
Author: Jarvis for Mr. Stark
"""

import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery, ContentType
from aiogram import F
from dotenv import load_dotenv

# ---------- CONFIG ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  balance INTEGER DEFAULT 0,
                  referred_by INTEGER,
                  registered_at TEXT)''')
    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  price INTEGER,
                  file_link TEXT,
                  active INTEGER DEFAULT 1)''')
    # Sales table
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  product_id INTEGER,
                  amount INTEGER,
                  affiliate_id INTEGER,
                  created_at TEXT)''')
    # Affiliate withdrawals
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount INTEGER,
                  status TEXT,
                  requested_at TEXT,
                  processed_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ---------- HELPER FUNCTIONS ----------
def get_user(user_id):
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def create_user(user_id, username, referred_by=None):
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("INSERT INTO users (user_id, username, referred_by, registered_at) VALUES (?, ?, ?, ?)",
              (user_id, username, referred_by, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_products():
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("SELECT id, name, price, file_link FROM products WHERE active = 1")
    rows = c.fetchall()
    conn.close()
    return rows

def get_product(product_id):
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("SELECT id, name, price, file_link FROM products WHERE id = ? AND active = 1", (product_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_sale(user_id, product_id, amount, affiliate_id=None):
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("INSERT INTO sales (user_id, product_id, amount, affiliate_id, created_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, product_id, amount, affiliate_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def add_balance(user_id, amount):
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ---------- COMMANDS ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referred_by = int(args[1].split("_")[1])
        except:
            pass

    user = get_user(message.from_user.id)
    if not user:
        create_user(message.from_user.id, message.from_user.username, referred_by)
        await message.answer(
            f"🎧 Welcome to **CODECRYPT Shop**!\n\n"
            f"Your personal bot to buy Python scripts.\n"
            f"Use /buy to see products.\n\n"
            f"🌟 Invite friends with your referral link:\n"
            f"`https://t.me/{bot.username}?start=ref_{message.from_user.id}`\n"
            f"You earn **30% commission** on their purchases!"
        )
    else:
        await message.answer(
            f"Welcome back! Use /buy to shop.\n"
            f"Your balance: {get_balance(message.from_user.id)} Stars"
        )

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    products = get_products()
    if not products:
        await message.answer("No products available at the moment.")
        return
    text = "📦 **Products:**\n\n"
    for p in products:
        text += f"`{p[0]}`. {p[1]} — {p[2]} Stars\n"
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
    product = get_product(product_id)
    if not product:
        await message.answer("Product not found.")
        return
    pid, name, price, file_link = product

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
    product = get_product(product_id)
    if not product:
        await message.answer("Product not found, but payment recorded. Contact admin.")
        return
    pid, name, price, file_link = product

    # Determine affiliate (if user was referred)
    user = get_user(message.from_user.id)
    affiliate_id = user[3] if user else None
    if affiliate_id:
        # Add commission to affiliate
        commission = int(price * 0.3)  # 30%
        add_balance(affiliate_id, commission)
        # Notify affiliate
        try:
            await bot.send_message(affiliate_id,
                                   f"🎉 You earned {commission} Stars commission!\n"
                                   f"User @{message.from_user.username} bought {name} using your link.")
        except:
            pass
    # Record sale
    add_sale(message.from_user.id, product_id, price, affiliate_id)

    # Send product link to buyer
    await message.answer(
        f"✅ **Payment received!**\n\n"
        f"You purchased: **{name}**\n"
        f"Download: {file_link}\n\n"
        f"Thank you for supporting CODECRYPT! 🙌"
    )

    # Notify admin
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
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Please /start first.")
        return
    link = f"https://t.me/CodeCryptAssistantBot_bot?start=ref_{message.from_user.id}"
    balance = get_balance(message.from_user.id)
    await message.answer(
        f"🌟 **Your Affiliate Link**\n"
        f"`{link}`\n\n"
        f"💰 **Current Balance:** {balance} Stars\n\n"
        f"Share your link — when someone buys, you get **30% commission**!\n"
        f"Use /withdraw to cash out your Stars."
    )

@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    bal = get_balance(message.from_user.id)
    await message.answer(f"Your balance: {bal} Stars")

@dp.message(Command("withdraw"))
async def cmd_withdraw(message: types.Message):
    bal = get_balance(message.from_user.id)
    if bal < 10:
        await message.answer("Minimum withdrawal is 10 Stars. Keep earning!")
        return
    # Record withdrawal request
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("INSERT INTO withdrawals (user_id, amount, status, requested_at) VALUES (?, ?, ?, ?)",
              (message.from_user.id, bal, "pending", datetime.now().isoformat()))
    conn.commit()
    conn.close()
    await message.answer(f"Withdrawal of {bal} Stars requested. Admin will process soon.")

# ---------- ADMIN COMMANDS ----------
@dp.message(Command("add_product"))
async def cmd_add_product(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    # Format: /add_product name price file_link
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
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("INSERT INTO products (name, price, file_link) VALUES (?, ?, ?)", (name, price, file_link))
    conn.commit()
    conn.close()
    await message.answer(f"Product '{name}' added with price {price} Stars.")

@dp.message(Command("list_products"))
async def cmd_list_products(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    products = get_products()
    if not products:
        await message.answer("No products.")
        return
    text = "📋 **Products:**\n"
    for p in products:
        text += f"`{p[0]}`. {p[1]} — {p[2]} Stars\n"
    await message.answer(text)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('codecrypt.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(amount) FROM sales")
    total_sales = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM sales WHERE affiliate_id IS NOT NULL")
    affiliate_sales = c.fetchone()[0] or 0
    conn.close()
    await message.answer(
        f"📊 **Stats**\n"
        f"Total users: {users}\n"
        f"Total sales: {total_sales} Stars\n"
        f"Affiliate sales: {affiliate_sales} Stars"
    )

# ---------- RUN ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
