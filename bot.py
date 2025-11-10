# Dreame Sales Bot v1
# ACTIONS REQUIRED BEFORE RUNNING:
# 1) Create a Telegram bot with @BotFather and paste TOKEN below
# 2) Create Google Sheet from template (provided) and deploy the Google Apps Script (code.gs)
#    as a web app that accepts POST requests. Copy the Web App URL and paste into APPSCRIPT_URL.
# 3) Host this file on Replit / PythonAnywhere / Termux and run `python bot.py`

import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes
)
from telegram import Update
from telegram.ext import filters

import os

# CONFIG
TOKEN = os.environ.get('DSB_TELEGRAM_TOKEN', '<PUT_YOUR_TOKEN_HERE>')
APPSCRIPT_URL = os.environ.get('DSB_APPSCRIPT_URL', '<PUT_YOUR_APPSCRIPT_URL_HERE>')
CURRENCY = '₽'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

(CHOOSING, ENTER_QTY, ENTER_PLAN, ENTER_PRICE, ENTER_DELETE) = range(5)

MAIN_MENU = [
    ["Добавить позицию", "Удалить позицию"],
    ["Просмотр премии", "Выполнение плана"],
    ["Указать план", "Изменить план"],
    ["Изменить сумму позиции", "❌ Очистить всё (только тест)"]
]

def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = MAIN_MENU
    reply = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
    update.message.reply_text(f"Привет, {user.first_name}!\nЯ помогу считать премии по продажам.\nВыбери действие:", reply_markup=reply)

def send_to_api(action, payload):
    data = {"action": action, "payload": payload}
    try:
        r = requests.post(APPSCRIPT_URL, json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("API call failed")
        return {"ok": False, "error": str(e)}

def handle_text(update: Update, context: CallbackContext):
    text = update.message.text
    user_id = update.effective_user.id
    if text == "Добавить позицию":
        resp = send_to_api("get_categories", {"user_id": user_id})
        if not resp.get("ok"):
            update.message.reply_text("Ошибка получения категорий: " + resp.get("error", ""))
            return
        kb = []
        for cat in resp["categories"]:
            kb.append([InlineKeyboardButton(cat, callback_data="cat:"+cat)])
        update.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(kb))
        return CHOOSING
    if text == "Просмотр премии":
        resp = send_to_api("get_report", {"user_id": user_id})
        if not resp.get("ok"):
            update.message.reply_text("Ошибка: " + resp.get("error",""))
            return
        out = f"📊 Итоговая премия: {resp['summary']['total_commission']:,} {CURRENCY}\n"
        out += f"Оборот: {resp['summary']['turnover']:,} {CURRENCY}\n"
        out += f"План: {resp['summary']['plan']:,} {CURRENCY}\n"
        out += f"Выполнение: {resp['summary']['pct']:.1f}%\n\n"
        out += "Продажи (по обороту):\n"
        for it in resp.get("sales", []):
            out += f"- {it['model']} — {it['qty']} шт — {it['turnover']:,} {CURRENCY} — {it['commission']:,} {CURRENCY}\n"
        update.message.reply_text(out)
        return
    if text == "Выполнение плана":
        resp = send_to_api("get_progress", {"user_id": user_id})
        if not resp.get("ok"):
            update.message.reply_text("Ошибка: " + resp.get("error",""))
            return
        out = f"Оборот: {resp['turnover']:,} {CURRENCY}\nПлан: {resp['plan']:,} {CURRENCY}\nВыполнение: {resp['pct']:.1f}%"
        update.message.reply_text(out)
        return
    if text == "Указать план":
        update.message.reply_text("Введи план по обороту в рублях (например: 500000)")
        return ENTER_PLAN
    if text == "Изменить план":
        update.message.reply_text("Введи новый план по обороту в рублях (например: 600000)")
        return ENTER_PLAN
    if text == "Изменить сумму позиции":
        update.message.reply_text("Введи код позиции и новую цену через пробел, например:\nVC03 45990")
        return ENTER_PRICE
    if text == "Удалить позицию":
        resp = send_to_api("list_sales", {"user_id": user_id})
        if not resp.get("ok"):
            update.message.reply_text("Ошибка: " + resp.get("error",""))
            return
        sales = resp.get("sales", [])
        if not sales:
            update.message.reply_text("Список продаж пуст.")
            return
        kb = []
        for s in sales:
            kb.append([InlineKeyboardButton(f"{s['model']} — {s['qty']}шт", callback_data="del:"+s['id'])])
        update.message.reply_text("Выберите запись для удаления:", reply_markup=InlineKeyboardMarkup(kb))
        return ENTER_DELETE
    if text == "❌ Очистить всё (только тест)":
        resp = send_to_api("clear_sales", {"user_id": user_id})
        update.message.reply_text("Тестовая очистка выполнена." if resp.get("ok") else "Ошибка")
        return

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()
    data = query.data
    if data.startswith("cat:"):
        cat = data.split("cat:",1)[1]
        resp = send_to_api("get_segments", {"category": cat})
        if not resp.get("ok"):
            query.edit_message_text("Ошибка: "+resp.get("error",""))
            return
        kb = []
        for seg in resp["segments"]:
            kb.append([InlineKeyboardButton(seg, callback_data=f"seg:{cat}|{seg}")])
        query.edit_message_text("Выберите сегмент:", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("seg:"):
        payload = data.split("seg:",1)[1]
        cat, seg = payload.split("|",1)
        resp = send_to_api("get_models", {"category": cat, "segment": seg})
        if not resp.get("ok"):
            query.edit_message_text("Ошибка: "+resp.get("error",""))
            return
        kb = []
        for m in resp["models"]:
            kb.append([InlineKeyboardButton(f"{m['code']} — {m['name']} — {m['price']:,}", callback_data=f"model:{m['code']}")])
        query.edit_message_text("Выберите модель:", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("model:"):
        code = data.split("model:",1)[1]
        context.user_data['pending_model'] = code
        query.edit_message_text(f"Вы выбрали {code}. Введите количество:")
        return ENTER_QTY
    if data.startswith("del:"):
        rec_id = data.split("del:",1)[1]
        resp = send_to_api("delete_sale", {"user_id": user_id, "record_id": rec_id})
        query.edit_message_text("Запись удалена." if resp.get("ok") else "Ошибка при удалении")
        return

def enter_qty(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text.isdigit():
        update.message.reply_text("Введите целое число.")
        return ENTER_QTY
    qty = int(text)
    code = context.user_data.get('pending_model')
    resp = send_to_api("add_sale", {"user_id": user_id, "code": code, "qty": qty})
    if not resp.get("ok"):
        update.message.reply_text("Ошибка при добавлении: " + resp.get("error",""))
    else:
        update.message.reply_text("Продажа добавлена.")
    return ConversationHandler.END

def enter_plan(update: Update, context: CallbackContext):
    text = update.message.text.strip().replace(" ","")
    if not text.isdigit():
        update.message.reply_text("Введите число в рублях, например: 500000")
        return ENTER_PLAN
    plan = int(text)
    user_id = update.effective_user.id
    resp = send_to_api("set_plan", {"user_id": user_id, "plan": plan})
    update.message.reply_text("План установлен." if resp.get("ok") else "Ошибка установки плана")
    return ConversationHandler.END

def enter_price(update: Update, context: CallbackContext):
    parts = update.message.text.strip().split()
    if len(parts) != 2:
        update.message.reply_text("Неверный формат. Пример: VC03 45990")
        return ENTER_PRICE
    code, price = parts[0], parts[1].replace(" ","")
    if not price.isdigit():
        update.message.reply_text("Цена должна быть числом")
        return ENTER_PRICE
    price = int(price)
    resp = send_to_api("set_price", {"code": code, "price": price})
    update.message.reply_text("Цена обновлена." if resp.get("ok") else "Ошибка обновления")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text('Операция отменена.')
    return ConversationHandler.END

def main():
    token = TOKEN
    if token.startswith("<") or token.strip()=="" or "PUT_YOUR_TOKEN" in token:
        print("ERROR: set your token in environment variable DSB_TELEGRAM_TOKEN or replace in file")
        return
    updater = ApplicationBuilder().token(TOKEN).build()
    dp = updater.application

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~Filters.command, handle_text)],
        states={
            CHOOSING: [CallbackQueryHandler(callback_handler)],
            ENTER_QTY: [MessageHandler(filters.TEXT & ~Filters.command, enter_qty)],
            ENTER_PLAN: [MessageHandler(filters.TEXT & ~Filters.command, enter_plan)],
            ENTER_PRICE: [MessageHandler(filters.TEXT & ~Filters.command, enter_price)],
            ENTER_DELETE: [CallbackQueryHandler(callback_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True
    )

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(conv)
    dp.add_handler(CallbackQueryHandler(callback_handler))

    print("Bot started. Press Ctrl+C to stop.")
    updater.run_polling()
    updater.idle()

if __name__ == '__main__':
    main()
if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    # Здесь добавятся все handlers
    application.run_polling()
