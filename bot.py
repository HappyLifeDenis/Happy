from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
import asyncio
from aiohttp import web
import threading

BOT_TOKEN = "7661463654:AAElQ6ZtcH229o-ww26xDcASXh42cIYS02Y"
MAX_DRIVERS = 50  # Изменил лимит на 50

drivers = set()
pending_order = None

def furniture_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚚 Хотите перевезти мебель?", callback_data="order_furniture")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте! Чем могу помочь?",
        reply_markup=furniture_button()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "order_furniture":
        await query.edit_message_text("📅 Какого числа вы хотите перевезти мебель?")
        return 1  # ASK_DATE

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text.strip()
    await update.message.reply_text("📦 Что хотите перевезти?")
    return 2

async def ask_goods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["goods"] = update.message.text.strip()
    await update.message.reply_text("🏠 Откуда забираем?")
    return 3

async def ask_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text.strip()
    await update.message.reply_text("🏠 Куда везём?")
    return 4

async def ask_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to"] = update.message.text.strip()
    await update.message.reply_text("👷‍♂️ Сколько грузчиков нужно?")
    return 5

async def ask_loaders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["loaders"] = update.message.text.strip()
    await update.message.reply_text("📞 Ваш номер телефона?")
    return 6

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pending_order
    context.user_data["phone"] = update.message.text.strip()

    if not drivers:
        await update.message.reply_text(
            "🚫 Пока нет зарегистрированных водителей. Попробуйте позже.",
            reply_markup=furniture_button()
        )
        return ConversationHandler.END

    full_order_text = (
        f"📅 Дата: {context.user_data.get('date')}\n"
        f"📦 Что перевозим: {context.user_data.get('goods')}\n"
        f"🏠 Адрес отправления: {context.user_data.get('from')}\n"
        f"🏠 Адрес назначения: {context.user_data.get('to')}\n"
        f"👷‍♂️ Грузчики: {context.user_data.get('loaders')}\n"
        f"📞 Телефон: {context.user_data.get('phone')}"
    )
    client_id = update.effective_user.id

    pending_order = {
        "text": full_order_text,
        "client_id": client_id,
        "message_ids": {},
        "claimed": False
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Принять", callback_data="accept")]
    ])

    for drv_id in drivers:
        msg = await context.bot.send_message(
            chat_id=drv_id,
            text=f"📥 Новая заявка:\n{full_order_text}",
            reply_markup=keyboard
        )
        pending_order["message_ids"][drv_id] = msg.message_id

    await update.message.reply_text("✅ Ждите звонка.", reply_markup=furniture_button())
    return ConversationHandler.END

async def accept_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pending_order
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if not pending_order or pending_order["claimed"]:
        await query.edit_message_text("🚫 Заявка уже принята другим водителем.")
        return

    if query.data == "accept":
        pending_order["claimed"] = True

        await context.bot.send_message(
            chat_id=pending_order["client_id"],
            text=f"✅ Ваш заказ принял водитель @{query.from_user.username or uid}."
        )
        await query.edit_message_text("✅ Вы приняли заявку! Свяжитесь с клиентом напрямую.")

        for drv_id, msg_id in pending_order["message_ids"].items():
            if drv_id != uid:
                try:
                    await context.bot.edit_message_text(
                        chat_id=drv_id,
                        message_id=msg_id,
                        text="❌ Заявка уже занята другим водителем."
                    )
                except Exception:
                    pass

        pending_order = None

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in drivers:
        await update.message.reply_text("❗ Вы уже зарегистрированы как водитель.")
    elif len(drivers) >= MAX_DRIVERS:
        await update.message.reply_text("⚠️ Лимит водителей достигнут.")
    else:
        drivers.add(user_id)
        await update.message.reply_text("✅ Вы успешно зарегистрированы как водитель!")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# --- HTTP сервер для пинга ---
async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def run_webserver():
    app = web.Application()
    app.add_routes([web.get('/', handle_ping)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("🌐 Webserver running on http://0.0.0.0:8080")

def start_webserver_in_thread():
    asyncio.run(run_webserver())

def main():
    # Запускаем веб-сервер в отдельном потоке
    threading.Thread(target=start_webserver_in_thread, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))

    client_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="order_furniture")],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_goods)],
            3: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_from)],
            4: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_to)],
            5: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_loaders)],
            6: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(client_conv_handler)
    application.add_handler(CallbackQueryHandler(accept_order, pattern="accept"))

    application.run_polling()

if __name__ == "__main__":
    main()
