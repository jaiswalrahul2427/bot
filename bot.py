import os
import json
import logging
import requests
import datetime
import hmac
import asyncio
from dotenv import load_dotenv

import google.generativeai as genai
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from aiohttp import web

from ai_prompt import SYSTEM_PROMPT
import database as db

# Load env variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ZAPIER_WEBHOOK_URL = os.getenv("ZAPIER_WEBHOOK_URL")
API_SECRET_HEADER = os.getenv("API_SECRET_HEADER")

# Configure Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    generation_config = {"temperature": 0.5, "top_p": 0.95, "top_k": 40, "max_output_tokens": 8192}
    model = genai.GenerativeModel(model_name="gemini-1.5-flash", generation_config=generation_config, system_instruction=SYSTEM_PROMPT)
else:
    logger.warning("GEMINI_API_KEY not set!")

# States for Registration Conversation
NAME, DOB, ADDRESS, EMAIL, PHONE = range(5)
# States for deletion
CONFIRM_DELETE = 5
# States for chat mode
CHAT_MODE = 6

def log_to_zapier(telegram_id: str, action: str, permission: str, status: str):
    """Log an action to Zapier Webhook"""
    if not ZAPIER_WEBHOOK_URL:
        return
        
    payload = {
        "agent_name": "CustomerDataBot",
        "agent_type": "telegram",
        "telegram_id": str(telegram_id),
        "action": action,
        "permission": permission,
        "status": status,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    }
    try:
        # Background request
        requests.post(ZAPIER_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to log to Zapier: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your secure customer assistant.\n"
        "I can securely store your details, answer your questions, and help you manage your account.\n\n"
        "Available commands:\n"
        "/register - Collect/update your data\n"
        "/mydata - View your stored information\n"
        "/delete - Permanently delete your data\n"
        "/chat - Free AI conversation mode\n"
        "/help - List all commands"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Welcome message\n"
        "/register - Collect/update customer data\n"
        "/mydata - View stored data\n"
        "/delete - Permanently delete data\n"
        "/chat - Free AI conversation mode\n"
        "/stop - Exit current mode\n"
        "/help - List all commands"
    )

# REGISTRATION FLOW
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Let's set up or update your profile. What is your full name?", reply_markup=ReplyKeyboardRemove())
    return NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Thanks! Please enter your Date of Birth (e.g., YYYY-MM-DD):")
    return DOB

async def register_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dob'] = update.message.text
    await update.message.reply_text("Got it. What is your full residential address?")
    return ADDRESS

async def register_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['address'] = update.message.text
    await update.message.reply_text("Excellent. Now, please enter your email address:")
    return EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    await update.message.reply_text("Finally, what is your phone number (with country code)?")
    return PHONE

async def register_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    user_id = str(update.effective_user.id)
    
    # Save to db
    await db.save_customer(
        telegram_id=user_id,
        name=context.user_data['name'],
        dob=context.user_data['dob'],
        address=context.user_data['address'],
        email=context.user_data['email'],
        phone=context.user_data['phone']
    )
    
    log_to_zapier(user_id, "customer_registered", "write", "success")
    await update.message.reply_text("Your details have been securely encrypted and saved. Use /mydata to view them.")
    
    # clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registration cancelled. You can use /register to start again.")
    context.user_data.clear()
    return ConversationHandler.END

# MYDATA FLOW
async def mydata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = await db.get_customer(user_id)
    
    log_to_zapier(user_id, "customer_viewed_data", "read", "success")
    
    if data:
        msg = (
            "Here is your securely stored data:\n\n"
            f"**Name:** {data['name']}\n"
            f"**DOB:** {data['dob']}\n"
            f"**Address:** {data['address']}\n"
            f"**Email:** {data['email']}\n"
            f"**Phone:** {data['phone']}\n\n"
            "If you want to update it, just use /register."
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text("You don't have any data stored yet. Use /register to get started.")

# DELETE FLOW
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = await db.get_customer(user_id)
    if not data:
        await update.message.reply_text("You don't have any data stored.")
        return ConversationHandler.END
        
    await update.message.reply_text("Are you sure you want to permanently delete your data? Type YES to confirm.", reply_markup=ReplyKeyboardRemove())
    return CONFIRM_DELETE

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = str(update.effective_user.id)
    if text == "YES":
        await db.delete_customer(user_id)
        log_to_zapier(user_id, "customer_deleted", "write", "success")
        await update.message.reply_text("Your data has been permanently deleted.")
    else:
        await update.message.reply_text("Deletion cancelled.")
    return ConversationHandler.END

# CHAT FLOW
async def chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("You are now in AI chat mode. Send me a message, and I'll assist you! Type /stop to exit.")
    
    user_id = str(update.effective_user.id)
    data = await db.get_customer(user_id)
    
    customer_context = "No registered data."
    if data:
        customer_context = f"Customer Data:\\nName: {data['name']}\\nDOB: {data['dob']}\\nAddress: {data['address']}\\nEmail: {data['email']}\\nPhone: {data['phone']}"
        
    try:
        chat = model.start_chat(history=[])
        context.user_data['chat'] = chat
        context.user_data['customer_context'] = customer_context
        return CHAT_MODE
    except Exception as e:
        logger.error(f"Failed to start chat: {e}")
        await update.message.reply_text("Error starting chat mode. Ensure Gemini API key is configured.")
        return ConversationHandler.END

async def chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = context.user_data.get('chat')
    customer_context = context.user_data.get('customer_context', '')
    if not chat:
        await update.message.reply_text("Chat session expired. Please type /chat to start again.")
        return ConversationHandler.END
        
    user_message = update.message.text
    
    try:
        response = chat.send_message(f"Current Context: {customer_context}\\n\\nUser: {user_message}")
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        await update.message.reply_text("I'm sorry, I encountered an error processing your request.")

    return CHAT_MODE

async def chat_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Exited chat mode.")
    if 'chat' in context.user_data:
        del context.user_data['chat']
    return ConversationHandler.END

# GLOBAL STOP HANDLER
async def global_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# API SERVER for external platform HMAC verification
async def verify_hmac(request):
    """Endpoint for API verification"""
    auth_header = request.headers.get('X-API-Key')
    if not auth_header or not API_SECRET_HEADER:
        return web.json_response({"error": "Unauthorized"}, status=401)
        
    if hmac.compare_digest(auth_header, API_SECRET_HEADER):
        return web.json_response({"status": "success", "message": "Authenticated"})
    else:
        return web.json_response({"error": "Forbidden"}, status=403)


async def main():
    await db.init_db()

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        # We don't return here so we can at least test API without bot

    application = None
    if TELEGRAM_BOT_TOKEN:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("mydata", mydata))

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
        application.add_handler(reg_conv)

        del_conv = ConversationHandler(
            entry_points=[CommandHandler("delete", delete_start)],
            states={
                CONFIRM_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)]
            },
            fallbacks=[CommandHandler("stop", global_stop)]
        )
        application.add_handler(del_conv)
        
        chat_conv = ConversationHandler(
            entry_points=[CommandHandler("chat", chat_start)],
            states={
                CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_message)]
            },
            fallbacks=[CommandHandler("stop", chat_stop)]
        )
        application.add_handler(chat_conv)
        
        application.add_handler(CommandHandler("stop", global_stop))

    # AIOHTTP server for HMAC API verification
    app = web.Application()
    app.router.add_get('/api/verify', verify_hmac)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    
    logger.info("Starting API server...")
    await site.start()
    
    if application:
        logger.info("Starting Telegram Bot...")
        async with application:
            await application.start()
            await application.updater.start_polling()
            
            stop_event = asyncio.Event()
            await stop_event.wait()
            
            await application.updater.stop()
            await application.stop()
    else:
        logger.info("Bot not started. API server is running.")
        stop_event = asyncio.Event()
        await stop_event.wait()
        
    await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
