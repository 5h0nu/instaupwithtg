import subprocess
import sys
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ConversationHandler, 
    ContextTypes
)
from telegram.request import HTTPXRequest
from instagrapi import Client

# --- AUTO-INSTALLER SECTION ---
def install_dependencies():
    libs = {
        "python-telegram-bot": "telegram",
        "instagrapi": "instagrapi",
        "moviepy": "moviepy",
        "pydantic": "pydantic",
        "pillow": "PIL"
    }
    for pip_name, import_name in libs.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"Installing {pip_name}... please wait.")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name, "--user", "--no-cache-dir"])
            except Exception as e:
                print(f"Critical Error: Could not install {pip_name}. Error: {e}")
                sys.exit(1)

install_dependencies()

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# States
CHOOSING, ASKING_REEL, ASKING_TITLE, CONFIRM_UPLOAD, ASKING_COMMENT_LINK, \
ASKING_COMMENT_TEXT, CONFIRM_COMMENT, ASKING_SESSION, ASKING_PIN_ONLY_LINK = range(9)

user_sessions = {} 
temp_data = {}

# --- MAIN MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📹 Upload Reel", callback_data='upload_reel')],
        [InlineKeyboardButton("💬 Post Comment", callback_data='post_comment')],
        [InlineKeyboardButton("📌 Pin Latest Comment", callback_data='pin_latest')],
        [InlineKeyboardButton("🔑 Manage Session", callback_data='manage_session')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "🚀 **Instagram Automation Bot**\nSelect an option from the menu below:"
    
    # Handle both /start command and callback updates
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return CHOOSING

# --- SESSION MANAGEMENT ---
# --- SESSION MANAGEMENT ---
async def manage_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id in user_sessions:
        username = user_sessions[user_id]['username']
        await query.edit_message_text(f"✅ Currently logged in as: **@{username}**")
        return await start(update, context)
    else:
        await query.edit_message_text("No account found. Please send your Instagram **Session ID**:")
        return ASKING_SESSION

async def save_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = update.message.text.strip()
    cl = Client()
    msg = await update.message.reply_text("⏳ Verifying session... please wait.")
    try:
        cl.login_by_sessionid(session_id)
        user_sessions[update.message.from_user.id] = {"cl": cl, "username": cl.account_info().username}
        await msg.edit_text(f"✅ Success! Logged in as: **@{user_sessions[update.message.from_user.id]['username']}**")
    except Exception as e:
        await msg.edit_text(f"❌ Login Failed: {str(e)}")
    return await start(update, context)# --- REEL UPLOAD FLOW ---
async def ask_reel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("Please upload the **MP4 Video** file:")
    return ASKING_REEL

async def get_reel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_file = await update.message.video.get_file()
    path = f"temp_{update.message.from_user.id}.mp4"
    await video_file.download_to_drive(path)
    temp_data[update.message.from_user.id] = {'path': path}
    await update.message.reply_text("Video received! Now enter the **Caption/Title**:")
    return ASKING_TITLE

async def confirm_upload_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    temp_data[user_id]['title'] = update.message.text
    
    keyboard = [[InlineKeyboardButton("✅ Confirm & Upload", callback_data='final_upload')]]
    
    await update.message.reply_video(
        video=open(temp_data[user_id]['path'], 'rb'),
        caption=f"**PREVIEW**\nCaption: {temp_data[user_id]['title']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown',
        read_timeout=60
    )
    return CONFIRM_UPLOAD

async def final_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cl = user_sessions.get(user_id, {}).get("cl")
    
    if not cl:
        await query.answer("Please login first!", show_alert=True)
        return await start(update, context)

    await query.edit_message_caption(caption="⏳ Uploading to Instagram... this may take a moment.")
    
    try:
        media = cl.clip_upload(temp_data[user_id]['path'], temp_data[user_id]['title'])
        await query.message.reply_text(f"✅ **Reel Uploaded Successfully!**\nLink: https://www.instagram.com/reels/{media.code}/")
    except Exception as e:
        await query.message.reply_text(f"❌ Instagram Error: {e}")
    
    if os.path.exists(temp_data[user_id]['path']):
        os.remove(temp_data[user_id]['path'])
    return await start(update, context)

# --- COMMENT FLOW ---
async def ask_comment_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("Send the Instagram Video/Reel **Link**:")
    return ASKING_COMMENT_LINK

async def get_comment_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    temp_data[update.message.from_user.id] = {'vid_url': update.message.text}
    await update.message.reply_text("Enter the **Comment Text**:")
    return ASKING_COMMENT_TEXT

async def confirm_comment_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    temp_data[user_id]['text'] = update.message.text
    
    keyboard = [
        [InlineKeyboardButton("💬 Comment", callback_data='do_comment')],
        [InlineKeyboardButton("📌 Comment & Pin", callback_data='do_pin')]
    ]
    await update.message.reply_text(
        f"**COMMENT PREVIEW**\nURL: {temp_data[user_id]['vid_url']}\nText: {temp_data[user_id]['text']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CONFIRM_COMMENT

async def final_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cl = user_sessions.get(user_id, {}).get("cl")
    
    if not cl:
        await query.answer("Session expired!", show_alert=True)
        return await start(update, context)

    await query.edit_message_text("⏳ Processing comment...")

    try:
        media_id = cl.media_pk_from_url(temp_data[user_id]['vid_url'])
        comment = cl.media_comment(media_id, temp_data[user_id]['text'])

        if query.data == 'do_pin':
            # Use direct POST for pinning
            cl.private_request(f"media/{media_id}/pin_comment/{comment.pk}/", data={'_uuid': cl.uuid})
            await query.edit_message_text("✅ Comment posted and pinned successfully!")
        else:
            await query.edit_message_text("✅ Comment posted successfully!")

    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")
        
    return await start(update, context)

# --- PIN LATEST COMMENT LOGIC ---
async def ask_pin_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("🔗 Send the Link of the Reel to pin its latest comment:")
    return ASKING_PIN_ONLY_LINK

async def process_pin_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reel_url = update.message.text.strip()
    cl = user_sessions.get(user_id, {}).get("cl")
    
    if not cl:
        await update.message.reply_text("❌ Login first!")
        return await start(update, context)

    status_msg = await update.message.reply_text("⏳ Fetching latest comment...")
    
    try:
        media_id = cl.media_pk_from_url(reel_url)
        comments = cl.media_comments(media_id, amount=1)
        
        if not comments:
            await status_msg.edit_text("❌ No comments found.")
            return await start(update, context)
        
        latest_comment = comments[0]
        cl.private_request(f"media/{media_id}/pin_comment/{latest_comment.pk}/", data={'_uuid': cl.uuid})
        await status_msg.edit_text(f"✅ **Pinned!**\n\"{latest_comment.text}\"")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
        
    return await start(update, context)

def main():
    TOKEN = "8647682398:AAEPcrlLe4bm0d4rP4bqBw-uLmJMlmV71TM"
    
    request = HTTPXRequest(connect_timeout=40, read_timeout=40)
    app = Application.builder().token(TOKEN).request(request).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [
                CallbackQueryHandler(ask_reel, pattern='^upload_reel$'),
                CallbackQueryHandler(ask_comment_link, pattern='^post_comment$'),
                CallbackQueryHandler(ask_pin_link, pattern='^pin_latest$'),
                CallbackQueryHandler(manage_session, pattern='^manage_session$'),
            ],
            ASKING_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_session)],
            ASKING_REEL: [MessageHandler(filters.VIDEO, get_reel)],
            ASKING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_upload_step)],
            CONFIRM_UPLOAD: [CallbackQueryHandler(final_upload, pattern='^final_upload$')],
            ASKING_COMMENT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment_text)],
            ASKING_COMMENT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_comment_step)],
            CONFIRM_COMMENT: [
                CallbackQueryHandler(final_comment, pattern='^do_comment$'),
                CallbackQueryHandler(final_comment, pattern='^do_pin$'),
            ],
            ASKING_PIN_ONLY_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pin_latest)],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    app.add_handler(conv_handler)
    print("Bot is live...")
    app.run_polling()

if __name__ == '__main__':
    main()
