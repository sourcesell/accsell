#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║         SOURCE CODE STORE BOT — v3.0 (Wallet System)        ║
║   Telethon • MongoDB • Wallet • UPI QR • OxaPay Crypto       ║
╚══════════════════════════════════════════════════════════════╝

Flow:
  1. User deposits Rs via UPI or Crypto → wallet me add hota hai
  2. Browse karo → product click → features + price dikhe
  3. "Buy Now" → wallet se auto-cut → file deliver

pip install telethon motor pymongo qrcode[pil] aiohttp pillow python-dotenv
"""

import asyncio
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import qrcode
from PIL import Image, ImageDraw, ImageFont
from motor.motor_asyncio import AsyncIOMotorClient
from telethon import TelegramClient, events, Button

# ══════════════════════════════════════════════════════════════════
#  CONFIG  — replace or use env vars
# ══════════════════════════════════════════════════════════════════

BOT_TOKEN         = "8643034907:AAELPGXD_I5wDEs8Cyu5qtT_AEZwBnHhDGA"
API_ID            = 27896193
API_HASH          = "38a5463cb8bf980d4519fba0ced298c2"
MONGO_URI         = "mongodb+srv://kumartijil71_db_user:r4CHHowUcuPe8Nvv@bokachoda.scsnfov.mongodb.net/?retryWrites=true&w=majority"
SUPER_ADMIN_ID    = 8568245247
ADMIN_LOG_CHANNEL = -1003831478369
UPI_ID            = "tijil-kumar@fam"
UPI_NAME          = "Source Store"
OXAPAY_API_KEY    = "R7GWJN-NPCMVX-H3QYHQ-FL2DJA"
INR_PER_USDT      = 91
UPLOAD_DIR        = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  MONGODB COLLECTIONS
# ══════════════════════════════════════════════════════════════════

_mongo       = AsyncIOMotorClient(MONGO_URI)
db           = _mongo["source_store"]
col_products = db["products"]    # source codes
col_orders   = db["orders"]      # purchase + deposit history
col_admins   = db["admins"]      # extra admins
col_sessions = db["sessions"]    # conversation state
col_wallets  = db["wallets"]     # user balances  {uid, balance_inr}

# ══════════════════════════════════════════════════════════════════
#  TELETHON CLIENT
# ══════════════════════════════════════════════════════════════════

bot = TelegramClient("source_store_bot", API_ID, API_HASH)

# ══════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════

def gen_id(n: int = 8) -> str:
    return str(uuid.uuid4()).replace("-", "")[:n].upper()

def inr_to_usdt(inr: float) -> float:
    return round(inr / INR_PER_USDT, 4)

async def is_admin(uid: int) -> bool:
    if uid == SUPER_ADMIN_ID:
        return True
    return bool(await col_admins.find_one({"uid": uid}))

# ── Wallet helpers ─────────────────────────────────────────────────

async def get_balance(uid: int) -> float:
    doc = await col_wallets.find_one({"uid": uid})
    return round(doc["balance_inr"], 2) if doc else 0.0

async def credit_wallet(uid: int, amount: float):
    await col_wallets.update_one(
        {"uid": uid},
        {"$inc": {"balance_inr": amount}},
        upsert=True,
    )

async def debit_wallet(uid: int, amount: float) -> bool:
    """Returns True if debit successful, False if insufficient balance."""
    doc = await col_wallets.find_one({"uid": uid})
    bal = doc["balance_inr"] if doc else 0.0
    if bal < amount:
        return False
    await col_wallets.update_one({"uid": uid}, {"$inc": {"balance_inr": -amount}})
    return True

# ── Session helpers ────────────────────────────────────────────────

async def get_session(uid: int) -> dict:
    return (await col_sessions.find_one({"uid": uid})) or {}

async def set_session(uid: int, data: dict):
    await col_sessions.replace_one({"uid": uid}, {"uid": uid, **data}, upsert=True)

async def clear_session(uid: int):
    await col_sessions.delete_one({"uid": uid})

def features_text(features: list) -> str:
    if not features:
        return "  _No features listed._"
    return "\n".join(f"  ✅ {f}" for f in features)

# ══════════════════════════════════════════════════════════════════
#  UPI QR CODE GENERATOR
# ══════════════════════════════════════════════════════════════════

def make_upi_qr(amount: float) -> io.BytesIO:
    uri = (
        f"upi://pay?pa={UPI_ID}"
        f"&pn={UPI_NAME.replace(' ', '%20')}"
        f"&am={amount:.2f}&cu=INR&tn=SourceStoreDeposit"
    )
    qr = qrcode.QRCode(version=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0d1117", back_color="white").convert("RGB")
    w, h = img.size

    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        fm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except Exception:
        fb = fm = fs = ImageFont.load_default()

    canvas = Image.new("RGB", (w, h + 105), "#0d1117")
    canvas.paste(img, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([(0, 0), (w, 5)], fill="#5865f2")
    d.text((w // 2, h + 16), f"Rs. {amount:.2f}",        fill="#ffffff", font=fb, anchor="mm")
    d.text((w // 2, h + 44), f"UPI: {UPI_ID}",           fill="#aaaacc", font=fm, anchor="mm")
    d.text((w // 2, h + 68), "Scan with any UPI app",    fill="#666688", font=fs, anchor="mm")
    d.text((w // 2, h + 88), "GPay  PhonePe  Paytm  BHIM", fill="#444466", font=fs, anchor="mm")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ══════════════════════════════════════════════════════════════════
#  OXAPAY HELPERS
# ══════════════════════════════════════════════════════════════════

async def create_oxapay_invoice(amount_usdt: float, order_id: str, desc: str) -> Optional[dict]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.oxapay.com/merchants/request",
                json={
                    "merchant": OXAPAY_API_KEY, "amount": amount_usdt,
                    "currency": "USDT", "lifeTime": 30,
                    "feePaidByPayer": 0, "description": desc, "orderId": order_id,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                res = await r.json()
                if res.get("result") == 100:
                    return res
    except Exception as e:
        log.error(f"OxaPay create: {e}")
    return None

async def check_oxapay_status(track_id: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.oxapay.com/merchants/inquiry",
                json={"merchant": OXAPAY_API_KEY, "trackId": track_id},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return (await r.json()).get("status")
    except Exception as e:
        log.error(f"OxaPay inquiry: {e}")
    return None

# ══════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════

def main_menu_kb(admin=False):
    rows = [
        [Button.inline("🛒 Source Codes", b"browse"),
         Button.inline("👛 My Wallet",    b"wallet")],
        [Button.inline("📦 My Orders",   b"myorders"),
         Button.inline("ℹ️ Help",        b"help")],
    ]
    if admin:
        rows.append([Button.inline("⚙️ Admin Panel", b"adminpanel")])
    return rows

def admin_panel_kb():
    return [
        [Button.inline("➕ Add Product",    b"adm_add"),
         Button.inline("📋 Products",       b"adm_list")],
        [Button.inline("✏️ Edit Product",   b"adm_edit_select"),
         Button.inline("🗑 Delete Product", b"adm_del_select")],
        [Button.inline("👤 Add Admin",      b"adm_addadmin"),
         Button.inline("👤 Del Admin",      b"adm_deladmin")],
        [Button.inline("📢 Broadcast",      b"adm_broadcast"),
         Button.inline("📊 Stats",          b"adm_stats")],
        [Button.inline("📋 All Orders",     b"adm_orders"),
         Button.inline("⏳ Pending UPI",    b"adm_pendingupi")],
        [Button.inline("🔙 Main Menu",      b"start")],
    ]

# ══════════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════════

@bot.on(events.NewMessage(pattern="/start"))
async def cmd_start(event):
    uid    = event.sender_id
    adm    = await is_admin(uid)
    await clear_session(uid)
    sender = await event.get_sender()
    name   = getattr(sender, "first_name", "User")
    bal    = await get_balance(uid)
    await event.respond(
        f"👋 **Welcome, {name}!**\n\n"
        "🏪 **Source Code Store**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Buy premium bots & scripts instantly.\n\n"
        f"👛 Your Wallet: **Rs {bal:.2f}**\n\n"
        "_Deposit funds → Browse → Buy Now!_",
        buttons=main_menu_kb(adm),
    )

# ══════════════════════════════════════════════════════════════════
#  CALLBACK ROUTER
# ══════════════════════════════════════════════════════════════════

@bot.on(events.CallbackQuery())
async def callback_router(event):
    data = event.data.decode()
    uid  = event.sender_id

    # ── Main / Nav ──────────────────────────────────────────────────
    if data == "start":
        adm = await is_admin(uid)
        await clear_session(uid)
        bal = await get_balance(uid)
        await event.edit(
            f"🏪 **Source Code Store** — Main Menu\n👛 Wallet: **Rs {bal:.2f}**",
            buttons=main_menu_kb(adm),
        )

    elif data == "browse":
        await show_browse(event)

    elif data == "wallet":
        await show_wallet(event)

    elif data == "myorders":
        await show_my_orders(event)

    elif data == "help":
        await event.edit(
            "ℹ️ **How It Works**\n\n"
            "**Step 1 — Deposit**\n"
            "  👛 Tap **My Wallet** → Deposit → choose UPI or Crypto.\n"
            "  Funds get added to your wallet balance.\n\n"
            "**Step 2 — Browse**\n"
            "  🛒 Tap **Source Codes** → tap any product.\n"
            "  See full features, description & price.\n\n"
            "**Step 3 — Buy**\n"
            "  🛍 Tap **Buy Now** → price auto-cuts from wallet.\n"
            "  File delivered instantly! No manual steps.\n\n"
            "📧 Support: @YourUsername",
            buttons=[[Button.inline("🔙 Back", b"start")]],
        )

    # ── Wallet deposit options ──────────────────────────────────────
    elif data == "dep_upi":
        await set_session(uid, {"state": "dep_upi_amount"})
        await event.edit(
            "💳 **Deposit via UPI**\n\nSend the **amount in Rs** to deposit:\n_e.g. 500_",
            buttons=[[Button.inline("❌ Cancel", b"wallet")]],
        )

    elif data == "dep_crypto":
        await set_session(uid, {"state": "dep_crypto_amount"})
        await event.edit(
            f"🔷 **Deposit via Crypto (USDT)**\n\n"
            f"Send the **amount in USDT** you want to deposit:\n_e.g. 5_\n\n"
            f"💱 Rate: 1 USDT = Rs {INR_PER_USDT}",
            buttons=[[Button.inline("❌ Cancel", b"wallet")]],
        )

    elif data.startswith("dep_check_"):
        order_id = data[10:]
        await check_dep_crypto(event, order_id)

    # ── UPI deposit approve/reject (from admin log channel) ─────────
    elif data.startswith("dep_approve_"):
        order_id = data[12:]
        await admin_dep_approve(event, order_id)

    elif data.startswith("dep_reject_"):
        order_id = data[11:]
        await admin_dep_reject(event, order_id)

    # ── Product detail ──────────────────────────────────────────────
    elif data.startswith("product_"):
        pid = data[8:]
        await show_product(event, pid)

    # ── Buy Now (wallet debit) ──────────────────────────────────────
    elif data.startswith("buynow_"):
        pid = data[7:]
        await buy_now(event, pid)

    # ── Admin UPI approve/reject (purchase) ────────────────────────
    elif data.startswith("upi_approve_"):
        await event.answer("UPI deposits use dep_approve_ prefix.", alert=True)

    elif data.startswith("upi_reject_"):
        await event.answer("UPI deposits use dep_reject_ prefix.", alert=True)

    # ── Admin panel ─────────────────────────────────────────────────
    elif data == "adminpanel":
        if not await is_admin(uid):
            return await event.answer("Not an admin!", alert=True)
        await event.edit("⚙️ **Admin Panel**", buttons=admin_panel_kb())

    elif data == "adm_add":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await set_session(uid, {"state": "adm_add_title"})
        await event.edit(
            "➕ **Add New Product**\n\n**Step 1/5** — Send the **Title**:",
            buttons=[[Button.inline("❌ Cancel", b"adminpanel")]],
        )

    elif data == "adm_list":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await admin_list_products(event)

    elif data == "adm_edit_select":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await admin_select_product(event, "edit")

    elif data == "adm_del_select":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await admin_select_product(event, "del")

    elif data.startswith("adm_edit_"):
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        pid = data[9:]
        p = await col_products.find_one({"pid": pid})
        if not p: return await event.answer("Not found!", alert=True)
        await set_session(uid, {"edit_pid": pid})
        await event.edit(
            f"✏️ **Edit: {p['title']}**\n\nChoose field:",
            buttons=[
                [Button.inline("📝 Title",       f"ef_title_{pid}".encode()),
                 Button.inline("💰 Price (Rs)",  f"ef_price_{pid}".encode())],
                [Button.inline("📄 Description", f"ef_desc_{pid}".encode()),
                 Button.inline("✨ Features",    f"ef_features_{pid}".encode())],
                [Button.inline("📁 File",        f"ef_file_{pid}".encode())],
                [Button.inline("🔙 Back",        b"adm_list")],
            ],
        )

    elif data.startswith("adm_del_confirm_"):
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        pid = data[16:]
        p   = await col_products.find_one({"pid": pid})
        if p:
            await event.edit(
                f"🗑 **Delete: {p['title']}?**\nThis cannot be undone.",
                buttons=[
                    [Button.inline("✅ Yes, Delete", f"adm_del_do_{pid}".encode()),
                     Button.inline("❌ Cancel",      b"adm_del_select")],
                ],
            )

    elif data.startswith("adm_del_do_"):
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        pid = data[11:]
        await col_products.delete_one({"pid": pid})
        await event.answer("Deleted!", alert=True)
        await admin_list_products(event)

    elif data.startswith("ef_"):
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        _, field, pid = data.split("_", 2)
        await set_session(uid, {"state": f"adm_edit_{field}", "edit_pid": pid})
        labels = {
            "title":    "new title",
            "price":    "new price in Rs (number only)",
            "desc":     "new description",
            "features": "features — one per line\ne.g.\nAdmin panel\nAnti-spam\nMongoDB support",
            "file":     "new source code file",
        }
        await event.edit(
            f"✏️ Send the **{labels.get(field, field)}**:",
            buttons=[[Button.inline("❌ Cancel", b"adminpanel")]],
        )

    elif data == "adm_orders":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await admin_all_orders(event)

    elif data == "adm_pendingupi":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await admin_pending_upi(event)

    elif data == "adm_stats":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await admin_stats(event)

    elif data == "adm_addadmin":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await set_session(uid, {"state": "adm_addadmin"})
        await event.edit("👤 Send **User ID** to promote:",
                         buttons=[[Button.inline("❌ Cancel", b"adminpanel")]])

    elif data == "adm_deladmin":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await set_session(uid, {"state": "adm_deladmin"})
        await event.edit("👤 Send **User ID** to demote:",
                         buttons=[[Button.inline("❌ Cancel", b"adminpanel")]])

    elif data == "adm_broadcast":
        if not await is_admin(uid): return await event.answer("Not admin!", alert=True)
        await set_session(uid, {"state": "adm_broadcast"})
        await event.edit("📢 Send your broadcast message:",
                         buttons=[[Button.inline("❌ Cancel", b"adminpanel")]])

    else:
        await event.answer()

# ══════════════════════════════════════════════════════════════════
#  WALLET PAGE
# ══════════════════════════════════════════════════════════════════

async def show_wallet(event):
    uid = event.sender_id
    bal = await get_balance(uid)
    await event.edit(
        f"👛 **Your Wallet**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Balance: **Rs {bal:.2f}**\n\n"
        "Deposit funds to buy source codes instantly.\n"
        "Choose deposit method:",
        buttons=[
            [Button.inline("💳 Deposit via UPI",    b"dep_upi"),
             Button.inline("🔷 Deposit via Crypto", b"dep_crypto")],
            [Button.inline("🔙 Back", b"start")],
        ],
    )

# ══════════════════════════════════════════════════════════════════
#  BROWSE — only product titles as buttons
# ══════════════════════════════════════════════════════════════════

async def show_browse(event):
    products = await col_products.find().to_list(length=50)
    if not products:
        return await event.edit(
            "❌ No source codes available yet. Check back soon!",
            buttons=[[Button.inline("🔙 Back", b"start")]],
        )
    rows = []
    for p in products:
        rows.append([Button.inline(f"📦 {p['title']}", f"product_{p['pid']}".encode())])
    rows.append([Button.inline("🔙 Back", b"start")])
    await event.edit(
        "🛒 **Source Codes**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Tap a product to see features & price 👇",
        buttons=rows,
    )

# ══════════════════════════════════════════════════════════════════
#  PRODUCT DETAIL — features + Buy Now button only
# ══════════════════════════════════════════════════════════════════

async def show_product(event, pid: str):
    p = await col_products.find_one({"pid": pid})
    if not p:
        return await event.edit("❌ Product not found.")

    uid      = event.sender_id
    bal      = await get_balance(uid)
    usdt     = inr_to_usdt(p["price"])
    feat_str = features_text(p.get("features", []))
    can_buy  = bal >= p["price"]

    text = (
        f"📦 **{p['title']}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Description:**\n{p.get('description', 'N/A')}\n\n"
        f"✨ **Features:**\n{feat_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price:   **Rs {p['price']}**  (~${usdt} USDT)\n"
        f"👛 Balance: **Rs {bal:.2f}**"
    )

    if can_buy:
        buy_row = [Button.inline("🛍 Buy Now", f"buynow_{pid}".encode())]
    else:
        needed = p["price"] - bal
        buy_row = [Button.inline(f"💳 Deposit Rs {needed:.0f} more", b"wallet")]

    buttons = [
        buy_row,
        [Button.inline("🔙 Back", b"browse")],
    ]
    await event.edit(text, buttons=buttons)

# ══════════════════════════════════════════════════════════════════
#  BUY NOW — wallet debit + instant deliver
# ══════════════════════════════════════════════════════════════════

async def buy_now(event, pid: str):
    uid = event.sender_id
    p   = await col_products.find_one({"pid": pid})
    if not p:
        return await event.edit("❌ Product not found.")

    bal = await get_balance(uid)
    if bal < p["price"]:
        needed = p["price"] - bal
        return await event.edit(
            f"❌ **Insufficient Balance**\n\n"
            f"💰 Price:    Rs {p['price']}\n"
            f"👛 Balance:  Rs {bal:.2f}\n"
            f"📉 Need:     Rs {needed:.2f} more\n\n"
            "Deposit funds and try again.",
            buttons=[
                [Button.inline("💳 Deposit Now", b"wallet")],
                [Button.inline("🔙 Back",        f"product_{pid}".encode())],
            ],
        )

    # Debit wallet
    success = await debit_wallet(uid, p["price"])
    if not success:
        return await event.edit("❌ Balance deduction failed. Try again.",
                                buttons=[[Button.inline("🔙 Back", b"browse")]])

    order_id = gen_id()
    await col_orders.insert_one({
        "order_id":   order_id,
        "uid":        uid,
        "pid":        pid,
        "title":      p["title"],
        "amount":     p["price"],
        "method":     "wallet",
        "type":       "purchase",
        "status":     "completed",
        "created_at": datetime.now(timezone.utc),
    })

    new_bal = await get_balance(uid)

    # Deliver file
    await event.edit(
        f"✅ **Purchase Successful!**\n\n"
        f"📦 **{p['title']}**\n"
        f"💰 Rs {p['price']} deducted\n"
        f"👛 New Balance: Rs {new_bal:.2f}\n\n"
        "Your file is being sent below 👇",
        buttons=[[Button.inline("🔙 Main Menu", b"start")]],
    )

    if p.get("file_path") and os.path.exists(p["file_path"]):
        await bot.send_file(
            uid,
            file=p["file_path"],
            caption=(
                f"📦 **{p['title']}**\n\n"
                f"✅ Purchased successfully!\n"
                f"🆔 Order: `{order_id}`\n\n"
                "Thank you! 🎉"
            ),
        )
    else:
        await bot.send_message(uid, "✅ File will be delivered manually by admin shortly.")

    # Log to admin channel
    try:
        await bot.send_message(
            ADMIN_LOG_CHANNEL,
            f"✅ **New Purchase (Wallet)**\n\n"
            f"👤 User: `{uid}`\n"
            f"📦 Product: **{p['title']}**\n"
            f"💰 Amount: Rs {p['price']}\n"
            f"🆔 Order: `{order_id}`",
        )
    except Exception as e:
        log.warning(f"Log channel: {e}")

# ══════════════════════════════════════════════════════════════════
#  DEPOSIT — UPI screenshot flow
# ══════════════════════════════════════════════════════════════════

async def handle_dep_upi_amount(event, uid: int, text: str):
    try:
        amount = float(text.strip())
        if amount < 1:
            raise ValueError
    except:
        return await event.respond("❌ Invalid amount. Enter a number e.g. `200`")

    order_id = gen_id()
    await col_orders.insert_one({
        "order_id":   order_id,
        "uid":        uid,
        "amount":     amount,
        "method":     "upi",
        "type":       "deposit",
        "status":     "pending",
        "created_at": datetime.now(timezone.utc),
    })
    await set_session(uid, {"state": "dep_upi_ss", "order_id": order_id})

    qr_buf = make_upi_qr(amount)
    # Save to temp file so Telegram sends it as a photo, not a document
    tmp_path = os.path.join(UPLOAD_DIR, f"qr_{order_id}.png")
    with open(tmp_path, "wb") as f:
        f.write(qr_buf.read())
    await bot.send_file(
        uid,
        file=tmp_path,
        caption=(
            f"💳 **UPI Deposit**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Amount:  **Rs {amount:.2f}**\n"
            f"🏦 UPI ID:  `{UPI_ID}`\n\n"
            f"1️⃣ Scan QR or pay to UPI ID above\n"
            f"2️⃣ Pay exactly **Rs {amount:.2f}**\n"
            f"3️⃣ Send **payment screenshot** here\n\n"
            f"🆔 Order: `{order_id}`"
        ),
        buttons=[[Button.inline("❌ Cancel", b"wallet")]],
    )
    try:
        os.remove(tmp_path)
    except:
        pass

# ══════════════════════════════════════════════════════════════════
#  DEPOSIT — Crypto (OxaPay) flow
# ══════════════════════════════════════════════════════════════════

async def handle_dep_crypto_amount(event, uid: int, text: str):
    try:
        usdt = float(text.strip())
        if usdt <= 0:
            raise ValueError
    except:
        return await event.respond("❌ Invalid amount. Enter USDT amount e.g. `5`")

    amount_inr = round(usdt * INR_PER_USDT, 2)  # USDT → INR
    order_id   = gen_id()
    msg        = await event.respond(f"⏳ Creating **${usdt} USDT** invoice…")

    invoice = await create_oxapay_invoice(usdt, order_id, f"Deposit ${usdt} USDT")
    if not invoice:
        return await msg.edit("❌ Invoice creation failed. Try UPI deposit.")

    pay_url  = invoice.get("payLink", "")
    track_id = invoice.get("trackId", "")

    await col_orders.insert_one({
        "order_id":    order_id,
        "uid":         uid,
        "amount":      amount_inr,
        "amount_usdt": usdt,
        "method":      "crypto",
        "type":        "deposit",
        "status":      "pending",
        "track_id":    track_id,
        "created_at":  datetime.now(timezone.utc),
    })
    await clear_session(uid)

    await msg.edit(
        f"🔷 **Crypto Deposit (USDT)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Amount:  **${usdt} USDT**  _(~Rs {amount_inr})_\n"
        f"⏳ Expires: **30 minutes**\n\n"
        "1️⃣ Tap **Pay Now** below\n"
        "2️⃣ Complete payment on OxaPay\n"
        "3️⃣ Tap **Check Payment** — wallet credited instantly!",
        buttons=[
            [Button.url("💳 Pay Now", pay_url)],
            [Button.inline("🔄 Check Payment", f"dep_check_{order_id}".encode())],
            [Button.inline("🔙 Cancel",        b"wallet")],
        ],
        link_preview=False,
    )

async def check_dep_crypto(event, order_id: str):
    uid   = event.sender_id
    order = await col_orders.find_one({"order_id": order_id, "uid": uid, "type": "deposit"})
    if not order:
        return await event.answer("Order not found!", alert=True)
    if order["status"] == "completed":
        return await event.answer("Already credited!", alert=True)

    status = await check_oxapay_status(order.get("track_id", ""))
    if status == "Paid":
        await col_orders.update_one(
            {"order_id": order_id},
            {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}},
        )
        await credit_wallet(uid, order["amount"])
        new_bal = await get_balance(uid)
        await event.edit(
            f"✅ **Deposit Confirmed!**\n\n"
            f"💰 **Rs {order['amount']:.2f}** added to your wallet!\n"
            f"👛 New Balance: **Rs {new_bal:.2f}**\n\n"
            "Now browse and buy source codes 🚀",
            buttons=[[Button.inline("🛒 Browse Now", b"browse")]],
        )
        try:
            await bot.send_message(
                ADMIN_LOG_CHANNEL,
                f"✅ **Crypto Deposit Confirmed**\n"
                f"User: `{uid}`\n"
                f"Amount: Rs {order['amount']} (${order.get('amount_usdt')} USDT)\n"
                f"Order: `{order_id}`",
            )
        except: pass
    elif status == "Expired":
        await col_orders.update_one({"order_id": order_id}, {"$set": {"status": "expired"}})
        await event.edit("❌ Invoice expired.",
                         buttons=[[Button.inline("Try Again", b"dep_crypto")]])
    else:
        await event.answer(f"Status: {status or 'Pending'} — pay first then check.")

# ══════════════════════════════════════════════════════════════════
#  ADMIN — UPI DEPOSIT APPROVE / REJECT
# ══════════════════════════════════════════════════════════════════

async def admin_dep_approve(event, order_id: str):
    if not await is_admin(event.sender_id):
        return await event.answer("Not admin!", alert=True)
    order = await col_orders.find_one({"order_id": order_id, "type": "deposit"})
    if not order:
        return await event.answer("Order not found!", alert=True)
    if order["status"] == "completed":
        return await event.answer("Already approved!", alert=True)

    await col_orders.update_one(
        {"order_id": order_id},
        {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}},
    )
    await credit_wallet(order["uid"], order["amount"])
    new_bal = await get_balance(order["uid"])

    await event.edit(f"✅ Approved! Rs {order['amount']} credited to `{order['uid']}`.")

    try:
        await bot.send_message(
            order["uid"],
            f"✅ **Deposit Approved!**\n\n"
            f"💰 **Rs {order['amount']:.2f}** added to your wallet!\n"
            f"👛 New Balance: **Rs {new_bal:.2f}**\n\n"
            "Browse source codes and buy now! 🚀",
            buttons=[[Button.inline("🛒 Browse Now", b"browse")]],
        )
    except: pass

async def admin_dep_reject(event, order_id: str):
    if not await is_admin(event.sender_id):
        return await event.answer("Not admin!", alert=True)
    order = await col_orders.find_one({"order_id": order_id})
    if not order: return await event.answer("Not found!", alert=True)

    await col_orders.update_one({"order_id": order_id}, {"$set": {"status": "rejected"}})
    await event.edit(f"❌ Rejected deposit `{order_id}`.")

    try:
        await bot.send_message(
            order["uid"],
            f"❌ **Deposit Rejected**\n\nOrder: `{order_id}`\n"
            "Screenshot not verified. Try again or contact support.",
            buttons=[[Button.inline("👛 My Wallet", b"wallet")]],
        )
    except: pass

# ══════════════════════════════════════════════════════════════════
#  ADMIN — PRODUCT MANAGEMENT HELPERS
# ══════════════════════════════════════════════════════════════════

async def admin_select_product(event, action: str):
    products = await col_products.find().to_list(100)
    if not products:
        return await event.edit("No products.", buttons=[[Button.inline("🔙 Back", b"adminpanel")]])
    rows = []
    for p in products:
        cb   = f"adm_edit_{p['pid']}" if action == "edit" else f"adm_del_confirm_{p['pid']}"
        icon = "✏️" if action == "edit" else "🗑"
        rows.append([Button.inline(f"{icon} {p['title'][:30]}", cb.encode())])
    rows.append([Button.inline("🔙 Back", b"adminpanel")])
    await event.edit(
        "✏️ Select product to edit:" if action == "edit" else "🗑 Select product to delete:",
        buttons=rows,
    )

async def admin_list_products(event):
    products = await col_products.find().to_list(100)
    if not products:
        return await event.edit("No products.", buttons=[[Button.inline("🔙 Back", b"adminpanel")]])
    text = "📋 **All Products**\n\n"
    for p in products:
        fc = len(p.get("features", []))
        text += (
            f"📦 **{p['title']}**\n"
            f"   💰 Rs {p['price']}  |  ✨ {fc} features\n"
            f"   🆔 `{p['pid']}`\n\n"
        )
    await event.edit(text, buttons=[[Button.inline("🔙 Back", b"adminpanel")]])

async def admin_all_orders(event):
    orders = await col_orders.find().sort("created_at", -1).to_list(30)
    if not orders:
        return await event.edit("No orders.", buttons=[[Button.inline("🔙 Back", b"adminpanel")]])
    se = {"completed": "✅", "pending": "⏳", "rejected": "❌", "expired": "💀"}
    text = "📋 **Recent Orders** (last 30)\n\n"
    for o in orders:
        e = se.get(o["status"], "❓")
        text += f"{e} `{o['order_id']}` | {o.get('title','deposit')[:16]} | Rs{o.get('amount')} | {o.get('type','?')}\n"
    await event.edit(text, buttons=[[Button.inline("🔙 Back", b"adminpanel")]])

async def admin_pending_upi(event):
    orders = await col_orders.find({"method": "upi", "status": "pending"}).to_list(50)
    if not orders:
        return await event.edit("✅ No pending UPI deposits.",
                                buttons=[[Button.inline("🔙 Back", b"adminpanel")]])
    for o in orders:
        await bot.send_message(
            event.sender_id,
            f"🔍 **Pending UPI Deposit**\n"
            f"User: `{o['uid']}`\n"
            f"Amount: **Rs {o['amount']}**\n"
            f"Type: {o.get('type', 'deposit')}\n"
            f"Order: `{o['order_id']}`",
            buttons=[
                [Button.inline("✅ Approve", f"dep_approve_{o['order_id']}".encode()),
                 Button.inline("❌ Reject",  f"dep_reject_{o['order_id']}".encode())],
            ],
        )
    await event.edit("📋 Pending UPI deposits listed above.",
                     buttons=[[Button.inline("🔙 Back", b"adminpanel")]])

async def admin_stats(event):
    tp   = await col_products.count_documents({})
    to   = await col_orders.count_documents({"type": "purchase", "status": "completed"})
    td   = await col_orders.count_documents({"type": "deposit",  "status": "completed"})
    pupi = await col_orders.count_documents({"method": "upi", "status": "pending"})
    nadm = await col_admins.count_documents({}) + 1
    pipe = [{"$match": {"type": "purchase", "status": "completed"}},
            {"$group": {"_id": None, "t": {"$sum": "$amount"}}}]
    rr   = await col_orders.aggregate(pipe).to_list(1)
    rev  = rr[0]["t"] if rr else 0
    pipe2 = [{"$match": {"type": "deposit", "status": "completed"}},
             {"$group": {"_id": None, "t": {"$sum": "$amount"}}}]
    dr   = await col_orders.aggregate(pipe2).to_list(1)
    dep  = dr[0]["t"] if dr else 0
    await event.edit(
        f"📊 **Bot Statistics**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Products:        `{tp}`\n"
        f"✅ Sales:           `{to}`\n"
        f"💰 Total Deposits:  `Rs {dep:.2f}`\n"
        f"💵 Revenue (Sales): `Rs {rev:.2f}`\n"
        f"⏳ Pending UPI:     `{pupi}`\n"
        f"👤 Admins:          `{nadm}`\n",
        buttons=[[Button.inline("🔙 Back", b"adminpanel")]],
    )

async def show_my_orders(event):
    uid    = event.sender_id
    orders = await col_orders.find({"uid": uid, "type": "purchase"}).sort("created_at", -1).to_list(20)
    if not orders:
        return await event.edit("📦 No purchases yet.",
                                buttons=[[Button.inline("🔙 Back", b"start")]])
    se = {"completed": "✅", "pending": "⏳", "rejected": "❌"}
    text = "📦 **Your Purchases**\n\n"
    for o in orders:
        e = se.get(o["status"], "❓")
        text += f"{e} `{o['order_id']}` — {o.get('title','?')[:22]} — Rs {o.get('amount')}\n"
    await event.edit(text, buttons=[[Button.inline("🔙 Back", b"start")]])

# ══════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER — all conversation states
# ══════════════════════════════════════════════════════════════════

@bot.on(events.NewMessage())
async def message_handler(event):
    if event.sender_id == (await bot.get_me()).id:
        return
    uid     = event.sender_id
    session = await get_session(uid)
    state   = session.get("state", "")

    # ── Deposit: UPI amount ────────────────────────────────────────
    if state == "dep_upi_amount":
        await clear_session(uid)
        await handle_dep_upi_amount(event, uid, event.raw_text or "")

    # ── Deposit: UPI screenshot ────────────────────────────────────
    elif state == "dep_upi_ss":
        if not event.photo and not event.document:
            return await event.respond("❌ Please send a **screenshot** of your payment.")
        sess     = await get_session(uid)
        order_id = sess.get("order_id")
        order    = await col_orders.find_one({"order_id": order_id})
        if not order:
            return await event.respond("❌ Order not found.")
        await col_orders.update_one({"order_id": order_id},
                                    {"$set": {"status": "awaiting_admin"}})
        await clear_session(uid)
        sender = await event.get_sender()
        try:
            await bot.forward_messages(ADMIN_LOG_CHANNEL, event.message)
            await bot.send_message(
                ADMIN_LOG_CHANNEL,
                f"💳 **UPI Deposit — Verify**\n\n"
                f"👤 [{sender.first_name}](tg://user?id={uid}) (`{uid}`)\n"
                f"💰 **Rs {order['amount']:.2f}**\n"
                f"🆔 `{order_id}`\n\n"
                "Verify the screenshot above and approve/reject:",
                buttons=[
                    [Button.inline("✅ Approve", f"dep_approve_{order_id}".encode()),
                     Button.inline("❌ Reject",  f"dep_reject_{order_id}".encode())],
                ],
            )
        except Exception as e:
            log.warning(f"Log channel: {e}")
        await event.respond(
            "✅ **Screenshot received!**\n\n"
            "Admin will verify & credit your wallet shortly.\n"
            f"🆔 Order: `{order_id}`",
            buttons=[[Button.inline("👛 My Wallet", b"wallet")]],
        )

    # ── Deposit: Crypto amount ─────────────────────────────────────
    elif state == "dep_crypto_amount":
        await clear_session(uid)
        await handle_dep_crypto_amount(event, uid, event.raw_text or "")

    # ── Admin: Add product — Step 1 Title ─────────────────────────
    elif state == "adm_add_title":
        await set_session(uid, {"state": "adm_add_price", "title": event.raw_text.strip()})
        await event.respond("**Step 2/5** — Send **Price in Rs** (number only):\n_e.g. 299_")

    elif state == "adm_add_price":
        try:
            price = float(event.raw_text.strip())
        except:
            return await event.respond("❌ Invalid. Numbers only e.g. `299`")
        sess = await get_session(uid)
        await set_session(uid, {**sess, "state": "adm_add_desc", "price": price})
        await event.respond("**Step 3/5** — Send **Description**:")

    elif state == "adm_add_desc":
        sess = await get_session(uid)
        await set_session(uid, {**sess, "state": "adm_add_features", "desc": event.raw_text.strip()})
        await event.respond(
            "**Step 4/5** — Send **Features** (one per line):\n\n"
            "_Example:_\n"
            "Admin panel\nAnti-spam\nMongoDB support\nInline buttons\nAuto-reply"
        )

    elif state == "adm_add_features":
        sess     = await get_session(uid)
        features = [f.strip() for f in event.raw_text.strip().split("\n") if f.strip()]
        await set_session(uid, {**sess, "state": "adm_add_file", "features": features})
        preview = "\n".join(f"✅ {f}" for f in features)
        await event.respond(
            f"✨ **{len(features)} features saved!**\n\n{preview}\n\n"
            "**Step 5/5** — Upload the **Source Code File** (zip/rar/py etc.):"
        )

    elif state == "adm_add_file":
        if not event.document:
            return await event.respond("❌ Upload a **file**, not text.")
        sess = await get_session(uid)
        pid  = gen_id()
        try:
            orig = event.document.attributes[0].file_name
        except:
            orig = "source.zip"
        fpath = os.path.join(UPLOAD_DIR, f"{pid}_{orig}")
        await event.download_media(file=fpath)
        features = sess.get("features", [])
        await col_products.insert_one({
            "pid":         pid,
            "title":       sess.get("title", "Untitled"),
            "price":       sess.get("price", 0),
            "description": sess.get("desc", ""),
            "features":    features,
            "file_path":   fpath,
            "added_by":    uid,
            "created_at":  datetime.now(timezone.utc),
        })
        await clear_session(uid)
        feat_str = "\n".join(f"  ✅ {f}" for f in features) or "  (none)"
        await event.respond(
            f"✅ **Product Added!**\n\n"
            f"📦 **{sess.get('title')}**\n"
            f"💰 Rs {sess.get('price')}\n"
            f"✨ Features:\n{feat_str}\n"
            f"🆔 `{pid}`",
            buttons=[[Button.inline("🔙 Admin Panel", b"adminpanel")]],
        )

    # ── Admin: Edit fields ─────────────────────────────────────────
    elif state and state.startswith("adm_edit_") and state not in (
        "adm_edit_choose",
    ):
        field = state.replace("adm_edit_", "")
        sess  = await get_session(uid)
        pid   = sess.get("edit_pid")
        if field == "file":
            if not event.document:
                return await event.respond("❌ Send a file.")
            try: orig = event.document.attributes[0].file_name
            except: orig = "source.zip"
            fpath = os.path.join(UPLOAD_DIR, f"{pid}_{orig}")
            await event.download_media(file=fpath)
            await col_products.update_one({"pid": pid}, {"$set": {"file_path": fpath}})
        elif field == "price":
            try: val = float(event.raw_text.strip())
            except: return await event.respond("❌ Numbers only.")
            await col_products.update_one({"pid": pid}, {"$set": {"price": val}})
        elif field == "title":
            await col_products.update_one({"pid": pid}, {"$set": {"title": event.raw_text.strip()}})
        elif field == "desc":
            await col_products.update_one({"pid": pid}, {"$set": {"description": event.raw_text.strip()}})
        elif field == "features":
            features = [f.strip() for f in event.raw_text.strip().split("\n") if f.strip()]
            await col_products.update_one({"pid": pid}, {"$set": {"features": features}})
        await clear_session(uid)
        await event.respond("✅ Updated!",
                            buttons=[[Button.inline("🔙 Admin Panel", b"adminpanel")]])

    # ── Admin: Add/Del admin ───────────────────────────────────────
    elif state == "adm_addadmin":
        try: new_uid = int(event.raw_text.strip())
        except: return await event.respond("❌ Invalid User ID.")
        await col_admins.update_one({"uid": new_uid}, {"$set": {"uid": new_uid}}, upsert=True)
        await clear_session(uid)
        await event.respond(f"✅ `{new_uid}` is now an admin.",
                            buttons=[[Button.inline("🔙 Panel", b"adminpanel")]])

    elif state == "adm_deladmin":
        try: del_uid = int(event.raw_text.strip())
        except: return await event.respond("❌ Invalid User ID.")
        if del_uid == SUPER_ADMIN_ID:
            return await event.respond("❌ Cannot remove super admin!")
        await col_admins.delete_one({"uid": del_uid})
        await clear_session(uid)
        await event.respond(f"✅ `{del_uid}` removed.",
                            buttons=[[Button.inline("🔙 Panel", b"adminpanel")]])

    # ── Admin: Broadcast ───────────────────────────────────────────
    elif state == "adm_broadcast":
        msg_text = event.raw_text or ""
        user_ids = set()
        async for o in col_orders.find({}, {"uid": 1}):
            user_ids.add(o["uid"])
        async for w in col_wallets.find({}, {"uid": 1}):
            user_ids.add(w["uid"])
        sent = failed = 0
        for u in user_ids:
            try:
                await bot.send_message(u, f"📢 **Announcement**\n\n{msg_text}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        await clear_session(uid)
        await event.respond(
            f"📢 **Done!** Sent: {sent} | Failed: {failed}",
            buttons=[[Button.inline("🔙 Panel", b"adminpanel")]],
        )

# ══════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS (slash)
# ══════════════════════════════════════════════════════════════════

@bot.on(events.NewMessage(pattern="/admin"))
async def cmd_admin(event):
    if not await is_admin(event.sender_id):
        return await event.respond("❌ You are not an admin.")
    await event.respond("⚙️ **Admin Panel**", buttons=admin_panel_kb())

@bot.on(events.NewMessage(pattern=r"/addadmin (\d+)"))
async def cmd_addadmin(event):
    if not await is_admin(event.sender_id): return
    new_uid = int(event.pattern_match.group(1))
    await col_admins.update_one({"uid": new_uid}, {"$set": {"uid": new_uid}}, upsert=True)
    await event.respond(f"✅ `{new_uid}` promoted to admin.")

@bot.on(events.NewMessage(pattern=r"/deladmin (\d+)"))
async def cmd_deladmin(event):
    if event.sender_id != SUPER_ADMIN_ID: return
    del_uid = int(event.pattern_match.group(1))
    await col_admins.delete_one({"uid": del_uid})
    await event.respond(f"✅ `{del_uid}` removed.")

@bot.on(events.NewMessage(pattern="/broadcast"))
async def cmd_broadcast(event):
    if not await is_admin(event.sender_id): return
    await set_session(event.sender_id, {"state": "adm_broadcast"})
    await event.respond("📢 Send your broadcast message:")

@bot.on(events.NewMessage(pattern=r"/wallet (\d+)"))
async def cmd_wallet_admin(event):
    """Admin: check user wallet — /wallet 123456"""
    if not await is_admin(event.sender_id): return
    target = int(event.pattern_match.group(1))
    bal = await get_balance(target)
    await event.respond(f"👛 User `{target}` balance: **Rs {bal:.2f}**")

@bot.on(events.NewMessage(pattern=r"/addbal (\d+) (\d+\.?\d*)"))
async def cmd_addbal(event):
    """Admin: manually credit balance — /addbal USER_ID AMOUNT"""
    if not await is_admin(event.sender_id): return
    target = int(event.pattern_match.group(1))
    amount = float(event.pattern_match.group(2))
    await credit_wallet(target, amount)
    new_bal = await get_balance(target)
    await event.respond(f"✅ Rs {amount} credited to `{target}`.\nNew balance: Rs {new_bal:.2f}")
    try:
        await bot.send_message(target,
            f"✅ **Rs {amount:.2f}** has been added to your wallet by admin!\n"
            f"👛 New Balance: **Rs {new_bal:.2f}**")
    except: pass

# ══════════════════════════════════════════════════════════════════
#  BACKGROUND — auto verify crypto deposits every 30s
# ══════════════════════════════════════════════════════════════════

async def auto_check_loop():
    await asyncio.sleep(10)
    while True:
        try:
            async for order in col_orders.find({
                "method":   "crypto",
                "type":     "deposit",
                "status":   "pending",
                "track_id": {"$exists": True},
            }):
                status = await check_oxapay_status(order["track_id"])
                if status == "Paid":
                    await col_orders.update_one(
                        {"order_id": order["order_id"]},
                        {"$set": {"status": "completed",
                                  "completed_at": datetime.now(timezone.utc)}},
                    )
                    await credit_wallet(order["uid"], order["amount"])
                    new_bal = await get_balance(order["uid"])
                    try:
                        await bot.send_message(
                            order["uid"],
                            f"✅ **Deposit Confirmed!**\n\n"
                            f"💰 **Rs {order['amount']:.2f}** added to wallet!\n"
                            f"👛 Balance: **Rs {new_bal:.2f}**\n\n"
                            "Browse and buy source codes now 🚀",
                            buttons=[[Button.inline("🛒 Browse", b"browse")]],
                        )
                    except: pass
                elif status == "Expired":
                    await col_orders.update_one(
                        {"order_id": order["order_id"]},
                        {"$set": {"status": "expired"}},
                    )
                    try:
                        await bot.send_message(
                            order["uid"],
                            "❌ Your deposit invoice expired. Please try again.",
                            buttons=[[Button.inline("👛 Wallet", b"wallet")]],
                        )
                    except: pass
        except Exception as e:
            log.error(f"Auto-check loop: {e}")
        await asyncio.sleep(30)

# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()
    log.info(f"✅ Bot started: @{me.username}")

    await col_orders.create_index("order_id",  unique=True)
    await col_products.create_index("pid",     unique=True)
    await col_admins.create_index("uid",       unique=True)
    await col_wallets.create_index("uid",      unique=True)

    asyncio.create_task(auto_check_loop())
    log.info("🔄 Listening…")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

