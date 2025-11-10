# Dreame Sales Bot v1 (PTB v20+ compatible)
# Requirements: python-telegram-bot==20.3, requests

import logging
import requests
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
)
from telegram.ext import filters

# CONFIG
TOKEN = os.environ.get("DSB_TELEGRAM_TOKEN", "<PUT_YOUR_TOKEN_HERE>")
APPSCRIPT_URL = os.environ.get("DSB_APPSCRIPT_URL", "<PUT_YOUR_APPSCRIPT_URL_HERE>")
CURRENCY = "₽"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
CHOOSING, ENTER_QTY, ENTER_PLAN, ENTER_PRICE, ENTER_DELETE = range(5)

MAIN_MENU = [
    ["Добавить позицию", "Удалить позицию"],
    ["Просмотр премии", "Выполнение плана"],
    ["Указать план", "Изменить план"],
    ["Изменить сумму позиции", "❌ Очистить всё (только тест)"],
]

# --- Helpers ---
def send_to_api(action, payload):
    data = {"action": action, "payload": payload}
    try:
        r = requests.post(APPSCRIPT_URL, json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("API call failed")
        return {"ok": False, "error": str(e)}

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = MAIN_MENU
    reply = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
    await update.message.reply_text(
        f"Привет, {user.first_name}!\nЯ помогу считать премии по продажам.\nВыбери действие:",
        reply_markup=reply,
    )

async def main_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "Добавить позицию":
        resp = send_to_api("get_categories", {"user_id": user_id})
        if not resp.get("ok"):
            await update.message.reply_text("Ошибка получения категорий: " + resp.get("error", ""))
            return
        kb = [[InlineKeyboardButton(cat, callback_data="cat:" + cat)] for cat in resp.get("categories", [])]
        await update.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(kb))
        return CHOOSING

    if text == "Просмотр премии":
        resp = send_to_api("get_report", {"user_id": user_id})
        if not resp.get("ok"):
            await update.message.reply_text("Ошибка: " + resp.get("error", ""))
            return
        out = f"📊 Итоговая премия: {resp['summary']['total_commission']:,} {CURRENCY}\n"
        out += f"Оборот: {resp['summary']['turnover']:,} {CURRENCY}\n"
        out += f"План: {resp['summary']['plan']:,} {CURRENCY}\n"
        out += f"Выполнение: {resp['summary']['pct']:.1f}%\n\n"
        out += "Продажи (по обороту):\n"
        for it in resp.get("sales", []):
            out += f"- {it['model']} — {it['qty']} шт — {it['turnover']:,} {CURRENCY} — {it['commission']:,} {CURRENCY}\n"
        await update.message.reply_text(out)
        return

    if text == "Выполнение плана":
        resp = send_to_api("get_progress", {"user_id": user_id})
        if not resp.get("ok"):
            await update.message.reply_text("Ошибка: " + resp.get("error", ""))
            return
        out = f"Оборот: {resp['turnover']:,} {CURRENCY}\nПлан: {resp['plan']:,} {CURRENCY}\nВыполнение: {resp['pct']:.1f}%"
        await update.message.reply_text(out)
        return

    if text == "Указать план" or text == "Изменить план":
        await update.message.reply_text("Введи план по обороту в рублях (например: 500000)")
        return ENTER_PLAN

    if text == "Изменить сумму позиции":
        await update.message.reply_text("Введи код позиции и новую цену через пробел, например:\nVC03 45990")
        return ENTER_PRICE

    if text == "Удалить позицию":
        resp = send_to_api("list_sales", {"user_id": user_id})
        if not resp.get("ok"):
            await update.message.reply_text("Ошибка: " + resp.get("error", ""))
            return
        sales = resp.get("sales", [])
        if not sales:
            await update.message.reply_text("Список продаж пуст.")
            return
        kb = [
            [InlineKeyboardButton(f"{s['model']} — {s['qty']}шт", callback_data="del:" + s["id"])]
            for s in sales
        ]
        await update.message.reply_text("Выберите запись для удаления:", reply_markup=InlineKeyboardMarkup(kb))
        return ENTER_DELETE

    if text == "❌ Очистить всё (только тест)":
        resp = send_to_api("clear_sales", {"user_id": user_id})
        await update.message.reply_text("Тестовая очистка выполнена." if resp.get("ok") else "Ошибка")
        return

    # Default fallback
    await update.message.reply_text("Неизвестная команда/кнопка. Выберите действие в меню.")

# CallbackQuery handler for category/segment/model/delete actions
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("cat:"):
        cat = data.split("cat:", 1)[1]
        resp = send_to_api("get_segments", {"category": cat})
        if not resp.get("ok"):
            await query.edit_message_text("Ошибка: " + resp.get("error", ""))
            return
        kb = [[InlineKeyboardButton(seg, callback_data=f"seg:{cat}|{seg}")] for seg in resp.get("segments", [])]
        await query.edit_message_text("Выберите сегмент:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("seg:"):
        payload = data.split("seg:", 1)[1]
        cat, seg = payload.split("|", 1)
        resp = send_to_api("get_models", {"category": cat, "segment": seg})
        if not resp.get("ok"):
            await query.edit_message_text("Ошибка: " + resp.get("error", ""))
            return
        kb = [
            [InlineKeyboardButton(f"{m['code']} — {m['name']} — {int(m['price']):,}", callback_data=f"model:{m['code']}")]
            for m in resp.get("models", [])
        ]
        await query.edit_message_text("Выберите модель:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("model:"):
        code = data.split("model:", 1)[1]
        # save pending model
        context.user_data["pending_model"] = code
        await query.edit_message_text(f"Вы выбрали {code}. Введите количество:")
        return

    if data.startswith("del:"):
        rec_id = data.split("del:", 1)[1]
        resp = send_to_api("delete_sale", {"user_id": user_id, "record_id": rec_id})
        await query.edit_message_text("Запись удалена." if resp.get("ok") else "Ошибка при удалении")
        return

# ENTER_QTY handler
async def enter_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Введите целое число.")
        return ENTER_QTY
    qty = int(text)
    code = context.user_data.get("pending_model")
    resp = send_to_api("add_sale", {"user_id": user_id, "code": code, "qty": qty})
    if not resp.get("ok"):
        await update.message.reply_text("Ошибка при добавлении: " + resp.get("error", ""))
    else:
        await update.message.reply_text("Продажа добавлена.")
    return ConversationHandler.END

# ENTER_PLAN handler
async def enter_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not text.isdigit():
        await update.message.reply_text("Введите число в рублях, например: 500000")
        return ENTER_PLAN
    plan = int(text)
    user_id = update.effective_user.id
    resp = send_to_api("set_plan", {"user_id": user_id, "plan": plan})
    await update.message.reply_text("План установлен." if resp.get("ok") else "Ошибка установки плана")
    return ConversationHandler.END

# ENTER_PRICE handler
async def enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.strip().split()
    if len(parts) != 2:
        await update.message.reply_text("Неверный формат. Пример: VC03 45990")
        return ENTER_PRICE
    code, price = parts[0], parts[1].replace(" ", "")
    if not price.isdigit():
        await update.message.reply_text("Цена должна быть числом")
        return ENTER_PRICE
    price = int(price)
    resp = send_to_api("set_price", {"code": code, "price": price})
    await update.message.reply_text("Цена обновлена." if resp.get("ok") else "Ошибка обновления")
    return ConversationHandler.END

# Delete via callback already handled; fallback cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Main entry / wiring
def main():
    if TOKEN.startswith("<") or TOKEN.strip() == "" or "PUT_YOUR_TOKEN" in TOKEN:
        print("ERROR: set your token in environment variable DSB_TELEGRAM_TOKEN or replace in file")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, main_text)],
        states={
            CHOOSING: [CallbackQueryHandler(callback_handler)],
            ENTER_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_qty)],
            ENTER_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_plan)],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price)],
            ENTER_DELETE: [CallbackQueryHandler(callback_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv)
    # Also add callback handler globally to catch inline callbacks outside conv
    application.add_handler(CallbackQueryHandler(callback_handler))

    print("Bot started. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()
