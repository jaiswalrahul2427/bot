import os
import json
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Import everything from our bot.py file
from bot import (
    start, help_command, mydata, 
    register_start, register_name, register_dob, register_address, register_email, register_phone, cancel_register,
    delete_start, confirm_delete, global_stop,
    chat_start, chat_message, chat_stop,
    NAME, DOB, ADDRESS, EMAIL, PHONE, CONFIRM_DELETE, CHAT_MODE
)

# Create FastAPI app
app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Global application instance
ptb = None

@app.on_event("startup")
async def startup_event():
    global ptb
    if not TELEGRAM_BOT_TOKEN:
        print("Warning: TELEGRAM_BOT_TOKEN not found.")
        return
        
    # Build application
    ptb = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add all handlers
    ptb.add_handler(CommandHandler("start", start))
    ptb.add_handler(CommandHandler("help", help_command))
    ptb.add_handler(CommandHandler("mydata", mydata))

    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_dob)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_address)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)],
        },
        fallbacks=[CommandHandler("stop", cancel_register)]
    )
    ptb.add_handler(reg_conv)

    del_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", delete_start)],
        states={
            CONFIRM_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)]
        },
        fallbacks=[CommandHandler("stop", global_stop)]
    )
    ptb.add_handler(del_conv)
    
    chat_conv = ConversationHandler(
        entry_points=[CommandHandler("chat", chat_start)],
        states={
            CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_message)]
        },
        fallbacks=[CommandHandler("stop", chat_stop)]
    )
    ptb.add_handler(chat_conv)
    
    ptb.add_handler(CommandHandler("stop", global_stop))

    await ptb.initialize()
    print("Telegram Bot Application initialized!")

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    if ptb is None:
        return Response("Bot not initialized", status_code=500)
    
    try:
        body = await request.json()
        update = Update.de_json(body, ptb.bot)
        await ptb.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        print(f"Error processing update: {e}")
        return Response(status_code=500)

@app.get("/")
async def root():
    return {"message": "Telegram Bot is running on Vercel!"}

@app.get("/api/set-webhook")
async def set_webhook(url: str):
    """
    Utility endpoint to easily set the webhook URL.
    Usage: Visit /api/set-webhook?url=https://your-vercel-domain.vercel.app/api/webhook
    """
    if not ptb:
        return {"error": "Bot not initialized. Check your TELEGRAM_BOT_TOKEN"}
    
    success = await ptb.bot.set_webhook(url)
    return {"status": "Webhook set", "success": success, "url": url}
