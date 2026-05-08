"""
Delivery Confirmation Bot
========================
Commands:
  /delivered ORD-001         -> marks order as Delivered
  /shipped ORD-001           -> marks order as Shipped
  /status ORD-001            -> checks current status of an order
  /pending                   -> lists all pending orders
  /summary                   -> shows today's delivery count
"""

import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ── Config ──────────────────────────────────────────────
BOT_TOKEN  = os.environ["BOT_TOKEN"]
SHEET_ID   = os.environ["SHEET_ID"]
CREDS_JSON = os.environ["GOOGLE_CREDS_JSON"]

ORDERS_SHEET = "📋 Orders"
ORDER_ID_COL = 1
STATUS_COL   = 8
DATE_COL     = 2
PRODUCT_COL  = 4
CUSTOMER_COL = 3
LOCATION_COL = 5
QTY_COL      = 6
HEADER_ROW   = 3

# ── Google Sheets connection ─────────────────────────────
def get_sheet():
    creds_dict = json.loads(CREDS_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(ORDERS_SHEET)

def find_order_row(sheet, order_id: str):
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows, 1):
        if i <= HEADER_ROW:
            continue
        if row and row[ORDER_ID_COL - 1].strip().upper() == order_id.strip().upper():
            return i, row
    return None, None

def update_status(sheet, row_index: int, new_status: str):
    sheet.update_cell(row_index, STATUS_COL, new_status)

# ── Bot handlers ─────────────────────────────────────────
async def cmd_delivered(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /delivered ORD-001")
        return

    order_id = ctx.args[0].upper()
    user     = update.effective_user.first_name

    try:
        sheet = get_sheet()
        row, data = find_order_row(sheet, order_id)

        if not row:
            await update.message.reply_text(f"Order {order_id} not found.")
            return

        current = data[STATUS_COL - 1]
        if "Delivered" in current:
            await update.message.reply_text(f"{order_id} is already marked Delivered.")
            return

        update_status(sheet, row, "Delivered")

        product  = data[PRODUCT_COL - 1]
        customer = data[CUSTOMER_COL - 1]
        location = data[LOCATION_COL - 1]
        qty      = data[QTY_COL - 1]

        await update.message.reply_text(
            f"Delivered: {order_id}\n\n"
            f"Customer: {customer}\n"
            f"Product: {product} (x{qty})\n"
            f"Location: {location}\n"
            f"Confirmed by: {user}"
        )

    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Error: {e}")


async def cmd_shipped(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /shipped ORD-001")
        return

    order_id = ctx.args[0].upper()
    user     = update.effective_user.first_name

    try:
        sheet = get_sheet()
        row, data = find_order_row(sheet, order_id)

        if not row:
            await update.message.reply_text(f"Order {order_id} not found.")
            return

        update_status(sheet, row, "Shipped")
        product  = data[PRODUCT_COL - 1]
        customer = data[CUSTOMER_COL - 1]

        await update.message.reply_text(
            f"Shipped: {order_id}\n"
            f"Customer: {customer} | Product: {product}\n"
            f"Confirmed by: {user}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /status ORD-001")
        return

    order_id = ctx.args[0].upper()

    try:
        sheet = get_sheet()
        row, data = find_order_row(sheet, order_id)

        if not row:
            await update.message.reply_text(f"Order {order_id} not found.")
            return

        status   = data[STATUS_COL - 1]
        product  = data[PRODUCT_COL - 1]
        customer = data[CUSTOMER_COL - 1]
        location = data[LOCATION_COL - 1]
        qty      = data[QTY_COL - 1]
        date     = data[DATE_COL - 1]

        await update.message.reply_text(
            f"Order {order_id}\n\n"
            f"Status: {status}\n"
            f"Customer: {customer}\n"
            f"Product: {product} (x{qty})\n"
            f"Location: {location}\n"
            f"Date: {date}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        sheet    = get_sheet()
        all_rows = sheet.get_all_values()
        pending  = []

        for i, row in enumerate(all_rows, 1):
            if i <= HEADER_ROW or not row or not row[ORDER_ID_COL - 1]:
                continue
            status = row[STATUS_COL - 1]
            if status in ("Pending", "", "Pending"):
                pending.append(
                    f"- {row[ORDER_ID_COL-1]} | {row[CUSTOMER_COL-1]} | "
                    f"{row[PRODUCT_COL-1]} | {row[LOCATION_COL-1]}"
                )

        if not pending:
            await update.message.reply_text("No pending orders right now!")
        else:
            msg = f"Pending Orders ({len(pending)})\n\n" + "\n".join(pending[:20])
            if len(pending) > 20:
                msg += f"\n\n...and {len(pending)-20} more"
            await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        sheet    = get_sheet()
        all_rows = sheet.get_all_values()
        today    = datetime.now().strftime("%Y-%m-%d")

        delivered = shipped = pending = 0
        for i, row in enumerate(all_rows, 1):
            if i <= HEADER_ROW or not row or not row[ORDER_ID_COL - 1]:
                continue
            status = row[STATUS_COL - 1]
            if "Delivered" in status:
                delivered += 1
            elif "Shipped" in status:
                shipped += 1
            elif "Pending" in status or status == "":
                pending += 1

        await update.message.reply_text(
            f"Delivery Summary\n"
            f"{today}\n\n"
            f"Delivered: {delivered}\n"
            f"Shipped:   {shipped}\n"
            f"Pending:   {pending}\n"
            f"Total:     {delivered + shipped + pending}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Delivery Bot Commands\n\n"
        "/delivered ORD-001 - Mark order as delivered\n"
        "/shipped ORD-001   - Mark order as shipped\n"
        "/status ORD-001    - Check order status\n"
        "/pending           - List all pending orders\n"
        "/summary           - Today's delivery count"
    )


# ── Main ─────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("delivered", cmd_delivered))
    app.add_handler(CommandHandler("shipped",   cmd_shipped))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("pending",   cmd_pending))
    app.add_handler(CommandHandler("summary",   cmd_summary))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("start",     cmd_help))
    print("Delivery bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
