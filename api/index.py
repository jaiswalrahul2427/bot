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

async def get_ptb():
    global ptb
    if ptb is not None:
        return ptb
        
    if not TELEGRAM_BOT_TOKEN:
        print("CRITICAL: TELEGRAM_BOT_TOKEN is missing!")
        return None

    try:
        # Build application
        new_ptb = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Add all handlers
        new_ptb.add_handler(CommandHandler("start", start))
        new_ptb.add_handler(CommandHandler("help", help_command))
        new_ptb.add_handler(CommandHandler("mydata", mydata))

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
        new_ptb.add_handler(reg_conv)

        del_conv = ConversationHandler(
            entry_points=[CommandHandler("delete", delete_start)],
            states={
                CONFIRM_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)]
            },
            fallbacks=[CommandHandler("stop", global_stop)]
        )
        new_ptb.add_handler(del_conv)
        
        chat_conv = ConversationHandler(
            entry_points=[CommandHandler("chat", chat_start)],
            states={
                CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_message)]
            },
            fallbacks=[CommandHandler("stop", chat_stop)]
        )
        new_ptb.add_handler(chat_conv)
        
        new_ptb.add_handler(CommandHandler("stop", global_stop))

        await new_ptb.initialize()
        ptb = new_ptb
        return ptb
    except Exception as e:
        print(f"Failed to initialize PTB: {e}")
        return None

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    bot_app = await get_ptb()
    if bot_app is None:
        return Response("Bot not initialized. Check Environment Variables.", status_code=500)
    
    try:
        body = await request.json()
        update = Update.de_json(body, bot_app.bot)
        await bot_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        print(f"Error processing update: {e}")
        return Response(status_code=500)

@app.get("/")
async def root():
    return {"message": "Telegram Bot is running on Vercel!"}

@app.get("/api/set-webhook")
async def set_webhook(url: str):
    bot_app = await get_ptb()
    if not bot_app:
        return {"error": "Bot not initialized. Check your TELEGRAM_BOT_TOKEN"}
    
    try:
        success = await bot_app.bot.set_webhook(url)
        return {"status": "Webhook set", "success": success, "url": url}
    except Exception as e:
        return {"error": str(e)}
