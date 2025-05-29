import os
import sys
import logging
import sqlite3
import random
import asyncio
import pytz
from datetime import datetime, timedelta
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, InputMediaVideo, ChatMember

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
TOKEN = "7846852905:AAHaT-_OQGvEL5ciUBEsYtTCYbMwHYXHppo"

# Admin credentials
ADMIN_USERNAME = "@unknownleaksbotsupport"
ADMIN_ID = 6644007366
ADMIN_PASSWORD = "Orkutcomsingh@1"
CHANNEL_USERNAME = "@unknownleaksbotupdates"
CHANNEL_ID = "@unknownleaksbotupdates"  # Channel ID for checking membership

# Indian timezone
INDIAN_TZ = pytz.timezone('Asia/Kolkata')

def get_indian_time():
    """Get current time in Indian timezone"""
    return datetime.now(INDIAN_TZ)

def get_indian_greeting():
    """Get appropriate greeting based on Indian time"""
    current_hour = get_indian_time().hour
    if 5 <= current_hour < 12:
        return "Good morning"
    elif 12 <= current_hour < 17:
        return "Good afternoon"
    elif 17 <= current_hour < 21:
        return "Good evening"
    else:
        return "Good night"

# States for conversation handlers
(TERMS_ACCEPT, NAME, AGE, USERNAME, ADMIN_AUTH, ADMIN_MENU, ADD_PHOTO, ADD_VIDEO, 
 PHOTO_CAPTION, VIDEO_CAPTION, PHOTO_PRICE, VIDEO_PRICE, SETTINGS_MENU,
 EDIT_NAME, EDIT_AGE, EDIT_USERNAME, NOTIFICATION_SETTINGS, ADD_STARS, REMOVE_STARS,
 BAN_USER, WARN_USER, ADMIN_BROADCAST, ADMIN_DELETE_MEDIA) = range(23)

# Initialize database
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Create users table with enhanced fields
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        age INTEGER,
        username TEXT UNIQUE,
        stars REAL DEFAULT 10,
        registration_date TEXT,
        last_login TEXT,
        notification_enabled INTEGER DEFAULT 1,
        terms_accepted INTEGER DEFAULT 0, 
        is_banned INTEGER DEFAULT 0,
        warnings INTEGER DEFAULT 0,
        ban_reason TEXT DEFAULT NULL
    )
    ''')

    # Create media table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        file_id TEXT,
        caption TEXT,
        price REAL,
        added_date TEXT,
        added_by INTEGER
    )
    ''')

    # Create bookmarks table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bookmarks (
        user_id INTEGER,
        media_id INTEGER,
        bookmark_date TEXT,
        PRIMARY KEY (user_id, media_id)
    )
    ''')

    # Create daily login table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_logins (
        user_id INTEGER,
        login_date TEXT,
        PRIMARY KEY (user_id, login_date)
    )
    ''')

    # Create transactions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        description TEXT,
        transaction_date TEXT
    )
    ''')

    # Create user activity log
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        activity_type TEXT,
        details TEXT,
        activity_date TEXT
    )
    ''')

    # Create table to track viewed media from channels
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS viewed_channel_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message_id INTEGER,
        channel_id TEXT,
        media_type TEXT,
        view_date TEXT,
        UNIQUE(user_id, message_id, channel_id)
    )
    ''')

    # Create table to track which videos have been sent to each user
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sent_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        media_id INTEGER,
        sent_date TEXT,
        UNIQUE(user_id, media_id)
    )
    ''')

    # Create table to store channel media cache
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channel_media_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT,
        message_id INTEGER,
        media_type TEXT,
        added_date TEXT,
        UNIQUE(channel_id, message_id)
    )
    ''')

    # Create table for anti-spam button tracking
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS button_cooldowns (
        user_id INTEGER,
        button_type TEXT,
        last_pressed TEXT,
        PRIMARY KEY (user_id, button_type)
    )
    ''')

    # Create table for blocked users from admin panel
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_blocked_users (
        user_id INTEGER PRIMARY KEY,
        blocked_by INTEGER,
        block_reason TEXT,
        block_date TEXT
    )
    ''')

    # Ensure all existing tables have the required columns
    # This is safer than dropping and recreating tables

    # Check if notification_enabled column exists in users table
    try:
        cursor.execute("SELECT notification_enabled FROM users LIMIT 1")
    except sqlite3.OperationalError:
        # Add the column if it doesn't exist
        cursor.execute("ALTER TABLE users ADD COLUMN notification_enabled INTEGER DEFAULT 1")

    # Check for other new columns in users table
    try:
        cursor.execute("SELECT is_banned FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")

    try:
        cursor.execute("SELECT warnings FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN warnings INTEGER DEFAULT 0")

    try:
        cursor.execute("SELECT ban_reason FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT DEFAULT NULL")

    try:
        cursor.execute("SELECT terms_accepted FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN terms_accepted INTEGER DEFAULT 0")

    conn.commit()
    conn.close()

# Channel membership check
async def check_channel_membership(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if user is a member of the required channel"""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception as e:
        logger.error(f"Error checking channel membership for user {user_id}: {e}")
        return False

async def force_channel_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Force user to join channel before proceeding"""
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "User"

    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
        [InlineKeyboardButton("✅ I Joined", callback_data="check_membership")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        f"🔒 *CHANNEL MEMBERSHIP REQUIRED* 🔒\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Hello, *{first_name}*!\n\n"
        f"To use this bot, you must join our official updates channel:\n"
        f"{CHANNEL_USERNAME}\n\n"
        f"📍 *Why join?*\n"
        f"• Get latest updates and announcements\n"
        f"• Be the first to know about new features\n"
        f"• Receive important notifications\n\n"
        f"👆 Click 'Join Channel' above, then click 'I Joined' to continue."
    )

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    return TERMS_ACCEPT

# User registration with improved UI
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    first_name = update.effective_user.first_name or "User"

    # Check if this is a referral
    if update.message.text and ' ' in update.message.text:
        parts = update.message.text.split()
        if len(parts) > 1 and parts[1].startswith('ref_'):
            try:
                referrer_id = int(parts[1].replace('ref_', ''))
                # Store the referrer ID in context for later use during registration
                context.user_data['referrer_id'] = referrer_id
                logger.info(f"Referral detected: {referrer_id} referred {user_id}")

                # Add a welcoming referral message
                await update.message.reply_text(
                    f"👋 *Welcome, {first_name}!*\n\n"
                    f"You've been invited by a friend to join Unknown Leaks.\n"
                    f"You'll receive bonus stars when you complete registration!",
                    parse_mode='Markdown'
                )
            except ValueError:
                logger.error(f"Invalid referral format: {parts[1]}")

    # Check if user already exists
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    # Check if user is banned
    if user and user[9] == 1:  # is_banned column
        ban_reason = user[11] or "No reason provided"
        conn.close()
        await update.message.reply_text(
            f"🚫 *YOU ARE BLOCKED FROM THE BOT* 🚫\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Your access to this bot has been blocked.\n\n"
            f"*REASON:*\n{ban_reason}\n\n"
            f"If you believe this is an error, please contact our support team:\n{ADMIN_USERNAME}",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    conn.close()

    if user:
        # Check channel membership for existing users
        if not await check_channel_membership(context, user_id):
            return await force_channel_join(update, context)

        # Update last login and give daily stars if new day
        await update_login_and_give_stars(user_id)

        # Welcome back message for returning users
        await update.message.reply_text(
            f"✨ *WELCOME BACK* ✨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Great to see you again! Loading your personalized experience...",
            parse_mode='Markdown'
        )

        await show_home_menu(update, context)
        return ConversationHandler.END

    # For new users, force channel join first
    return await force_channel_join(update, context)

async def handle_terms_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_first_name = update.effective_user.first_name or "User"

    if query.data == "check_membership":
        # Always proceed to terms when user clicks "I Joined" - no actual membership check
        keyboard = [
            [InlineKeyboardButton("✅ I ACCEPT", callback_data="accept_terms")],
            [InlineKeyboardButton("❌ DECLINE", callback_data="decline_terms")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Current date for a professional feel
        current_date = get_indian_time().strftime('%d %b %Y')

        # Enhanced professional formatting with elegant design
        await query.message.edit_text(
            f"✨ *WELCOME TO UNKNOWN LEAKS* ✨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Hello, *{user_first_name}*!\n"
            f"We're delighted to have you join our exclusive community.\n\n"
            f"📜 *TERMS OF SERVICE*\n"
            f"Date: {current_date}\n\n"
            f"Please review our membership terms:\n\n"
            f"• Age verification (18+ years required)\n"
            f"• Personal responsibility for account usage\n"
            f"• Content for entertainment purposes only\n"
            f"• Non-refundable purchase policy\n"
            f"• Data security & encryption protocols\n"
            f"• Secure transaction processing\n\n"
            f"By selecting \"I ACCEPT\" below, you confirm that you have read, understood, and agree to abide by our complete terms and privacy policy.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return TERMS_ACCEPT

    if query.data == "decline_terms":
        await query.message.edit_text(
            "❌ *REGISTRATION CANCELLED* ❌\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Hello {user_first_name},\n\n"
            "You have declined our terms and conditions.\n\n"
            "For security and compliance reasons, access to our premium content requires acceptance of our terms.\n\n"
            "Should you change your mind, simply use /start to begin the registration process again.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # User accepted terms - automatically create account and redirect to home
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    today = get_indian_time().strftime('%Y-%m-%d')

    # Save user data automatically
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (user_id, name, age, username, registration_date, last_login, terms_accepted) VALUES (?, ?, ?, ?, ?, ?, 1)",
        (user_id, user_first_name, 18, username, today, today)
    )

    # Record the first login
    cursor.execute(
        "INSERT INTO daily_logins (user_id, login_date) VALUES (?, ?)",
        (user_id, today)
    )

    # Log this activity
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "REGISTRATION", f"User registered automatically", today)
    )

    # Record the welcome bonus transaction
    cursor.execute(
        "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
        (user_id, 10, "Welcome bonus", today)
    )

    # Check if this user was referred by someone
    if 'referrer_id' in context.user_data:
        referrer_id = context.user_data['referrer_id']

        # Make sure referrer exists and is not the same as new user
        if referrer_id != user_id:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (referrer_id,))
            referrer = cursor.fetchone()

            if referrer:
                # Give the referrer 5 stars
                cursor.execute("UPDATE users SET stars = stars + 5 WHERE user_id = ?", (referrer_id,))

                # Give the new user 2 extra stars (on top of welcome bonus)
                cursor.execute("UPDATE users SET stars = stars + 2 WHERE user_id = ?", (user_id,))

                # Record transactions for both users
                cursor.execute(
                    "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
                    (referrer_id, 5, f"Referral reward for user {user_id}", today)
                )

                cursor.execute(
                    "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
                    (user_id, 2, "Referred user bonus", today)
                )

                # Try to notify the referrer
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 *REFERRAL BONUS* 🎉\n\n"
                             f"Someone joined using your referral link!\n\n"
                             f"*Bonus:* +5 ⭐ added to your account\n\n"
                             f"Keep sharing your link to earn more stars!",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to send referral notification to user {referrer_id}: {e}")

    conn.commit()
    conn.close()

    # Show welcome message and redirect to home
    await query.message.edit_text(
        f"🎉 *WELCOME TO UNKNOWN LEAKS* 🎉\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Welcome, *{user_first_name}*!\n\n"
        f"✅ *ACCOUNT CREATED SUCCESSFULLY*\n"
        f"• Username: *@{username}*\n"
        f"• Registration Date: *{today}*\n\n"
        f"🎁 *WELCOME BONUS*\n"
        f"• You've received *10 ⭐ stars* to start exploring!\n\n"
        f"💰 *STAR VALUE GUIDE*\n"
        f"• Videos: 1 ⭐ each\n"
        f"• Photos: 0.5 ⭐ each\n\n"
        f"📱 *DAILY REWARDS*\n"
        f"• Log in daily to receive *5 ⭐ bonus stars*\n\n"
        f"Let's get started!",
        parse_mode='Markdown'
    )

    # Redirect to home menu
    await show_home_menu(update, context)
    return ConversationHandler.END

async def process_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chosen_name = update.message.text.strip()

    # Basic validation
    if len(chosen_name) < 2:
        await update.message.reply_text(
            "⚠️ *NAME TOO SHORT* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Your display name must be at least 2 characters long.\n\n"
            "Please enter a valid display name:",
            parse_mode='Markdown'
        )
        return NAME

    if len(chosen_name) > 25:
        chosen_name = chosen_name[:25]  # Truncate if too long

    context.user_data['name'] = chosen_name

    await update.message.reply_text(
        "✨ *ACCOUNT CREATION* ✨\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Nice to meet you, *{chosen_name}*!\n\n"
        "🔹 *STEP 2 OF 3: AGE VERIFICATION*\n\n"
        "For legal and compliance purposes, we need to verify your age.\n\n"
        "📝 *Please enter your age in years:*\n"
        "_(You must be at least 18 years old to access our content)_",
        parse_mode='Markdown'
    )
    return AGE

async def process_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        age_text = update.message.text.strip()
        age = int(age_text)

        if age < 18:
            await update.message.reply_text(
                "⚠️ *AGE RESTRICTION* ⚠️\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "We're sorry, but you must be at least 18 years old to access our content.\n\n"
                "This verification is required by law and for your protection.\n\n"
                "Please enter a valid age if you're 18 or older:",
                parse_mode='Markdown'
            )
            return AGE

        if age > 120:
            await update.message.reply_text(
                "⚠️ *INVALID AGE* ⚠️\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter a realistic age value (18-120):",
                parse_mode='Markdown'
            )
            return AGE

        context.user_data['age'] = age

        await update.message.reply_text(
            "✨ *ACCOUNT CREATION* ✨\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔹 *STEP 3 OF 3: USERNAME SELECTION*\n\n"
            f"Thanks for confirming your information:\n"
            f"• *Name:* {context.user_data['name']}\n"
            f"• *Age:* {age} years\n\n"
            "Finally, please create a unique username that you'll use to identify yourself in our community.\n\n"
            "📝 *Create your username:*\n"
            "• Minimum 5 characters\n"
            "• Cannot be already in use\n"
            "• Avoid personal information",
            parse_mode='Markdown'
        )
        return USERNAME

    except ValueError:
        await update.message.reply_text(
            "⚠️ *INVALID ENTRY* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter your age as a number only.\n"
            "Example: 25",
            parse_mode='Markdown'
        )
        return AGE

async def process_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = update.message.text

    if len(username) < 5:
        await update.message.reply_text(
            "⚠️ *USERNAME TOO SHORT* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "For security reasons, your username must be at least 5 characters long.\n\n"
            "Please choose a longer username:",
            parse_mode='Markdown'
        )
        return USERNAME

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Check if username exists
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        await update.message.reply_text(
            "⚠️ *USERNAME UNAVAILABLE* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "This username is already taken by another member.\n\n"
            "Please choose a different username:",
            parse_mode='Markdown'
        )
        return USERNAME

    # Save user data
    user_id = update.effective_user.id
    name = context.user_data['name']
    age = context.user_data['age']
    today = datetime.now().strftime('%Y-%m-%d')

    cursor.execute(
        "INSERT INTO users (user_id, name, age, username, registration_date, last_login, terms_accepted) VALUES (?, ?, ?, ?, ?, ?, 1)",
        (user_id, name, age, username, today, today)
    )

    # Record the first login
    cursor.execute(
        "INSERT INTO daily_logins (user_id, login_date) VALUES (?, ?)",
        (user_id, today)
    )

    # Log this activity
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "REGISTRATION", f"User registered with username: {username}", today)
    )

    # Record the welcome bonus transaction
    cursor.execute(
        "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
        (user_id, 10, "Welcome bonus", today)
    )

    # Check if this user was referred by someone
    if 'referrer_id' in context.user_data:
        referrer_id = context.user_data['referrer_id']

        # Make sure referrer exists and is not the same as new user
        if referrer_id != user_id:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (referrer_id,))
            referrer = cursor.fetchone()

            if referrer:
                # Give the referrer 5 stars
                cursor.execute("UPDATE users SET stars = stars + 5 WHERE user_id = ?", (referrer_id,))

                # Give the new user 2 extra stars (on top of welcome bonus)
                cursor.execute("UPDATE users SET stars = stars + 2 WHERE user_id = ?", (user_id,))

                # Record transactions for both users
                cursor.execute(
                    "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
                    (referrer_id, 5, f"Referral reward for user {user_id}", today)
                )

                cursor.execute(
                    "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
                    (user_id, 2, "Referred user bonus", today)
                )

                # Log the referral
                cursor.execute(
                    "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                    (referrer_id, "REFERRAL", f"Referred new user: {user_id}", today)
                )

                # Try to notify the referrer
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 *REFERRAL BONUS* 🎉\n\n"
                             f"Someone joined using your referral link!\n\n"
                             f"*Bonus:* +5 ⭐ added to your account\n\n"
                             f"Keep sharing your link to earn more stars!",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to send referral notification to user {referrer_id}: {e}")

    conn.commit()
    conn.close()

    # Show an enhanced professional success message
    await update.message.reply_text(
        "🎉 *REGISTRATION SUCCESSFUL* 🎉\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Welcome to Unknown Leaks, *{name}*!\n\n"
        "✅ *ACCOUNT CREATED*\n"
        f"• Username: *@{username}*\n"
        f"• Account created: *{today}*\n\n"
        "🎁 *WELCOME BONUS*\n"
        "• You've received *10 ⭐ stars* to start exploring our premium content!\n\n"
        "💰 *STAR VALUE GUIDE*\n"
        "• 1 ⭐ = 2 rupees\n"
        "• Videos: 1 ⭐ each\n"
        "• Photos: 0.5 ⭐ each\n\n"
        "📱 *DAILY REWARDS PROGRAM*\n"
        "• Log in daily to receive *5 ⭐ bonus stars*\n"
        "• Refer friends to earn even more rewards",
        parse_mode='Markdown'
    )

    # Add a slight delay for better UX
    await show_home_menu(update, context)
    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    await query.message.edit_text(
        "❌ *Registration Cancelled* ❌\n\n"
        "You have cancelled the registration process.\n"
        "Use /start to begin again whenever you're ready.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def update_login_and_give_stars(user_id):
    today = get_indian_time().strftime('%Y-%m-%d')

    conn = sqlite3.connect('bot_database.db', timeout=30)
    cursor = conn.cursor()

    # Update last login
    cursor.execute("UPDATE users SET last_login = ? WHERE user_id = ?", (today, user_id))

    # Check if already logged in today
    cursor.execute("SELECT * FROM daily_logins WHERE user_id = ? AND login_date = ?", (user_id, today))
    already_logged = cursor.fetchone()

    if not already_logged:
        # Give daily stars and record login
        cursor.execute("UPDATE users SET stars = stars + 5 WHERE user_id = ?", (user_id,))
        cursor.execute("INSERT OR IGNORE INTO daily_logins (user_id, login_date) VALUES (?, ?)", (user_id, today))

        # Record the transaction
        cursor.execute(
            "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
            (user_id, 5, "Daily login bonus", today)
        )

        # Log the activity
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "LOGIN", "User received daily login bonus", today)
        )

        conn.commit()
        logger.info(f"Daily login bonus of 5 stars added to user {user_id}")
        conn.close()
        return True  # Return True if bonus was given
    else:
        logger.info(f"User {user_id} already received daily login bonus today")
        conn.close()
        return False  # Return False if no bonus given

# Modern Home menu with inline keyboards
async def show_home_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check channel membership before showing home
    if not await check_channel_membership(context, user_id):
        # User left the channel, ban them from the bot
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?",
            ("Left required channel", user_id)
        )
        conn.commit()
        conn.close()

        keyboard = [
            [InlineKeyboardButton("📢 Rejoin Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
            [InlineKeyboardButton("✅ I Rejoined", callback_data="check_rejoin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = (
            f"⚠️ *CHANNEL MEMBERSHIP LOST* ⚠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"You have left our required updates channel!\n\n"
            f"🚫 *Your bot access has been suspended.*\n\n"
            f"To restore access:\n"
            f"1. Rejoin our channel: {CHANNEL_USERNAME}\n"
            f"2. Click 'I Rejoined' below\n\n"
            f"If you don't rejoin, you will be permanently banned from using this bot."
        )

        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.edit_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        return

    # Update login and check for daily bonus
    bonus_given = await update_login_and_give_stars(user_id)

    # Get user info for personalized message
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, stars, last_login FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    conn.close()

    name = user_info[0] if user_info else "User"
    stars = user_info[1] if user_info else 0
    last_login = user_info[2] if user_info and len(user_info) > 2 else None

    # Create keyboard buttons in the chat input area with improved layout
    keyboard = [
        [KeyboardButton("🎬 Videos")],
        [KeyboardButton("👤 My Profile"), KeyboardButton("💰 Buy Stars")],
        [KeyboardButton("🔖 Bookmarks"), KeyboardButton("🔄 Refer & Earn")],
        [KeyboardButton("ℹ️ Help"), KeyboardButton("📢 Support & Channel")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Format the welcome message with Indian time and greeting
    indian_time = get_indian_time()
    current_time = indian_time.strftime('%H:%M')
    current_date = indian_time.strftime('%d %b %Y')
    greeting = get_indian_greeting()

    # Show daily bonus notification if given
    daily_bonus_text = ""
    if bonus_given:
        daily_bonus_text = "\n🎉 *+5 ⭐ Daily Login Bonus Added!*\n"

    welcome_text = (
        f"✨ *UNKNOWN LEAKS* ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{greeting}, *{name}*!\n"
        f"📅 {current_date} | ⏰ {current_time} (IST){daily_bonus_text}\n\n"
        f"💼 *WALLET STATUS*\n"
        f"• Balance: *{stars} ⭐*\n"
        f"• Value: *{stars * 2} ₹*\n\n"
        f"🔥 *DAILY REWARD*\n"
        f"• Login daily: +5 ⭐\n\n"
        f"Select an option below to explore premium content."
    )

    # Use edit_message_text if it's a callback query
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(
            welcome_text,
            parse_mode='Markdown'
        )
        await update.callback_query.message.reply_text(
            "Use the keyboard to navigate:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# Media browsing functions
async def get_random_media(media_type):
    """Get random media from database"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get all media of the specified type
    cursor.execute("SELECT * FROM media WHERE type = ? ORDER BY RANDOM() LIMIT 1", (media_type,))
    media_item = cursor.fetchone()

    conn.close()
    return media_item

async def get_all_media(media_type=None, limit=50):
    """Get all media from database, optionally filtered by type"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    if media_type:
        cursor.execute("SELECT * FROM media WHERE type = ? ORDER BY id DESC LIMIT ?", (media_type, limit))
    else:
        cursor.execute("SELECT * FROM media ORDER BY id DESC LIMIT ?", (limit,))

    media_items = cursor.fetchall()
    conn.close()
    return media_items

async def show_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = query.from_user.id if query else update.effective_user.id

    # Anti-spam check for video button
    if not await check_button_cooldown(user_id, "videos_button", 2):
        message = "⏳ *Please wait* ⏳\n\nDon't spam! You can access videos every 2 seconds."
        if query:
            await query.answer("Don't spam! Please wait.", show_alert=True)
            return
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
            return

    # Get user stars and check if banned
    conn = sqlite3.connect('bot_database.db', timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT stars, is_banned FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        message = "You need to register first. Please use /start"
        if query:
            await query.answer("Not registered!")
            await query.message.edit_text(message)
        else:
            await update.message.reply_text(message)
        conn.close()
        return

    user_stars, is_banned = user[0], user[1]

    if is_banned:
        message = "🚫 *YOU ARE BLOCKED FROM THE BOT* 🚫\n\nYour access has been blocked. Contact support for assistance."
        if query:
            await query.answer("You are blocked from the bot!")
            await query.message.edit_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        conn.close()
        return

    # Get videos that haven't been sent to this user, shuffled
    cursor.execute("""
        SELECT * FROM media 
        WHERE type = 'video' 
        AND id NOT IN (SELECT media_id FROM sent_videos WHERE user_id = ?)
        ORDER BY RANDOM()
    """, (user_id,))
    unsent_videos = cursor.fetchall()

    if not unsent_videos:
        # Check if user has seen all videos
        cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
        total_videos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sent_videos WHERE user_id = ?", (user_id,))
        sent_count = cursor.fetchone()[0]

        if total_videos > 0 and sent_count >= total_videos:
            # User has seen all videos, reset and start fresh
            cursor.execute("DELETE FROM sent_videos WHERE user_id = ?", (user_id,))
            conn.commit()

            # Get fresh shuffled videos
            cursor.execute("SELECT * FROM media WHERE type = 'video' ORDER BY RANDOM()")
            unsent_videos = cursor.fetchall()

            if query:
                await query.answer("🔄 Starting fresh! All videos reset.")
            else:
                await update.message.reply_text(
                    "🔄 *Fresh Start!*\n\nYou've seen all our videos! Starting over with a new shuffled order.",
                    parse_mode='Markdown'
                )
        else:
            # Add default placeholder videos if none exist
            today = datetime.now().strftime('%Y-%m-%d')
            placeholder_video_id = "BAACAgUAAxkBAAELGDBlzw-UO_05NQE3BNskZnNlEVvGFwACGggAAnUAAYNi9YHCW_6Uc1UwBA"

            sample_videos = [
                ('video', placeholder_video_id, 'Premium video content #1', 1.0, today, 0),
                ('video', placeholder_video_id, 'Premium video content #2', 1.0, today, 0),
                ('video', placeholder_video_id, 'Premium video content #3', 1.0, today, 0)
            ]

            # Insert sample videos
            for video in sample_videos:
                cursor.execute(
                    "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                    video
                )
            conn.commit()

            # Get the newly added videos
            cursor.execute("SELECT * FROM media WHERE type = 'video' ORDER BY RANDOM()")
            unsent_videos = cursor.fetchall()

    if not unsent_videos:
        await update.message.reply_text(
            "📹 *No Videos Available*\n\n"
            "There are currently no videos in the database. Please contact the admin.",
            parse_mode='Markdown'
        )
        conn.close()
        return

    # Store unsent videos in context for navigation
    context.user_data['videos'] = unsent_videos
    context.user_data['current_video_index'] = 0
    context.user_data['current_media_type'] = "video"

    conn.close()

    # Show first video
    await send_media_with_navigation(update, context, "video")

async def show_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = query.from_user.id if query else update.effective_user.id

    # Get user stars and check if banned
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT stars, is_banned FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        message = "You need to register first. Please use /start"
        if query:
            await query.answer("Not registered!")
            await query.message.edit_text(message)
        else:
            await update.message.reply_text(message)
        return

    user_stars, is_banned = user[0], user[1]

    if is_banned:
        message = "🚫 *YOU ARE BLOCKED FROM THE BOT* 🚫\n\nYour access has been blocked. Contact support for assistance."
        if query:
            await query.answer("You are blocked from the bot!")
            await query.message.edit_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        return

    # Show loading message
    loading_message = None
    if query:
        await query.answer("Loading photos...")
    else:
        loading_message = await update.message.reply_text(
            "📡 *LOADING CONTENT*\n"
            "Please wait while we fetch the latest photos...",
            parse_mode='Markdown'
        )

    # Get photos from database
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get all photos first and store in context for navigation
    cursor.execute("SELECT * FROM media WHERE type = 'photo' ORDER BY id DESC")
    all_photos = cursor.fetchall()

    if all_photos:
        context.user_data['photos'] = all_photos
        context.user_data['current_photo_index'] = 0
        random_photo = all_photos[0]  # Use the first one to start
    else:
        # Add default placeholder photos if none exist
        today = datetime.now().strftime('%Y-%m-%d')
        placeholder_photo_id = "AgACAgUAAxkBAAIV4Wgi4vmOqV5HttPyKzMNtqHJmh9tAAJuwzEbjF4ZVWgFQWaIwlJwAQADAgADeQADNgQ"

        sample_photos = [
            ('photo', placeholder_photo_id, 'Premium photo content #1', 0.5, today, 0),
            ('photo', placeholder_photo_id, 'Premium photo content #2', 0.5, today, 0),
            ('photo', placeholder_photo_id, 'Premium photo content #3', 0.5, today, 0)
        ]

        # Insert sample photos
        for photo in sample_photos:
            cursor.execute(
                "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                photo
            )
        conn.commit()

        # Retrieve all photos again
        cursor.execute("SELECT * FROM media WHERE type = 'photo' ORDER BY id DESC")
        all_photos = cursor.fetchall()

        if all_photos:
            context.user_data['photos'] = all_photos
            context.user_data['current_photo_index'] = 0
            random_photo = all_photos[0]
        else:
            random_photo = None

    if not random_photo:
        if loading_message:
            try:
                await loading_message.delete()
            except Exception:
                pass

        await update.message.reply_text(
            "📷 *No Photos Available*\n\n"
            "There are currently no photos in the database. Please contact the admin.",
            parse_mode='Markdown'
        )
        conn.close()
        return

    # Extract photo information
    media_id = random_photo[0]
    media_type = random_photo[1]
    file_id = random_photo[2]
    caption = random_photo[3]
    price = random_photo[4]

    # Record that user viewed this photo
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "INSERT OR IGNORE INTO viewed_channel_media (user_id, message_id, channel_id, media_type, view_date) VALUES (?, ?, ?, ?, ?)",
        (user_id, media_id, "direct", "photo", today)
    )
    conn.commit()

    # Get user stars for display
    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
    user_result = cursor.fetchone()
    user_stars = user_result[0] if user_result else 0
    conn.close()

    # Store current media info in context for navigation
    context.user_data['current_media_id'] = media_id
    context.user_data['current_media_type'] = "photo"

    # Send the photo directly since we have its file_id
    try:
        if loading_message:
            try:
                await loading_message.delete()
            except Exception:
                pass

        # Create a fancy caption
        photo_caption = (
            f"📷 *PREMIUM PHOTO* 📷\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*ID:* #{media_id}\n\n"
            f"*DESCRIPTION:*\n{caption}\n\n"
            f"💰 *PRICE:* {price} ⭐\n"
            f"💳 *YOUR BALANCE:* {user_stars} ⭐\n\n"
            f"Use the buttons below to navigate or purchase this photo."
        )

        # Loading message
        await context.bot.send_message(
            chat_id=user_id,
            text="📡 *Loading Photo Preview*...",
            parse_mode='Markdown'
        )

        # Define a placeholder photo to use if original fails
        placeholder_photo_id = "AgACAgUAAxkBAAIV4Wgi4vmOqV5HttPyKzMNtqHJmh9tAAJuwzEbjF4ZVWgFQWaIwlJwAQADAgADeQADNgQ"

        # Try sending the photo
        try:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=file_id,
                caption=photo_caption,
                parse_mode='Markdown',
                protect_content=True
            )
        except Exception as send_error:
            logger.error(f"Error sending with file_id: {send_error}")

            # If failed, use placeholder
            logger.info(f"Using placeholder photo as fallback")

            # Update database with working placeholder
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE media SET file_id = ? WHERE id = ?", (placeholder_photo_id, media_id))
            conn.commit()
            conn.close()

            # Send with placeholder
            try:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=placeholder_photo_id,
                    caption=photo_caption,
                    parse_mode='Markdown',
                    protect_content=True
                )
            except Exception as placeholder_error:
                logger.error(f"Error sending placeholder photo: {placeholder_error}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"{photo_caption}\n\n⚠️ *Photo preview unavailable*\n\nTry viewing other photos or contact support if this persists.",
                    parse_mode='Markdown'
                )

        # Send navigation buttons
        keyboard = [
            [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
            [KeyboardButton("👍 Like"), KeyboardButton("👎 Dislike")],
            [KeyboardButton("💾 Download"), KeyboardButton("🔖 Bookmark")],
            [KeyboardButton("🏠 Home")]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await context.bot.send_message(
            chat_id=user_id,
            text="Use the buttons below to navigate through photos",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error in photo delivery process: {e}")
        # Final fallback error message
        if query:
            await query.message.edit_text(
                "⚠️ *ERROR LOADING PHOTO*\n\n"
                "There was a problem loading the photo. Please try again later.\n\nError: " + str(e)[:100],
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "⚠️ *ERROR LOADING PHOTO*\n\n"
                "There was a problem loading the photo. Please try again later.\n\nError: " + str(e)[:100],
                parse_mode='Markdown'
            )

async def send_media_with_navigation(update, context: ContextTypes.DEFAULT_TYPE, media_type):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = query.from_user.id if query else update.effective_user.id

    if media_type == "video":
        media_list = context.user_data.get('videos', [])
        current_index = context.user_data.get('current_video_index', 0)
    else:
        media_list = context.user_data.get('photos', [])
        current_index = context.user_data.get('current_photo_index', 0)

    if not media_list or current_index >= len(media_list):
        # If user has reached the end, fetch new unsent videos
        if media_type == "video":
            conn = sqlite3.connect('bot_database.db', timeout=30)
            cursor = conn.cursor()

            # Get more unsent videos
            cursor.execute("""
                SELECT * FROM media 
                WHERE type = 'video' 
                AND id NOT IN (SELECT media_id FROM sent_videos WHERE user_id = ?)
                ORDER BY RANDOM()
            """, (user_id,))
            new_videos = cursor.fetchall()

            if new_videos:
                context.user_data['videos'] = new_videos
                context.user_data['current_video_index'] = 0
                conn.close()
                return await send_media_with_navigation(update, context, media_type)

            conn.close()

        message = f"📭 *No more {media_type}s available*\n\nCheck back later for new content."
        keyboard = [[KeyboardButton("🏠 Home")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        if query:
            await query.message.edit_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        return

    media = media_list[current_index]

    # Mark this video as sent to this user
    if media_type == "video":
        media_id = media[0]
        today = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect('bot_database.db', timeout=30)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT OR IGNORE INTO sent_videos (user_id, media_id, sent_date) VALUES (?, ?, ?)",
                (user_id, media_id, today)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error tracking sent video: {e}")
        finally:
            conn.close()

    # Adjust for potential changes in db schema
    if len(media) >= 7:  # New schema with added_date and added_by
        media_id, media_type, file_id, caption, price, added_date = media[0], media[1], media[2], media[3], media[4], media[5]
    else:
        media_id, media_type, file_id, caption, price = media
        added_date = "Unknown"

    # Format date if available
    try:
        if added_date and added_date != "Unknown":
            formatted_date = datetime.strptime(added_date, '%Y-%m-%d').strftime('%d %b %Y')
        else:
            formatted_date = "Unknown"
    except:
        formatted_date = added_date

    # Get user stars
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    user_stars = user[0] if user else 0

    # Check if media is bookmarked
    cursor.execute("SELECT * FROM bookmarks WHERE user_id = ? AND media_id = ?", (user_id, media_id))
    is_bookmarked = cursor.fetchone() is not None

    # Check if user has purchased this media
    cursor.execute(
        "SELECT * FROM transactions WHERE user_id = ? AND description LIKE ? AND amount < 0", 
        (user_id, f"Downloaded %{media_id}%")
    )
    is_purchased = cursor.fetchone() is not None

    # Get real like/dislike counts from a new table we'll create if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media_ratings (
        media_id INTEGER,
        user_id INTEGER,
        rating TEXT, -- 'like' or 'dislike'
        rating_date TEXT,
        PRIMARY KEY (media_id, user_id)
    )
    ''')

    # Count likes
    cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'like'", (media_id,))
    likes = cursor.fetchone()[0] or 0

    # Count dislikes
    cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'dislike'", (media_id,))
    dislikes = cursor.fetchone()[0] or 0

    # Calculate percentage
    total_ratings = likes + dislikes
    like_percentage = (likes / total_ratings * 100) if total_ratings > 0 else 0
    dislike_percentage = (dislikes / total_ratings * 100) if total_ratings > 0 else 0

    # Check if user has already rated this media
    cursor.execute("SELECT rating FROM media_ratings WHERE media_id = ? AND user_id = ?", (media_id, user_id))
    user_rating = cursor.fetchone()
    user_rating = user_rating[0] if user_rating else None

    # Check if user has enough stars to purchase
    can_purchase = user_stars >= price

    conn.close()

    # Build a professional-looking caption with enhanced layout and organization
    media_icon = "🎬" if media_type == "video" else "📸"

    full_caption = (
        f"{media_icon} *PREMIUM {media_type.upper()}* {media_icon}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*ID:* #{media_id} • *Added:* {formatted_date}\n\n"
        f"💰 *PURCHASE INFO*\n"
        f"• Price: {price} ⭐\n"
        f"• Your Balance: {user_stars} ⭐ {('✅ Sufficient' if can_purchase else '❌ Insufficient')}\n\n"
        f"📊 *COMMUNITY RATINGS*\n"
        f"• 👍 {round(like_percentage)}% Positive • 👎 {round(dislike_percentage)}% Negative"
        f"{' • You rated: ' + ('👍' if user_rating == 'like' else '👎') if user_rating else ''}\n\n"
        f"📁 *NAVIGATION*\n"
        f"• Status: {'📖 Bookmarked' if is_bookmarked else '📋 Not bookmarked'}\n"
        f"• Purchase: {'✅ Purchased' if is_purchased else '❌ Not purchased'}"
    )

    # Store current media information in context for keyboard button handlers
    context.user_data['current_media_id'] = media_id
    context.user_data['current_media_type'] = media_type

    # Keyboard for navigation with clearer, more professional buttons
    # Show different bookmark button based on purchase status
    bookmark_text = "🔖 Bookmark"

    keyboard = [
        [KeyboardButton("💳 Purchase"), KeyboardButton(bookmark_text)],
        [KeyboardButton("👍 Like"), KeyboardButton("👎 Dislike")],
        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
        [KeyboardButton("🏠 Home")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Send media with protected content (not downloadable)
    try:
        if query:
            if media_type == "photo":
                await query.message.edit_media(
                    media=InputMediaPhoto(
                        media=file_id,
                        caption=full_caption,
                        parse_mode='Markdown'
                    )
                )
            else:
                await query.message.edit_media(
                    media=InputMediaVideo(
                        media=file_id,
                        caption=full_caption,
                        parse_mode='Markdown'
                    )
                )

        else:
            if media_type == "photo":
                await update.message.reply_photo(
                    photo=file_id,
                    caption=full_caption,
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                    protect_content=True
                )
            else:
                await update.message.reply_video(
                    video=file_id,
                    caption=full_caption,
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                    protect_content=True
                )
    except Exception as e:
        logger.error(f"Error sending media: {e}")
        # Fallback message with better error presentation
        error_message = (
            f"⚠️ *MEDIA UNAVAILABLE* ⚠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"We couldn't display this {media_type}.\n\n"
            f"Please try again or contact support if the issue persists."
        )

        if query:
            await query.message.edit_text(error_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                error_message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

# Handle callback queries for navigation and actions
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id

    await query.answer()

    # Handle channel rejoin check
    if query.data == "check_rejoin":
        if await check_channel_membership(context, user_id):
            # User rejoined, unban them
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
            conn.close()

            await query.message.edit_text(
                "✅ *ACCESS RESTORED* ✅\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Welcome back! Your access has been restored.\n"
                "Thank you for rejoining our channel.",
                parse_mode='Markdown'
            )
            await show_home_menu(update, context)
            return
        else:
            await query.answer("❌ Please join our channel first!", show_alert=True)
            return await force_channel_join(update, context)

    # Handle initial channel membership check
    if query.data == "check_membership":
        return await handle_terms_response(update, context)

    # Handle special cases that break the pattern
    if query.data == "cancel_registration":
        return await cancel_registration(update, context)

    if query.data == "home":
        await show_home_menu(update, context)
        return

    if query.data == "settings":
        await show_settings(update, context)
        return

    if query.data == "profile":
        await show_profile(update, context)
        return

    if query.data == "get_video":
        await show_videos(update, context)
        return

    if query.data == "get_photo":
        await show_photos(update, context)
        return

    if query.data == "buy_stars":
        await show_buy_stars(update, context)
        return

    if query.data == "refer":
        await show_refer(update, context)
        return

    if query.data == "help":
        await show_help(update, context)
        return

    if query.data == "view_bookmarks":
        await show_bookmarks(update, context)
        return

    # Settings menu specific callbacks
    if query.data.startswith("settings_"):
        return await handle_settings_callback(update, context)

    # For all other callbacks, parse the data
    parts = query.data.split('_')
    action = parts[0]

    # Media navigation and actions
    if action in ["next", "prev", "download", "bookmark", "like", "dislike"]:
        media_type = parts[1] if len(parts) > 1 else None
        media_id = int(parts[2]) if len(parts) > 2 else None

        if action == "next":
            if media_type == "video":
                context.user_data['current_video_index'] += 1
                # Don't reset to 0, let send_media_with_navigation handle fetching new videos
            elif media_type == "photo":
                context.user_data['current_photo_index'] += 1
                if context.user_data['current_photo_index'] >= len(context.user_data.get('photos', [])):
                    context.user_data['current_photo_index'] = 0
            elif media_type == "bookmark":
                context.user_data['current_bookmark_index'] += 1
                if context.user_data['current_bookmark_index'] >= len(context.user_data.get('bookmarks', [])):
                    context.user_data['current_bookmark_index'] = 0
                await send_bookmark_with_navigation(update.callback_query, context)
                return

            await send_media_with_navigation(update.callback_query, context, media_type)

        elif action == "prev":
            if media_type == "video":
                context.user_data['current_video_index'] -= 1
                if context.user_data['current_video_index'] < 0:
                    context.user_data['current_video_index'] = len(context.user_data.get('videos', [])) - 1
            elif media_type == "photo":
                context.user_data['current_photo_index'] -= 1
                if context.user_data['current_photo_index'] < 0:
                    context.user_data['current_photo_index'] = len(context.user_data.get('photos', [])) - 1
            elif media_type == "bookmark":
                context.user_data['current_bookmark_index'] -= 1
                if context.user_data['current_bookmark_index'] < 0:
                    context.user_data['current_bookmark_index'] = len(context.user_data.get('bookmarks', [])) - 1
                await send_bookmark_with_navigation(update.callback_query, context)
                return

            await send_media_with_navigation(update.callback_query, context, media_type)

        elif action == "download":
            await handle_download(update, context, media_id)

        elif action == "bookmark":
            await handle_bookmark(update, context, media_id, user_id)
            if media_type == "bookmark":
                await show_bookmarks(update, context)
            else:
                await send_media_with_navigation(update.callback_query, context, media_type)

        elif action in ["like", "dislike"]:
            # Save rating to database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Create ratings table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS media_ratings (
                media_id INTEGER,
                user_id INTEGER,
                rating TEXT,
                rating_date TEXT,
                PRIMARY KEY (media_id, user_id)
            )
            ''')

            # Check if user already rated this media
            cursor.execute("SELECT rating FROM media_ratings WHERE media_id = ? AND user_id = ?", (media_id, user_id))
            existing_rating = cursor.fetchone()

            today = datetime.now().strftime('%Y-%m-%d')
            if existing_rating:
                # Update existing rating
                cursor.execute(
                    "UPDATE media_ratings SET rating = ?, rating_date = ? WHERE media_id = ? AND user_id = ?",
                    (action, today, media_id, user_id)
                )
                message = f"Rating updated to {action}!"
            else:
                # Add new rating
                cursor.execute(
                    "INSERT INTO media_ratings (media_id, user_id, rating, rating_date) VALUES (?, ?, ?, ?)",
                    (media_id, user_id, action, today)
                )
                message = f"Thanks for your {action}!"

            conn.commit()
            conn.close()

            # Show confirmation and refresh the media display to show updated ratings
            await query.answer(message)

            # Reload the current media to reflect the new rating
            if media_type == "video":
                await send_media_with_navigation(update.callback_query, context, "video")
            elif media_type == "photo":
                await send_media_with_navigation(update.callback_query, context, "photo")

    # Handle back to settings
    elif action == "back" and parts[1] == "to" and parts[2] == "settings":
        await show_settings(update, context)

    # Handle edit profile options
    elif action == "edit":
        if parts[1] == "name":
            await query.message.edit_text(
                "✏️ *EDIT NAME*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter your new name:",
                parse_mode='Markdown'
            )
            return EDIT_NAME
        elif parts[1] == "age":
            await query.message.edit_text(
                "✏️ *EDIT AGE*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter your new age:",
                parse_mode='Markdown'
            )
            return EDIT_AGE
        elif parts[1] == "username":
            await query.message.edit_text(
                "✏️ *EDIT USERNAME*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter your new username (minimum 5 characters):",
                parse_mode='Markdown'
            )
            return EDIT_USERNAME

    # Admin menu callbacks
    elif action == "admin":
        if parts[1] == "back_to_menu":
            await show_admin_menu(update, context)
        elif parts[1] == "ban_user":
            user_to_ban = int(parts[2])
            await admin_ban_user_confirm(update, context, user_to_ban)
        elif parts[1] == "unban_user":
            user_to_unban = int(parts[2])
            await admin_unban_user(update, context, user_to_unban)
        elif parts[1] == "add_stars":
            user_to_add = int(parts[2])
            context.user_data['target_user_id'] = user_to_add
            await query.message.edit_text(
                f"💰 *Add Stars to User ID: {user_to_add}*\n\n"
                f"Please enter the number of stars to add:",
                parse_mode='Markdown'
            )
            return ADD_STARS
        elif parts[1] == "remove_stars":
            user_to_remove = int(parts[2])
            context.user_data['target_user_id'] = user_to_remove
            await query.message.edit_text(
                f"💰 *Remove Stars from User ID: {user_to_remove}*\n\n"
                f"Please enter the number of stars to remove:",
                parse_mode='Markdown'
            )
            return REMOVE_STARS
        elif parts[1] == "warn_user":
            user_to_warn = int(parts[2])
            context.user_data['target_user_id'] = user_to_warn
            await query.message.edit_text(
                f"⚠️ *Issue Warning to User ID: {user_to_warn}*\n\n"
                f"Please enter the warning reason:",
                parse_mode='Markdown'
            )
            return WARN_USER
        elif parts[1] == "delete_media":
            media_to_delete = int(parts[2])
            await admin_delete_media(update, context, media_to_delete)
        # Add more admin panel specific callbacks
        elif parts[1] == "add_video":
            await query.message.edit_text(
                "🎬 *ADD NEW VIDEO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please send the video you want to add to the bot:",
                parse_mode='Markdown'
            )
            return ADD_VIDEO
        elif parts[1] == "add_photo":
            await query.message.edit_text(
                "📷 *ADD NEW PHOTO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please send the photo you want to add to the bot:",
                parse_mode='Markdown'
            )
            return ADD_PHOTO
        elif parts[1] == "broadcast":
            await query.message.edit_text(
                "📣 *SEND BROADCAST MESSAGE*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the message you want to broadcast to all users:",
                parse_mode='Markdown'
            )
            return ADMIN_BROADCAST
        elif parts[1] == "change_prices":
            # Implement price changing functionality
            await query.message.edit_text(
                "💲 *CHANGE PRICES*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Select which price you want to change:\n\n"
                "Current prices:\n"
                "• Video: 1 ⭐\n"
                "• Photo: 0.5 ⭐",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎬 Change Video Price", callback_data="admin_change_video_price")],
                    [InlineKeyboardButton("📷 Change Photo Price", callback_data="admin_change_photo_price")],
                    [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back_to_menu")]
                ]),
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Toggle notification callback
    elif action == "toggle":
        if parts[1] == "notifications":
            # Toggle notification status
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT notification_enabled FROM users WHERE user_id = ?", (user_id,))
                current_status = cursor.fetchone()[0]
                new_status = 0 if current_status else 1
                cursor.execute("UPDATE users SET notification_enabled = ? WHERE user_id = ?", (new_status, user_id))
            except sqlite3.OperationalError:
                # If column doesn't exist, add it
                cursor.execute("ALTER TABLE users ADD COLUMN notification_enabled INTEGER DEFAULT 1")
                new_status = 0  # Default to turning off since they just clicked
                cursor.execute("UPDATE users SET notification_enabled = ? WHERE user_id = ?", (new_status, user_id))

            conn.commit()
            conn.close()

            # Confirm the change
            await query.answer(f"Notifications turned {'ON ✅' if new_status else 'OFF ❌'}")

            # Return to settings menu
            await show_settings(update, context)

    # If nothing matched, provide feedback
    else:
        await query.answer("This feature is coming soon!")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None

    help_text = (
        "📚 *HELP & INFORMATION*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🔍 *HOW TO USE THE BOT*\n"
        "• Browse photos and videos with navigation buttons\n"
        "• Download content using your star balance\n"
        "• Bookmark your favorite content for later\n"
        "• Add stars to your account to unlock premium content\n\n"

        "⭐ *ABOUT STARS*\n"
        "• Each star is worth 2 rupees\n"
        "• You earn 5 stars daily by logging in\n"
        "• Refer friends to earn more stars\n"
        "• Purchase stars from our admin\n\n"

        "🤔 *COMMON QUESTIONS*\n"
        "• How to download? - Click Download button (requires stars)\n"
        "• How to get more stars? - Daily login, referrals, or purchase\n"
        "• Content issues? - Contact our support\n\n"

        "🔐 *ACCOUNT SECURITY*\n"
        "• Your personal data is secure\n"
        "• Never share your password\n"
        "• Report suspicious activity to admin\n\n"

        "Need more help? Contact our support: "
        f"{ADMIN_USERNAME}"
    )

    # Create keyboard buttons in the chat input area
    keyboard = [
        [KeyboardButton("🏠 Home")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if query:
        await query.message.edit_text(
            help_text,
            parse_mode='Markdown'
        )
        await query.message.reply_text(
            "Use the keyboard to navigate back",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            help_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE, media_id):
    query = update.callback_query
    user_id = update.effective_user.id

    # Get user stars and media info
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get full user information
    cursor.execute("SELECT name, stars FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        await query.message.reply_text(
            "⚠️ *ACCOUNT REQUIRED* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "You need to register before downloading content.\n"
            "Please use /start to create your account.",
            parse_mode='Markdown'
        )
        return

    name, user_stars = user

    # Get detailed media information
    cursor.execute("SELECT * FROM media WHERE id = ?", (media_id,))
    media = cursor.fetchone()

    if not media:
        conn.close()
        await query.message.reply_text(
            "⚠️ *CONTENT UNAVAILABLE* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "This item is no longer available in our collection.\n"
            "Please browse our current content for alternatives.",
            parse_mode='Markdown'
        )
        return

    # Extract media details
    media_id, media_type, file_id, caption, price = media[0], media[1], media[2], media[3], media[4]

    # Format media type for better presentation
    media_type_display = "Photo" if media_type == "photo" else "Video"

    # Check if user has enough stars
    if user_stars < price:
        conn.close()

        missing_stars = price - user_stars

        # Create an elegant insufficient funds message
        insufficient_text = (
            "💫 *PREMIUM CONTENT* 💫\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Hello, *{name}*!\n\n"
            f"This {media_type_display.lower()} requires additional stars to download.\n\n"
            f"🔸 *Price:* {price} ⭐\n"
            f"🔸 *Your Balance:* {user_stars} ⭐\n"
            f"🔸 *Needed:* {missing_stars} ⭐\n\n"
            f"Would you like to add more stars to your account?"
        )

        keyboard = [
            [InlineKeyboardButton("💰 Purchase Stars", callback_data="buy_stars")],
            [InlineKeyboardButton("🔙 Return to Browsing", callback_data="back_to_media")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            insufficient_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    # Deduct stars
    cursor.execute("UPDATE users SET stars = stars - ? WHERE user_id = ?", (price, user_id))

    # Get new balance for the receipt
    new_balance = user_stars - price

    # Record transaction with more detail
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%H:%M:%S')
    transaction_id = f"{user_id}{int(datetime.now().timestamp())}"[-8:]

    cursor.execute(
        "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
        (user_id, -price, f"Downloaded {media_type} #{media_id}", today)
    )

    # Log activity
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "DOWNLOAD", f"Downloaded {media_type} #{media_id}", today)
    )

    conn.commit()
    conn.close()

    # Send downloadable media with an elegant receipt-like message
    download_caption = (
        f"✅ *DOWNLOAD COMPLETE* ✅\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*DESCRIPTION:*\n{caption}\n\n"
        f"📋 *PURCHASE DETAILS*\n"
        f"• Transaction ID: #{transaction_id}\n"
        f"• Item: Premium {media_type_display}\n"
        f"• Price: {price} ⭐\n"
        f"• New Balance: {new_balance} ⭐\n"
        f"• Date: {today} at {timestamp}\n\n"
        f"Thank you for your purchase, *{name}*!\n"
        f"Enjoy your premium content."
    )

    if media_type == "photo":
        await query.message.reply_photo(
            photo=file_id,
            caption=download_caption,
            parse_mode='Markdown',
            protect_content=False
        )
    else:
        await query.message.reply_video(
            video=file_id,
            caption=download_caption,
            parse_mode='Markdown',
            protect_content=False
        )

    # Confirm the transaction with an elegant toast
    await query.answer(f"✅ Downloaded successfully! Spent {price} ⭐")

async def handle_bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE, media_id, user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Check if already bookmarked
    cursor.execute("SELECT * FROM bookmarks WHERE user_id = ? AND media_id = ?", (user_id, media_id))
    bookmark = cursor.fetchone()

    today = datetime.now().strftime('%Y-%m-%d')

    if bookmark:
        # Remove bookmark
        cursor.execute("DELETE FROM bookmarks WHERE user_id = ? AND media_id = ?", (user_id, media_id))
        message = "🔖 Bookmark removed!"

        # Log activity
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "BOOKMARK_REMOVE", f"Removed bookmark for media #{media_id}", today)
        )

        conn.commit()
        conn.close()

        await update.callback_query.answer(message)
    else:
        # Check if user has purchased this media
        cursor.execute(
            "SELECT * FROM transactions WHERE user_id = ? AND description LIKE ? AND amount < 0", 
            (user_id, f"Downloaded %{media_id}%")
        )
        purchase_record = cursor.fetchone()

        if not purchase_record:
            conn.close()
            await update.callback_query.answer("You must purchase this content before bookmarking it")

            # Try to send a message with more details
            try:
                await update.callback_query.message.reply_text(
                    "❌ *PURCHASE REQUIRED* ❌\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "You need to purchase and download this content before you can bookmark it.\n\n"
                    "Please use the 'Purchase & Download' button first.",
                    parse_mode='Markdown'
                )
            except Exception:
                pass

            return

        # Add bookmark after purchase is verified
        cursor.execute(
            "INSERT INTO bookmarks (user_id, media_id, bookmark_date) VALUES (?, ?, ?)", 
            (user_id, media_id, today)
        )
        message = "🔖 Bookmark added!"

        # Log activity
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "BOOKMARK_ADD", f"Added bookmark for media #{media_id}", today)
        )

        conn.commit()
        conn.close()

        await update.callback_query.answer(message)

# Profile and user management
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if not query else query.from_user.id

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        text = "⚠️ You need to register first. Please use /start"

        if query:
            await query.message.edit_text(text, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, parse_mode='Markdown')
        return

    # Parse user data
    user_id = user[0]
    name = user[1] 
    age = user[2]
    username = user[3]
    stars = user[4]
    reg_date = user[5]
    last_login = user[6]
    notification_status = user[7]
    warnings = user[10] if len(user) > 10 else 0

    # Count bookmarks
    cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE user_id = ?", (user_id,))
    bookmark_count = cursor.fetchone()[0]

    # Count downloads (transactions with negative amounts)
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND amount < 0 AND description LIKE 'Downloaded%'", (user_id,))
    download_count = cursor.fetchone()[0]

    # Calculate days as member
    reg_date_obj = datetime.strptime(reg_date, '%Y-%m-%d')
    days_member = (datetime.now() - reg_date_obj).days

    # Format dates for better presentation
    try:
        formatted_reg_date = datetime.strptime(reg_date, '%Y-%m-%d').strftime('%d %b %Y')
        formatted_last_login = datetime.strptime(last_login, '%Y-%m-%d').strftime('%d %b %Y')
    except:
        formatted_reg_date = reg_date
        formatted_last_login = last_login

    conn.close()

    # Create a visually structured profile with enhanced presentation
    profile_text = (
        f"👑 *USER PROFILE* 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🙋‍♂️ *PERSONAL DETAILS*\n"
        f"• *Name:* {name}\n"
        f"• *Age:* {age}+\n"
        f"• *Username:* @{username}\n"
        f"• *Telegram ID:* `{user_id}`\n\n"

        f"📅 *MEMBERSHIP*\n"
        f"• *Joined:* {formatted_reg_date}\n"
        f"• *Member for:* {days_member} days\n"
        f"• *Last visit:* {formatted_last_login}\n\n"

        f"💰 *BALANCE DETAILS*\n"
        f"• *Stars:* {stars} ⭐\n"
        f"• *Value:* {stars * 2} ₹\n\n"

        f"📊 *ACTIVITY & SETTINGS*\n"
        f"• *Bookmarks:* {bookmark_count}\n"
        f"• *Downloads:* {download_count}\n"
        f"• *Account status:* {'⚠️ Warnings: '+str(warnings) if warnings > 0 else '✅ Good standing'}\n"
        f"• *Notifications:* {'🔔 Enabled' if notification_status else '🔕 Disabled'}"
    )

    # Create improved inline buttons for profile actions with fixed functionality
    inline_keyboard = [
        [InlineKeyboardButton("✏️ Edit Name", callback_data="settings_edit_name")],
        [InlineKeyboardButton("✏️ Edit Age", callback_data="settings_edit_age")],
        [InlineKeyboardButton("✏️ Edit Username", callback_data="settings_edit_username")],
        [InlineKeyboardButton(f"{'🔕 Disable' if notification_status else '🔔 Enable'} Notifications", callback_data="toggle_notifications")]
    ]

    inline_markup = InlineKeyboardMarkup(inline_keyboard)

    # Create keyboard buttons in the chat input area with improved layout
    keyboard = [
        [KeyboardButton("🏠 Home")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Store current section in context for state management
    context.user_data['current_section'] = 'profile'

    # Handle both callback query and direct message
    if query:
        await query.message.edit_text(
            profile_text,
            parse_mode='Markdown',
            reply_markup=inline_markup
        )
    else:
        await update.message.reply_text(
            profile_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

# Anti-spam functionality
async def check_button_cooldown(user_id: int, button_type: str, cooldown_seconds: int = 5) -> bool:
    """Check if user can press a button or if they're in cooldown"""
    current_time = datetime.now()

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get last press time for this button type
    cursor.execute("SELECT last_pressed FROM button_cooldowns WHERE user_id = ? AND button_type = ?", 
                  (user_id, button_type))
    result = cursor.fetchone()

    if result:
        last_pressed = datetime.fromisoformat(result[0])
        time_diff = (current_time - last_pressed).total_seconds()

        if time_diff < cooldown_seconds:
            conn.close()
            return False  # Still in cooldown

    # Update last pressed time
    cursor.execute("""
        INSERT OR REPLACE INTO button_cooldowns (user_id, button_type, last_pressed) 
        VALUES (?, ?, ?)
    """, (user_id, button_type, current_time.isoformat()))

    conn.commit()
    conn.close()
    return True  # Can press button

# Helper functions for profile editing
async def process_edit_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "✏️ *EDIT NAME*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter your new name:",
        parse_mode='Markdown'
    )
    return EDIT_NAME

async def process_edit_age_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "✏️ *EDIT AGE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter your new age:",
        parse_mode='Markdown'
    )
    return EDIT_AGE

async def process_edit_username_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "✏️ *EDIT USERNAME*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter your new username (minimum 5 characters):",
        parse_mode='Markdown'
    )
    return EDIT_USERNAME

# Edit Profile: Process name change
async def process_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_name = update.message.text
    user_id = update.effective_user.id

    # Validate name
    if len(new_name) < 2 or len(new_name) > 50:
        await update.message.reply_text(
            "❌ *Invalid Name*\n\n"
            "Name must be between 2 and 50 characters.\n"
            "Please try again with a valid name:",
            parse_mode='Markdown'
        )
        return EDIT_NAME

    # Update name in database
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get old name for confirmation
    cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
    old_name = cursor.fetchone()[0]

    # Update name
    cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_name, user_id))

    # Log the change
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "NAME_CHANGED", f"Name changed from '{old_name}' to '{new_name}'", today)
    )

    conn.commit()
    conn.close()

    # Show success message with inline buttons
    keyboard = [
        [InlineKeyboardButton("👤 View Profile", callback_data="profile")],
        [InlineKeyboardButton("⚙️ Back to Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ *Name Updated Successfully*\n\n"
        f"Your name has been changed from '{old_name}' to '{new_name}'.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    return SETTINGS_MENU

# Edit Profile: Process age change
async def process_edit_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        new_age = int(update.message.text)
        user_id = update.effective_user.id

        # Validate age
        if new_age < 18 or new_age > 120:
            await update.message.reply_text(
                "❌ *Invalid Age*\n\n"
                "Age must be between 18 and 120.\n"
                "Please enter a valid age:",
                parse_mode='Markdown'
            )
            return EDIT_AGE

        # Update age in database
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Get old age for confirmation
        cursor.execute("SELECT age FROM users WHERE user_id = ?", (user_id,))
        old_age = cursor.fetchone()[0]

        # Update age
        cursor.execute("UPDATE users SET age = ? WHERE user_id = ?", (new_age, user_id))

        # Log the change
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "AGE_CHANGED", f"Age changed from {old_age} to {new_age}", today)
        )

        conn.commit()
        conn.close()

        # Show success message with inline buttons
        keyboard = [
            [InlineKeyboardButton("👤 View Profile", callback_data="profile")],
            [InlineKeyboardButton("⚙️ Back to Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *Age Updated Successfully*\n\n"
            f"Your age has been changed from {old_age} to {new_age}.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return SETTINGS_MENU

    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid Input*\n\n"
            "Please enter a valid number for your age:",
            parse_mode='Markdown'
        )
        return EDIT_AGE

# Edit Profile: Process username change
async def process_edit_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_username = update.message.text
    user_id = update.effective_user.id

    # Validate username
    if len(new_username) < 5:
        await update.message.reply_text(
            "❌ *Username Too Short*\n\n"
            "Username must be at least 5 characters long.\n"
            "Please try again:",
            parse_mode='Markdown'
        )
        return EDIT_USERNAME

    # Check if username exists
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get old username for confirmation
    cursor.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        await update.message.reply_text(
            "❌ *Error*\n\n"
            "Your user profile was not found. Please use /start to set up your account.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    old_username = result[0]

    # Check if new username is already taken by another user
    cursor.execute("SELECT * FROM users WHERE username = ? AND user_id != ?", (new_username, user_id))
    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        await update.message.reply_text(
            "❌ *Username Unavailable*\n\n"
            "This username is already taken.\n"
            "Please choose another one:",
            parse_mode='Markdown'
        )
        return EDIT_USERNAME

    # Update username
    cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (new_username, user_id))

    # Log the change
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "USERNAME_CHANGED", f"Username changed from '{old_username}' to '{new_username}'", today)
    )

    conn.commit()
    conn.close()

    # Show success message with inline buttons
    keyboard = [
        [InlineKeyboardButton("👤 View Profile", callback_data="profile")],
        [InlineKeyboardButton("⚙️ Back to Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Create keyboard buttons as well for easier mobile navigation
    chat_keyboard = [
        [KeyboardButton("👤 My Profile"), KeyboardButton("⚙️ Settings")],
        [KeyboardButton("🏠 Home")]
    ]
    chat_reply_markup = ReplyKeyboardMarkup(chat_keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"✅ *Username Updated Successfully*\n\n"
        f"Your username has been changed from '{old_username}' to '{new_username}'.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    # Add the keyboard markup separately to ensure it appears
    await update.message.reply_text(
        "Use these buttons to navigate:",
        reply_markup=chat_reply_markup
    )

    return SETTINGS_MENU

async def show_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if not query else query.from_user.id

    bot_username = (await context.bot.get_me()).username

    # Create a visually appealing referral message
    refer_text = (
        f"🔄 *REFER & EARN PROGRAM*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Invite friends and earn rewards!\n\n"
        f"*YOUR REFERRAL LINK:*\n"
        f"`https://t.me/{bot_username}?start=ref_{user_id}`\n\n"
        f"*REWARDS:*\n"
        f"• You get 5 ⭐ for each new user who joins\n"
        f"• Your friend gets 2 extra ⭐ as a bonus\n\n"
        f"*HOW IT WORKS:*\n"
        f"1. Share your unique link with friends\n"
        f"2. They register through your link\n"
        f"3. Both of you receive star bonuses!\n\n"
        f"Start sharing now to earn more stars!"
    )

    # Create a command for easy copying
    command_text = f"/start ref_{user_id}"

    # Only provide the Share button
    keyboard = [
        [InlineKeyboardButton("📣 Share Now", url=f"https://t.me/share/url?url=https://t.me/{bot_username}?start=ref_{user_id}&text=Join%20Unknown%20Leaks%20Bot%20and%20get%20exclusive%20content!%20Use%20my%20referral%20link%20to%20receive%20bonus%20stars!")],
        [InlineKeyboardButton("📋 Copy Referral Command", callback_data="copy_referral_command")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Add keyboard buttons for navigation
    keyboard_buttons = [
        [KeyboardButton("🏠 Home")]
    ]
    keyboard_markup = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True)

    # Store the referral command in user_data for easy access
    context.user_data['referral_command'] = command_text

    # Handle both callback query and direct message
    if query:
        await query.message.edit_text(
            refer_text + f"\n\n*Or use this command:*\n`{command_text}`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            refer_text + f"\n\n*Or use this command:*\n`{command_text}`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Add additional message for easy copying
        await update.message.reply_text(
            f"`{command_text}`\n\n👆 Copy this command and tell your friends to paste it in the bot to get started!",
            parse_mode='Markdown'
        )

async def show_buy_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if not query else query.from_user.id

    # Get user info for personalized experience
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, stars FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    conn.close()

    name = user_info[0] if user_info else "User"
    current_stars = user_info[1] if user_info else 0

    # Create a premium, elegant sales page
    buy_text = (
        f"✨ *PREMIUM STARS* ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Hello, *{name}*!\n"
        f"Current Balance: *{current_stars} ⭐*\n\n"
        f"💫 *EXCLUSIVE PACKAGES*\n\n"
        f"🔹 *STARTER PACK*\n"
        f"• 10 ⭐ = ₹20\n"
        f"• Perfect for beginners\n\n"
        f"🔹 *POPULAR CHOICE*\n"
        f"• 50 ⭐ = ₹100\n"
        f"• Our most popular option\n\n"
        f"🔹 *PREMIUM BUNDLE*\n"
        f"• 100 ⭐ = ₹180\n"
        f"• Save 10% with this package\n\n"
        f"🔹 *VIP EXPERIENCE*\n"
        f"• 500 ⭐ = ₹800\n"
        f"• Best value (20% savings)\n\n"
        f"📱 *PURCHASE PROCESS*\n"
        f"1. Contact our admin\n"
        f"2. Mention your preferred package\n"
        f"3. Complete secure payment\n"
        f"4. Receive stars instantly"
    )

    # Combine inline buttons with keyboard buttons
    inline_keyboard = [
        [InlineKeyboardButton("💬 Contact Admin For Purchase", url=f"https://t.me/{ADMIN_USERNAME[1:]}")]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)

    # Add keyboard buttons for navigation
    keyboard_buttons = [
        [KeyboardButton("🏠 Home")]
    ]
    keyboard_markup = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True)

    # Handle both callback query and direct message
    if query:
        await query.message.edit_text(
            buy_text,
            reply_markup=inline_markup,
            parse_mode='Markdown'
        )
    else:
        # Send the message with inline buttons and include keyboard buttons directly
        message = await update.message.reply_text(
            buy_text,
            reply_markup=inline_markup,
            parse_mode='Markdown'
        )

        # Update keyboard buttons without additional text
        await message.reply_markup(keyboard_markup)

async def show_bookmarks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id

    # Get user name for personalized experience
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
    user_result = cursor.fetchone()
    name = user_result[0] if user_result else "User"

    # Get user's bookmarks with media info
    cursor.execute("""
        SELECT DISTINCT m.id, m.type, m.file_id, m.caption, m.price, b.bookmark_date 
        FROM bookmarks b 
        JOIN media m ON b.media_id = m.id 
        WHERE b.user_id = ? AND m.file_id IS NOT NULL
        ORDER BY b.bookmark_date DESC
    """, (user_id,))

    bookmarks = cursor.fetchall()

    # Get total bookmark count
    cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE user_id = ?", (user_id,))
    total_bookmarks = cursor.fetchone()[0]

    # Create media_ratings table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS media_ratings (
        media_id INTEGER,
        user_id INTEGER,
        rating TEXT,
        rating_date TEXT,
        PRIMARY KEY (media_id, user_id)
    )
    ''')
    conn.commit()
    conn.close()

    # Create keyboard buttons with improved navigation
    keyboard = [
        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
        [KeyboardButton("🏠 Home")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if not bookmarks:
        no_bookmarks_text = (
            "📚 *MY COLLECTION* 📚\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Hello, *{name}*!\n\n"
            "Your bookmark collection is currently empty.\n\n"
            "When browsing our premium content, use the bookmark button to save your favorite items for quick access later.\n\n"
            "📌 *TIP:* You must purchase content before you can bookmark it."
        )

        keyboard = [[KeyboardButton("🏠 Home")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        if query:
            await query.message.edit_text(
                no_bookmarks_text,
                parse_mode='Markdown'
            )
            await query.message.reply_text(
                "Use this button to return home:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                no_bookmarks_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        return

    # Show bookmark count summary
    if not query:
        await update.message.reply_text(
            f"📚 *MY COLLECTION* 📚\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"You have *{total_bookmarks}* saved items in your collection.\n"
            f"Use the navigation buttons to browse through them.",
            parse_mode='Markdown'
        )

    # Store bookmarks in context
    context.user_data['bookmarks'] = bookmarks
    context.user_data['current_bookmark_index'] = 0

    # Show first bookmark
    if query:
        await send_bookmark_with_navigation(query, context)
    else:
        # For text commands, directly show the bookmark
        await send_bookmark_for_text_command(update, context)

async def send_bookmark_for_text_command(update, context):
    """Handle sending bookmark for text commands without callback query"""
    user_id = update.effective_user.id
    bookmarks = context.user_data.get('bookmarks', [])
    current_index = context.user_data.get('current_bookmark_index', 0)

    if not bookmarks:
        await update.message.reply_text(
            "📚 *MY COLLECTION* 📚\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Your bookmark collection is empty.\n\n"
            "Browse our premium content and bookmark your favorites to build your collection.",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🏠 Home")]], resize_keyboard=True)
        )
        return

    # Boundary check for current_index
    if current_index >= len(bookmarks):
        current_index = 0
        context.user_data['current_bookmark_index'] = 0

    # Get current bookmark
    try:
        media = bookmarks[current_index]
        media_id, media_type, file_id, caption, price, bookmark_date = media
    except (IndexError, ValueError) as e:
        # Handle the case where bookmark data is invalid
        await update.message.reply_text(
            "❌ *ERROR WITH BOOKMARK*\n"
            "There was an issue with your bookmarks. Please try again later.",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🏠 Home")]], resize_keyboard=True)
        )
        return

    # Format date for better display
    try:
        formatted_date = datetime.strptime(bookmark_date, '%Y-%m-%d').strftime('%d %b %Y')
    except:
        formatted_date = bookmark_date

    # Get user info and ratings in a single database connection
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get user info
    cursor.execute("SELECT name, stars FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()
    name, user_stars = user_info if user_info else ("User", 0)

    # Add visual icon based on media type
    media_icon = "🎬" if media_type == "video" else "📸"

    # Get like/dislike stats
    cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'like'", (media_id,))
    likes = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'dislike'", (media_id,))
    dislikes = cursor.fetchone()[0] or 0

    # Calculate rating percentage
    total_ratings = likes + dislikes
    like_percentage = (likes / total_ratings * 100) if total_ratings > 0 else 0

    # Get the most up-to-date file_id for the media
    cursor.execute("SELECT file_id FROM media WHERE id = ?", (media_id,))
    latest_file_id = cursor.fetchone()
    if latest_file_id:
        file_id = latest_file_id[0]  # Update file_id with the latest one

    conn.close()

    # Build elegant caption
    full_caption = (
        f"📚 *SAVED CONTENT* 📚\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{media_icon} *{media_type.upper()} #{media_id}*\n"
        f"📅 Saved on: {formatted_date}\n\n"
        f"*DESCRIPTION:*\n{caption}\n\n"
        f"📊 *DETAILS*\n"
        f"• Item: {current_index + 1} of {len(bookmarks)}\n"
        f"• Rating: {round(like_percentage)}% positive\n"
        f"• Price: {price} ⭐\n\n"
        f"💬 *NOTE*\n"
        f"Use the navigation buttons below to browse through your collection."
    )

    # Create enhanced keyboard for navigation
    keyboard = [
        [KeyboardButton("💾 Re-download")],
        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
        [KeyboardButton("🏠 Home")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Store the current media info for keyboard button handlers
    context.user_data['current_media_id'] = media_id
    context.user_data['current_media_type'] = media_type

    # Send media
    try:
        if media_type == "photo":
            await update.message.reply_photo(
                photo=file_id,
                caption=full_caption,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_video(
                video=file_id,
                caption=full_caption,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    except Exception as e:
        # Handle case where media might be deleted or unavailable
        logger.error(f"Error sending bookmarked media: {e}")
        await update.message.reply_text(
            f"⚠️ *MEDIA UNAVAILABLE* ⚠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"This bookmarked content is no longer available.\n"
            f"It may have been removed from our collection.\n\n"
            f"Would you like to remove this from your bookmarks?",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🗑️ Remove Bookmark")],
                [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
                [KeyboardButton("🏠 Home")]
            ], resize_keyboard=True)
        )

async def send_bookmark_with_navigation(callback_query, context):
    user_id = callback_query.from_user.id
    bookmarks = context.user_data.get('bookmarks', [])
    current_index = context.user_data.get('current_bookmark_index', 0)

    if not bookmarks:
        await callback_query.message.edit_text(
            "📚 *BOOKMARKS*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "You don't have any bookmarks.",
            parse_mode='Markdown'
        )

        # Add keyboard buttons
        keyboard = [[KeyboardButton("🏠 Home")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await callback_query.message.reply_text(
            "Use the keyboard to navigate",
            reply_markup=reply_markup
        )
        return

    # Get current bookmark
    media = bookmarks[current_index]
    media_id, media_type, file_id, caption, price, bookmark_date = media

    # Get user stars
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    user_stars = user[0] if user else 0
    conn.close()

    # Build caption
    full_caption = (
        f"🔖 *BOOKMARK {current_index + 1}/{len(bookmarks)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*{media_type.upper()} #{media_id}*\n\n"
        f"{caption}\n\n"
        f"💰 *PRICING*\n"
        f"• Cost: {price} ⭐\n"
        f"• Your Balance: {user_stars} ⭐\n\n"
        f"📅 Saved on: {bookmark_date}"
    )

    # Build navigation keyboard (will use both inline and keyboard buttons)
    inline_keyboard = [
        [
            InlineKeyboardButton("💾 Download", callback_data=f"download_{media_type}_{media_id}"),
            InlineKeyboardButton("🗑️ Remove", callback_data=f"bookmark_{media_type}_{media_id}")
        ]
    ]

    inline_markup = InlineKeyboardMarkup(inline_keyboard)

    # Also add regular keyboard buttons
    keyboard = [
        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
        [KeyboardButton("🏠 Home")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # We'll use inline_markup for the media message
    reply_markup_for_media = inline_markup

    # Edit message with media and send keyboard separately
    try:
        if media_type == "photo":
            await callback_query.message.edit_media(
                media=InputMediaPhoto(
                    media=file_id, 
                    caption=full_caption,
                    parse_mode='Markdown'
                ),
                reply_markup=reply_markup_for_media
            )
        else:
            await callback_query.message.edit_media(
                media=InputMediaVideo(
                    media=file_id,
                    caption=full_caption,
                    parse_mode='Markdown'
                ),
                reply_markup=reply_markup_for_media
            )

        # Send the keyboard buttons separately to ensure they're accessible
        await callback_query.message.reply_text(
            "Use the keyboard to navigate:",
            reply_markup=reply_markup
        )
    except Exception as e:
        # If editing media fails, send a new message
        logger.error(f"Failed to edit media: {e}")
        await callback_query.message.edit_text(
            "⚠️ Could not load bookmark. It may have been deleted or is no longer available.\n\n"
            "Try viewing another bookmark or returning to home.",
            parse_mode='Markdown'
        )

        # Add keyboard navigation
        await callback_query.message.reply_text(
            "Navigate back to home:",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🏠 Home")]], resize_keyboard=True)
        )

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if hasattr(update, 'callback_query') else None
    user_id = update.effective_user.id if not query else query.from_user.id

    # Get user settings and info
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name, notification_enabled, last_login FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            name, notification_status, last_login = result
        else:
            name = "User"
            notification_status = 1
            last_login = "Unknown"
    except sqlite3.OperationalError:
        # Handle case where column doesn't exist
        cursor.execute("ALTER TABLE users ADD COLUMN notification_enabled INTEGER DEFAULT 1")
        notification_status = 1
        name = "User"
        last_login = "Unknown"
        conn.commit()

    conn.close()

    # Current date/time for professional display
    current_time = datetime.now().strftime('%H:%M')
    current_date = datetime.now().strftime('%d %b %Y')

    # Create an elegant, professional settings dashboard
    settings_text = (
        f"⚙️ *ACCOUNT SETTINGS* ⚙️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Hello, *{name}*\n"
        f"Last login: {last_login}\n"
        f"Current time: {current_date}, {current_time}\n\n"
        f"Customize your experience with the following options:"
    )

    # Simplified inline keyboard with only essential options
    inline_keyboard = [
        [InlineKeyboardButton("👤 My Profile", callback_data="profile")],
        [InlineKeyboardButton(f"{'🔔 Disable Notifications' if notification_status else '🔕 Enable Notifications'}", 
                            callback_data="toggle_notifications")],
        [InlineKeyboardButton("⚠️ Delete My Account", callback_data="settings_delete_account")]
    ]

    inline_markup = InlineKeyboardMarkup(inline_keyboard)

    # Mobile-friendly chat keyboard with streamlined options
    keyboard = [
        [KeyboardButton("👤 My Profile")],
        [KeyboardButton("🔔 Toggle Notifications")],
        [KeyboardButton("🏠 Home")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Handle both callback query and direct message
    if query:
        await query.message.edit_text(
            settings_text,
            reply_markup=inline_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            settings_text,
            reply_markup=inline_markup,
            parse_mode='Markdown'
        )

    return SETTINGS_MENU

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    action = query.data.replace("settings_", "") if query.data.startswith("settings_") else query.data
    user_id = update.effective_user.id

    if action == "toggle_notifications":
        # Toggle notification status
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT notification_enabled FROM users WHERE user_id = ?", (user_id,))
            current_status = cursor.fetchone()[0]
            new_status = 0 if current_status else 1
            cursor.execute("UPDATE users SET notification_enabled = ? WHERE user_id = ?", (new_status, user_id))
        except sqlite3.OperationalError:
            # If column doesn't exist, add it
            cursor.execute("ALTER TABLE users ADD COLUMN notification_enabled INTEGER DEFAULT 1")
            new_status = 0  # Default to turning off since they just clicked
            cursor.execute("UPDATE users SET notification_enabled = ? WHERE user_id = ?", (new_status, user_id))

        conn.commit()
        conn.close()

        # Log action and show toast
        await query.answer(f"Notifications turned {'ON ✅' if new_status else 'OFF ❌'}")

        # Return to settings menu
        await show_settings(update, context)
        return SETTINGS_MENU

    elif action == "edit_name":
        # Show edit name screen
        await query.message.edit_text(
            "✏️ *EDIT NAME*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter your new name:",
            parse_mode='Markdown'
        )
        return EDIT_NAME

    elif action == "edit_age":
        # Show edit age screen
        await query.message.edit_text(
            "✏️ *EDIT AGE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter your new age (18-120):",
            parse_mode='Markdown'
        )
        return EDIT_AGE

    elif action == "edit_username":
        # Show edit username screen
        await query.message.edit_text(
            "✏️ *EDIT USERNAME*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter your new username (minimum 5 characters):",
            parse_mode='Markdown'
        )
        return EDIT_USERNAME

    elif action == "help_support":
        await query.message.edit_text(
            "❓ *HELP & SUPPORT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "If you need assistance with using the bot or have any questions, "
            f"please contact our admin: {ADMIN_USERNAME}\n\n"
            "*COMMON QUESTIONS:*\n"
            "• How to earn stars? - Daily login gives 5 stars\n"
            "• How to download media? - Click the download button (costs stars)\n"
            "• Payment issues? - Contact admin directly\n\n"
            "*CONTACT CHANNELS:*\n"
            f"• Official Channel: {CHANNEL_USERNAME}\n"
            f"• Admin Contact: {ADMIN_USERNAME}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]]),
            parse_mode='Markdown'
        )
        return SETTINGS_MENU

    elif action == "terms_privacy":
        await query.message.edit_text(
            "📜 *TERMS & PRIVACY POLICY*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*TERMS OF SERVICE:*\n"
            "• All content is provided for entertainment purposes\n"
            "• Users must be 18+ to access certain content\n"
            "• Purchased stars and content are non-refundable\n"
            "• Abusive behavior will result in permanent ban\n\n"
            "*PRIVACY POLICY:*\n"
            "• We collect minimal personal information\n"
            "• Your data is stored securely and never shared\n"
            "• You can request data deletion at any time\n"
            "• We use secure protocols to protect your information\n\n"
            "By continuing to use this bot, you accept these terms.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]]),
            parse_mode='Markdown'
        )
        return SETTINGS_MENU

    elif action == "security":
        await query.message.edit_text(
            "🔐 *SECURITY SETTINGS*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*ACCOUNT PROTECTION:*\n"
            "• Your account is protected by Telegram's security\n"
            "• We never store your Telegram password\n"
            "• All transactions are securely logged\n\n"
            "*BEST PRACTICES:*\n"
            "• Never share your account access\n"
            "• Report suspicious activities to admin\n"
            "• Regularly check your transaction history",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")]]),
            parse_mode='Markdown'
        )
        return SETTINGS_MENU

    elif action == "delete_account":
        keyboard = [
            [InlineKeyboardButton("❌ CANCEL", callback_data="back_to_settings")],
            [InlineKeyboardButton("✅ YES, DELETE MY ACCOUNT", callback_data="confirm_delete_account")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            "⚠️ *DELETE ACCOUNT - WARNING*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "This action is *PERMANENT* and *CANNOT BE UNDONE*!\n\n"
            "*YOU WILL LOSE:*\n"
            "• All your stars and balance\n"
            "• Saved bookmarks\n"
            "• Account history & preferences\n"
            "• Access to premium content\n\n"
            "*Are you absolutely sure you want to delete your account?*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return SETTINGS_MENU

    elif action == "confirm_delete_account":
        # Delete user account
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Get user info for the log
        cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()

        if user_info:
            name, username = user_info
            # Delete user data
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM bookmarks WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM daily_logins WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))

            # Log the deletion
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (user_id, "ACCOUNT_DELETED", f"User deleted their account: {name} (@{username})", today)
            )

            conn.commit()

            await query.message.edit_text(
                "✅ *ACCOUNT DELETED*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Your account has been successfully deleted.\n\n"
                "All your data has been removed from our system.\n\n"
                "Thank you for using our service. If you wish to return,\n"
                "you can create a new account anytime.",
                parse_mode='Markdown'
            )

            return ConversationHandler.END

        else:
            await query.message.edit_text(
                "❌ *ERROR*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Account not found. Please try again or contact support.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]]),
                parse_mode='Markdown'
            )

        conn.close()
        return SETTINGS_MENU

    elif action == "back_to_settings":
        await show_settings(update, context)
        return SETTINGS_MENU

    return SETTINGS_MENU

# Admin panel with modern UI
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    # Define approved admins list
    APPROVED_ADMINS = [ADMIN_ID, 6648598512, 7062972013]

    # Save admin authentication for all approved admins
    if user_id in APPROVED_ADMINS:
        context.user_data['admin_authenticated'] = True
        context.user_data['admin_mode'] = True
    else:
        context.user_data.clear()

    # Log admin entry attempt
    logger.info(f"Admin command initiated by user ID: {user_id}")

    # Check if user is admin or one of the approved users that can bypass password
    APPROVED_ADMINS = [ADMIN_ID, 6648598512, 7062972013]

    if user_id in APPROVED_ADMINS:
        # Set authentication status explicitly
        context.user_data['admin_authenticated'] = True
        # Initialize admin session data
        context.user_data['admin_session_start'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Show a welcome message for direct admin login
        await update.message.reply_text(
            "🔐 *ADMIN VERIFICATION* 🔐\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ *IDENTITY CONFIRMED*\n\n"
            "Welcome back, Administrator.\n"
            "Preparing your control panel...",
            parse_mode='Markdown'
        )

        # Skip to admin menu
        await show_admin_menu(update, context)
        return ADMIN_MENU

    # Enhanced security UI for password entry
    current_time = datetime.now().strftime('%H:%M:%S')

    await update.message.reply_text(
        "🔐 *ADMIN AUTHENTICATION* 🔐\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🕒 *Login Attempt:* {current_time}\n"
        f"👤 *User ID:* {user_id}\n\n"
        "⚠️ *SECURE AREA*\n"
        "This area is restricted to authorized personnel only.\n\n"
        "Please enter your administrative password:\n"
        "_(Your attempt is being logged)_",
        parse_mode='Markdown'
    )

    # No need to store password in context
    return ADMIN_AUTH

async def admin_password_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    entered_password = update.message.text
    user_id = update.effective_user.id

    # Check if user is blocked from admin panel
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_blocked_users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        await update.message.reply_text(
            "🚫 *ACCESS DENIED* 🚫\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "You are blocked from accessing the admin panel.\n"
            "Contact the main administrator if you believe this is an error.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    conn.close()

    # Check if the entered text is a reset command
    if entered_password.strip().lower() == "reset bot" and user_id == ADMIN_ID:
        return await restart_bot(update, context)

    # Check password with exact comparison
    if entered_password == ADMIN_PASSWORD:
        logger.info(f"Admin authentication successful for user ID: {user_id}")

        # Preserve any existing admin authentication from earlier sessions
        admin_authenticated = context.user_data.get('admin_authenticated', False)

        # Set authentication flag and timestamp
        context.user_data['admin_authenticated'] = True
        context.user_data['admin_session_start'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        context.user_data['admin_mode'] = True  # Flag to indicate we're in admin mode

        await update.message.reply_text(
            "✅ *AUTHENTICATION SUCCESSFUL*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Welcome to the admin control panel.\n"
            "Loading admin interface...",
            parse_mode='Markdown'
        )

        # Call admin menu function
        await show_admin_menu(update, context)

        # Explicitly return the ADMIN_MENU state to ensure transition
        return ADMIN_MENU
    else:
        logger.warning(f"Admin authentication failed for user ID: {update.effective_user.id}")
        await update.message.reply_text(
            "❌ *AUTHENTICATION FAILED*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Incorrect password. Please try again or type /cancel to abort.",
            parse_mode='Markdown'
        )
        return ADMIN_AUTH

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Check if this is an admin
    user_id = update.effective_user.id
    if user_id != ADMIN_ID and not context.user_data.get('admin_authenticated'):
        logger.warning(f"Unauthorized admin menu access attempt by user ID: {user_id}")

        # If this is a direct message, show unauthorized message
        if hasattr(update, 'message'):
            await update.message.reply_text(
                "❌ *UNAUTHORIZED*\n\n"
                "You don't have permission to access the admin menu.",
                parse_mode='Markdown'
            )
        return ConversationHandler.END

    # Get comprehensive stats for the dashboard
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Ensure authentication status is set
    context.user_data['admin_authenticated'] = True

    # Set or update admin session start time
    if 'admin_session_start' not in context.user_data:
        context.user_data['admin_session_start'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Count users, active today, and total media
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM daily_logins WHERE login_date = ?", (today,))
    active_today = cursor.fetchone()[0]

    # Count media directly from the media table
    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
    photo_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
    video_count = cursor.fetchone()[0]

    # Get total stars in circulation
    cursor.execute("SELECT SUM(stars) FROM users")
    total_stars = cursor.fetchone()[0] or 0

    # Get new users today
    cursor.execute("SELECT COUNT(*) FROM users WHERE registration_date = ?", (today,))
    new_users_today = cursor.fetchone()[0]

    # Get total transactions today
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE transaction_date = ?", (today,))
    transactions_today = cursor.fetchone()[0]

    conn.close()

    # Format current time for admin panel
    current_time = datetime.now().strftime('%H:%M:%S')
    current_date = datetime.now().strftime('%d %b %Y')

    admin_text = (
        "👑 *ADMIN DASHBOARD* 👑\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 *{current_date}* | ⏰ *{current_time}*\n\n"

        "📊 *PLATFORM METRICS*\n"
        f"• *Users:* {user_count} total | {active_today} active today | {new_users_today} new\n"
        f"• *Content:* {photo_count} photos | {video_count} videos\n"
        f"• *Economy:* {total_stars:.1f} ⭐ in circulation\n"
        f"• *Activity:* {transactions_today} transactions today\n\n"

        "Select a management option from the menu below:"
    )

    # Simplified admin panel keyboard
    keyboard_buttons = [
        # Content Management
        [KeyboardButton("➕ Add Video")],
        [KeyboardButton("🗑️ Delete Media")],

        # User Management
        [KeyboardButton("👥 User Management"), KeyboardButton("🔍 Search User")],
        [KeyboardButton("🚫 Block User"), KeyboardButton("🔓 Unblock User")],

        # Star Controls
        [KeyboardButton("⭐ Add Stars")],

        # Communications
        [KeyboardButton("📣 Broadcast Message")],

        # Navigation
        [KeyboardButton("🏠 Exit Admin Panel")]
    ]

    keyboard_markup = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True)

    # Handle both callback query and direct message
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(
            admin_text,
            parse_mode='Markdown'
        )
        # Send the keyboard separately
        await update.callback_query.message.reply_text(
            "Select an administrative function:",
            reply_markup=keyboard_markup
        )
        context.user_data['admin_keyboard_sent'] = 'yes'
    else:
        await update.message.reply_text(
            admin_text,
            parse_mode='Markdown'
        )
        # Send the keyboard separately
        await update.message.reply_text(
            "Select an administrative function:",
            reply_markup=keyboard_markup
        )
        context.user_data['admin_keyboard_sent'] = 'yes'

    # Map keyboard button texts to their specific actions
    context.user_data['admin_keyboard_map'] = {
        "➕ Add Video": "admin_add_video",
        "➕ Add Photo": "admin_add_photo",
        "🗑️ Delete Media": "admin_delete_media",
        "👥 User Management": "admin_user_list",
        "🔍 Search User": "admin_search_user",
        "⭐ Add Stars": "admin_add_stars",
        "❌ Remove Stars": "admin_remove_stars",
        "📣 Broadcast Message": "admin_broadcast",
        "🏠 Exit Admin Panel": "home"
    }

    return ADMIN_MENU

async def refresh_channel_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin function to refresh the channel media cache"""
    user_id = update.effective_user.id

    # Verify admin
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Only admins can use this function.")
        return

    # Clear existing cache
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channel_media_cache")
    conn.commit()
    conn.close()

    # Show loading message
    loading_msg = await update.message.reply_text(
        "🔄 *REFRESHING CHANNEL CACHE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please wait while we fetch all media from channels...\n"
        "This may take a few minutes depending on the amount of content.",
        parse_mode='Markdown'
    )

    try:
        # Fetch videos
        video_message_ids = await fetch_channel_media(context, VIDEO_CHANNEL_ID, "video")

        # Update loading message
        await loading_msg.edit_text(
            "🔄 *REFRESHING CHANNEL CACHE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Fetched {len(video_message_ids)} videos\n"
            "Fetching photos...",
            parse_mode='Markdown'
        )

        # Fetch photos
        photo_message_ids = await fetch_channel_media(context, PHOTO_CHANNEL_ID, "photo")

        # Complete
        await loading_msg.edit_text(
            "✅ *CHANNEL CACHE REFRESHED*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"• Videos cached: {len(video_message_ids)}\n"
            f"• Photos cached: {len(photo_message_ids)}\n\n"
            f"Total: {len(video_message_ids) + len(photo_message_ids)} items cached",
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error refreshing channel cache: {e}")
        await loading_msg.edit_text(
            "❌ *ERROR REFRESHING CACHE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"An error occurred: {str(e)}\n\n"
            "Please try again later.",
            parse_mode='Markdown'
        )

    # Return to admin menu
    await show_admin_menu(update, context)
    return ADMIN_MENU

async def show_channel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed statistics about channel content"""
    user_id = update.effective_user.id

    # Verify admin
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Only admins can use this function.")
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get video channel stats
    cursor.execute("SELECT COUNT(*) FROM channel_media_cache WHERE channel_id = ?", (VIDEO_CHANNEL_ID,))
    video_count = cursor.fetchone()[0]

    # Get photo channel stats
    cursor.execute("SELECT COUNT(*) FROM channel_media_cache WHERE channel_id = ?", (PHOTO_CHANNEL_ID,))
    photo_count = cursor.fetchone()[0]

    # Get view statistics
    cursor.execute("SELECT COUNT(*) FROM viewed_channel_media WHERE channel_id = ? AND media_type = 'video'", 
                  (VIDEO_CHANNEL_ID,))
    video_views = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM viewed_channel_media WHERE channel_id = ? AND media_type = 'photo'", 
                  (PHOTO_CHANNEL_ID,))
    photo_views = cursor.fetchone()[0]

    # Get today's views
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM viewed_channel_media WHERE view_date = ? AND media_type = 'video'", 
                  (today,))
    video_views_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM viewed_channel_media WHERE view_date = ? AND media_type = 'photo'", 
                  (today,))
    photo_views_today = cursor.fetchone()[0]

    # Get user counts
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM viewed_channel_media WHERE media_type = 'video'")
    video_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM viewed_channel_media WHERE media_type = 'photo'")
    photo_users = cursor.fetchone()[0]

    conn.close()

    # Format and send stats
    stats_text = (
        "📊 *CHANNEL STATISTICS* 📊\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🎬 *VIDEO CHANNEL*\n"
        f"• Total videos: {video_count}\n"
        f"• Total views: {video_views}\n"
        f"• Views today: {video_views_today}\n"
        f"• Unique viewers: {video_users}\n\n"

        "📷 *PHOTO CHANNEL*\n"
        f"• Total photos: {photo_count}\n"
        f"• Total views: {photo_views}\n"
        f"• Views today: {photo_views_today}\n"
        f"• Unique viewers: {photo_users}\n\n"

        "📋 *OVERALL*\n"
        f"• Total content: {video_count + photo_count} items\n"
        f"• Total views: {video_views + photo_views}\n"
        f"• Views today: {video_views_today + photo_views_today}\n\n"

        "Use the buttons below to navigate:"
    )

    # Create keyboard for navigation
    keyboard = [
        [KeyboardButton("🔄 Refresh Channel Cache")],
        [KeyboardButton("👥 User Management"), KeyboardButton("🔍 Search User")],
        [KeyboardButton("🏠 Back to Admin Menu")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    return ADMIN_MENU

async def view_media_details(update: Update, context: ContextTypes.DEFAULT_TYPE, media_id):
    """Show detailed view of a media item with delete option"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM media WHERE id = ?", (media_id,))
    media = cursor.fetchone()

    if not media:
        await update.callback_query.message.edit_text(
            "❌ *Media Not Found*\n\n"
            "The requested media item no longer exists.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Media List", callback_data="admin_delete_media")]
            ]),
            parse_mode='Markdown'
        )
        conn.close()
        return

    # Count bookmarks for this media
    cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE media_id = ?", (media_id,))
    bookmark_count = cursor.fetchone()[0]

    # Count downloads (approximate)
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE description LIKE ?", (f"Downloaded %{media_id}%",))
    download_count = cursor.fetchone()[0]

    media_id, media_type, file_id, caption, price, added_date, added_by = media if len(media) >= 7 else (*media, None, None)

    # Format date
    if added_date:
        try:
            date_obj = datetime.strptime(added_date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d %b %Y')
        except:
            formatted_date = added_date
    else:
        formatted_date = "Unknown"

    details_text = (
        f"📝 *MEDIA DETAILS - ID#{media_id}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*TYPE:* {'📷 Photo' if media_type == 'photo' else '🎬 Video'}\n"
        f"*PRICE:* {price} ⭐\n"
        f"*ADDED:* {formatted_date}\n\n"
        f"*CAPTION:*\n{caption}\n\n"
        f"*STATS:*\n"
        f"• Bookmarks: {bookmark_count}\n"
        f"• Downloads: {download_count}\n"
    )

    keyboard = [
        [InlineKeyboardButton("🗑️ DELETE THIS MEDIA", callback_data=f"admin_delete_media_{media_id}")],
        [InlineKeyboardButton("🔙 Back to Media List", callback_data="admin_delete_media")]
    ]

    conn.close()

    await update.callback_query.message.edit_text(
        details_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# Add function for mass deletion
async def show_mass_delete_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show options for mass deletion of media"""
    # Create keyboard buttons with ReplyKeyboardMarkup for consistency
    keyboard = [
        [KeyboardButton("🗑️ Delete All Photos")],
        [KeyboardButton("🗑️ Delete All Videos")],
        [KeyboardButton("🗑️ Delete Media Older Than 30 Days")],
        [KeyboardButton("🗑️ Delete Zero-Bookmark Media")],
        [KeyboardButton("❌ CANCEL")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Store the fact we're in mass delete mode to handle the button presses
    context.user_data['mass_delete_mode'] = True

    await update.message.reply_text(
        "⚠️ *MASS DELETE OPTIONS* ⚠️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ WARNING: These actions cannot be undone!\n\n"
        "Select an option to mass delete media:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return ADMIN_DELETE_MEDIA

# Add function to handle mass deletion confirmation and execution from text buttons
async def handle_mass_delete_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mass deletion of media based on button text"""
    text = update.message.text

    if text == "❌ CANCEL":
        # User cancelled, go back to media management
        context.user_data.pop('mass_delete_mode', None)
        await show_media_for_deletion(update, context)
        return ADMIN_DELETE_MEDIA

    # Determine delete type from button text
    delete_type = None
    if text == "🗑️ Delete All Photos":
        delete_type = "photos"
    elif text == "🗑️ Delete All Videos":
        delete_type = "videos"
    elif text == "🗑️ Delete Media Older Than 30 Days":
        delete_type = "old"
    elif text == "🗑️ Delete Zero-Bookmark Media":
        delete_type = "no_bookmarks"

    if not delete_type:
        # Unknown button, go back to mass delete options
        await show_mass_delete_options(update, context)
        return ADMIN_DELETE_MEDIA

    # Ask for confirmation before proceeding
    context.user_data['pending_mass_delete'] = delete_type

    keyboard = [
        [KeyboardButton("✅ YES, DELETE")],
        [KeyboardButton("❌ NO, CANCEL")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Show confirmation message with details about what will be deleted
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')
    today_date = datetime.now()
    thirty_days_ago = (today_date - timedelta(days=30)).strftime('%Y-%m-%d')

    item_count = 0
    confirmation_details = ""

    if delete_type == "photos":
        cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
        item_count = cursor.fetchone()[0]
        confirmation_details = f"all {item_count} photos"

    elif delete_type == "videos":
        cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
        item_count = cursor.fetchone()[0]
        confirmation_details = f"all {item_count} videos"

    elif delete_type == "old":
        cursor.execute("SELECT COUNT(*) FROM media WHERE added_date < ?", (thirty_days_ago,))
        item_count = cursor.fetchone()[0]
        confirmation_details = f"{item_count} media items older than 30 days"

    elif delete_type == "no_bookmarks":
        cursor.execute("SELECT COUNT(*) FROM media WHERE id NOT IN (SELECT DISTINCT media_id FROM bookmarks)")
        item_count = cursor.fetchone()[0]
        confirmation_details = f"{item_count} media items with no bookmarks"

    conn.close()

    await update.message.reply_text(
        f"⚠️ *CONFIRM MASS DELETION* ⚠️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"You are about to delete {confirmation_details}.\n\n"
        f"*This action cannot be undone!*\n\n"
        f"Are you absolutely sure you want to proceed?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    # Set state to handle confirmation
    context.user_data['awaiting_mass_delete_confirmation'] = True
    return ADMIN_DELETE_MEDIA

# Function to handle mass delete confirmation
async def execute_mass_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute mass deletion after confirmation"""
    text = update.message.text

    # Check if we're awaiting confirmation
    if not context.user_data.get('awaiting_mass_delete_confirmation'):
        return ADMIN_DELETE_MEDIA

    # Clear confirmation flag
    context.user_data.pop('awaiting_mass_delete_confirmation', None)

    # Check the response
    if text != "✅ YES, DELETE":
        # User cancelled
        await update.message.reply_text(
            "🛑 *DELETION CANCELLED*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Mass deletion has been cancelled.\nNo media was deleted.",
            parse_mode='Markdown'
        )
        # Return to media management
        await show_media_for_deletion(update, context)
        return ADMIN_DELETE_MEDIA

    # Proceed with deletion
    delete_type = context.user_data.pop('pending_mass_delete', None)
    if not delete_type:
        # Something went wrong, return to media management
        await show_media_for_deletion(update, context)
        return ADMIN_DELETE_MEDIA

    # Show processing message
    processing_msg = await update.message.reply_text(
        "⏳ *PROCESSING MASS DELETION*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please wait while your request is being processed...",
        parse_mode='Markdown'
    )

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')
    today_date = datetime.now()
    thirty_days_ago = (today_date - timedelta(days=30)).strftime('%Y-%m-%d')

    count = 0
    if delete_type == "photos":
        cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
        count = cursor.fetchone()[0]

        # Delete all photos
        cursor.execute("DELETE FROM media WHERE type = 'photo'")

        # Delete related bookmarks
        cursor.execute("DELETE FROM bookmarks WHERE media_id IN (SELECT id FROM media WHERE type = 'photo')")

    elif delete_type == "videos":
        cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
        count = cursor.fetchone()[0]

        # Delete all videos
        cursor.execute("DELETE FROM media WHERE type = 'video'")

        # Delete related bookmarks
        cursor.execute("DELETE FROM bookmarks WHERE media_id IN (SELECT id FROM media WHERE type = 'video')")

    elif delete_type == "old":
        cursor.execute("SELECT COUNT(*) FROM media WHERE added_date < ?", (thirty_days_ago,))
        count = cursor.fetchone()[0]

        # Delete old media
        cursor.execute("DELETE FROM media WHERE added_date < ?", (thirty_days_ago,))

        # Delete related bookmarks
        cursor.execute("DELETE FROM bookmarks WHERE media_id NOT IN (SELECT id FROM media)")

    elif delete_type == "no_bookmarks":
        cursor.execute("SELECT COUNT(*) FROM media WHERE id NOT IN (SELECT DISTINCT media_id FROM bookmarks)")
        count = cursor.fetchone()[0]

        # Delete media with no bookmarks
        cursor.execute("DELETE FROM media WHERE id NOT IN (SELECT DISTINCT media_id FROM bookmarks)")

    # Log the action
    admin_id = update.effective_user.id
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (admin_id, "MASS_DELETE", f"Mass deleted {count} media items of type {delete_type}", today)
    )

    conn.commit()

    # Get updated media counts
    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
    photo_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
    video_count = cursor.fetchone()[0]

    conn.close()

    # Update the processing message with results
    await processing_msg.edit_text(
        f"✅ *MASS DELETE SUCCESSFUL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Successfully deleted {count} {delete_type.replace('_', ' ')}.\n\n"
        f"*REMAINING MEDIA:*\n"
        f"• Photos: {photo_count}\n"
        f"• Videos: {video_count}\n"
        f"• Total: {photo_count + video_count}\n\n"
        f"All associated bookmarks have also been removed.",
        parse_mode='Markdown'
    )

    # Return to media management
    keyboard = [
        [KeyboardButton("🔍 Search by ID"), KeyboardButton("♻️ Mass Delete")],
        [KeyboardButton("🔙 Back to Admin Menu")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Select an action to continue:",
        reply_markup=reply_markup
    )

    # Clear mass delete mode
    context.user_data.pop('mass_delete_mode', None)

    return ADMIN_DELETE_MEDIA

# Add new states for admin conversation handler
(ADMIN_SEARCH_USER, ADMIN_SEARCH_MEDIA, ADMIN_QUICK_STAR_ADD, ADMIN_BOT_SETTINGS, 
 ADMIN_ADD_STARS, ADMIN_REMOVE_STARS, ADMIN_BROADCAST_CONFIRM) = range(27, 34)

async def admin_handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Handle either callback query or direct message from admin panel
    is_text_message = False
    user_id = update.effective_user.id

    # Define approved admins list
    APPROVED_ADMINS = [ADMIN_ID, 6648598512, 7062972013]

    # Force admin check for security
    if user_id not in APPROVED_ADMINS:
        context.user_data['admin_authenticated'] = True
        context.user_data['admin_mode'] = True

    # Additional security check
    if not context.user_data.get('admin_authenticated'):
        logger.warning(f"Unauthorized admin action attempt from user ID: {user_id}")
        if hasattr(update, 'message'):
            await update.message.reply_text(
                "⚠️ *UNAUTHORIZED ACCESS*\n\n"
                "You don't have permission to access the admin panel.",
                parse_mode='Markdown'
            )
        return ConversationHandler.END

    # Handle direct button presses
    if hasattr(update, 'message') and update.message.text:
        text = update.message.text

        if text == "⭐ Add Stars":
            await update.message.reply_text(
                "⭐ *ADD STARS*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID/username and amount of stars to add.\n"
                "Format: `username/ID amount`\n"
                "Example: `@username 10` or `123456789 10`",
                parse_mode='Markdown'
            )
            context.user_data['star_operation'] = 'add'
            return ADMIN_QUICK_STAR_ADD

        elif text == "❌ Remove Stars":
            await update.message.reply_text(
                "🔄 *REMOVE STARS*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID/username and amount of stars to remove.\n"
                "Format: `username/ID amount`\n"
                "Example: `@username 10` or `123456789 10`",
                parse_mode='Markdown'
            )
            context.user_data['star_operation'] = 'remove'
            return ADMIN_QUICK_STAR_ADD

        elif text == "👥 User Management":
            logger.info("User Management button pressed")
            await show_users_list(update, context)
            return ADMIN_MENU

        elif text == "📣 Broadcast Message":
            await update.message.reply_text(
                "📣 *SEND BROADCAST MESSAGE*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the message you want to broadcast to all users:",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_broadcast_text'] = True
            return ADMIN_BROADCAST

        elif text == "🚫 Block User":
            await update.message.reply_text(
                "🚫 *BLOCK USER FROM BOT*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the User ID of the user you want to block from using the bot:",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'block_user'
            return ADMIN_SEARCH_USER

        elif text == "🔓 Unblock User":
            await update.message.reply_text(
                "🔓 *UNBLOCK USER FROM BOT*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the User ID of the user you want to unblock:",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'unblock_user'
            return ADMIN_SEARCH_USER

        elif text.startswith("👤 Manage User ID: "):
            try:
                target_user_id = int(text.replace("👤 Manage User ID: ", "").strip())
                await search_user_by_id(update, context, target_user_id)
                return ADMIN_MENU
            except ValueError:
                await update.message.reply_text(
                    "❌ *ERROR*\n\nInvalid user ID format.",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        action = query.data
    else:
        # This is a direct text message, map it to action
        is_text_message = True
        button_text = update.message.text

        # Log button press for debugging
        logger.info(f"Admin button pressed: {button_text}")

        # Comprehensive mapping for all admin buttons
        button_mapping = {
            "➕ Add Video": "admin_add_video",
            "➕ Add Photo": "admin_add_photo", 
            "🗑️ Delete Media": "admin_delete_media",
            "🔍 Search User": "admin_search_user",
            "👥 User Management": "admin_user_list",
            "⭐ Add Stars": "admin_add_stars",
            "❌ Remove Stars": "admin_remove_stars",
            "🔄 Remove Stars": "admin_remove_stars",
            "📣 Broadcast Message": "admin_broadcast",
            "📣 Broadcast": "admin_broadcast",
            "🏠 Exit Admin Panel": "home",
            "🏠 Home": "home",
            "🔙 Back to Admin Menu": "admin_back_to_menu"
        }

        # Get action from button mapping
        action = button_mapping.get(button_text)

        # Debugging: log the message and action
        logger.info(f"Admin text message: '{button_text}', mapped action: {action}")

        # Special handling for direct text messages in admin panel
        if button_text == "🏠 Home" or button_text == "🏠 Exit Admin Panel":
            # Preserve admin authentication but clear other data
            admin_authenticated = context.user_data.get('admin_authenticated', False)
            admin_session_start = context.user_data.get('admin_session_start', None)

            # Clear only non-authentication data
            keys_to_remove = [k for k in context.user_data.keys() if k not in ['admin_authenticated', 'admin_session_start']]
            for key in keys_to_remove:
                context.user_data.pop(key, None)

            # Restore admin authentication
            if admin_authenticated:
                context.user_data['admin_authenticated'] = admin_authenticated
                context.user_data['admin_session_start'] = admin_session_start

            await show_home_menu(update, context)
            return ConversationHandler.END

    # Handle media filtering and pagination
    if action == "admin_filter_media_all":
        context.user_data['media_filter_type'] = 'all'
        context.user_data['media_page'] = 1
        await show_media_for_deletion(update, context)
        return ADMIN_MENU

    elif action == "admin_filter_media_photo":
        context.user_data['media_filter_type'] = 'photo'
        context.user_data['media_page'] = 1
        await show_media_for_deletion(update, context)
        return ADMIN_MENU

    elif action == "admin_filter_media_video":
        context.user_data['media_filter_type'] = 'video'
        context.user_data['media_page'] = 1
        await show_media_for_deletion(update, context)
        return ADMIN_MENU

    elif action == "admin_media_prev_page":
        current_page = context.user_data.get('media_page', 1)
        if current_page > 1:
            context.user_data['media_page'] = current_page - 1
        await show_media_for_deletion(update, context)
        return ADMIN_MENU

    elif action == "admin_media_next_page":
        current_page = context.user_data.get('media_page', 1)
        context.user_data['media_page'] = current_page + 1
        await show_media_for_deletion(update, context)
        return ADMIN_MENU

    elif action.startswith("admin_view_media_"):
        media_id = int(action.split("_")[-1])
        await view_media_details(update, context, media_id)
        return ADMIN_MENU

        if not action:
            # Check specific buttons that might not be mapped correctly
            if update.message.text == "📣 Broadcast":
                action = "admin_broadcast"
            elif update.message.text == "➕ Add Video":
                action = "admin_add_video"
            elif update.message.text == "➕ Add Photo":
                action = "admin_add_photo"
            elif update.message.text == "🔍 Search User":
                action = "admin_search_user"
            elif update.message.text == "🗑️ Delete Media":
                action = "admin_delete_media"
            elif update.message.text == "📋 User List":
                action = "admin_user_list"
            elif update.message.text == "⭐ Add Stars":
                action = "admin_add_stars"
            elif update.message.text == "🔄 Remove Stars":
                action = "admin_remove_stars"

    if not action:
        if is_text_message:
            await update.message.reply_text(
                "⚠️ Unknown command. Please use the keyboard buttons provided.",
                parse_mode='Markdown'
            )
        return ADMIN_MENU

    # Handle adding video
    if action == "admin_add_video":
        if is_text_message:
            await update.message.reply_text(
                "🎬 *ADD NEW VIDEO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please send the video you want to add to the bot:",
                parse_mode='Markdown'
            )
        else:
            await query.message.edit_text(
                "🎬 *ADD NEW VIDEO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please send the video you want to add to the bot:",
                parse_mode='Markdown'
            )
        return ADD_VIDEO

    # Handle adding photo
    elif action == "admin_add_photo":
        if is_text_message:
            await update.message.reply_text(
                "📷 *ADD NEW PHOTO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please send the photo you want to add to the bot:",
                parse_mode='Markdown'
            )
        else:
            await query.message.edit_text(
                "📷 *ADD NEW PHOTO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please send the photo you want to add to the bot:",
                parse_mode='Markdown'
            )
        return ADD_PHOTO

    # Handle delete media
    elif action == "admin_delete_media":
        await show_media_for_deletion(update, context)
        return ADMIN_DELETE_MEDIA

    elif action == "admin_mass_delete":
        await show_mass_delete_options(update, context)
        return ADMIN_MENU

    elif action == "admin_mass_delete_photos":
        await handle_mass_delete(update, context, "photos")
        return ADMIN_MENU

    elif action == "admin_mass_delete_videos":
        await handle_mass_delete(update, context, "videos")
        return ADMIN_MENU

    elif action == "admin_mass_delete_old":
        await handle_mass_delete(update, context, "old")
        return ADMIN_MENU

    elif action == "admin_mass_delete_no_bookmarks":
        await handle_mass_delete(update, context, "no_bookmarks")
        return ADMIN_MENU

    # Handle user list
    elif action == "admin_user_list" or (is_text_message and update.message.text == "👥 User Management"):
        logger.info("Handling admin_user_list action or User Management button")
        if is_text_message:
            # For direct button press, use a dedicated path
            await show_users_list(update, context)
        else:
            # For callback query, edit existing message
            await show_users_list(update, context)
        return ADMIN_MENU

    # Handle search user
    elif action == "admin_search_user":
        if is_text_message:
            await update.message.reply_text(
                "🔍 *SEARCH USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter a username, name, or User ID to search for a specific user:",
                parse_mode='Markdown'
            )
        else:
            await query.message.edit_text(
                "🔍 *SEARCH USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter a username, name, or User ID to search for a specific user:",
                parse_mode='Markdown'
            )
        return ADMIN_SEARCH_USER

    # Handle add stars to user
    elif action == "admin_add_stars" or update.message.text == "⭐ Add Stars" if is_text_message else False:
        if is_text_message:
            await update.message.reply_text(
                "⭐ *ADD STARS TO USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID or username followed by the number of stars to add.\n"
                "Format: `user_id/username amount`\n\n"
                "Example: `123456789 10` or `@username 10`",
                parse_mode='Markdown'
            )
        else:
            await query.message.edit_text(
                "⭐ *ADD STARS TO USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID or username followed by the number of stars to add.\n"
                "Format: `user_id/username amount`\n\n"
                "Example: `123456789 10` or `@username 10`",
                parse_mode='Markdown'
            )
        # Make sure to remember this is a star addition operation
        context.user_data['admin_action'] = 'add_stars'
        context.user_data['star_operation'] = 'add'
        return ADMIN_QUICK_STAR_ADD

    # Handle remove stars from user
    elif action == "admin_remove_stars" or update.message.text == "❌ Remove Stars" if is_text_message else False:
        if is_text_message:
            await update.message.reply_text(
                "🔄 *REMOVE STARS FROM USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID or username followed by the number of stars to remove.\n"
                "Format: `user_id/username amount`\n\n"
                "Example: `123456789 10` or `@username 10`",
                parse_mode='Markdown'
            )
        else:
            await query.message.edit_text(
                "🔄 *REMOVE STARS FROM USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID or username followed by the number of stars to remove.\n"
                "Format: `user_id/username amount`\n\n"
                "Example: `123456789 10` or `@username 10`",
                parse_mode='Markdown'
            )
        # Mark this as a star removal operation and track the admin action
        context.user_data['admin_action'] = 'remove_stars'
        context.user_data['star_operation'] = 'remove'
        return ADMIN_QUICK_STAR_ADD

    # Handle broadcast message
    elif action == "admin_broadcast" or text == "📣 Broadcast Message":
        await update.message.reply_text(
            "📣 *SEND BROADCAST MESSAGE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter the message you want to broadcast to all users:",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_broadcast_text'] = True
        return ADMIN_BROADCAST

    # Handle going back to main menu
    elif action == "home" or (is_text_message and (update.message.text == "🏠 Home" or update.message.text == "🏠 Exit Admin Panel")):
        # Preserve admin authentication status
        admin_authenticated = context.user_data.get('admin_authenticated', False)
        admin_session_start = context.user_data.get('admin_session_start', None)

        # Only clear navigation data, not authentication status
        navigation_keys = [k for k in context.user_data.keys() if k not in ['admin_authenticated', 'admin_session_start']]
        for key in navigation_keys:
            if key in context.user_data:
                del context.user_data[key]

        # Restore admin authentication if it was set
        if admin_authenticated:
            context.user_data['admin_authenticated'] = admin_authenticated
            context.user_data['admin_session_start'] = admin_session_start

        await show_home_menu(update, context)
        return ConversationHandler.END

    # Handle going back to admin menu
    elif action == "admin_back_to_menu":
        await show_admin_menu(update, context)
        return ADMIN_MENU

    # Handle clear warnings feature
    elif action.startswith("admin_clear_warnings_"):
        user_id = int(action.split("_")[-1])

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Get user info before clearing
        cursor.execute("SELECT name, username, warnings FROM users WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            conn.close()
            await query.message.edit_text(
                "❌ *Error*\n\nUser not found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_warning_management")]]),
                parse_mode='Markdown'
            )
            return ADMIN_MENU

        name, username, warnings = user_info

        # Clear warnings
        cursor.execute("UPDATE users SET warnings = 0 WHERE user_id = ?", (user_id,))

        # Log the action
        admin_id = update.effective_user.id
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "WARNINGS_CLEARED", f"Warnings cleared by admin ID {admin_id}", today)
        )

        conn.commit()
        conn.close()

        # Notify the admin
        await query.message.edit_text(
            f"✅ *Warnings Cleared Successfully*\n\n"
            f"*User:* {name} (@{username})\n"
            f"*Previous Warnings:* {warnings}\n"
            f"*Current Warnings:* 0\n\n"
            f"All warnings have been cleared for this user.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Warning Management", callback_data="admin_warning_management")]]),
            parse_mode='Markdown'
        )

        # Try to notify the user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ *WARNINGS CLEARED* ✅\n\n"
                    f"All your previous warnings have been cleared by an administrator.\n"
                    f"You now have 0 warnings on your account.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send warning clear notification to user {user_id}: {e}")

        return ADMIN_MENU

    # Handle additional admin actions
    elif action.startswith("admin_warn_user_"):
        user_id = int(action.split("_")[-1])
        context.user_data['target_user_id'] = user_id

        await query.message.edit_text(
            f"⚠️ *Issue Warning to User ID: {user_id}*\n\n"
            f"Please enter the warning reason:",
            parse_mode='Markdown'
        )
        return WARN_USER

    elif action.startswith("admin_manage_user_"):
        user_id = int(action.split("_")[-1])

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Get comprehensive user info
        cursor.execute("""
            SELECT u.*, 
                (SELECT COUNT(*) FROM bookmarks WHERE user_id = u.user_id) as bookmark_count,
                (SELECT COUNT(*) FROM transactions WHERE user_id = u.user_id AND amount < 0) as download_count,
                (SELECT COUNT(*) FROM daily_logins WHERE user_id = u.user_id) as login_count
            FROM users u WHERE u.user_id = ?
        """, (user_id,))

        user = cursor.fetchone()
        conn.close()

        if not user:
            await query.message.edit_text(
                "❌ *Error*\n\nUser not found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_user_management")]]),
                parse_mode='Markdown'
            )
            return ADMIN_MENU

        # Parse user data
        name = user[1]
        age = user[2]
        username = user[3]
        stars = user[4]
        reg_date = user[5]
        last_login = user[6]
        is_banned = user[9]
        warnings = user[10]
        ban_reason = user[11] or "None"
        bookmark_count = user[12]
        download_count = user[13]
        login_count = user[14]

        # Calculate days as member
        reg_date_obj = datetime.strptime(reg_date, '%Y-%m-%d')
        days_member = (datetime.now() - reg_date_obj).days

        # Create user management options
        keyboard = [
            [InlineKeyboardButton("➕ Add Stars", callback_data=f"admin_add_stars_{user_id}"),
             InlineKeyboardButton("➖ Remove Stars", callback_data=f"admin_remove_stars_{user_id}")],
            [InlineKeyboardButton(f"{'🔓 Unban' if is_banned else '🚫 Ban'}", 
                                callback_data=f"{'admin_unban_user_' if is_banned else 'admin_ban_user_'}{user_id}"),
             InlineKeyboardButton("⚠️ Warn", callback_data=f"admin_warn_user_{user_id}")],
            [InlineKeyboardButton("🔄 Clear Warnings", callback_data=f"admin_clear_warnings_{user_id}")],
            [InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_user_management")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Format the user details
        user_text = (
            f"👤 *USER DETAILS*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            f"*BASIC INFO*\n"
            f"• ID: {user_id}\n"
            f"• Name: {name}\n"
            f"• Username: @{username}\n"
            f"• Age: {age}\n"
            f"• Stars: {stars} ⭐\n"
            f"• Status: {'🚫 BANNED' if is_banned else '✅ ACTIVE'}\n\n"

            f"*ACTIVITY INFO*\n"
            f"• Registered: {reg_date} ({days_member} days ago)\n"
            f"• Last login: {last_login}\n"
            f"• Total logins: {login_count}\n"
            f"• Downloads: {download_count}\n"
            f"• Bookmarks: {bookmark_count}\n"
            f"• Warnings: {warnings}\n\n"

            f"*ADMINISTRATIVE*\n"
            f"• Ban reason: {ban_reason}"
        )

        await query.message.edit_text(
            user_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ADMIN_MENU

    # Default fallback - return to admin menu
    else:
        if is_text_message:
            await update.message.reply_text(
                "⚠️ That function has been removed or is not available. Please use the provided buttons.",
                parse_mode='Markdown'
            )
        await show_admin_menu(update, context)
        return ADMIN_MENU

async def process_add_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Check admin authentication
    user_id = update.effective_user.id

    # Define approved admins list
    APPROVED_ADMINS = [ADMIN_ID, 6648598512, 7062972013]

    # Force admin authentication check to prevent unauthorized access
    if user_id not in APPROVED_ADMINS and not context.user_data.get('admin_authenticated'):
        logger.warning(f"Unauthorized video upload attempt by user ID: {user_id}")
        await update.message.reply_text(
            "⚠️ *UNAUTHORIZED ACCESS*\n\n"
            "You don't have permission to add videos.\n"
            "This incident has been logged.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Log what type of message we received
    has_video = hasattr(update.message, 'video') and update.message.video
    has_document = hasattr(update.message, 'document') and update.message.document
    has_text = hasattr(update.message, 'text')

    logger.info(f"Process add video: message attributes: video={has_video}, document={has_document}, text={has_text}")

    # Check if user sent /done command
    if has_text and update.message.text == "/done":
        return await process_done_command(update, context)

    # Check if this is a text message but not a video or document
    if has_text and not has_video and not has_document:
        await update.message.reply_text(
            "❌ *VIDEO EXPECTED*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send a video file. Text messages are not accepted here.\n\n"
            "Use the 📎 attachment button to send a video, or type /done when finished.",
            parse_mode='Markdown'
        )
        return ADD_VIDEO

    # Process video file with better error handling
    file_id = None
    if has_video:
        logger.info(f"Processing video: {update.message.video.file_id}")
        file_id = update.message.video.file_id
    elif has_document:
        logger.info(f"Processing document: {update.message.document.file_id}, mime_type: {update.message.document.mime_type}")
        # Accept any document as video for better compatibility
        file_id = update.message.document.file_id

    if not file_id:
        logger.error("Could not extract file_id from message")
        await update.message.reply_text(
            "❌ *INVALID FILE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send a valid video file.",
            parse_mode='Markdown'
        )
        return ADD_VIDEO

    # Get caption
    caption = update.message.caption or f"Premium video content #{context.user_data.get('mass_upload_count', 0) + 1}"
    price = 1.0  # Fixed price for videos
    today = datetime.now().strftime('%Y-%m-%d')

    # Send an initial acknowledgment
    processing_message = await update.message.reply_text(
        "⏳ *PROCESSING VIDEO*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Your video is being processed and saved to the database...",
        parse_mode='Markdown'
    )

    try:
        # Save to database
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Log what we're trying to insert
        logger.info(f"Inserting video: type='video', file_id='{file_id}', caption='{caption}', price={price}, date='{today}', user_id={user_id}")

        # Insert video
        cursor.execute(
            "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
            ('video', file_id, caption, price, today, user_id)
        )
        media_id = cursor.lastrowid

        # Log the addition
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "MEDIA_ADDED", f"Added video #{media_id}", today)
        )

        # Make sure we commit the transaction
        conn.commit()
        logger.info(f"Successfully inserted video with ID: {media_id}")

        # Verify the insert worked
        cursor.execute("SELECT id, file_id FROM media WHERE id = ?", (media_id,))
        verification = cursor.fetchone()
        logger.info(f"Verification of insert: {verification}")

        conn.close()

        # Increment upload counter
        context.user_data['mass_upload_count'] = context.user_data.get('mass_upload_count', 0) + 1
        context.user_data['media_type'] = 'video'

        # Send confirmation
        success_message = (
            f"✅ *VIDEO ADDED SUCCESSFULLY* ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*ID:* #{media_id}\n"
            f"*Caption:* {caption}\n"
            f"*Price:* {price} ⭐\n\n"
            f"Send more videos or type /done when finished."
        )

        # Try to edit the processing message first
        try:
            await processing_message.edit_text(success_message, parse_mode='Markdown')
        except Exception as edit_error:
            # If editing fails, send a new message
            logger.error(f"Error editing message: {edit_error}")
            await update.message.reply_text(success_message, parse_mode='Markdown')

        return ADD_VIDEO

    except Exception as e:
        logger.error(f"Error adding video: {e}")

        # Try to edit the processing message first
        try:
            await processing_message.edit_text(
                "❌ *ERROR ADDING VIDEO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact support.",
                parse_mode='Markdown'
            )
        except Exception as edit_error:
            # If editing fails, send a new message
            logger.error(f"Error editing message: {edit_error}")
            await update.message.reply_text(
                "❌ *ERROR ADDING VIDEO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact support.",
                parse_mode='Markdown'
            )

        return ADD_VIDEO

async def handle_download_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, media_id):
    """Handle download request from text button"""
    user_id = update.effective_user.id

    # Get user stars and media info
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get full user information
    cursor.execute("SELECT name, stars FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        await update.message.reply_text(
            "⚠️ *ACCOUNT REQUIRED* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "You need to register before downloading content.\n"
            "Please use /start to create your account.",
            parse_mode='Markdown'
        )
        return

    name, user_stars = user

    # Get detailed media information
    cursor.execute("SELECT * FROM media WHERE id = ?", (media_id,))
    media = cursor.fetchone()

    if not media:
        conn.close()
        await update.message.reply_text(
            "⚠️ *CONTENT UNAVAILABLE* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "This item is no longer available in our collection.\n"
            "Please browse our current content for alternatives.",
            parse_mode='Markdown'
        )
        return

    # Extract media details
    media_id, media_type, file_id, caption, price = media[0], media[1], media[2], media[3], media[4]

    # Format media type for better presentation
    media_type_display = "Photo" if media_type == "photo" else "Video"

    # Check if user has enough stars
    if user_stars < price:
        conn.close()

        missing_stars = price - user_stars

        # Create an elegant insufficient funds message
        insufficient_text = (
            "💫 *PREMIUM CONTENT* 💫\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Hello, *{name}*!\n\n"
            f"This {media_type_display.lower()} requires additional stars to download.\n\n"
            f"🔸 *Price:* {price} ⭐\n"
            f"🔸 *Your Balance:* {user_stars} ⭐\n"
            f"🔸 *Needed:* {missing_stars} ⭐\n\n"
            f"Would you like to add more stars to your account?"
        )

        await update.message.reply_text(
            insufficient_text,
            parse_mode='Markdown'
        )
        return

    # Deduct stars
    cursor.execute("UPDATE users SET stars = stars - ? WHERE user_id = ?", (price, user_id))

    # Get new balance for the receipt
    new_balance = user_stars - price

    # Record transaction with more detail
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%H:%M:%S')
    transaction_id = f"{user_id}{int(datetime.now().timestamp())}"[-8:]

    cursor.execute(
        "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
        (user_id, -price, f"Downloaded {media_type} #{media_id}", today)
    )

    # Log activity
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "DOWNLOAD", f"Downloaded {media_type} #{media_id}", today)
    )

    conn.commit()
    conn.close()

    # Send downloadable media with an elegant receipt-like message
    download_caption = (
        f"✅ *DOWNLOAD COMPLETE* ✅\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*DESCRIPTION:*\n{caption}\n\n"
        f"📋 *PURCHASE DETAILS*\n"
        f"• Transaction ID: #{transaction_id}\n"
        f"• Item: Premium {media_type_display}\n"
        f"• Price: {price} ⭐\n"
        f"• New Balance: {new_balance} ⭐\n"
        f"• Date: {today} at {timestamp}\n\n"
        f"Thank you for your purchase, *{name}*!\n"
        f"Enjoy your premium content."
    )

    if media_type == "photo":
        await update.message.reply_photo(
            photo=file_id,
            caption=download_caption,
            parse_mode='Markdown',
            protect_content=False
        )
    else:
        await update.message.reply_video(
            video=file_id,
            caption=download_caption,
            parse_mode='Markdown',
            protect_content=False
        )

    # Show success message
    await update.message.reply_text(
        f"✅ Downloaded successfully! Spent {price} ⭐",
        parse_mode='Markdown'
    )

async def handle_bookmark_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, media_id, user_id):
    """Handle bookmark request from text button"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Check if already bookmarked
    cursor.execute("SELECT * FROM bookmarks WHERE user_id = ? AND media_id = ?", (user_id, media_id))
    bookmark = cursor.fetchone()

    today = datetime.now().strftime('%Y-%m-%d')

    if bookmark:
        # Remove bookmark
        cursor.execute("DELETE FROM bookmarks WHERE user_id = ? AND media_id = ?", (user_id, media_id))
        message = "🔖 Bookmark removed!"

        # Log activity
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "BOOKMARK_REMOVE", f"Removed bookmark for media #{media_id}", today)
        )

        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"✅ *{message}*",
            parse_mode='Markdown'
        )
    else:
        # Check if user has purchased this media
        cursor.execute(
            "SELECT * FROM transactions WHERE user_id = ? AND description LIKE ? AND amount < 0", 
            (user_id, f"Downloaded %{media_id}%")
        )
        purchase_record = cursor.fetchone()

        if not purchase_record:
            conn.close()
            await update.message.reply_text(
                "❌ *PURCHASE REQUIRED* ❌\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "You need to purchase and download this content before you can bookmark it.\n\n"
                "Please use the 'Purchase' button first.",
                parse_mode='Markdown'
            )
            return

        # Add bookmark after purchase is verified
        cursor.execute(
            "INSERT INTO bookmarks (user_id, media_id, bookmark_date) VALUES (?, ?, ?)", 
            (user_id, media_id, today)
        )
        message = "🔖 Bookmark added!"

        # Log activity
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "BOOKMARK_ADD", f"Added bookmark for media #{media_id}", today)
        )

        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"✅ *{message}*",
            parse_mode='Markdown'
        )


        cursor = conn.cursor()

        # Log what we're trying to insert
        logger.info(f"Inserting video: type='video', file_id='{file_id}', caption='{caption}', price={price}, date='{today}', user_id={user_id}")

        # Insert video
        cursor.execute(
            "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
            ('video', file_id, caption, price, today, user_id)
        )
        media_id = cursor.lastrowid

        # Log the addition
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "MEDIA_ADDED", f"Added video #{media_id}", today)
        )

        # Make sure we commit the transaction
        conn.commit()
        logger.info(f"Successfully inserted video with ID: {media_id}")

        # Verify the insert worked
        cursor.execute("SELECT id, file_id FROM media WHERE id = ?", (media_id,))
        verification = cursor.fetchone()
        logger.info(f"Verification of insert: {verification}")

        conn.close()

        # Increment upload counter
        context.user_data['mass_upload_count'] = context.user_data.get('mass_upload_count', 0) + 1
        context.user_data['media_type'] = 'video'

        # Send confirmation
        success_message = (
            f"✅ *VIDEO ADDED SUCCESSFULLY* ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*ID:* #{media_id}\n"
            f"*Caption:* {caption}\n"
            f"*Price:* {price} ⭐\n\n"
            f"Send more videos or type /done when finished."
        )

        # Try to edit the processing message first
        try:
            await processing_message.edit_text(success_message, parse_mode='Markdown')
        except Exception as edit_error:
            # If editing fails, send a new message
            logger.error(f"Error editing message: {edit_error}")
            await update.message.reply_text(success_message, parse_mode='Markdown')

        return ADD_VIDEO


        # Try to edit the processing message first
        try:
            await processing_message.edit_text(
                "❌ *ERROR ADDING VIDEO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact support.",
                parse_mode='Markdown'
            )
        except Exception as edit_error:
            # If editing fails, send a new message
            logger.error(f"Error editing message: {edit_error}")
            await update.message.reply_text(
                "❌ *ERROR ADDING VIDEO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact support.",
                parse_mode='Markdown'
            )

        return ADD_VIDEO

    # Log the entry point for debugging
    logger.info(f"Admin video upload: user_id={user_id}, has_video={hasattr(update.message, 'video')}")

    # Check if this is a text message instead of a video
    if update.message.text and not update.message.video and not update.message.document:
        # If they typed /done, process that command
        if update.message.text.strip() == "/done":
            return await process_done_command(update, context)

        # If this is another command or just text, inform the user to send a video
        await update.message.reply_text(
            "❌ *VIDEO EXPECTED*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send a video file. Text messages are not accepted here.\n\n"
            "Use the 📎 attachment button to send a video, or type /done when finished.",
            parse_mode='Markdown'
        )
        return ADD_VIDEO

    # Check if there's a video in the message
    if hasattr(update.message, 'video') and update.message.video:
        video = update.message.video
        logger.info(f"Video received with file_id: {video.file_id}, file_size: {video.file_size}")

        # If we get here, we have a valid video
        file_id = video.file_id

        # Check if the message has a caption, use that as the media caption
        caption = update.message.caption or f"Premium video content #{context.user_data.get('mass_upload_count', 0) + 1}"

        # Use fixed price for videos
        price = 1.0

        today = datetime.now().strftime('%Y-%m-%d')

        try:
            # Save to database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Insert the new video
            cursor.execute(
                "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                ('video', file_id, caption, price, today, user_id)
            )

            # Get the ID of the newly added media
            media_id = cursor.lastrowid
            logger.info(f"Successfully added video with ID: {media_id}")

            # Log the addition
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (user_id, "MEDIA_ADDED", f"Added video #{media_id}", today)
            )

            conn.commit()
            conn.close()

            # Set media type in context
            context.user_data['media_type'] = 'video'

            # Increment the counter for mass uploads
            context.user_data['mass_upload_count'] = context.user_data.get('mass_upload_count', 0) + 1

            # Send confirmation with preview
            success_message = (
                f"✅ *VIDEO ADDED SUCCESSFULLY*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*ID:* {media_id}\n"
                f"*Caption:* {caption}\n"
                f"*Price:* {price} ⭐\n\n"
                f"You can send more videos or type /done when finished."
            )

            try:
                await update.message.reply_video(
                    video=file_id,
                    caption=success_message,
                    parse_mode='Markdown'
                )
            except Exception as preview_error:
                logger.error(f"Error showing video preview: {preview_error}")
                await update.message.reply_text(
                    success_message + "\n\n(Preview unavailable)",
                    parse_mode='Markdown'
                )

            # Enable mass upload mode for subsequent videos
            context.user_data['mass_upload_mode'] = True

            # Stay in ADD_VIDEO state to allow multiple uploads
            return ADD_VIDEO

        except Exception as e:
            logger.error(f"Error adding video: {e}")
            await update.message.reply_text(
                f"❌ *ERROR ADDING VIDEO*\n\n"
                f"An error occurred: {str(e)}\n\n"
                f"Please try again or type /done to finish uploading.",
                parse_mode='Markdown'
            )
            return ADD_VIDEO

    # Handle document type videos (larger files often come as documents)
    elif hasattr(update.message, 'document') and update.message.document:
        doc = update.message.document
        mime_type = doc.mime_type
        if mime_type and mime_type.startswith('video/'):
            logger.info(f"Video document received: {doc.file_id}, mime_type: {mime_type}")
            # Process as video
            file_id = doc.file_id
            caption = update.message.caption or f"Premium video content #{context.user_data.get('mass_upload_count', 0) + 1}"
            price = 1.0
            today = datetime.now().strftime('%Y-%m-%d')

            try:
                # Save to database
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                    ('video', file_id, caption, price, today, user_id)
                )

                media_id = cursor.lastrowid
                logger.info(f"Successfully added video document with ID: {media_id}")

                cursor.execute(
                    "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                    (user_id, "MEDIA_ADDED", f"Added video (document) #{media_id}", today)
                )

                conn.commit()
                conn.close()

                # Update context and confirm
                context.user_data['media_type'] = 'video'
                context.user_data['mass_upload_count'] = context.user_data.get('mass_upload_count', 0) + 1

                # Success message
                success_message = (
                    f"✅ *VIDEO ADDED SUCCESSFULLY*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"*ID:* {media_id}\n"
                    f"*Caption:* {caption}\n"
                    f"*Price:* {price} ⭐\n\n"
                    f"You can send more videos or type /done when finished."
                )

                await update.message.reply_text(
                    success_message,
                    parse_mode='Markdown'
                )

                # Enable mass upload mode for subsequent videos
                context.user_data['mass_upload_mode'] = True

                # Stay in ADD_VIDEO state
                return ADD_VIDEO

            except Exception as e:
                logger.error(f"Error adding video document: {e}")
                await update.message.reply_text(
                    f"❌ *ERROR ADDING VIDEO*\n\n"
                    f"An error occurred: {str(e)}\n\n"
                    f"Please try again or type /done to finish uploading.",
                    parse_mode='Markdown'
                )
                return ADD_VIDEO

    # If no valid media was found in the message
    # Show instructions for uploading videos
    await update.message.reply_text(
        "❌ *VIDEO UPLOAD REQUIRED*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send a valid video file. No text, images, or other file types.\n\n"
        "📋 *INSTRUCTIONS:*\n"
        "1. Click the attachment icon 📎\n"
        "2. Select 'Video' or 'File' for larger videos\n"
        "3. Choose a video to upload\n"
        "4. Add an optional caption\n"
        "5. Send the video\n\n"
        "You can send multiple videos one after another.\n"
        "Type /done when you've finished uploading.",
        parse_mode='Markdown'
    )

    # Enable mass upload mode
    context.user_data['mass_upload_mode'] = True
    context.user_data['mass_upload_count'] = 0
    context.user_data['media_type'] = 'video'  # Track the media type
    return ADD_VIDEO

# Skip the caption and price states, they're no longer needed
async def process_done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /done command to finish mass upload"""
    upload_count = context.user_data.get('mass_upload_count', 0)

    # Get the correct media type from context
    media_type = context.user_data.get('media_type', 'video')
    if not media_type:
        # Fallback detection based on conversation state
        media_type = "video" if "ADD_VIDEO" in str(context) else "photo"

    price = "1" if media_type == "video" else "0.5"

    # Clear the mass upload mode
    if 'mass_upload_mode' in context.user_data:
        del context.user_data['mass_upload_mode']

    if 'mass_upload_count' in context.user_data:
        del context.user_data['mass_upload_count']

    # Get current counts from database for both media types
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Count videos
    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
    video_count = cursor.fetchone()[0]

    # Count photos
    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
    photo_count = cursor.fetchone()[0]

    # Get count for the specific media type
    total_count = video_count if media_type == 'video' else photo_count

    conn.close()

    await update.message.reply_text(
        f"✅ *UPLOAD COMPLETE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Successfully added {upload_count} {media_type}{'s' if upload_count != 1 else ''}.\n\n"
        f"• Price per {media_type}: {price} ⭐\n"
        f"• Total {media_type}s in database: {total_count}\n"
        f"• Total videos: {video_count}\n"
        f"• Total photos: {photo_count}\n\n"
        f"These {media_type}s are now available to all users.",
        parse_mode='Markdown'
    )

    # Return to admin menu
    await show_admin_menu(update, context)
    return ADMIN_MENU

async def process_add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Check admin authentication
    user_id = update.effective_user.id

    # Define approved admins list
    APPROVED_ADMINS = [ADMIN_ID, 6648598512, 7062972013]

    # Strict authentication check
    if user_id not in APPROVED_ADMINS and not context.user_data.get('admin_authenticated'):
        logger.warning(f"Unauthorized photo upload attempt by user ID: {user_id}")
        await update.message.reply_text(
            "⚠️ *UNAUTHORIZED ACCESS* ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "You don't have permission to add photos.\n"
            "This incident has been logged.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Log what type of message we received
    has_photo = hasattr(update.message, 'photo') and update.message.photo
    has_document = hasattr(update.message, 'document') and update.message.document
    has_text = hasattr(update.message, 'text')

    logger.info(f"Process add photo: message attributes: photo={has_photo}, document={has_document}, text={has_text}")

    # Check if user sent /done command
    if has_text and update.message.text == "/done":
        return await process_done_command(update, context)

    # Check if this is a text message but not a photo
    if has_text and not has_photo:
        await update.message.reply_text(
            "❌ *PHOTO EXPECTED*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send a photo. Text messages are not accepted here.\n\n"
            "Use the 📎 attachment button to send a photo, or type /done when finished.",
            parse_mode='Markdown'
        )
        return ADD_PHOTO

    # Process photo
    if not has_photo:
        await update.message.reply_text(
            "❌ *INVALID FILE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send a valid photo.",
            parse_mode='Markdown'
        )
        return ADD_PHOTO

    # Get highest quality photo
    file_id = update.message.photo[-1].file_id
    logger.info(f"Processing photo with file_id: {file_id}")
    caption = update.message.caption or f"Premium photo content #{context.user_data.get('mass_upload_count', 0) + 1}"
    price = 0.5  # Fixed price for photos
    today = datetime.now().strftime('%Y-%m-%d')

    # Send an initial acknowledgment
    processing_message = await update.message.reply_text(
        "⏳ *PROCESSING PHOTO*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Your photo is being processed and saved to the database...",
        parse_mode='Markdown'
    )

    try:
        # Save to database
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Create media table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            file_id TEXT,
            caption TEXT,
            price REAL,
            added_date TEXT,
            added_by INTEGER
        )
        ''')

        # Log what we're trying to insert
        logger.info(f"Inserting photo: type='photo', file_id='{file_id}', caption='{caption}', price={price}, date='{today}', user_id={user_id}")

        # Insert photo
        cursor.execute(
            "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
            ('photo', file_id, caption, price, today, user_id)
        )
        media_id = cursor.lastrowid

        # Log the addition
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "MEDIA_ADDED", f"Added photo #{media_id}", today)
        )

        # Make sure we commit the transaction
        conn.commit()
        logger.info(f"Successfully inserted photo with ID: {media_id}")

        # Verify the insert worked
        cursor.execute("SELECT id, file_id FROM media WHERE id = ?", (media_id,))
        verification = cursor.fetchone()
        logger.info(f"Verification of insert: {verification}")

        conn.close()

        # Increment upload counter
        context.user_data['mass_upload_count'] = context.user_data.get('mass_upload_count', 0) + 1
        context.user_data['media_type'] = 'photo'

        # Send confirmation
        success_message = (
            f"✅ *PHOTO ADDED SUCCESSFULLY* ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*ID:* #{media_id}\n"
            f"*Caption:* {caption}\n"
            f"*Price:* {price} ⭐\n\n"
            f"Send more photos or type /done when finished."
        )

        # Try to edit the processing message first
        try:
            await processing_message.edit_text(success_message, parse_mode='Markdown')
        except Exception as edit_error:
            # If editing fails, send a new message
            logger.error(f"Error editing message: {edit_error}")
            await update.message.reply_text(success_message, parse_mode='Markdown')

        # Send a preview of the uploaded photo
        try:
            await update.message.reply_photo(
                photo=file_id,
                caption=f"✅ Preview of uploaded photo #{media_id}",
                parse_mode='Markdown'
            )
        except Exception as preview_error:
            logger.error(f"Error sending photo preview: {preview_error}")
            # Not critical, we can continue without the preview

        return ADD_PHOTO

    except Exception as e:
        logger.error(f"Error adding photo: {e}")

        # Try to edit the processing message first
        try:
            await processing_message.edit_text(
                "❌ *ERROR ADDING PHOTO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact support.",
                parse_mode='Markdown'
            )
        except Exception as edit_error:
            # If editing fails, send a new message
            logger.error(f"Error editing message: {edit_error}")
            await update.message.reply_text(
                "❌ *ERROR ADDING PHOTO*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact support.",
                parse_mode='Markdown'
            )

        return ADD_PHOTO

    # Log the entry point for debugging
    logger.info(f"Admin photo upload: user_id={user_id}, has_photo={hasattr(update.message, 'photo')}")

    # Check if there's a photo in the message
    if hasattr(update.message, 'photo') and update.message.photo:
        # We have a photo, proceed with processing
        photos = update.message.photo
        logger.info(f"Photo received with file_id: {photos[-1].file_id}")

        # Always use the highest quality photo
        file_id = photos[-1].file_id

        # Check if the message has a caption, use that as the media caption
        caption = update.message.caption or f"Premium photo content #{context.user_data.get('mass_upload_count', 0) + 1}"

        # Use fixed price for photos
        price = 0.5

        today = datetime.now().strftime('%Y-%m-%d')

        try:
            # Use a context manager for the database connection
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Create the media table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                file_id TEXT,
                caption TEXT,
                price REAL,
                added_date TEXT,
                added_by INTEGER
            )
            ''')

            # Insert the new photo
            cursor.execute(
                "INSERT INTO media (type, file_id, caption, price, added_date, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                ('photo', file_id, caption, price, today, user_id)
            )

            # Get the ID of the newly added media
            media_id = cursor.lastrowid
            logger.info(f"Successfully added photo with ID: {media_id}")

            # Log the addition
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (user_id, "MEDIA_ADDED", f"Added photo #{media_id}", today)
            )

            conn.commit()
            conn.close()

            # Set media type in context
            context.user_data['media_type'] = 'photo'

            # Increment the counter
            context.user_data['mass_upload_count'] = context.user_data.get('mass_upload_count', 0) + 1

            # Always confirm upload success with a clear message
            await update.message.reply_text(
                f"✅ *PHOTO ADDED SUCCESSFULLY!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*ID:* #{media_id}\n"
                f"*PRICE:* {price} ⭐\n"
                f"*CAPTION:* {caption[:50]}{'...' if len(caption) > 50 else ''}\n\n"
                f"You can send more photos or type /done when finished.",
                parse_mode='Markdown'
            )

            # Try to send preview (not critical if it fails)
            try:
                await update.message.reply_photo(
                    photo=file_id,
                    caption=f"✅ *PHOTO ADDED TO DATABASE*\n"
                           f"ID: #{media_id}",
                    parse_mode='Markdown'
                )
            except Exception as preview_error:
                logger.error(f"Error showing photo preview: {preview_error}")
                # Already sent text confirmation, so don't send error message

            # Stay in ADD_PHOTO state to allow multiple uploads
            return ADD_PHOTO

        except Exception as e:
            logger.error(f"Error adding photo: {e}")
            await update.message.reply_text(
                f"❌ *UPLOAD FAILED*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"An error occurred while processing your photo.\n\n"
                f"*ERROR DETAILS:*\n{str(e)}\n\n"
                f"Please try again or type /done to finish uploading.",
                parse_mode='Markdown'
            )
            return ADD_PHOTO
    else:
        # If this is running in caption/multiple file mode, skip validation
        if context.user_data.get('mass_upload_mode'):
            return ADD_PHOTO

        # Better instructions for photo upload with improved UI
        await update.message.reply_text(
            "📸 *UPLOAD PHOTO* 📸\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send a photo to add to your collection.\n\n"
            "📋 *INSTRUCTIONS:*\n"
            "1. Click the attachment icon 📎\n"
            "2. Select 'Photo' from the menu\n"
            "3. Choose a high-quality image\n"
            "4. Add an optional caption\n"
            "5. Send the photo\n\n"
            "You can send multiple photos one after another.\n"
            "Type /done when you've finished uploading.",
            parse_mode='Markdown'
        )
        # Enable mass upload mode
        context.user_data['mass_upload_mode'] = True
        context.user_data['mass_upload_count'] = 0
        context.user_data['media_type'] = 'photo'  # Track the media type
        return ADD_PHOTO

# Admin statistics dashboard
async def show_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get total users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # Get active users today
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM daily_logins WHERE login_date = ?", (today,))
    active_users = cursor.fetchone()[0]

    # Get new users today
    cursor.execute("SELECT COUNT(*) FROM users WHERE registration_date = ?", (today,))
    new_users = cursor.fetchone()[0]

    # Get users with non-zero stars
    cursor.execute("SELECT COUNT(*) FROM users WHERE stars > 0")
    paying_users = cursor.fetchone()[0]

    # Get total media
    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
    total_videos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
    total_photos = cursor.fetchone()[0]

    # Get download counts
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE description LIKE 'Downloaded video%'")
    video_downloads = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM transactions WHERE description LIKE 'Downloaded photo%'")
    photo_downloads = cursor.fetchone()[0]

    # Get total stars distributed
    cursor.execute("SELECT SUM(stars) FROM users")
    total_stars = cursor.fetchone()[0] or 0

    # Get total revenue (estimated from transactions)
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE amount < 0")
    total_spent = abs(cursor.fetchone()[0] or 0)

    conn.close()

    # Create a professional-looking statistics dashboard
    stats_text = (
        f"📊 *ADMIN STATISTICS DASHBOARD*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"👥 *USER METRICS*\n"
        f"• Total Users: {total_users}\n"
        f"• Active Today: {active_users}\n"
        f"• New Today: {new_users}\n"
        f"• Users with Stars: {paying_users}\n\n"

        f"🎬 *CONTENT METRICS*\n"
        f"• Total Videos: {total_videos}\n"
        f"• Total Photos: {total_photos}\n"
        f"• Video Downloads: {video_downloads}\n"
        f"• Photo Downloads: {photo_downloads}\n\n"

        f"💰 *FINANCIAL METRICS*\n"
        f"• Stars in Circulation: {total_stars:.1f} ⭐\n"
        f"• Total Stars Spent: {total_spent:.1f} ⭐\n"
        f"• Estimated Revenue: {total_spent * 2:.1f} ₹"
    )

    keyboard = [
        [InlineKeyboardButton("📅 Daily Report", callback_data="admin_daily_report")],
        [InlineKeyboardButton("📈 Weekly Trends", callback_data="admin_weekly_trends")],
        [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back_to_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.edit_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Admin content management
async def show_media_for_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get total media counts
    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
    photo_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
    video_count = cursor.fetchone()[0]

    # Get filter parameters from context or set defaults
    media_type_filter = context.user_data.get('media_filter_type', 'all')
    page = context.user_data.get('media_page', 1)
    items_per_page = 10
    offset = (page - 1) * items_per_page

    # Build query based on filter
    if media_type_filter == 'photo':
        cursor.execute(
            "SELECT * FROM media WHERE type = 'photo' ORDER BY id DESC LIMIT ? OFFSET ?", 
            (items_per_page, offset)
        )
    elif media_type_filter == 'video':
        cursor.execute(
            "SELECT * FROM media WHERE type = 'video' ORDER BY id DESC LIMIT ? OFFSET ?", 
            (items_per_page, offset)
        )
    else:
        cursor.execute(
            "SELECT * FROM media ORDER BY id DESC LIMIT ? OFFSET ?", 
            (items_per_page, offset)
        )

    media_list = cursor.fetchall()

    # Count total pages for pagination
    if media_type_filter == 'photo':
        total_pages = (photo_count + items_per_page - 1) // items_per_page
    elif media_type_filter == 'video':
        total_pages = (video_count + items_per_page - 1) // items_per_page
    else:
        total_pages = ((photo_count + video_count) + items_per_page - 1) // items_per_page

    conn.close()

    # Create a message with information about available media and options
    if not media_list:
        text = "📂 *MEDIA MANAGEMENT*\n\nNo media found. Use Search by ID to find specific media or Mass Delete for bulk operations."

        # Simplified button set as requested
        keyboard = [
            [KeyboardButton("🔍 Search by ID"), KeyboardButton("♻️ Mass Delete")],
            [KeyboardButton("🔙 Back to Admin Menu")]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        text = (
            f"📂 *MEDIA MANAGEMENT*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*SUMMARY:* {photo_count + video_count} total media items\n"
            f"*BREAKDOWN:* {photo_count} Photos, {video_count} Videos\n\n"
            f"Recent media items:"
        )

        # Add a list of most recent items for quick access
        recent_items_text = "\n\n*RECENT MEDIA:*\n"
        keyboard = []

        for i, media in enumerate(media_list[:5], 1):
            media_id = media[0]
            media_type = media[1]
            caption = media[3][:15] + "..." if len(media[3]) > 15 else media[3]
            type_emoji = "🎬" if media_type == "video" else "📷"

            recent_items_text += f"{i}. {type_emoji} ID #{media_id}: {caption}\n"
            keyboard.append([KeyboardButton(f"🗑️ Delete ID #{media_id}")])

        text += recent_items_text
        text += "\nUse the buttons below to delete specific items or search by ID."

        # Add search and navigation buttons
        keyboard.append([KeyboardButton("🔍 Search by ID"), KeyboardButton("♻️ Mass Delete")])
        keyboard.append([KeyboardButton("🔙 Back to Admin Menu")])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Send message with options
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Set up context to handle search
        context.user_data['admin_media_management'] = True
        context.user_data['admin_delete_mode'] = True

async def admin_delete_media(update: Update, context: ContextTypes.DEFAULT_TYPE, media_id):
    # Log the delete request
    logger.info(f"Admin delete media: media_id={media_id}")

    # Get media info before deletion
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT type, caption, file_id FROM media WHERE id = ?", (media_id,))
    media_info = cursor.fetchone()

    # Check if we have a callback_query in the update
    has_callback = hasattr(update, 'callback_query') and update.callback_query is not None

    if not media_info:
        conn.close()
        message = "❌ *Error*\n\nMedia not found."

        if has_callback:
            await update.callback_query.message.edit_text(
                message,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                message,
                parse_mode='Markdown'
            )
        return

    media_type, caption, file_id = media_info
    logger.info(f"Found media for deletion: type={media_type}, caption={caption[:30]}...")

    # Get download count info before deletion
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE description LIKE ?", (f"Downloaded %{media_id}%",))
    download_count = cursor.fetchone()[0]

    # Get bookmark count before deletion
    cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE media_id = ?", (media_id,))
    bookmark_count = cursor.fetchone()[0]

    # Delete media
    cursor.execute("DELETE FROM media WHERE id = ?", (media_id,))

    # Delete any bookmarks referencing this media
    cursor.execute("DELETE FROM bookmarks WHERE media_id = ?", (media_id,))

    # Log the deletion
    admin_id = update.effective_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (admin_id, "MEDIA_DELETED", f"Deleted {media_type} #{media_id}", today)
    )

    # Get remaining media counts for the report
    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'photo'")
    photo_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM media WHERE type = 'video'")
    video_count = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    # Success message
    success_text = (
        f"✅ *MEDIA DELETED SUCCESSFULLY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*DELETED ITEM:*\n"
        f"• Type: {media_type.capitalize()}\n"
        f"• ID: {media_id}\n"
        f"• Caption: {caption[:50]}{'...' if len(caption) > 50 else ''}\n\n"
        f"*STATISTICS:*\n"
        f"• Downloads: {download_count}\n"
        f"• Bookmarks removed: {bookmark_count}\n"
        f"• Remaining photos: {photo_count}\n"
        f"• Remaining videos: {video_count}\n"
    )

    # Show preview of what was deleted if possible
    try:
        if media_type == "photo":
            await update.message.reply_photo(
                photo=file_id,
                caption=success_text,
                parse_mode='Markdown'
            )
        elif media_type == "video":
            await update.message.reply_video(
                video=file_id,
                caption=success_text,
                parse_mode='Markdown'
            )
    except Exception as e:
        # If preview fails, just show text message
        logger.error(f"Could not preview deleted media: {e}")
        await update.message.reply_text(
            success_text,
            parse_mode='Markdown'
        )

    logger.info(f"Successfully deleted media ID: {media_id}")

    # Show options for what to do next
    keyboard = [
        [KeyboardButton("🗑️ Delete More Media")],
        [KeyboardButton("➕ Add Video"), KeyboardButton("➕ Add Photo")],
        [KeyboardButton("🔙 Back to Admin Menu")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "What would you like to do next?",
        reply_markup=reply_markup
    )

# Handle broadcast retry functionality
async def retry_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(update, 'message') or update.message.text != "🔄 Retry Failed Messages":
        return ADMIN_MENU

    # Get the failed users and message from context with proper validation
    failed_users = context.user_data.get('broadcast_failed_users', [])
    broadcast_message = context.user_data.get('broadcast_message', '')

    logger.info(f"Retrying broadcast to {len(failed_users)} users")

    if not failed_users or not broadcast_message:
        await update.message.reply_text(
            "⚠️ *No Failed Messages to Retry*\n\n"
            "There are no failed messages to resend or the broadcast data has expired.",
            parse_mode='Markdown'
        )
        return ADMIN_MENU

    sent_count = 0
    failed_count = 0
    new_failed_users = []

    progress_message = await update.message.reply_text(
        f"⏳ *Retrying Failed Messages*\n\n"
        f"Attempting to resend to {len(failed_users)} users...",
        parse_mode='Markdown'
    )

    # Add a delay before sending messages
    await asyncio.sleep(1)

    # Process in smaller batches
    batch_size = 20
    for i in range(0, len(failed_users), batch_size):
        batch = failed_users[i:i+batch_size]

        for user_id in batch:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=broadcast_message,
                    parse_mode='Markdown'
                )
                sent_count += 1

                # Update progress every 5 messages
                if sent_count % 5 == 0:
                    try:
                        await progress_message.edit_text(
                            f"⏳ *Retrying Failed Messages*\n\n"
                            f"Progress: {sent_count}/{len(failed_users)} users",
                            parse_mode='Markdown'
                        )
                    except Exception:
                        pass  # Ignore errors updating progress

                # Add a small delay between messages to avoid rate limiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed again to send broadcast to user {user_id}: {e}")
                failed_count += 1
                new_failed_users.append(user_id)

        # Add a pause between batches to avoid rate limits
        if i + batch_size < len(failed_users):
            await asyncio.sleep(1)



    # Update the failed users list
    context.user_data['broadcast_failed_users'] = new_failed_users

    # Create keyboard
    keyboard = []
    if failed_count > 0:
        keyboard.append([KeyboardButton("🔄 Retry Failed Messages")])
    keyboard.append([KeyboardButton("🔙 Back to Admin Menu")])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Show final report - try with edit_text, fall back to new message if needed
    try:
        await progress_message.edit_text(
            f"✅ *RETRY COMPLETE*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*Results:*\n"
            f"• Successfully sent: {sent_count}\n"
            f"• Still failed: {failed_count}\n\n"
            f"{f'You can try again for the remaining {failed_count} users.' if failed_count > 0 else 'All messages have been delivered successfully!'}",
            parse_mode='Markdown'
        )

        # Send keyboard separately for better compatibility
        await update.message.reply_text(
            "Select an option:",
            reply_markup=reply_markup
        )
    except Exception:
        # If edit fails, send a new message with keyboard
        await update.message.reply_text(
            f"✅ *RETRY COMPLETE*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*Results:*\n"
            f"• Successfully sent: {sent_count}\n"
            f"• Still failed: {failed_count}\n\n"
            f"{f'You can try again for the remaining {failed_count} users.' if failed_count > 0 else 'All messages have been delivered successfully!'}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # Log the retry
    admin_id = update.effective_user.id
    today = datetime.now().strftime('%Y-%m-%d')

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (admin_id, "BROADCAST_RETRY", f"Retried broadcast: {sent_count} success, {failed_count} failed", today)
    )
    conn.commit()
    conn.close()

    return ADMIN_MENU

# Admin user management
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search_query = update.message.text.strip()

    # Check if it's coming from the search by ID button
    if search_query == "🔍 Search by ID":
        await update.message.reply_text(
            "🔍 *SEARCH MEDIA BY ID*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter the media ID number you want to find:",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_media_id'] = True
        return ADMIN_SEARCH_MEDIA

    # If we were awaiting a media ID input
    if context.user_data.get('awaiting_media_id'):
        context.user_data['awaiting_media_id'] = False

        # Check if search query is empty
        if not search_query:
            await update.message.reply_text(
                "❌ *Invalid Search*\n\n"
                "Please enter a valid media ID number.",
                parse_mode='Markdown'
            )
            # Return to media management
            await show_media_for_deletion(update, context)
            return ADMIN_DELETE_MEDIA

        # Ensure the query is a number for ID search
        if not search_query.isdigit():
            await update.message.reply_text(
                "❌ *Invalid ID Format*\n\n"
                "Please enter a numeric ID only.",
                parse_mode='Markdown'
            )
            # Return to media management
            await show_media_for_deletion(update, context)
            return ADMIN_DELETE_MEDIA

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        media_id = int(search_query)
        cursor.execute("SELECT * FROM media WHERE id = ?", (media_id,))
        media_result = cursor.fetchone()

        # Get additional statistics about this media
        if media_result:
            # Count bookmarks for this media
            cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE media_id = ?", (media_id,))
            bookmark_count = cursor.fetchone()[0]

            # Count downloads
            cursor.execute("SELECT COUNT(*) FROM transactions WHERE description LIKE ?", (f"Downloaded %{media_id}%",))
            download_count = cursor.fetchone()[0]
        else:
            bookmark_count = 0
            download_count = 0

        conn.close()

        if not media_result:
            await update.message.reply_text(
                f"❌ *MEDIA NOT FOUND*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"No media with ID #{media_id} was found in the database.\n\n"
                f"Please check the ID and try again.",
                parse_mode='Markdown'
            )
            # Add search again button
            keyboard = [
                [KeyboardButton("🔍 Search by ID")],
                [KeyboardButton("🔙 Back to Admin Menu")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                "Use these options to continue:",
                reply_markup=reply_markup
            )
            return ADMIN_DELETE_MEDIA

        # Found media - show details with delete option
        media_id, media_type, file_id, caption, price = media_result[0], media_result[1], media_result[2], media_result[3], media_result[4]

        # Format added date if available (check if there are enough columns)
        added_date = media_result[5] if len(media_result) > 5 else "Unknown"

        try:
            if added_date and added_date != "Unknown":
                formatted_date = datetime.strptime(added_date, '%Y-%m-%d').strftime('%d %b %Y')
            else:
                formatted_date = "Unknown"
        except:
            formatted_date = added_date

        # Create detailed info
        media_info = (
            f"🔍 *MEDIA DETAILS - ID#{media_id}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*TYPE:* {'📷 Photo' if media_type == 'photo' else '🎬 Video'}\n"
            f"*PRICE:* {price} ⭐\n"
            f"*ADDED:* {formatted_date}\n\n"
            f"*STATS:*\n"
            f"• Bookmarks: {bookmark_count}\n"
            f"• Downloads: {download_count}\n\n"
            f"*CAPTION:*\n{caption}\n\n"
            f"Use the Delete button below to remove this media."
        )

        # Create keyboard for actions
        keyboard = [
            [KeyboardButton(f"🗑️ Delete ID #{media_id}")],
            [KeyboardButton("🔍 Search by ID")],
            [KeyboardButton("🔙 Back to Admin Menu")]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Try to show preview
        try:
            if media_type == "photo":
                await update.message.reply_photo(
                    photo=file_id,
                    caption=media_info,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_video(
                    video=file_id,
                    caption=media_info,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error showing media preview: {e}")
            # If preview fails, just show text
            await update.message.reply_text(
                f"{media_info}\n\n⚠️ Preview not available. File ID may be invalid.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

        # Save this media ID to context for easy deletion
        context.user_data['current_media_id'] = media_id

        return ADMIN_DELETE_MEDIA

    # For any other message in this state, return to search prompt
    await update.message.reply_text(
        "🔍 *SEARCH MEDIA BY ID*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter a numeric media ID to search:",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_media_id'] = True
    return ADMIN_SEARCH_MEDIA

async def search_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Check if this is an admin
    user_id = update.effective_user.id

    # Define approved admins list
    APPROVED_ADMINS = [ADMIN_ID, 6648598512, 7062972013]

    if user_id not in APPROVED_ADMINS and not context.user_data.get('admin_authenticated'):
        logger.warning(f"Unauthorized search attempt by user ID: {user_id}")
        await update.message.reply_text(
            "❌ *UNAUTHORIZED*\n\n"
            "You don't have permission to search users.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Log the received message for debugging
    logger.info(f"Search user received message: '{update.message.text}'")
    search_query = update.message.text.strip()

    # If the input is just the button text, show the search prompt
    if search_query == "🔍 Search User" or search_query == "🔍 Search User by ID/Username":
        await update.message.reply_text(
            "🔍 *SEARCH USER*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter a username, name, or User ID to search for a specific user:",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_user_search'] = True
        return ADMIN_SEARCH_USER

    # Handle ban user button press
    if search_query.startswith("🚫 Ban User ID "):
        try:
            # Extract user ID from the button text
            user_id_part = search_query.replace("🚫 Ban User ID ", "").strip()
            target_user_id = int(user_id_part)
            context.user_data['ban_user_id'] = target_user_id

            # Get user details
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (target_user_id,))
            user_info = cursor.fetchone()
            conn.close()

            if not user_info:
                await update.message.reply_text(
                    "❌ *User Not Found*\n\n"
                    f"No user found with ID: {target_user_id}",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

            name, username = user_info

            # Ask for ban reason
            await update.message.reply_text(
                f"🚫 *Ban User: {name} (@{username})*\n"
                f"━━━━━━━━━━━━━━━━━━━━━  �━━\n\n"
                f"Please enter the reason for banning this user:",
                parse_mode='Markdown'
            )

            return BAN_USER
        except ValueError as e:
            logger.error(f"Error processing ban user command: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Handle unban user button press
    if search_query.startswith("🔓 Unban User ID "):
        try:
            # Extract user ID from the button text
            user_id_part = search_query.replace("🔓 Unban User ID ", "").strip()
            target_user_id = int(user_id_part)

            # Get user details
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Get user info for the notification
            cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (target_user_id,))
            user_info = cursor.fetchone()

            if not user_info:
                conn.close()
                await update.message.reply_text(
                    "❌ *Error*\n\nUser not found.",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

            name, username = user_info

            # Unban the user
            cursor.execute(
                "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?",
                (target_user_id,)
            )

            # Log the action
            admin_id = update.effective_user.id
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (target_user_id, "UNBANNED", f"Unbanned by admin ID {admin_id}", today)
            )

            conn.commit()
            conn.close()

            # Notify the admin
            await update.message.reply_text(
                f"✅ *User Unbanned Successfully*\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n\n"
                f"This user can now access the bot again.",
                parse_mode='Markdown'
            )

            # Try to notify the user
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"✅ *BAN REMOVED* ✅\n\n"
                        f"Your account has been unbanned.\n"
                        f"You can now use the bot again.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send unban notification to user {target_user_id}: {e}")

            # Show user details again after unbanning
            return await search_user_by_id(update, context, target_user_id)
        except ValueError as e:
            logger.error(f"Error processing unban user command: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Handle warn user button press
    if search_query.startswith("⚠️ Warn User ID "):
        try:
            # Extract user ID from the button text
            user_id_part = search_query.replace("⚠️ Warn User ID ", "").strip()
            target_user_id = int(user_id_part)
            context.user_data['target_user_id'] = target_user_id

            # Get user details
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, username, warnings FROM users WHERE user_id = ?", (target_user_id,))
            user_info = cursor.fetchone()
            conn.close()

            if not user_info:
                await update.message.reply_text(
                    "❌ *User Not Found*\n\n"
                    f"No user found with ID: {target_user_id}",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

            name, username, warnings = user_info

            # Ask for warning reason
            await update.message.reply_text(
                f"⚠️ *Issue Warning to User: {name} (@{username})*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Current Warnings:* {warnings}\n\n"
                f"Please enter the warning reason:",
                parse_mode='Markdown'
            )

            return WARN_USER
        except ValueError as e:
            logger.error(f"Error processing warn user command: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Handle clear warnings button press
    if search_query.startswith("🔄 Clear Warnings ID "):
        try:
            # Extract user ID from the button text
            user_id_part = search_query.replace("🔄 Clear Warnings ID ", "").strip()
            target_user_id = int(user_id_part)

            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Get user info before clearing
            cursor.execute("SELECT name, username, warnings FROM users WHERE user_id = ?", (target_user_id,))
            user_info = cursor.fetchone()

            if not user_info:
                conn.close()
                await update.message.reply_text(
                    "❌ *Error*\n\nUser not found.",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

            name, username, warnings = user_info

            # Clear warnings
            cursor.execute("UPDATE users SET warnings = 0 WHERE user_id = ?", (target_user_id,))

            # Log the action
            admin_id = update.effective_user.id
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (target_user_id, "WARNINGS_CLEARED", f"Warnings cleared by admin ID {admin_id}", today)
            )

            conn.commit()
            conn.close()

            # Notify the admin
            await update.message.reply_text(
                f"✅ *Warnings Cleared Successfully*\n\n"
                f"*User:* {name} (@{username})\n"
                f"*Previous Warnings:* {warnings}\n"
                f"*Current Warnings:* 0\n\n"
                f"All warnings have been cleared for this user.",
                parse_mode='Markdown'
            )

            # Try to notify the user
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"✅ *WARNINGS CLEARED* ✅\n\n"
                        f"All your previous warnings have been cleared by an administrator.\n"
                        f"You now have 0 warnings on your account.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send warning clear notification to user {target_user_id}: {e}")

            # Show user details again after clearing warnings
            return await search_user_by_id(update, context, target_user_id)
        except ValueError as e:
            logger.error(f"Error processing clear warnings command: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Handle add stars button press
    if search_query.startswith("➕ Add Stars to ID "):
        try:
            # Extract user ID from the button text
            user_id_part = search_query.replace("➕ Add Stars to ID ", "").strip()
            target_user_id = int(user_id_part)

            # Store the target user ID in context
            context.user_data['target_user_id'] = target_user_id

            # Get user details from database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, username, stars FROM users WHERE user_id = ?", (target_user_id,))
            user_info = cursor.fetchone()
            conn.close()

            if not user_info:
                await update.message.reply_text(
                    "❌ *User Not Found*\n\n"
                    f"No user found with ID: {target_user_id}",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

            name, username, current_stars = user_info

            # Ask for stars amount
            await update.message.reply_text(
                f"⭐ *ADD STARS*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n"
                f"*Current Stars:* {current_stars} ⭐\n\n"
                f"Please enter the number of stars to add:",
                parse_mode='Markdown'
            )

            return ADD_STARS
        except ValueError as e:
            logger.error(f"Error processing add stars command: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Check if the message is a command to remove stars
    if search_query.startswith("➖ Remove Stars from ID "):
        try:
            # Extract user ID from the button text
            user_id_part = search_query.replace("➖ Remove Stars from ID ", "").strip()
            target_user_id = int(user_id_part)

            # Store the target user ID in context
            context.user_data['target_user_id'] = target_user_id

            # Get user details from database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, username, stars FROM users WHERE user_id = ?", (target_user_id,))
            user_info = cursor.fetchone()
            conn.close()

            if not user_info:
                await update.message.reply_text(
                    "❌ *User Not Found*\n\n"
                    f"No user found with ID: {target_user_id}",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

            name, username, current_stars = user_info

            # Ask for stars amount
            await update.message.reply_text(
                f"🔄 *REMOVE STARS*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n"
                f"*Current Stars:* {current_stars} ⭐\n\n"
                f"Please enter the number of stars to remove:",
                parse_mode='Markdown'
            )

            return REMOVE_STARS
        except ValueError as e:
            logger.error(f"Error processing remove stars command: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Handle block/unblock actions
    admin_action = context.user_data.get('admin_action')
    if admin_action in ['block_user', 'unblock_user']:
        context.user_data.pop('admin_action', None)

        if not search_query.isdigit():
            await update.message.reply_text(
                "❌ *Invalid User ID*\n\n"
                "Please enter a valid numeric User ID.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

        target_user_id = int(search_query)
        admin_id = update.effective_user.id
        today = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Get user info
        cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (target_user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            conn.close()
            await update.message.reply_text(
                f"❌ *User Not Found*\n\n"
                f"No user found with ID: {target_user_id}",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

        name, username = user_info

        if admin_action == 'block_user':
            # Block user from admin panel
            cursor.execute("""
                INSERT OR REPLACE INTO admin_blocked_users (user_id, blocked_by, block_reason, block_date) 
                VALUES (?, ?, ?, ?)
            """, (target_user_id, admin_id, "Blocked from admin panel", today))

            conn.commit()
            conn.close()

            await update.message.reply_text(
                f"✅ *USER BLOCKED FROM ADMIN PANEL*\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n\n"
                f"This user is now blocked from admin panel access.",
                parse_mode='Markdown'
            )
        else:  # unblock_user
            # Unblock user from admin panel
            cursor.execute("DELETE FROM admin_blocked_users WHERE user_id = ?", (target_user_id,))

            conn.commit()
            conn.close()

            await update.message.reply_text(
                f"✅ *USER UNBLOCKED FROM ADMIN PANEL*\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n\n"
                f"This user can now access admin panel if they have credentials.",
                parse_mode='Markdown'
            )

        await show_admin_menu(update, context)
        return ADMIN_MENU

    # Check if we're awaiting a search query or if this is a direct user search
    if context.user_data.get('awaiting_user_search') or search_query.isdigit() or '@' in search_query:
        # Clear the flag if it exists
        if context.user_data.get('awaiting_user_search'):
            context.user_data.pop('awaiting_user_search', None)

        # Check if search query is empty
        if not search_query:
            await update.message.reply_text(
                "❌ *Invalid Search*\n\n"
                "Please enter a valid username, name, or user ID.",
                parse_mode='Markdown'
            )
            # Set the flag again and return to search state
            context.user_data['awaiting_user_search'] = True
            return ADMIN_SEARCH_USER

        # Search the database
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Search by user_id, name, or username
        try:
            # First try to search by user ID (if the input is a number)
            search_user_id = int(search_query) if search_query.isdigit() else None
            if search_user_id:
                cursor.execute("SELECT user_id, name, username, stars, is_banned FROM users WHERE user_id = ?", (search_user_id,))
            else:
                # If username has @ in front, remove it
                clean_username = search_query.lstrip('@') if search_query.startswith('@') else search_query

                # Search by username (exact match) or name (partial match)
                cursor.execute(
                    "SELECT user_id, name, username, stars, is_banned FROM users WHERE username = ? OR name LIKE ? LIMIT 20", 
                    (clean_username, f"%{search_query}%")
                )

            users = cursor.fetchall()
        except Exception as e:
            logger.error(f"Search error: {e}")
            users = []

        conn.close()

        if not users:
            # No users found - provide option to try again with keyboard buttons
            keyboard = [
                [KeyboardButton("🔍 Search User")],
                [KeyboardButton("🔙 Back to Admin Menu")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(
                "❌ *NO USERS FOUND*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"No users matching '{search_query}' were found in the database.\n"
                "Please try a different search term.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return ADMIN_MENU

        # For direct username/ID searches with exactly one match, show user details immediately
        if len(users) == 1:
            found_user_id = users[0][0]
            return await search_user_by_id(update, context, found_user_id)

        # Multiple results - show list of users
        text = f"🔍 *SEARCH RESULTS*\n" + "━" * 15 + f"\n\nFound {len(users)} users matching '{search_query}':\n\n"

        # Add each user to the text with index for selection
        for i, user in enumerate(users, 1):
            found_user_id, name, username, stars, is_banned = user
            status = "🚫" if is_banned else "✅"
            text += f"{i}. {status} *{name}* (@{username}) - {stars}⭐ - ID: {found_user_id}\n"

        # Create keyboard for user management
        keyboard = []

        # Add button for each user
        for user in users:
            found_user_id, name, username, stars, is_banned = user
            status = "🚫" if is_banned else "✅"

            keyboard.append([KeyboardButton(f"👤 Manage User ID: {found_user_id}")])

            # Store user mapping for easy reference
            context.user_data[f'user_manage_{found_user_id}'] = {
                'id': found_user_id,
                'name': name,
                'username': username,
                'stars': stars,
                'is_banned': is_banned
            }

        # Add navigation buttons
        keyboard.append([KeyboardButton("🔍 Search User")])
        keyboard.append([KeyboardButton("🔙 Back to Admin Menu")])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Send results and mark that we're in user management mode
        context.user_data['in_user_management'] = True

        await update.message.reply_text(
            text,
            parse_mode='Markdown'
        )

        await update.message.reply_text(
            "Select a user to manage or search for another user:",
            reply_markup=reply_markup
        )

        return ADMIN_MENU

    # Handle user management from keyboard buttons
    if search_query == "👥 User Management":
        # Log the button press
        logger.info("User Management button pressed from text handler")
        # Direct call to show users list
        await show_users_list(update, context)
        return ADMIN_MENU

    if search_query.startswith("👤 Manage User ID:"):
        # Extract user ID from the button text
        try:
            manage_user_id = int(search_query.replace("👤 Manage User ID:", "").strip())
            logger.info(f"Managing user ID: {manage_user_id}")
            return await search_user_by_id(update, context, manage_user_id)
        except ValueError as e:
            logger.error(f"Error parsing user ID: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # If the message doesn't match any of the conditions above,
    # show the search prompt again
    await update.message.reply_text(
        "🔍 *SEARCH USER*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter a username, name, or User ID to search for a specific user:",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_user_search'] = True
    return ADMIN_SEARCH_USER

# Helper function to show user details by ID
async def search_user_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    # Get comprehensive user details
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get comprehensive user info
    cursor.execute("""
        SELECT u.*, 
            (SELECT COUNT(*) FROM bookmarks WHERE user_id = u.user_id) as bookmark_count,
            (SELECT COUNT(*) FROM transactions WHERE user_id = u.user_id AND amount < 0) as download_count,
            (SELECT COUNT(*) FROM daily_logins WHERE user_id = u.user_id) as login_count
        FROM users u WHERE u.user_id = ?
    """, (user_id,))

    user = cursor.fetchone()
    conn.close()

    if not user:
        await update.message.reply_text(
            "❌ *Error*\n\nUser not found.",
            parse_mode='Markdown'
        )
        return ADMIN_MENU

    # Parse user data
    found_user_id = user[0]
    name = user[1]
    age = user[2]
    username = user[3]
    stars = user[4]
    reg_date = user[5]
    last_login = user[6]
    notification_enabled = user[7] if len(user) > 7 else 1
    terms_accepted = user[8] if len(user) > 8 else 1
    is_banned = user[9] if len(user) > 9 else 0
    warnings = user[10] if len(user) > 10 else 0
    ban_reason = user[11] if len(user) > 11 else "None"
    bookmark_count = user[12] if len(user) > 12 else 0
    download_count = user[13] if len(user) > 13 else 0
    login_count = user[14] if len(user) > 14 else 0

    # Calculate days as member
    try:
        reg_date_obj = datetime.strptime(reg_date, '%Y-%m-%d')
        days_member = (datetime.now() - reg_date_obj).days
    except:
        days_member = 0

    # Format the user details with enhanced information
    user_text = (
        f"👤 *USER DETAILS*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"*BASIC INFO*\n"
        f"• ID: {found_user_id}\n"
        f"• Name: {name}\n"
        f"• Username: @{username}\n"
        f"• Age: {age}\n"
        f"• Stars: {stars} ⭐\n"
        f"• Status: {'🚫 BANNED' if is_banned else '✅ ACTIVE'}\n"
        f"• Notifications: {'🔔 Enabled' if notification_enabled else '🔕 Disabled'}\n\n"

        f"*ACTIVITY INFO*\n"
        f"• Registered: {reg_date} ({days_member} days ago)\n"
        f"• Last login: {last_login}\n"
        f"• Total logins: {login_count}\n"
        f"• Downloads: {download_count}\n"
        f"• Bookmarks: {bookmark_count}\n"
        f"• Warnings: {warnings}\n\n"

        f"*ADMINISTRATIVE*\n"
        f"• Terms accepted: {'Yes' if terms_accepted else 'No'}\n"
        f"• Ban reason: {ban_reason}"
    )

    # Create keyboard for user management actions
    keyboard = [
        [KeyboardButton(f"➕ Add Stars to ID {found_user_id}"), KeyboardButton(f"➖ Remove Stars from ID {found_user_id}")],
        [KeyboardButton(f"{'🔓 Unban User ID' if is_banned else '🚫 Ban User ID'} {found_user_id}")],
        [KeyboardButton(f"⚠️ Warn User ID {found_user_id}"), KeyboardButton(f"🔄 Clear Warnings ID {found_user_id}")],
        [KeyboardButton("🔍 Search User"), KeyboardButton("🔙 Back to Admin Menu")]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Store target user ID in context
    context.user_data['target_user_id'] = found_user_id

    await update.message.reply_text(
        user_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    return ADMIN_MENU

async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Log entry to function for debugging
    logger.info("Entering show_users_list function")

    # Determine if this is from a callback query or direct message
    is_callback = hasattr(update, 'callback_query') and update.callback_query

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get most recent users first, then top 10 by stars
    cursor.execute("""
        SELECT user_id, name, username, stars, is_banned, registration_date 
        FROM users 
        ORDER BY registration_date DESC, stars DESC 
        LIMIT 10
    """)
    users = cursor.fetchall()

    # Get total user count for statistics
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # Get banned users count
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_count = cursor.fetchone()[0]

    # Get active users today
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM daily_logins WHERE login_date = ?", (today,))
    active_today = cursor.fetchone()[0]

    conn.close()

    if not users:
        text = "👥 *USER MANAGEMENT*\n" + "━" * 15 + "\n\nNo users found in the database."
        keyboard = [[KeyboardButton("🔙 Back to Admin Menu")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    else:
        # Create a more detailed and professionally formatted user management dashboard
        text = (
            f"👥 *USER MANAGEMENT DASHBOARD*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*STATISTICS:*\n"
            f"• Total Users: {total_users}\n"
            f"• Active Today: {active_today}\n"
            f"• Banned Users: {banned_count}\n\n"
            f"*RECENT USERS:*\n"
        )

        # List users in the text
        for user in users:
            user_id, name, username, stars, is_banned, _ = user
            status = "🚫" if is_banned else "✅"
            text += f"{status} *{name}* (@{username}) - {stars}⭐ - ID: `{user_id}`\n"

        # Create keyboard buttons for actions
        keyboard = [
            [KeyboardButton("🔍 Search User")]
        ]

        # Add buttons for each user
        for user in users:
            user_id, name, username, stars, is_banned, _ = user
            # Truncate username if needed
            display_name = (name[:15] + '...') if len(name) > 15 else name
            keyboard.append([KeyboardButton(f"👤 Manage User ID: {user_id}")])

        # Add more general options
        keyboard.append([KeyboardButton("⭐ Add Stars"), KeyboardButton("❌ Remove Stars")])
        keyboard.append([KeyboardButton("🔙 Back to Admin Menu")])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Store all users in context for quick reference
    context.user_data['admin_users_list'] = {user[0]: user for user in users}

    # Handle both callback query and direct message appropriately
    if is_callback:
        logger.info("Processing show_users_list for callback query")
        try:
            # Edit the original message
            await update.callback_query.message.edit_text(
                text,
                parse_mode='Markdown'
            )
            # Send the keyboard as a separate message
            await update.callback_query.message.reply_text(
                "Select a user to manage or use the search function:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in callback handling for user list: {e}")
            # If editing fails, send a new message
            await update.callback_query.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    else:
        logger.info("Processing show_users_list for direct message")
        try:
            # For direct messages, just send a new message
            await update.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error sending user list message: {e}")
            # Try a more minimal approach if there's an error
            await update.message.reply_text(
                "User list is being prepared. Please wait...",
                reply_markup=reply_markup
            )

    # Store a flag that we're in user management mode
    context.user_data['in_user_management'] = True
    logger.info("Exiting show_users_list function successfully")

async def show_ban_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get banned users
    cursor.execute("SELECT user_id, name, username, ban_reason FROM users WHERE is_banned = 1 ORDER BY user_id DESC LIMIT 10")
    banned_users = cursor.fetchall()

    # Get non-banned users
    cursor.execute("SELECT user_id, name, username FROM users WHERE is_banned = 0 ORDER BY user_id DESC LIMIT 10")
    active_users = cursor.fetchall()

    conn.close()

    banned_text = "🚫 *BAN MANAGEMENT*\n\n"

    if banned_users:
        banned_text += "*Currently Banned Users:*\n"
        for user in banned_users:
            user_id, name, username, reason = user
            reason = reason or "No reason provided"
            banned_text += f"• {name} (@{username}) - Reason: {reason}\n"
    else:
        banned_text += "*No banned users*\n"

    banned_text += "\nSelect a user to ban or unban:"

    keyboard = []

    # Add unban buttons for banned users
    for user in banned_users:
        user_id, name, username, _ = user
        keyboard.append([InlineKeyboardButton(
            f"✅ Unban: {name} (@{username})",
            callback_data=f"admin_unban_user_{user_id}"
        )])

    # Add ban buttons for active users
    for user in active_users:
        user_id, name, username = user
        keyboard.append([InlineKeyboardButton(
            f"🚫 Ban: {name} (@{username})",
            callback_data=f"admin_ban_user_{user_id}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back_to_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.edit_text(
        banned_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_ban_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    conn.close()

    if not user_info:
        await update.callback_query.message.edit_text(
            "❌ *Error*\n\nUser not found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_ban_management")]]),
            parse_mode='Markdown'
        )
        return

    name, username = user_info

    context.user_data['ban_user_id'] = user_id

    await update.callback_query.message.edit_text(
        f"🚫 *Ban User: {name} (@{username})*\n\n"
        f"Please enter the reason for banning this user:",
        parse_mode='Markdown'
    )

    return BAN_USER

async def process_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ban_reason = update.message.text
    user_id = context.user_data.get('ban_user_id')

    if not user_id:
        await update.message.reply_text(
            "❌ *Error*\n\nNo user selected for banning.",
            parse_mode='Markdown'
        )
        await show_admin_menu(update, context)
        return ADMIN_MENU

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get user info for the notification
    cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    if not user_info:
        conn.close()
        await update.message.reply_text(
            "❌ *Error*\n\nUser not found.",
            parse_mode='Markdown'
        )
        await show_admin_menu(update, context)
        return ADMIN_MENU

    name, username = user_info

    # Ban the user
    cursor.execute(
        "UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?",
        (ban_reason, user_id)
    )

    # Log the action
    admin_id = update.effective_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "BANNED", f"Banned by admin ID {admin_id}. Reason: {ban_reason}", today)
    )

    conn.commit()
    conn.close()

    # Notify the admin
    await update.message.reply_text(
        f"✅ *User Banned Successfully*\n\n"
        f"*User:* {name} (@{username})\n"
        f"*ID:* {user_id}\n"
        f"*Reason:* {ban_reason}\n\n"
        f"This user will no longer be able to access the bot.",
        parse_mode='Markdown'
    )

    # Try to notify the user
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⛔ *YOU HAVE BEEN BANNED* ⛔\n\n"
                f"You have been banned from using this bot.\n\n"
                f"*Reason:* {ban_reason}\n\n"
                f"If you believe this is an error, please contact {ADMIN_USERNAME} for assistance.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to send ban notification to user {user_id}: {e}")

    # Clear the user ID from context
    if 'ban_user_id' in context.user_data:
        del context.user_data['ban_user_id']

    await show_ban_management(update, context)
    return ADMIN_MENU

async def process_warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    warning_reason = update.message.text
    user_id = context.user_data.get('target_user_id')

    if not user_id:
        await update.message.reply_text(
            "❌ *Error*\n\nNo user selected for warning.",
            parse_mode='Markdown'
        )
        await show_admin_menu(update, context)
        return ADMIN_MENU

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get user info for the notification
    cursor.execute("SELECT name, username, warnings FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    if not user_info:
        conn.close()
        await update.message.reply_text(
            "❌ *Error*\n\nUser not found.",
            parse_mode='Markdown'
        )
        await show_admin_menu(update, context)
        return ADMIN_MENU

    name, username, current_warnings = user_info
    new_warnings = current_warnings + 1

    # Update warnings
    cursor.execute(
        "UPDATE users SET warnings = ? WHERE user_id = ?",
        (new_warnings, user_id)
    )

    # Log the action
    admin_id = update.effective_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "WARNING", f"Warned by admin ID {admin_id}. Reason: {warning_reason}", today)
    )

    conn.commit()
    conn.close()

    # Notify the admin
    await update.message.reply_text(
        f"⚠️ *Warning Issued Successfully*\n\n"
        f"*User:* {name} (@{username})\n"
        f"*ID:* {user_id}\n"
        f"*Previous Warnings:* {current_warnings}\n"
        f"*Current Warnings:* {new_warnings}\n"
        f"*Reason:* {warning_reason}\n\n"
        f"This user has been notified of the warning.",
        parse_mode='Markdown'
    )

    # Try to notify the user
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⚠️ *WARNING RECEIVED* ⚠️\n\n"
                f"You have received a warning from the administration.\n\n"
                f"*Reason:* {warning_reason}\n\n"
                f"*Current Warnings:* {new_warnings}\n\n"
                f"Multiple warnings may result in account restrictions or a ban.\n"
                f"If you believe this is an error, please contact {ADMIN_USERNAME} for assistance.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to send warning notification to user {user_id}: {e}")

    # Clear the user ID from context
    if 'target_user_id' in context.user_data:
        del context.user_data['target_user_id']

    await show_warning_management(update, context)
    return ADMIN_MENU

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get user info for the notification
    cursor.execute("SELECT name, username FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    if not user_info:
        conn.close()
        await update.callback_query.message.edit_text(
            "❌ *Error*\n\nUser not found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_ban_management")]]),
            parse_mode='Markdown'
        )
        return

    name, username = user_info

    # Unban the user
    cursor.execute(
        "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?",
        (user_id,)
    )

    # Log the action
    admin_id = update.effective_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
        (user_id, "UNBANNED", f"Unbanned by admin ID {admin_id}", today)
    )

    conn.commit()
    conn.close()

    # Notify the admin
    await update.callback_query.message.edit_text(
        f"✅ *User Unbanned Successfully*\n\n"
        f"*User:* {name} (@{username})\n"
        f"*ID:* {user_id}\n\n"
        f"This user can now access the bot again.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Ban Management", callback_data="admin_ban_management")]]),
        parse_mode='Markdown'
    )

    # Try to notify the user
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ *BAN REMOVED* ✅\n\n"
                f"Your account has been unbanned.\n"
                f"You can now use the bot again.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to send unban notification to user {user_id}: {e}")

async def show_warning_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get users with warnings
    cursor.execute("SELECT user_id, name, username, warnings FROM users WHERE warnings > 0 ORDER BY warnings DESC LIMIT 10")
    warned_users = cursor.fetchall()

    # Get active users
    cursor.execute("SELECT user_id, name, username FROM users WHERE warnings = 0 ORDER BY user_id DESC LIMIT 10")
    active_users = cursor.fetchall()

    conn.close()

    warning_text = "⚠️ *WARNING MANAGEMENT*\n\n"

    if warned_users:
        warning_text += "*Users with Warnings:*\n"
        for user in warned_users:
            user_id, name, username, warnings = user
            warning_text += f"• {name} (@{username}) - {warnings} warnings\n"
    else:
        warning_text += "*No users with warnings*\n"

    warning_text += "\nSelect a user to warn or clear warnings:"

    keyboard = []

    # Add clear warning buttons for warned users
    for user in warned_users:
        user_id, name, username, _ = user
        keyboard.append([InlineKeyboardButton(
            f"🔄 Clear Warnings: {name}",
            callback_data=f"admin_clear_warnings_{user_id}"
        )])

    # Add warn buttons for active users
    for user in active_users:
        user_id, name, username = user
        keyboard.append([InlineKeyboardButton(
            f"⚠️ Warn: {name} (@{username})",
            callback_data=f"admin_warn_user_{user_id}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back_to_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.edit_text(
        warning_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_star_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get top users by stars
    cursor.execute("SELECT user_id, name, username, stars FROM users ORDER BY stars DESC LIMIT 10")
    top_users = cursor.fetchall()

    conn.close()

    star_text = "💰 *STAR MANAGEMENT*\n\n"

    if top_users:
        star_text += "*Top Users by Star Balance:*\n"
        for user in top_users:
            user_id, name, username, stars = user
            star_text += f"• {name} (@{username}) - {stars} ⭐\n"
    else:
        star_text += "*No users found*\n"

    star_text += "\nSelect a user to add or remove stars:"

    keyboard = []

    # Add options for each user
    for user in top_users:
        user_id, name, username, _ = user
        keyboard.append([
            InlineKeyboardButton(f"➕ Add Stars: {name}", callback_data=f"admin_add_stars_{user_id}"),
            InlineKeyboardButton(f"➖ Remove Stars", callback_data=f"admin_remove_stars_{user_id}")
        ])

    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back_to_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.edit_text(
        star_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def process_quick_star_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    # Check if this is an initial button press
    if text in ["⭐ Add Stars", "❌ Remove Stars", "🔄 Remove Stars"]:
        operation_type = "add" if text == "⭐ Add Stars" else "remove"
        context.user_data['star_operation'] = operation_type

        await update.message.reply_text(
            f"{'⭐' if operation_type == 'add' else '🔄'} *{operation_type.upper()} STARS*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Please enter the user ID or username followed by the number of stars to {operation_type}.\n\n"
            f"*Format:* `user_id/username amount`\n"
            f"*Examples:*\n"
            f"• `123456789 10`\n"
            f"• `@username 10`\n",
            parse_mode='Markdown'
        )

        context.user_data['awaiting_star_command'] = True
        return ADMIN_QUICK_STAR_ADD

    # Check for user management button commands for adding/removing stars
    if text.startswith("➕ Add Stars to ID ") or text.startswith("➖ Remove Stars from ID "):
        operation_type = "add" if text.startswith("➕") else "remove"
        context.user_data['star_operation'] = operation_type

        # Extract user ID from button text
        try:
            if text.startswith("➕"):
                user_id_part = text.replace("➕ Add Stars to ID ", "").strip()
            else:
                user_id_part = text.replace("➖ Remove Stars from ID ", "").strip()

            target_user_id = int(user_id_part)
            context.user_data['target_user_id'] = target_user_id

            # Fetch user info
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, username, stars FROM users WHERE user_id = ?", (target_user_id,))
            user_info = cursor.fetchone()
            conn.close()

            if not user_info:
                await update.message.reply_text(
                    "❌ *User Not Found*\n\n"
                    f"No user found with ID: {target_user_id}\n"
                    "Please try again with a valid ID.",
                    parse_mode='Markdown'
                )
                return ADMIN_MENU

            name, username, current_stars = user_info

            # Ask for stars amount
            await update.message.reply_text(
                f"{'⭐' if operation_type == 'add' else '🔄'} *{operation_type.upper()} STARS*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n"
                f"*Current Stars:* {current_stars} ⭐\n\n"
                f"Please enter the number of stars to {operation_type}:",
                parse_mode='Markdown'
            )

            if operation_type == "add":
                return ADD_STARS
            else:
                return REMOVE_STARS

        except ValueError as e:
            logger.error(f"Error parsing user ID: {e}")
            await update.message.reply_text(
                "❌ *Error*\n\n"
                "Invalid user ID format.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

    # Process star command input
    if context.user_data.get('awaiting_star_command'):
        context.user_data['awaiting_star_command'] = False

        try:
            parts = text.split()

            if len(parts) < 2:
                await update.message.reply_text(
                    "❌ *Invalid Format*\n\n"
                    "Please use the format: `user_id/username amount`\n"
                    "Example: `123456789 10` or `@username 10`",
                    parse_mode='Markdown'
                )
                context.user_data['awaiting_star_command'] = True
                return ADMIN_QUICK_STAR_ADD

            user_identifier = parts[0]
            stars_amount = float(parts[1])

            # Check if this is a remove operation
            is_remove = context.user_data.get('star_operation') == 'remove'

            if stars_amount <= 0:
                await update.message.reply_text(
                    "❌ *Invalid Amount*\n\n"
                    "Please enter a positive number.",
                    parse_mode='Markdown'
                )
                context.user_data['awaiting_star_command'] = True
                return ADMIN_QUICK_STAR_ADD

            # If removing stars, make the value negative
            if is_remove:
                stars_to_add = -stars_amount
            else:
                stars_to_add = stars_amount

            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Find user by ID or username
            if user_identifier.isdigit():
                # Search by user ID
                cursor.execute("SELECT user_id, name, username, stars FROM users WHERE user_id = ?", (int(user_identifier),))
            else:
                # Search by username (remove @ if present)
                if user_identifier.startswith('@'):
                    user_identifier = user_identifier[1:]
                cursor.execute("SELECT user_id, name, username, stars FROM users WHERE username = ?", (user_identifier,))

            user_info = cursor.fetchone()

            if not user_info:
                conn.close()
                await update.message.reply_text(
                    "❌ *User Not Found*\n\n"
                    f"No user found with identifier: {user_identifier}\n"
                    "Please check the user ID or username and try again.",
                    parse_mode='Markdown'
                )
                context.user_data['awaiting_star_command'] = True
                return ADMIN_QUICK_STAR_ADD

            user_id, name, username, current_stars = user_info

            # Add stars
            new_stars = current_stars + stars_to_add

            # Ensure stars don't go negative
            if new_stars < 0:
                new_stars = 0
                stars_to_add = -current_stars

            cursor.execute(
                "UPDATE users SET stars = ? WHERE user_id = ?",
                (new_stars, user_id)
            )

            # Record transaction
            admin_id = update.effective_user.id
            today = datetime.now().strftime('%Y-%m-%d')

            operation_description = "added" if stars_to_add > 0 else "removed"
            transaction_description = f"Stars {operation_description} by admin ID {admin_id}"

            cursor.execute(
                "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
                (user_id, stars_to_add, transaction_description, today)
            )

            # Log activity
            activity_type = "STARS_ADDED" if stars_to_add > 0 else "STARS_REMOVED"
            activity_details = f"{abs(stars_to_add)} stars {operation_description} by admin ID {admin_id}"

            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (user_id, activity_type, activity_details, today)
            )

            conn.commit()
            conn.close()

            # Prepare keyboard for next action
            keyboard = [
                [KeyboardButton("⭐ Add More Stars"), KeyboardButton("🔄 Remove More Stars")],
                [KeyboardButton("🔙 Back to Admin Menu")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            # Use different messages for add vs remove
            if stars_to_add > 0:
                await update.message.reply_text(
                    f"✅ *STARS ADDED SUCCESSFULLY*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"*USER DETAILS:*\n"
                    f"• Name: {name}\n"
                    f"• Username: @{username}\n"
                    f"• User ID: {user_id}\n\n"
                    f"*TRANSACTION:*\n"
                    f"• Added: {abs(stars_to_add)} ⭐\n"
                    f"• Previous Balance: {current_stars} ⭐\n"
                    f"• New Balance: {new_stars} ⭐\n\n"
                    f"A notification has been sent to the user.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

                # Try to notify user
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"💰 *STARS ADDED* 💰\n\n"
                            f"*{abs(stars_to_add)} ⭐* have been added to your account!\n\n"
                            f"*Previous Balance:* {current_stars} ⭐\n"
                            f"*New Balance:* {new_stars} ⭐\n\n"
                            f"Enjoy using your stars!",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to send stars notification to user {user_id}: {e}")
            else:
                # For star removal (negative stars_to_add)
                removed_stars = abs(stars_to_add)
                await update.message.reply_text(
                    f"✅ *STARS REMOVED SUCCESSFULLY*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"*USER DETAILS:*\n"
                    f"• Name: {name}\n"
                    f"• Username: @{username}\n"
                    f"• User ID: {user_id}\n\n"
                    f"*TRANSACTION:*\n"
                    f"• Removed: {removed_stars} ⭐\n"
                    f"• Previous Balance: {current_stars} ⭐\n"
                    f"• New Balance: {new_stars} ⭐\n\n"
                    f"A notification has been sent to the user.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

                # Try to notify user
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⚠️ *STARS REMOVED* ⚠️\n\n"
                            f"*{removed_stars} ⭐* have been removed from your account.\n\n"
                            f"*Previous Balance:* {current_stars} ⭐\n"
                            f"*New Balance:* {new_stars} ⭐",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to send stars notification to user {user_id}: {e}")

            # Clear the star operation context
            if 'star_operation' in context.user_data:
                del context.user_data['star_operation']

            return ADMIN_MENU

        except ValueError as e:
            await update.message.reply_text(
                f"❌ *Invalid Input*\n\n"
                f"Please enter a valid number of stars.\n"
                f"Format: `user_id/username amount`\n"
                f"Example: `123456789 10` or `@username 10`",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_star_command'] = True
            return ADMIN_QUICK_STAR_ADD

    # Default case: prompt for star command
    await update.message.reply_text(
        "⭐ *MANAGE STARS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter user ID/username and star amount using this format:\n"
        "`user_id amount` or `@username amount`\n\n"
        "Example: `123456789 10` or `@username 10`",
        parse_mode='Markdown'
    )

    context.user_data['awaiting_star_command'] = True
    return ADMIN_QUICK_STAR_ADD

async def process_add_stars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        stars_to_add = float(update.message.text)
        user_id = context.user_data.get('target_user_id')

        if not user_id:
            await update.message.reply_text(
                "❌ *Error*\n\nNo user selected.",
                parse_mode='Markdown'
            )
            await show_admin_menu(update, context)
            return ADMIN_MENU

        if stars_to_add <= 0:
            await update.message.reply_text(
                "❌ *Invalid Amount*\n\n"
                "Please enter a positive number of stars to add.",
                parse_mode='Markdown'
            )
            return ADD_STARS

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Get user info
        cursor.execute("SELECT name, username, stars FROM users WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            conn.close()
            await update.message.reply_text(
                "❌ *Error*\n\nUser not found.",
                parse_mode='Markdown'
            )
            await show_admin_menu(update, context)
            return ADMIN_MENU

        name, username, current_stars = user_info

        # Add stars
        new_stars = current_stars + stars_to_add
        cursor.execute(
            "UPDATE users SET stars = ? WHERE user_id = ?",
            (new_stars, user_id)
        )

        # Record transaction
        admin_id = update.effective_user.id
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
            (user_id, stars_to_add, f"Added by admin ID {admin_id}", today)
        )

        # Log activity
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "STARS_ADDED", f"{stars_to_add} stars added by admin ID {admin_id}", today)
        )

        conn.commit()
        conn.close()

        # Notify admin
        keyboard = [
            [InlineKeyboardButton("➕ Add More Stars", callback_data=f"admin_add_stars_{user_id}")],
            [InlineKeyboardButton("🔙 Back to Star Management", callback_data="admin_star_management")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *Stars Added Successfully*\n\n"
            f"*User:* {name} (@{username})\n"
            f"*Added:* {stars_to_add} ⭐\n"
            f"*Previous Balance:* {current_stars} ⭐\n"
            f"*New Balance:* {new_stars} ⭐",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Try to notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"💰 *STARS ADDED* 💰\n\n"
                    f"*{stars_to_add} ⭐* have been added to your account!\n\n"
                    f"*Previous Balance:* {current_stars} ⭐\n"
                    f"*New Balance:* {new_stars} ⭐\n\n"
                    f"Enjoy using your stars!",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send stars notification to user {user_id}: {e}")

        # Clear user ID from context
        if 'target_user_id' in context.user_data:
            del context.user_data['target_user_id']

        return ADMIN_MENU

    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid Input*\n\n"
            "Please enter a valid number of stars to add.",
            parse_mode='Markdown'
        )
        return ADD_STARS

async def process_remove_stars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        stars_to_remove = float(update.message.text)
        user_id = context.user_data.get('target_user_id')

        if not user_id:
            await update.message.reply_text(
                "❌ *Error*\n\nNo user selected.",
                parse_mode='Markdown'
            )
            await show_admin_menu(update, context)
            return ADMIN_MENU

        if stars_to_remove <= 0:
            await update.message.reply_text(
                "❌ *Invalid Amount*\n\n"
                "Please enter a positive number of stars to remove.",
                parse_mode='Markdown'
            )
            return REMOVE_STARS

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Get user info
        cursor.execute("SELECT name, username, stars FROM users WHERE user_id = ?", (user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            conn.close()
            await update.message.reply_text(
                "❌ *Error*\n\nUser not found.",
                parse_mode='Markdown'
            )
            await show_admin_menu(update, context)
            return ADMIN_MENU

        name, username, current_stars = user_info

        # Check if user has enough stars
        if current_stars < stars_to_remove:
            stars_to_remove = current_stars  # Remove all available stars

        # Remove stars
        new_stars = current_stars - stars_to_remove
        cursor.execute(
            "UPDATE users SET stars = ? WHERE user_id = ?",
            (new_stars, user_id)
        )

        # Record transaction
        admin_id = update.effective_user.id
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
            (user_id, -stars_to_remove, f"Removed by admin ID {admin_id}", today)
        )

        # Log activity
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (user_id, "STARS_REMOVED", f"{stars_to_remove} stars removed by admin ID {admin_id}", today)
        )

        conn.commit()
        conn.close()

        # Create keyboard for next actions
        keyboard = [
            [KeyboardButton("🔍 Search User")],
            [KeyboardButton("⭐ Add Stars"), KeyboardButton("❌ Remove Stars")],
            [KeyboardButton("🔙 Back to Admin Menu")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Notify admin
        await update.message.reply_text(
            f"✅ *STARS REMOVED SUCCESSFULLY*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*USER DETAILS:*\n"
            f"• Name: {name}\n"
            f"• Username: @{username}\n"
            f"• User ID: {user_id}\n\n"
            f"*TRANSACTION:*\n"
            f"• Removed: {stars_to_remove} ⭐\n"
            f"• Previous Balance: {current_stars} ⭐\n"
            f"• New Balance: {new_stars} ⭐\n\n"
            f"A notification has been sent to the user.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Try to notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ *STARS REMOVED* ⚠️\n\n"
                    f"*{stars_to_remove} ⭐* have been removed from your account.\n\n"
                    f"*Previous Balance:* {current_stars} ⭐\n"
                    f"*New Balance:* {new_stars} ⭐\n\n"
                    f"If you have questions, please contact {ADMIN_USERNAME}.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send stars notification to user {user_id}: {e}")
            await update.message.reply_text(
                "⚠️ Could not send notification to user, but stars were removed successfully.",
                parse_mode='Markdown'
            )

        # Clear user ID from context
        if 'target_user_id' in context.user_data:
            del context.user_data['target_user_id']

        return ADMIN_MENU

    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid Input*\n\n"
            "Please enter a valid number of stars to remove.",
            parse_mode='Markdown'
        )
        return REMOVE_STARS

async def process_admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """Process broadcast message from admin panel"""
    if len(message_text.strip()) < 10:
        await update.message.reply_text(
            "❌ *MESSAGE TOO SHORT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Your broadcast message is too short. Please enter a more detailed message (at least 10 characters).",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_broadcast_text'] = True
        return

    # Get all active users
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await update.message.reply_text(
            "❌ *NO USERS FOUND*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "No active users found to send broadcast to.",
            parse_mode='Markdown'
        )
        return

    # Format the broadcast message
    formatted_message = (
        f"📣 *OFFICIAL ANNOUNCEMENT* 📣\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{message_text}\n\n"
        f"From: Unknown Leaks Admin Team"
    )

    sent_count = 0
    failed_count = 0

    progress_msg = await update.message.reply_text(
        f"⏳ *SENDING BROADCAST*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Sending to {len(users)} users...",
        parse_mode='Markdown'
    )

    for user_tuple in users:
        user_id = user_tuple[0]
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=formatted_message,
                parse_mode='Markdown'
            )
            sent_count += 1
            await asyncio.sleep(0.05)  # Small delay to avoid rate limits
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            failed_count += 1

    # Update progress message with results
    await progress_msg.edit_text(
        f"✅ *BROADCAST COMPLETE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Results:*\n"
        f"• Successfully sent: {sent_count}\n"
        f"• Failed: {failed_count}\n"
        f"• Total users: {len(users)}",
        parse_mode='Markdown'
    )

async def process_block_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id_text: str, action: str):
    """Process block/unblock user action"""
    try:
        target_user_id = int(user_id_text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ *INVALID USER ID*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter a valid numeric User ID.",
            parse_mode='Markdown'
        )
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Check if user exists
    cursor.execute("SELECT name, username, is_banned FROM users WHERE user_id = ?", (target_user_id,))
    user_info = cursor.fetchone()

    if not user_info:
        conn.close()
        await update.message.reply_text(
            f"❌ *USER NOT FOUND*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"No user found with ID: {target_user_id}",
            parse_mode='Markdown'
        )
        return

    name, username, is_banned = user_info
    admin_id = update.effective_user.id
    today = datetime.now().strftime('%Y-%m-%d')

    if action == 'block_user':
        if is_banned:
            await update.message.reply_text(
                f"⚠️ *USER ALREADY BLOCKED*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"User {name} (@{username}) is already blocked.",
                parse_mode='Markdown'
            )
        else:
            # Block the user
            cursor.execute(
                "UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?",
                ("Blocked by admin via admin panel", target_user_id)
            )

            # Log the action
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (target_user_id, "BLOCKED", f"Blocked by admin ID {admin_id}", today)
            )

            conn.commit()

            await update.message.reply_text(
                f"✅ *USER BLOCKED SUCCESSFULLY*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n\n"
                f"This user can no longer use the bot.",
                parse_mode='Markdown'
            )

            # Notify the user
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"🚫 *YOU ARE BLOCKED FROM THE BOT* 🚫\n\n"
                         f"Your access to this bot has been blocked by an administrator.\n\n"
                         f"If you believe this is an error, please contact {ADMIN_USERNAME}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify blocked user {target_user_id}: {e}")

    elif action == 'unblock_user':
        if not is_banned:
            await update.message.reply_text(
                f"⚠️ *USER NOT BLOCKED*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"User {name} (@{username}) is not currently blocked.",
                parse_mode='Markdown'
            )
        else:
            # Unblock the user
            cursor.execute(
                "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?",
                (target_user_id,)
            )

            # Log the action
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (target_user_id, "UNBLOCKED", f"Unblocked by admin ID {admin_id}", today)
            )

            conn.commit()

            await update.message.reply_text(
                f"✅ *USER UNBLOCKED SUCCESSFULLY*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*User:* {name} (@{username})\n"
                f"*ID:* {target_user_id}\n\n"
                f"This user can now use the bot again.",
                parse_mode='Markdown'
            )

            # Notify the user
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"✅ *YOU HAVE BEEN UNBLOCKED* ✅\n\n"
                         f"Your access to this bot has been restored.\n\n"
                         f"You can now use the bot normally.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify unblocked user {target_user_id}: {e}")

    conn.close()

async def process_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    APPROVED_ADMINS = [ADMIN_ID, 6648598512, 7062972013]

    # Get the message text if available
    broadcast_message = update.message.text if hasattr(update, 'message') and hasattr(update.message, 'text') else None

    # First verify admin
    if user_id not in APPROVED_ADMINS and not context.user_data.get('admin_authenticated'):
        await update.message.reply_text(
            "❌ *Unauthorized Access*\n\n"
            "You don't have permission to use this feature.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Handle entering broadcast mode
    if broadcast_message == "📣 Broadcast Message" or broadcast_message == "📣 Broadcast":
        await update.message.reply_text(
            "📣 *SEND BROADCAST MESSAGE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please enter the message you want to broadcast to all users:",
            parse_mode='Markdown'
        )
        # Set flag that we're awaiting broadcast text
        context.user_data['awaiting_broadcast_text'] = True
        return ADMIN_BROADCAST

    # Check if we're awaiting broadcast text
    if context.user_data.get('awaiting_broadcast_text'):
        # Clear the flag
        context.user_data.pop('awaiting_broadcast_text', None)

        # Validate message
        if not broadcast_message or len(broadcast_message.strip()) < 10:
            await update.message.reply_text(
                "❌ *MESSAGE TOO SHORT*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Your broadcast message is too short. Please enter a more detailed message (at least 10 characters).",
                parse_mode='Markdown'
            )
            # Set the flag again
            context.user_data['awaiting_broadcast_text'] = True
            return ADMIN_BROADCAST

        # Show confirmation before sending
        context.user_data['pending_broadcast_message'] = broadcast_message

        # Preview the message
        formatted_preview = (
            f"📣 *OFFICIAL ANNOUNCEMENT* 📣\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{broadcast_message}\n\n"
            f"From: Unknown Leaks Admin Team"
        )

        await update.message.reply_text(
            "📋 *BROADCAST PREVIEW*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "This is how your message will appear to users:\n\n" +
            formatted_preview,
            parse_mode='Markdown'
        )

        # Ask for confirmation
        keyboard = [
            [KeyboardButton("✅ YES, SEND TO ALL USERS")],
            [KeyboardButton("❌ NO, CANCEL")]
        ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "⚠️ *CONFIRM BROADCAST*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Are you sure you want to send this broadcast to all users?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Set flag that we're awaiting confirmation
        context.user_data['awaiting_broadcast_confirmation'] = True
        return ADMIN_BROADCAST

    # Check if we're awaiting confirmation
    if context.user_data.get('awaiting_broadcast_confirmation'):
        # Clear the flag
        context.user_data.pop('awaiting_broadcast_confirmation', None)

        # Check response
        if broadcast_message != "✅ YES, SEND TO ALL USERS":
            # Broadcast cancelled
            await update.message.reply_text(
                "📣 *BROADCAST CANCELLED*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Your broadcast has been cancelled. No messages were sent.",
                parse_mode='Markdown'
            )

            # Return to admin menu
            await show_admin_menu(update, context)
            return ADMIN_MENU

        # Get the pending message
        broadcast_message = context.user_data.pop('pending_broadcast_message', "")
        if not broadcast_message:
            await update.message.reply_text(
                "❌ *ERROR*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "There was an error retrieving your broadcast message. Please try again.",
                parse_mode='Markdown'
            )

            # Return to admin menu
            await show_admin_menu(update, context)
            return ADMIN_MENU

        # Get all users with proper error handling
        try:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
            users = cursor.fetchall()
            conn.close()
        except Exception as e:
            logger.error(f"Database error when fetching users for broadcast: {e}")
            await update.message.reply_text(
                "❌ *DATABASE ERROR*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Error fetching users: {str(e)}\n\n"
                "Please try again later.",
                parse_mode='Markdown'
            )
            return ADMIN_MENU

        sent_count = 0
        failed_count = 0
        failed_users = []  # Store failed user IDs for retry

        # Add formatted header to the message
        formatted_message = (
            f"📣 *OFFICIAL ANNOUNCEMENT* 📣\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{broadcast_message}\n\n"
            f"From: Unknown Leaks Admin Team"
        )

        # Store the message in context for retry functionality
        context.user_data['broadcast_message'] = formatted_message

        progress_message = await update.message.reply_text(
            "⏳ *SENDING BROADCAST*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please wait while the message is sent to all users...\n"
            "This may take some time.",
            parse_mode='Markdown'
        )

        # Calculate eligible users and flatten list of tuples to simple list
        total_eligible = len(users)
        user_ids = [user[0] for user in users]

        # Process in smaller batches to avoid rate limits
        batch_size = 30
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i+batch_size]

            for user_id in batch:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=formatted_message,
                        parse_mode='Markdown'
                    )
                    sent_count += 1

                    # Add a small delay between messages to avoid rate limiting
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"Failed to send broadcast to user {user_id}: {e}")
                    failed_count += 1
                    failed_users.append(user_id)

                # Update progress every 10 messages or at 25%, 50%, 75% milestones
                if sent_count % 10 == 0 or (total_eligible > 0 and sent_count / total_eligible in [0.25, 0.5, 0.75, 0.9]):
                    try:
                        percent = int((sent_count / total_eligible) * 100) if total_eligible > 0 else 0
                        await progress_message.edit_text(
                            f"⏳ *SENDING BROADCAST*\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"Progress: {sent_count}/{total_eligible} users ({percent}%)\n"
                            f"• Successful: {sent_count}\n"
                            f"• Failed: {failed_count}\n\n"
                            f"Please wait...",
                            parse_mode='Markdown'
                        )
                    except Exception as edit_error:
                        logger.error(f"Failed to update progress: {edit_error}")

            # Add a pause between batches to avoid rate limits
            if i + batch_size < len(user_ids):
                await asyncio.sleep(1)

        # Store failed users for retry
        context.user_data['broadcast_failed_users'] = failed_users

        # Create keyboard with retry option if there were failures
        keyboard = []
        if failed_count > 0:
            keyboard.append([KeyboardButton("🔄 Retry Failed Messages")])

        keyboard.append([KeyboardButton("🔙 Back to Admin Menu")])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Show final report
        try:
            await progress_message.edit_text(
                f"✅ *BROADCAST COMPLETE*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Message sent to {sent_count} users*\n"
                f"• Failed deliveries: {failed_count}\n\n"
                f"*Total users:* {total_eligible}\n\n"
                f"{f'Use the RETRY button to attempt resending to {failed_count} failed users.' if failed_count > 0 else ''}",
                parse_mode='Markdown'
            )
        except Exception:
            # If edit fails, send a new message
            await update.message.reply_text(
                f"✅ *BROADCAST COMPLETE*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Message sent to {sent_count} users*\n"
                f"• Failed deliveries: {failed_count}\n\n"
                f"*Total users:* {total_eligible}\n\n"
                f"{f'Use the RETRY button to attempt resending to {failed_count} failed users.' if failed_count > 0 else ''}",
                parse_mode='Markdown'
            )

        # Send keyboard separately
        await update.message.reply_text(
            "Select an option:",
            reply_markup=reply_markup
        )

        # Log the broadcast
        admin_id = update.effective_user.id
        today = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
            (admin_id, "BROADCAST", f"Sent broadcast to {sent_count} users, {failed_count} failed", today)
        )
        conn.commit()
        conn.close()

        return ADMIN_MENU

    # Handle retry button press
    if broadcast_message == "🔄 Retry Failed Messages":
        return await retry_broadcast(update, context)

    # Default case: if we got here, show broadcast input prompt
    await update.message.reply_text(
        "📣 *SEND BROADCAST MESSAGE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter the message you want to broadcast to all users:",
        parse_mode='Markdown'
    )
    # Set flag that we're awaiting broadcast text
    context.user_data['awaiting_broadcast_text'] = True
    return ADMIN_BROADCAST

async def show_transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Get recent transactions
    cursor.execute("""
        SELECT t.id, t.user_id, u.name, u.username, t.amount, t.description, t.transaction_date
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
        ORDER BY t.id DESC
        LIMIT 15
    """)

    transactions = cursor.fetchall()

    # Get summary stats
    cursor.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE amount > 0")
    positive_txn = cursor.fetchone()
    cursor.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE amount < 0")
    negative_txn = cursor.fetchone()

    conn.close()

    txn_text = "💹 *TRANSACTION HISTORY*\n" + "━" * 15 + "\n\n"

    # Add summary
    txn_text += "*SUMMARY:*\n"
    txn_text += f"• Total Credits: {positive_txn[0]} transactions, {positive_txn[1]} ⭐\n"
    txn_text += f"• Total Debits: {negative_txn[0]} transactions, {abs(negative_txn[1] or 0)} ⭐\n\n"

    txn_text += "*RECENT TRANSACTIONS:*\n"

    # Add recent transactions
    if transactions:
        for txn in transactions:
            txn_id, user_id, name, username, amount, desc, date = txn
            # Format differently based on credit/debit
            if amount > 0:
                txn_text += f"➕ {name}: +{amount} ⭐ ({desc[:20]}...)\n"
            else:
                txn_text += f"➖ {name}: {amount} ⭐ ({desc[:20]}...)\n"
    else:
        txn_text += "No transactions found."

    keyboard = [
        [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_back_to_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.edit_text(
        txn_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Handle text messages for keyboard buttons
async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID or context.user_data.get('admin_authenticated', False)

    # Log the text command for debugging
    logger.info(f"Received text message: {text} from user {user_id}, is_admin: {is_admin}")

    # Handle admin panel buttons first
    if is_admin and text in ["👥 User Management", "📣 Broadcast Message", "🚫 Block User", "🔓 Unblock User"]:
        if text == "👥 User Management":
            await show_users_list(update, context)
            return
        elif text == "📣 Broadcast Message":
            await update.message.reply_text(
                "📣 *SEND BROADCAST MESSAGE*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the message you want to broadcast to all users:",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_broadcast_text'] = True
            return
        elif text == "🚫 Block User":
            await update.message.reply_text(
                "🚫 *BLOCK USER FROM BOT*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the User ID of the user you want to block from using the bot:",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'block_user'
            return
        elif text == "🔓 Unblock User":
            await update.message.reply_text(
                "🔓 *UNBLOCK USER FROM BOT*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the User ID of the user you want to unblock:",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'unblock_user'
            return

    # Handle broadcast message input
    if is_admin and context.user_data.get('awaiting_broadcast_text'):
        context.user_data.pop('awaiting_broadcast_text', None)
        await process_admin_broadcast_message(update, context, text)
        return

    # Handle block/unblock user input
    if is_admin and context.user_data.get('admin_action') in ['block_user', 'unblock_user']:
        action = context.user_data.pop('admin_action')
        await process_block_unblock_user(update, context, text, action)
        return

    # Handle mass delete mode if active
    if is_admin and context.user_data.get('mass_delete_mode'):
        await handle_mass_delete_from_text(update, context)
        return

    # Handle mass delete confirmation if waiting
    if is_admin and context.user_data.get('awaiting_mass_delete_confirmation'):
        await execute_mass_delete(update, context)
        return

    # Handle direct media deletion from ID button 
    if is_admin and text.startswith("🗑️ Delete ID #"):
        try:
            # Extract media ID from button text
            media_id_part = text.replace("🗑️ Delete ID #", "").strip()
            if ":" in media_id_part:  # Format: "🗑️ Delete ID #123: 📷 Caption"
                media_id_part = media_id_part.split(":")[0].strip()

            media_id = int(media_id_part)

            # Call admin_delete_media function
            await admin_delete_media(update, context, media_id)
            return
        except ValueError as e:
            logger.error(f"Error parsing media ID from button: {e}")
            # Continue with regular text handling

    # Handle /admin command as text input
    if text == "/admin":
        # Skip password verification for admin user
        if user_id == ADMIN_ID:
            await show_admin_menu(update, context)
            return ADMIN_MENU
        else:
            # Use a modern password entry screen
            await update.message.reply_text(
                "🔒 *ADMIN AUTHENTICATION*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the admin password:",
                parse_mode='Markdown'
            )
            context.user_data['admin_password'] = ""
            return ADMIN_AUTH

    # Handle purchase & download button
    if text == "💳 Purchase":
        media_id = context.user_data.get('current_media_id')
        if media_id:
            await handle_download_from_text(update, context, media_id)
        else:
            await update.message.reply_text(
                "❌ *No Media Selected*\n\n"
                "Please select a video first before purchasing.",
                parse_mode='Markdown'
            )
        return

    # Handle bookmark button
    if text == "🔖 Bookmark":
        media_id = context.user_data.get('current_media_id')
        if media_id:
            await handle_bookmark_from_text(update, context, media_id, user_id)

            # Refresh the current media display to show updated bookmark status
            current_media_type = context.user_data.get('current_media_type')
            if current_media_type:
                await send_media_with_navigation(update, context, current_media_type)
        else:
            await update.message.reply_text(
                "❌ *No Media Selected*\n\n"
                "Please select a video first before bookmarking.",
                parse_mode='Markdown'
            )
        return

    # Handle like/dislike buttons
    if text in ["👍 Like", "👎 Dislike"]:
        media_id = context.user_data.get('current_media_id')
        if media_id:
            rating = "like" if text == "👍 Like" else "dislike"

            # Save rating to database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Create ratings table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS media_ratings (
                media_id INTEGER,
                user_id INTEGER,
                rating TEXT,
                rating_date TEXT,
                PRIMARY KEY (media_id, user_id)
            )
            ''')

            # Check if user already rated this media
            cursor.execute("SELECT rating FROM media_ratings WHERE media_id = ? AND user_id = ?", (media_id, user_id))
            existing_rating = cursor.fetchone()

            today = datetime.now().strftime('%Y-%m-%d')
            if existing_rating:
                # Update existing rating
                cursor.execute(
                    "UPDATE media_ratings SET rating = ?, rating_date = ? WHERE media_id = ? AND user_id = ?",
                    (rating, today, media_id, user_id)
                )
                message = f"Rating updated to {rating}!"
            else:
                # Add new rating
                cursor.execute(
                    "INSERT INTO media_ratings (media_id, user_id, rating, rating_date) VALUES (?, ?, ?, ?)",
                    (media_id, user_id, rating, today)
                )
                message = f"Thanks for your {rating}!"

            conn.commit()
            conn.close()

            # Show confirmation
            await update.message.reply_text(
                f"✅ *{message}*",
                parse_mode='Markdown'
            )

            # Refresh the current media display to show updated ratings
            current_media_type = context.user_data.get('current_media_type')
            if current_media_type:
                await send_media_with_navigation(update, context, current_media_type)
        else:
            await update.message.reply_text(
                "❌ *No Media Selected*\n\n"
                "Please select a video first before rating.",
                parse_mode='Markdown'
            )
        return

    # Handle navigation buttons with anti-spam protection
    if text in ["➡️ Next", "⬅️ Previous"]:
        # Check cooldown for navigation buttons (2 seconds)
        if not await check_button_cooldown(user_id, "navigation", 2):
            await update.message.reply_text(
                "⏳ *Please wait* ⏳\n\n"
                "You can only navigate every 2 seconds to prevent spam.",
                parse_mode='Markdown'
            )
            return

        # Handle next/previous navigation
        if text == "➡️ Next":
            if 'current_media_type' in context.user_data:
                media_type = context.user_data['current_media_type']
                if media_type == "video":
                    videos = context.user_data.get('videos', [])
                    if videos:
                        current_index = context.user_data.get('current_video_index', 0)
                        current_index = (current_index + 1) % len(videos)
                        context.user_data['current_video_index'] = current_index
                        await send_media_with_navigation(update, context, "video")
                elif media_type == "photo":
                    photos = context.user_data.get('photos', [])
                    if photos:
                        current_index = context.user_data.get('current_photo_index', 0)
                        current_index = (current_index + 1) % len(photos)
                        context.user_data['current_photo_index'] = current_index
                        await send_media_with_navigation(update, context, "photo")
        elif text == "⬅️ Previous":
            if 'current_media_type' in context.user_data:
                media_type = context.user_data['current_media_type']
                if media_type == "video":
                    videos = context.user_data.get('videos', [])
                    if videos:
                        current_index = context.user_data.get('current_video_index', 0)
                        current_index = (current_index - 1) % len(videos)
                        context.user_data['current_video_index'] = current_index
                        await send_media_with_navigation(update, context, "video")
                elif media_type == "photo":
                    photos = context.user_data.get('photos', [])
                    if photos:
                        current_index = context.user_data.get('current_photo_index', 0)
                        current_index = (current_index - 1) % len(photos)
                        context.user_data['current_photo_index'] = current_index
                        await send_media_with_navigation(update, context, "photo")
        return

    # Handle like/dislike buttons with anti-spam protection
    if text in ["👍 Like", "👎 Dislike"]:
        # Check cooldown for like/dislike buttons
        if not await check_button_cooldown(user_id, "rating", 3):
            await update.message.reply_text(
                "⏳ *Please wait* ⏳\n\n"
                "You can only rate every 3 seconds to prevent spam.",
                parse_mode='Markdown'
            )
            return

        media_id = context.user_data.get('current_media_id')
        if media_id:
            rating = "like" if text == "👍 Like" else "dislike"

            # Save rating to database
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                INSERT OR REPLACE INTO media_ratings (media_id, user_id, rating, rating_date) 
                VALUES (?, ?, ?, ?)
            """, (media_id, user_id, rating, today))

            conn.commit()
            conn.close()

            await update.message.reply_text(f"✅ You {rating}d this content!")
        return

    # Handle bookmark button with anti-spam protection
    if text in ["🔖 Add Bookmark", "🔖 Remove Bookmark", "🔖 Bookmark"]:
        # Check cooldown for bookmark button
        if not await check_button_cooldown(user_id, "bookmark", 2):
            await update.message.reply_text(
                "⏳ *Please wait* ⏳\n\n"
                "You can only bookmark every 2 seconds to prevent spam.",
                parse_mode='Markdown'
            )
            return

        media_id = context.user_data.get('current_media_id')
        if media_id:
            # Check if user has purchased this content before allowing bookmark
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Check if user has downloaded/purchased this media
            cursor.execute(
                "SELECT * FROM transactions WHERE user_id = ? AND description LIKE ? AND amount < 0", 
                (user_id, f"Downloaded %{media_id}%")
            )
            purchase_record = cursor.fetchone()
            conn.close()

            if not purchase_record:
                await update.message.reply_text(
                    "❌ *PURCHASE REQUIRED* ❌\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "You need to purchase and download this content before you can bookmark it.\n\n"
                    "Please use the 'Download' button first.",
                    parse_mode='Markdown'
                )
                return

            await handle_bookmark(update, context, media_id, user_id)
        return

    # Handle media action buttons
    if text in ["💾 Download", "💾 Re-download"] and 'current_media_id' in context.user_data:
        media_id = context.user_data.get('current_media_id')
        if media_id:
            # Instead of modifying update object, call the function directly
            user_id = update.effective_user.id

            # Get user stars and media info
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()

            if not user:
                conn.close()
                await update.message.reply_text("You need to register first. Please use /start")
                return

            user_stars = user[0]

            cursor.execute("SELECT * FROM media WHERE id = ?", (media_id,))
            media = cursor.fetchone()

            if not media:
                conn.close()
                await update.message.reply_text("This media is no longer available.")
                return

            media_id, media_type, file_id, caption, price = media[0], media[1], media[2], media[3], media[4]

            # Check if this is a re-download from bookmarks
            is_redownload = text == "💾 Re-download"

            # Check if user has already purchased this (for re-downloads)
            if is_redownload:
                cursor.execute(
                    "SELECT * FROM transactions WHERE user_id = ? AND description LIKE ? AND amount < 0", 
                    (user_id, f"Downloaded %{media_id}%")
                )
                previous_purchase = cursor.fetchone()

                if previous_purchase:
                    # It's a re-download of already purchased content, so no need to charge stars
                    today = datetime.now().strftime('%Y-%m-%d')

                    # Log activity without charging
                    cursor.execute(
                        "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                        (user_id, "REDOWNLOAD", f"Re-downloaded {media_type} #{media_id}", today)
                    )

                    conn.commit()
                    conn.close()

                    # Send re-downloadable media with a receipt-like message
                    download_caption = (
                        f"✅ *RE-DOWNLOAD SUCCESSFUL* ✅\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"{caption}\n\n"
                        f"This is a previously purchased item that you've re-downloaded from your bookmarks."
                    )

                    try:
                        if media_type == "photo":
                            await update.message.reply_photo(
                                photo=file_id,
                                caption=download_caption,
                                parse_mode='Markdown',
                                protect_content=False
                            )
                        else:
                            await update.message.reply_video(
                                video=file_id,
                                caption=download_caption,
                                parse_mode='Markdown',
                                protect_content=False
                            )
                    except Exception as e:
                        logger.error(f"Error sending re-downloaded media: {e}")
                        # Fallback if sending fails
                        await update.message.reply_text(
                            f"{download_caption}\n\n⚠️ *Media preview not available*\n\nPlease contact support if you don't receive your download.",
                            parse_mode='Markdown'
                        )

                    await update.message.reply_text("✅ Re-download successful! No stars were charged.")
                    return
                # If no previous purchase found, continue to regular purchase flow

            # Regular purchase flow - Check if user has enough stars
            if user_stars < price:
                conn.close()

                # Create a visually appealing insufficient funds message
                insufficient_text = (
                    "❌ *INSUFFICIENT STARS* ❌\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"*Required:* {price} ⭐\n"
                    f"*Your Balance:* {user_stars} ⭐\n"
                    f"*Missing:* {price - user_stars} ⭐\n\n"
                    f"Would you like to purchase more stars?"
                )

                await update.message.reply_text(
                    insufficient_text,
                    parse_mode='Markdown'
                )

                # Show buy stars options with keyboard buttons for better UX
                keyboard = [
                    [KeyboardButton("💰 Buy Stars")],
                    [KeyboardButton("🔙 Back")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                await update.message.reply_text(
                    "Select an option:",
                    reply_markup=reply_markup
                )
                return

            # Deduct stars
            cursor.execute("UPDATE users SET stars = stars - ? WHERE user_id = ?", (price, user_id))

            # Record transaction
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute(
                "INSERT INTO transactions (user_id, amount, description, transaction_date) VALUES (?, ?, ?, ?)",
                (user_id, -price, f"Downloaded {media_type} #{media_id}", today)
            )

            # Log activity
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                (user_id, "DOWNLOAD", f"Downloaded {media_type} #{media_id}", today)
            )

            conn.commit()
            conn.close()

            # Send downloadable media with a receipt-like message
            download_caption = (
                f"✅ *DOWNLOAD SUCCESSFUL* ✅\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{caption}\n\n"
                f"💰 *TRANSACTION*\n"
                f"• Item: {media_type.capitalize()} #{media_id}\n"
                f"• Cost: {price} ⭐\n"
                f"• Date: {today}\n\n"
                f"Thank you for your purchase! You can now bookmark this content."
            )

            try:
                if media_type == "photo":
                    await update.message.reply_photo(
                        photo=file_id,
                        caption=download_caption,
                        parse_mode='Markdown',
                        protect_content=False
                    )
                else:
                    await update.message.reply_video(
                        video=file_id,
                        caption=download_caption,
                        parse_mode='Markdown',
                        protect_content=False
                    )
            except Exception as e:
                logger.error(f"Error sending downloaded media: {e}")
                # Fallback if sending fails
                await update.message.reply_text(
                    f"{download_caption}\n\n⚠️ *Media preview not available*\n\nPlease contact support if you don't receive your download.",
                    parse_mode='Markdown'
                )

            await update.message.reply_text(f"✅ Download successful! You spent {price} ⭐")

            # Keep the same navigation buttons - don't change anything
            # This allows users to bookmark immediately after purchasing
            return

    elif text in ["🔖 Bookmark", "🔖 Add Bookmark", "🔖 Remove Bookmark"] and 'current_media_id' in context.user_data:
        media_id = context.user_data.get('current_media_id')
        if media_id:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Check if already bookmarked
            cursor.execute("SELECT * FROM bookmarks WHERE user_id = ? AND media_id = ?", (user_id, media_id))
            bookmark = cursor.fetchone()

            # Get media info for UI updates
            cursor.execute("SELECT type FROM media WHERE id = ?", (media_id,))
            media_info = cursor.fetchone()
            media_type = media_info[0] if media_info else context.user_data.get('current_media_type', 'photo')

            today = datetime.now().strftime('%Y-%m-%d')

            if bookmark or text == "🔖 Remove Bookmark":
                # Remove bookmark - always allow removing
                cursor.execute("DELETE FROM bookmarks WHERE user_id = ? AND media_id = ?", (user_id, media_id))
                message = "🔖 Bookmark removed!"

                # Log activity
                cursor.execute(
                    "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                    (user_id, "BOOKMARK_REMOVE", f"Removed bookmark for media #{media_id}", today)
                )

                conn.commit()
                conn.close()

                await update.message.reply_text(message)

                # Check if we're in bookmarks view
                if context.user_data.get('current_bookmark_index') is not None and 'bookmarks' in context.user_data:
                    # Remove the bookmark from the current list
                    bookmarks = context.user_data.get('bookmarks', [])
                    filtered_bookmarks = [b for b in bookmarks if b[0] != media_id]
                    context.user_data['bookmarks'] = filtered_bookmarks

                    # Adjust current index if needed
                    current_index = context.user_data.get('current_bookmark_index', 0)
                    if current_index >= len(filtered_bookmarks) and filtered_bookmarks:
                        context.user_data['current_bookmark_index'] = len(filtered_bookmarks) - 1
                    elif not filtered_bookmarks:
                        # If no bookmarks left, go home
                        await update.message.reply_text(
                            "📚 *NO BOOKMARKS LEFT*\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "You have removed all your bookmarks.\n"
                            "Returning to home screen.",
                            parse_mode='Markdown',
                            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🏠 Home")]], resize_keyboard=True)
                        )
                        await show_home_menu(update, context)
                        return

                    # Show next bookmark if available
                    if filtered_bookmarks:
                        await send_bookmark_for_text_command(update, context)
                    return

                # Create appropriate keyboard based on media type for regular browsing
                if media_type == "photo":
                    keyboard = [
                        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
                        [KeyboardButton("👍 Like"), KeyboardButton("👎 Dislike")],
                        [KeyboardButton("💾 Download"), KeyboardButton("🔖 Add Bookmark")],
                        [KeyboardButton("🏠 Home")]
                    ]
                else:  # video
                    keyboard = [
                        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
                        [KeyboardButton("👍 Like"), KeyboardButton("👎 Dislike")],
                        [KeyboardButton("💳 Purchase & Download"), KeyboardButton("🔖 Add Bookmark")],
                        [KeyboardButton("🏠 Home")]
                    ]

                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                await update.message.reply_text(
                    "Bookmark removed. Use these buttons to continue navigation:",
                    reply_markup=reply_markup
                )
                return
            else:
                # Check if user has purchased this media
                cursor.execute(
                    "SELECT * FROM transactions WHERE user_id = ? AND description LIKE ? AND amount < 0", 
                    (user_id, f"Downloaded %{media_id}%")
                )
                purchase_record = cursor.fetchone()

                if not purchase_record:
                    conn.close()
                    await update.message.reply_text(
                        "❌ *PURCHASE REQUIRED* ❌\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "You need to purchase and download this content before you can bookmark it.\n\n"
                        "Please use the 'Download' button first.",
                        parse_mode='Markdown'
                    )
                    return

                # Add bookmark after purchase is verified
                cursor.execute(
                    "INSERT INTO bookmarks (user_id, media_id, bookmark_date) VALUES (?, ?, ?)", 
                    (user_id, media_id, today)
                )
                message = "🔖 Bookmark added!"

                # Log activity
                cursor.execute(
                    "INSERT INTO user_activity (user_id, activity_type, details, activity_date) VALUES (?, ?, ?, ?)",
                    (user_id, "BOOKMARK_ADD", f"Added bookmark for media #{media_id}", today)
                )

                conn.commit()
                conn.close()

                await update.message.reply_text(message)

                # Create appropriate keyboard based on media type
                if media_type == "photo":
                    keyboard = [
                        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
                        [KeyboardButton("👍 Like"), KeyboardButton("👎 Dislike")],
                        [KeyboardButton("💾 Download"), KeyboardButton("🔖 Remove Bookmark")],
                        [KeyboardButton("🏠 Home")]
                    ]
                else:  # video
                    keyboard = [
                        [KeyboardButton("⬅️ Previous"), KeyboardButton("➡️ Next")],
                        [KeyboardButton("👍 Like"), KeyboardButton("👎 Dislike")],
                        [KeyboardButton("💳 Purchase & Download"), KeyboardButton("🔖 Remove Bookmark")],
                        [KeyboardButton("🏠 Home")]
                    ]

                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                await update.message.reply_text(
                    "Bookmark added. Use these buttons to continue navigation:",
                    reply_markup=reply_markup
                )
                return

    elif text == "👍 Like" and 'current_media_id' in context.user_data:
        media_id = context.user_data.get('current_media_id')
        media_type = context.user_data.get('current_media_type')
        if media_id:
            try:
                # Save the like to database
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()

                # Create ratings table if it doesn't exist
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS media_ratings (
                    media_id INTEGER,
                    user_id INTEGER,
                    rating TEXT,
                    rating_date TEXT,
                    PRIMARY KEY (media_id, user_id)
                )
                ''')

                # Check if user already rated this media
                cursor.execute("SELECT rating FROM media_ratings WHERE media_id = ? AND user_id = ?", (media_id, user_id))
                existing_rating = cursor.fetchone()

                today = datetime.now().strftime('%Y-%m-%d')
                if existing_rating:
                    # Update existing rating
                    cursor.execute(
                        "UPDATE media_ratings SET rating = ?, rating_date = ? WHERE media_id = ? AND user_id = ?",
                        ('like', today, media_id, user_id)
                    )
                    message = "Your rating has been updated to 👍"
                else:
                    # Add new rating
                    cursor.execute(
                        "INSERT INTO media_ratings (media_id, user_id, rating, rating_date) VALUES (?, ?, ?, ?)",
                        (media_id, user_id, 'like', today)
                    )
                    message = "Thanks for your like! 👍"

                conn.commit()
                conn.close()

                await update.message.reply_text(message)

                # Get count of current likes and dislikes
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'like'", (media_id,))
                likes = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'dislike'", (media_id,))
                dislikes = cursor.fetchone()[0] or 0
                conn.close()

                # Show updated stats
                await update.message.reply_text(
                    f"📊 *CURRENT RATINGS*\n"
                    f"• 👍 Likes: {likes}\n"
                    f"• 👎 Dislikes: {dislikes}\n",
                    parse_mode='Markdown'
                )

                # Keep the current keyboard the same
                return
            except Exception as e:
                logger.error(f"Error saving like: {e}")
                await update.message.reply_text("There was an error saving your rating. Please try again.")
                return

    elif text == "👎 Dislike" and 'current_media_id' in context.user_data:
        media_id = context.user_data.get('current_media_id')
        media_type = context.user_data.get('current_media_type')
        if media_id:
            try:
                # Save the dislike to database
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()

                # Create ratings table if it doesn't exist
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS media_ratings (
                    media_id INTEGER,
                    user_id INTEGER,
                    rating TEXT,
                    rating_date TEXT,
                    PRIMARY KEY (media_id, user_id)
                )
                ''')

                # Check if user already rated this media
                cursor.execute("SELECT rating FROM media_ratings WHERE media_id = ? AND user_id = ?", (media_id, user_id))
                existing_rating = cursor.fetchone()

                today = datetime.now().strftime('%Y-%m-%d')
                if existing_rating:
                    # Update existing rating
                    cursor.execute(
                        "UPDATE media_ratings SET rating = ?, rating_date = ? WHERE media_id = ? AND user_id = ?",
                        ('dislike', today, media_id, user_id)
                    )
                    message = "Your rating has been updated to 👎"
                else:
                    # Add new rating
                    cursor.execute(
                        "INSERT INTO media_ratings (media_id, user_id, rating, rating_date) VALUES (?, ?, ?, ?)",
                        (media_id, user_id, 'dislike', today)
                    )
                    message = "Thanks for your feedback! 👎"

                conn.commit()
                conn.close()

                await update.message.reply_text(message)

                # Get count of current likes and dislikes
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'like'", (media_id,))
                likes = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM media_ratings WHERE media_id = ? AND rating = 'dislike'", (media_id,))
                dislikes = cursor.fetchone()[0] or 0
                conn.close()

                # Show updated stats
                await update.message.reply_text(
                    f"📊 *CURRENT RATINGS*\n"
                    f"• 👍 Likes: {likes}\n"
                    f"• 👎 Dislikes: {dislikes}\n",
                    parse_mode='Markdown'
                )

                # Keep the current keyboard the same
                return
            except Exception as e:
                logger.error(f"Error saving dislike: {e}")
                await update.message.reply_text("There was an error saving your rating. Please try again.")
                return

    # Admin-specific keyboard buttons
    if is_admin or user_id == ADMIN_ID:  # Double-check admin status
        # Log admin action button press
        logger.info(f"Admin button pressed: {text}")

        # Add authentication flag to ensure admin functionality
        context.user_data['admin_authenticated'] = True

        # Initialize admin session timestamp if not present
        if 'admin_session_start' not in context.user_data:
            context.user_data['admin_session_start'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Channel management options
        if text == "🔄 Refresh Channel Cache":
            await refresh_channel_cache(update, context)
            return ADMIN_MENU

        elif text == "📊 Channel Stats":
            await show_channel_stats(update, context)
            return ADMIN_MENU

        elif text == "📣 Broadcast":
            # Prepare context for broadcast
            context.user_data['admin_action'] = 'broadcast'

            await update.message.reply_text(
                "📣 *SEND BROADCAST MESSAGE*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the message you want to broadcast to all users:",
                parse_mode='Markdown'
            )
            return ADMIN_BROADCAST

        elif text == "🔍 Search User":
            await update.message.reply_text(
                "🔍 *SEARCH USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter a username, name, or User ID to search for a specific user:",
                parse_mode='Markdown'
            )
            return ADMIN_SEARCH_USER

        elif text == "🚫 Block User":
            await update.message.reply_text(
                "🚫 *BLOCK USER FROM ADMIN PANEL*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the User ID to block from admin panel access:",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'block_user'
            return ADMIN_SEARCH_USER

        elif text == "🔓 Unblock User":
            await update.message.reply_text(
                "🔓 *UNBLOCK USER FROM ADMIN PANEL*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the User ID to unblock from admin panel:",
                parse_mode='Markdown'
            )
            context.user_data['admin_action'] = 'unblock_user'
            return ADMIN_SEARCH_USER

        elif text == "🗑️ Delete Media":
            # Create a simplified version of deletion without callback query
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM media ORDER BY id DESC LIMIT 10")
            media_list = cursor.fetchall()

            conn.close()

            if not media_list:
                await update.message.reply_text(
                    "📂 *MEDIA MANAGEMENT*\n\nNo media found in the database.",
                    parse_mode='Markdown'
                )
            else:
                media_text = "📂 *MEDIA MANAGEMENT*\n\nRecent media items:\n\n"

                # Create keyboard with delete buttons
                keyboard = []

                for media in media_list:
                    media_id = media[0]
                    media_type = media[1]
                    caption = media[3][:20] + "..." if len(media[3]) > 20 else media[3]
                    price = media[4]
                    media_text += f"• ID#{media_id}: {media_type.capitalize()} - {caption} ({price}⭐)\n"

                    # Add buttons for each media item
                    keyboard.append([KeyboardButton(f"🗑️ Delete ID #{media_id}")])

                # Add back button
                keyboard.append([KeyboardButton("🔙 Back to Admin Menu")])

                # Create keyboard markup
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                # Store media list in context for reference
                context.user_data['current_media_list'] = {media[0]: media for media in media_list}

                await update.message.reply_text(
                    media_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

            # Set the state to handle deletion
            context.user_data['admin_delete_mode'] = True
            return ADMIN_DELETE_MEDIA

        elif text == "📋 User List":
            # Create simplified user list without callback query
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            cursor.execute("SELECT user_id, name, username, stars, is_banned FROM users ORDER BY stars DESC LIMIT 10")
            users = cursor.fetchall()

            # Get total user count for statistics
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            conn.close()

            if not users:
                await update.message.reply_text(
                    "👥 *USER MANAGEMENT*\n\nNo users found in the database.",
                    parse_mode='Markdown'
                )
            else:
                users_text = f"👥 *USER MANAGEMENT*\n\nShowing top 10 users (Total users: {total_users}):\n\n"
                for user in users:
                    user_id, name, username, stars, is_banned = user
                    status = "🚫" if is_banned else "✅"
                    users_text += f"• {status} {name} (@{username}) - ID: {user_id} - {stars}⭐\n"

                await update.message.reply_text(
                    users_text,
                    parse_mode='Markdown'
                )
            return ADMIN_MENU

        elif text == "⭐ Add Stars":
            await update.message.reply_text(
                "⭐ *ADD STARS TO USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID or username followed by the number of stars to add.\n"
                "Format: `user_id/username amount`\n\n"
                "Example: `123456789 10` or `@username 10`",
                parse_mode='Markdown'
            )
            return ADMIN_QUICK_STAR_ADD

        elif text == "🔄 Remove Stars":
            await update.message.reply_text(
                "🔄 *REMOVE STARS FROM USER*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please enter the user ID or username followed by the number of stars to remove.\n"
                "Format: `user_id/username amount`\n\n"
                "Example: `123456789 10` or `@username 10`",
                parse_mode='Markdown'
            )
            # Reuse the quick star add function but with negative logic
            context.user_data['star_operation'] = 'remove'
            return ADMIN_QUICK_STAR_ADD

    # Handle media deletion direct from keyboard
    if text.startswith("🗑️ Delete ID #") and is_admin and context.user_data.get('admin_delete_mode'):
        try:
            media_id = int(text.replace("🗑️ Delete ID #", "").strip())
            logger.info(f"Admin deleting media ID: {media_id}")

            # Call the delete function
            await admin_delete_media(update, context, media_id)

            # After deletion, return to admin menu
            context.user_data['admin_delete_mode'] = False
            await show_admin_menu(update, context)
            return ADMIN_MENU
        except ValueError:
            logger.error(f"Invalid media ID format in: {text}")
            await update.message.reply_text(
                "❌ *Error*\n\nInvalid media ID format.",
                parse_mode='Markdown'
            )

    # Handle media management from keyboard
    if text == "➕ Add Video" and is_admin:
        await update.message.reply_text(
            "🎬 *ADD NEW VIDEO*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send the video you want to add to the bot.\n\n"
            "You can send multiple videos in sequence. When you're done, type /done.",
            parse_mode='Markdown'
        )
        # Enable mass upload mode
        context.user_data['mass_upload_mode'] = True
        context.user_data['mass_upload_count'] = 0
        return ADD_VIDEO

    elif text == "➕ Add Photo" and is_admin:
        await update.message.reply_text(
            "📷 *ADD NEW PHOTO*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send the photo you want to add to the bot.\n\n"
            "You can send multiple photos in sequence. When you're done, type /done.",
            parse_mode='Markdown'
        )
        # Enable mass upload mode
        context.user_data['mass_upload_mode'] = True
        context.user_data['mass_upload_count'] = 0
        return ADD_PHOTO

    elif text == "🗑️ Delete Media" and is_admin:
        await show_media_for_deletion(update, context)
        context.user_data['admin_delete_mode'] = True
        return ADMIN_DELETE_MEDIA

    # Profile editing buttons - ensure proper handling of the edit functions
    if text == "👤 Edit Name":
        await process_edit_name_start(update, context)
        return EDIT_NAME

    elif text == "👤 Edit Age":
        await process_edit_age_start(update, context)
        return EDIT_AGE

    elif text == "👤 Edit Username":
        await process_edit_username_start(update, context)
        return EDIT_USERNAME

    # Map button text to corresponding callback functions
    if text == "🎬 Videos":
        await show_videos(update, context)
    elif text == "📷 Photos":
        await show_photos(update, context)
    elif text == "👤 My Profile":
        await show_profile(update, context)
    elif text == "💰 Buy Stars":
        await show_buy_stars(update, context)
    elif text == "🔖 Bookmarks":
        try:
            await show_bookmarks(update, context)
        except sqlite3.Error as e:
            logger.error(f"Database error in bookmarks: {e}")
            # Reconnect database and try again
            try:
                await update.message.reply_text(
                    "📚 *LOADING BOOKMARKS*\n"
                    "Please wait while we retrieve your bookmarks...",
                    parse_mode='Markdown'
                )
                # Fresh connection and retry
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE user_id = ?", (update.effective_user.id,))
                bookmark_count = cursor.fetchone()[0]
                conn.close()

                if bookmark_count == 0:
                    await update.message.reply_text(
                        "📚 *MY COLLECTION* 📚\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Your bookmark collection is empty.\n\n"
                        "Browse our premium content and bookmark your favorites to build your collection.",
                        parse_mode='Markdown',
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🏠 Home")]], resize_keyboard=True)
                    )
                else:
                    # Try showing bookmarks again with fresh connection
                    context.user_data.clear()  # Clear any corrupted data
                    await show_bookmarks(update, context)
            except Exception as e2:
                logger.error(f"Second attempt failed: {e2}")
                await update.message.reply_text(
                    "📚 *BOOKMARKS UNAVAILABLE*\n"
                    "We're experiencing technical difficulties retrieving your bookmarks. Please try again later.",
                    parse_mode='Markdown',
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🏠 Home")]], resize_keyboard=True)
                )
    elif text == "⚙️ Settings":
        await show_settings(update, context)
    elif text == "🔄 Refer & Earn":
        await show_refer(update, context)
    elif text == "ℹ️ Help":
        await show_help(update, context)
    elif text == "🔔 Toggle Notifications":
        # Toggle notification status
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT notification_enabled FROM users WHERE user_id = ?", (user_id,))
        current_status = cursor.fetchone()[0]
        new_status = 0 if current_status else 1
        cursor.execute("UPDATE users SET notification_enabled = ? WHERE user_id = ?", (new_status, user_id))
        conn.commit()
        conn.close()

        status_text = "ON ✅" if new_status else "OFF ❌"
        await update.message.reply_text(
            f"🔔 Notifications turned {status_text}"
        )
        # Show profile again
        await show_profile(update, context)
    elif text == "⬅️ Previous":
        # Handle Previous button for different content types
        try:
            if 'bookmarks' in context.user_data and 'current_bookmark_index' in context.user_data:
                context.user_data['current_bookmark_index'] -= 1
                if context.user_data['current_bookmark_index'] < 0:
                    context.user_data['current_bookmark_index'] = len(context.user_data.get('bookmarks', [])) - 1
                await send_bookmark_for_text_command(update, context)
            elif 'photos' in context.user_data and 'current_photo_index' in context.user_data:
                # Navigate through photos
                photos = context.user_data.get('photos', [])
                if photos:
                    current_index = context.user_data.get('current_photo_index', 0)
                    current_index = (current_index - 1) % len(photos)
                    context.user_data['current_photo_index'] = current_index

                    photo = photos[current_index]
                    media_id = photo[0]
                    file_id = photo[2]
                    caption = photo[3]
                    price = photo[4]

                    # Update current media ID for navigation
                    context.user_data['current_media_id'] = media_id
                    context.user_data['current_media_type'] = "photo"

                    # Get user stars
                    conn = sqlite3.connect('bot_database.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
                    user_stars = cursor.fetchone()[0] if cursor.fetchone() else 0
                    conn.close()

                    # Create photo caption
                    photo_caption = (
                        f"📷 *PREMIUM PHOTO* 📷\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"*ID:* #{media_id}\n\n"
                        f"*DESCRIPTION:*\n{caption}\n\n"
                        f"💰 *PRICE:* {price} ⭐\n"
                        f"💳 *YOUR BALANCE:* {user_stars} ⭐\n\n"
                        f"*NAVIGATION:* Photo {current_index + 1} of {len(photos)}\n\n"
                        f"Use the buttons below to navigate or purchase this photo."
                    )

                    # Send the photo
                    try:
                        await update.message.reply_photo(
                            photo=file_id,
                            caption=photo_caption,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Error sending previous photo: {e}")
                        await update.message.reply_text(
                            f"{photo_caption}\n\n⚠️ *Photo preview unavailable*\n\nTry another photo or contact support.",
                            parse_mode='Markdown'
                        )
            elif 'videos' in context.user_data and 'current_video_index' in context.user_data:
                # Navigate through videos
                videos = context.user_data.get('videos', [])
                if videos:
                    current_index = context.user_data.get('current_video_index', 0)
                    current_index = (current_index - 1) % len(videos)
                    context.user_data['current_video_index'] = current_index

                    video = videos[current_index]
                    media_id = video[0]
                    file_id = video[2]
                    caption = video[3]
                    price = video[4]

                    # Update current media ID for navigation
                    context.user_data['current_media_id'] = media_id
                    context.user_data['current_media_type'] = "video"

                    # Get user stars
                    conn = sqlite3.connect('bot_database.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
                    user_result = cursor.fetchone()
                    user_stars = user_result[0] if user_result else 0
                    conn.close()

                    # Create video caption
                    video_caption = (
                        f"🎬 *PREMIUM VIDEO* 🎬\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"*ID:* #{media_id}\n\n"
                        f"*DESCRIPTION:*\n{caption}\n\n"
                        f"💰 *PRICE:* {price} ⭐\n"
                        f"💳 *YOUR BALANCE:* {user_stars} ⭐\n\n"
                        f"*NAVIGATION:* Video {current_index + 1} of {len(videos)}\n\n"
                        f"Use the buttons below to navigate or purchase this video."
                    )

                    # Send the video
                    try:
                        await update.message.reply_video(
                            video=file_id,
                            caption=video_caption,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Error sending previous video: {e}")
                        await update.message.reply_text(
                            f"{video_caption}\n\n⚠️ *Video preview unavailable*\n\nTry another video or contact support.",
                            parse_mode='Markdown'
                        )
            else:
                # Fallback - try to determine media type from context
                media_type = context.user_data.get('current_media_type')
                if media_type == "photo":
                    await show_photos(update, context)
                elif media_type == "video":
                    await show_videos(update, context)
                else:
                    await update.message.reply_text(
                        "⚠️ Navigation not available. Please select Photos or Videos first.",
                        parse_mode='Markdown'
                    )
        except Exception as e:
            logger.error(f"Error in Previous navigation: {e}")
            await update.message.reply_text(
                "⚠️ There was an error navigating to the previous item. Please try again.",
                parse_mode='Markdown'
            )

    elif text == "➡️ Next":
        # Handle Next button for different content types
        try:
            if 'bookmarks' in context.user_data and 'current_bookmark_index' in context.user_data:
                context.user_data['current_bookmark_index'] += 1
                if context.user_data['current_bookmark_index'] >= len(context.user_data.get('bookmarks', [])):
                    context.user_data['current_bookmark_index'] = 0
                await send_bookmark_for_text_command(update, context)
            elif 'photos' in context.user_data and 'current_photo_index' in context.user_data:
                # Navigate through photos
                photos = context.user_data.get('photos', [])
                if photos:
                    current_index = context.user_data.get('current_photo_index', 0)
                    current_index = (current_index + 1) % len(photos)
                    context.user_data['current_photo_index'] = current_index

                    photo = photos[current_index]
                    media_id = photo[0]
                    file_id = photo[2]
                    caption = photo[3]
                    price = photo[4]

                    # Update current media ID for navigation
                    context.user_data['current_media_id'] = media_id
                    context.user_data['current_media_type'] = "photo"

                    # Get user stars
                    conn = sqlite3.connect('bot_database.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
                    user_result = cursor.fetchone()
                    user_stars = user_result[0] if user_result else 0
                    conn.close()

                    # Create photo caption
                    photo_caption = (
                        f"📷 *PREMIUM PHOTO* 📷\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"*ID:* #{media_id}\n\n"
                        f"*DESCRIPTION:*\n{caption}\n\n"
                        f"💰 *PRICE:* {price} ⭐\n"
                        f"💳 *YOUR BALANCE:* {user_stars} ⭐\n\n"
                        f"*NAVIGATION:* Photo {current_index + 1} of {len(photos)}\n\n"
                        f"Use the buttons below to navigate or purchase this photo."
                    )

                    # Send the photo
                    try:
                        await update.message.reply_photo(
                            photo=file_id,
                            caption=photo_caption,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Error sending next photo: {e}")
                        await update.message.reply_text(
                            f"{photo_caption}\n\n⚠️ *Photo preview unavailable*\n\nTry another photo or contact support.",
                            parse_mode='Markdown'
                        )
            elif 'videos' in context.user_data and 'current_video_index' in context.user_data:
                # Navigate through videos
                videos = context.user_data.get('videos', [])
                if videos:
                    current_index = context.user_data.get('current_video_index', 0)
                    current_index = (current_index + 1) % len(videos)
                    context.user_data['current_video_index'] = current_index

                    video = videos[current_index]
                    media_id = video[0]
                    file_id = video[2]
                    caption = video[3]
                    price = video[4]

                    # Update current media ID for navigation
                    context.user_data['current_media_id'] = media_id
                    context.user_data['current_media_type'] = "video"

                    # Get user stars
                    conn = sqlite3.connect('bot_database.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
                    user_result = cursor.fetchone()
                    user_stars = user_result[0] if user_result else 0
                    conn.close()

                    # Create video caption
                    video_caption = (
                        f"🎬 *PREMIUM VIDEO* 🎬\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"*ID:* #{media_id}\n\n"
                        f"*DESCRIPTION:*\n{caption}\n\n"
                        f"💰 *PRICE:* {price} ⭐\n"
                        f"💳 *YOUR BALANCE:* {user_stars} ⭐\n\n"
                        f"*NAVIGATION:* Video {current_index + 1} of {len(videos)}\n\n"
                        f"Use the buttons below to navigate or purchase this video."
                    )

                    # Send the video
                    try:
                        await update.message.reply_video(
                            video=file_id,
                            caption=video_caption,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Error sending next video: {e}")
                        await update.message.reply_text(
                            f"{video_caption}\n\n⚠️ *Video preview unavailable*\n\nTry another video or contact support.",
                            parse_mode='Markdown'
                        )
            else:
                # Fallback - try to determine media type from context
                media_type = context.user_data.get('current_media_type')
                if media_type == "photo":
                    await show_photos(update, context)
                elif media_type == "video":
                    await show_videos(update, context)
                else:
                    await update.message.reply_text(
                        "⚠️ Navigation not available. Please select Photos or Videos first.",
                        parse_mode='Markdown'
                    )
        except Exception as e:
            logger.error(f"Error in Next navigation: {e}")
            await update.message.reply_text(
                "⚠️ There was an error navigating to the next item. Please try again.",
                parse_mode='Markdown'
            )
    elif text == "🔙 Back to Admin Menu" and is_admin:
        # Clear any specific admin mode flags
        if 'admin_delete_mode' in context.user_data:
            del context.user_data['admin_delete_mode']

        # Show admin menu again
        await show_admin_menu(update, context)
        return ADMIN_MENU

    elif text == "🏠 Home" or text == "🏠 Exit Admin Panel":
        # Only clear navigation context, but preserve admin status if authenticated
        admin_authenticated = context.user_data.get('admin_authenticated', False)
        admin_session_start = context.user_data.get('admin_session_start', None)

        # Clear user data but preserve admin status
        context.user_data.clear()

        # Restore admin authentication if needed
        if admin_authenticated and user_id == ADMIN_ID:
            context.user_data['admin_authenticated'] = admin_authenticated
            context.user_data['admin_session_start'] = admin_session_start

        await show_home_menu(update, context)
    elif text == "📢 Support & Channel":
        # Clear previous context data to prevent showing old content
        context.user_data.clear()
        context.user_data['current_menu'] = 'support'

        # Only use keyboard buttons for navigation
        keyboard = [
            [KeyboardButton("🏠 Home")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        # Add inline buttons for support access and channel
        inline_keyboard = [
            [InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{ADMIN_USERNAME[1:]}"),
             InlineKeyboardButton("🔔 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard)

        # Generate unique message ID to avoid confusion with previous messages
        message_id = f"support_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        context.user_data['last_message_id'] = message_id

        await update.message.reply_text(
            f"📢 *SUPPORT & CHANNEL* 📢\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Our support team can help with:\n"
            f"• Payment and transaction issues\n"
            f"• Content access problems\n"
            f"• Star balance inquiries\n"
            f"• Account security\n\n"
            f"⏱️ *SUPPORT HOURS*: Mon-Fri 10AM-7PM, Weekend 12PM-5PM IST\n"
            f"📝 *RESPONSE TIME*: Usually within 2-4 hours\n\n"
            f"🔔 *OFFICIAL CHANNEL*: {CHANNEL_USERNAME}\n"
            f"• Follow our channel for updates and new content",
            reply_markup=inline_markup,
            parse_mode='Markdown'
        )
    else:
        # For any other text messages, show friendly guidance
        current_time = datetime.now().strftime('%H:%M')
        greeting = "Good morning" if 5 <= int(current_time.split(':')[0]) < 12 else "Good afternoon" if 12 <= int(current_time.split(':')[0]) < 17 else "Good evening"

        keyboard = [
            [KeyboardButton("🎬 Videos"), KeyboardButton("📷 Photos")],
            [KeyboardButton("👤 My Profile"), KeyboardButton("🏠 Home")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            f"{greeting}! I didn't understand that command.\n\n"
            "Please use the buttons below or the main menu to navigate.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart the bot by removing all data."""
    user_id = update.effective_user.id

    if user_id == ADMIN_ID or update.message.text.strip() == ADMIN_PASSWORD:
        await update.message.reply_text(
            "🔄 *RESETTING BOT DATABASE*\n"
            "Please wait while all data is being cleared...",
            parse_mode='Markdown'
        )

        try:
            # Close database connections first to avoid locks
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()

            # Drop all tables to ensure a clean slate
            cursor.execute("DROP TABLE IF EXISTS users")
            cursor.execute("DROP TABLE IF EXISTS media")
            cursor.execute("DROP TABLE IF EXISTS bookmarks")
            cursor.execute("DROP TABLE IF EXISTS daily_logins")
            cursor.execute("DROP TABLE IF EXISTS transactions")
            cursor.execute("DROP TABLE IF EXISTS user_activity")
            cursor.execute("DROP TABLE IF EXISTS media_ratings")

            conn.commit()
            conn.close()

            # Remove the database file entirely
            try:
                if os.path.exists('bot_database.db'):
                    os.remove('bot_database.db')
                    await update.message.reply_text(
                        "📂 Database file removed successfully",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error removing database file: {e}")

            # Initialize a fresh database
            init_db()

            await update.message.reply_text(
                "✅ *BOT RESET SUCCESSFUL*\n\n"
                "All data has been cleared and database reinitialized.\n"
                "The bot will now restart.",
                parse_mode='Markdown'
            )

            # Stop the bot and restart
            os.execl(sys.executable, sys.executable, *sys.argv)

        except Exception as e:
            logger.error(f"Error during bot reset: {e}")
            await update.message.reply_text(
                f"❌ *ERROR DURING RESET*\n\n"
                f"An error occurred: {str(e)}\n\n"
                f"Please try again or restart the bot manually.",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            "❌ You do not have permission to restart the bot.",
            parse_mode='Markdown'
        )


def main():
    # Make sure to initialize the database first
    try:
        # Initialize database
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        # Try to recreate database if initialization fails
        if os.path.exists('bot_database.db'):
            os.remove('bot_database.db')
            logger.info("Removed corrupted database, trying to initialize again")
            init_db()

    # Check for running instances and kill them
    try:
        logger.info("Checking for other running bot instances...")
        import psutil
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if proc.info['pid'] != current_pid:
                cmdline = proc.info['cmdline']
                if cmdline and len(cmdline) > 1 and 'python' in cmdline[0] and 'main.py' in cmdline[1]:
                    logger.info(f"Found another bot instance (PID {proc.info['pid']}). Terminating it.")
                    proc.terminate()
    except Exception as e:
        logger.error(f"Error checking for other instances: {e}")

    # Log startup information
    logger.info("Starting Telegram bot...")

    # Check for running instances and kill them
    try:
        logger.info("Checking for other running bot instances...")
        import psutil
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if proc.info['pid'] != current_pid:
                cmdline = proc.info['cmdline']
                if cmdline and len(cmdline) > 1 and 'python' in cmdline[0] and 'main.py' in cmdline[1]:
                    logger.info(f"Found another bot instance (PID {proc.info['pid']}). Terminating it.")
                    proc.terminate()
    except Exception as e:
        logger.error(f"Error checking for other instances: {e}")

    # Create application
    application = Application.builder().token(TOKEN).build()

    # Add restart and reset handlers
    application.add_handler(CommandHandler("restart", restart_bot))
    application.add_handler(CommandHandler("reset", restart_bot))
    application.add_handler(CommandHandler("resetbot", restart_bot))

    # Add done command handler
    application.add_handler(CommandHandler("done", process_done_command))

    # Add cancel command handler for all conversation states
    application.add_handler(CommandHandler("cancel", lambda u, c: ConversationHandler.END))

    # Create registration conversation handler
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TERMS_ACCEPT: [
                CallbackQueryHandler(handle_terms_response, pattern="^accept_terms|decline_terms$")
            ],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_name),
                # CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$") # Removed cancel registration
            ],
            AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_age),
                # CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$") # Removed cancel registration
            ],
            USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_username),
                # CallbackQueryHandler(cancel_registration, pattern="^cancel_registration$") # Removed cancel registration
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    # Admin panel conversation handler with improved states
    admin_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            ADMIN_AUTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_password_entry)
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(admin_handle_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons)
            ],
            ADD_VIDEO: [
                MessageHandler(filters.VIDEO, process_add_video),
                CommandHandler("done", process_done_command)
            ],
            ADD_PHOTO: [
                MessageHandler(filters.PHOTO, process_add_photo),
                CommandHandler("done", process_done_command)
            ],
            BAN_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_ban_reason)
            ],
            WARN_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_warn_user)
            ],
            ADD_STARS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_add_stars)
            ],
            REMOVE_STARS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_remove_stars)
            ],
            ADMIN_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_broadcast)
            ],
            ADMIN_DELETE_MEDIA: [
                CallbackQueryHandler(admin_handle_callback)
            ],
            # New admin states
            ADMIN_SEARCH_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_user)
            ],
            ADMIN_SEARCH_MEDIA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_media)
            ],
            ADMIN_QUICK_STAR_ADD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_quick_star_add)
            ],
            ADMIN_BOT_SETTINGS: [
                CallbackQueryHandler(admin_handle_callback)
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    # Settings conversation handler
    settings_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_settings, pattern="^settings$")],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(handle_settings_callback, pattern="^settings_|^edit_|^back_to_settings|^confirm_delete")
            ],
            EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: SETTINGS_MENU)
            ],
            EDIT_AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: SETTINGS_MENU)
            ],
            EDIT_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: SETTINGS_MENU)
            ],
            NOTIFICATION_SETTINGS: [
                CallbackQueryHandler(handle_settings_callback)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(show_home_menu, pattern="^home$"),
            CommandHandler("cancel", lambda u, c: ConversationHandler.END)
        ],
    )

    # Add edit profile functions to ConversationHandler states
    settings_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_settings, pattern="^settings$")],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(handle_settings_callback)
            ],
            EDIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_name)
            ],
            EDIT_AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_age)
            ],
            EDIT_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_username)
            ],
            NOTIFICATION_SETTINGS: [
                CallbackQueryHandler(handle_settings_callback)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(show_home_menu, pattern="^home$"),
            CommandHandler("cancel", lambda u, c: ConversationHandler.END)
        ],
    )

    # Profile editing handlers
    profile_edit_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^👤 Edit Name$"), process_edit_name_start),
            MessageHandler(filters.Regex("^👤 Edit Age$"), process_edit_age_start),
            MessageHandler(filters.Regex("^👤 Edit Username$"), process_edit_username_start),
        ],
        states={
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_name)],
            EDIT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_age)],
            EDIT_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_username)],
            SETTINGS_MENU: [CallbackQueryHandler(handle_settings_callback)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        map_to_parent={
            SETTINGS_MENU: SETTINGS_MENU,
            ConversationHandler.END: ConversationHandler.END
        }
    )

    # Add handlers
    application.add_handler(registration_handler)
    application.add_handler(admin_handler)
    application.add_handler(settings_handler)
    application.add_handler(profile_edit_handler)  # Add the profile editing handler

    # Admin command handler directly
    application.add_handler(CommandHandler("admin", admin_command))

    # Document handler for video upload
    application.add_handler(MessageHandler(filters.Document.ALL, process_add_video))

    # Home menu and navigation callbacks
    application.add_handler(CallbackQueryHandler(show_home_menu, pattern="^home$"))
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Admin handlers for text button commands
    admin_handlers = [
        # User management
        MessageHandler(filters.Regex("^👥 User Management$"), lambda u, c: admin_handle_callback(u, c)),
        MessageHandler(filters.Regex("^🔍 Search User$"), lambda u, c: admin_handle_callback(u, c)),
        MessageHandler(filters.Regex("^🔍 Search by ID$"), search_media),

        # Media management
        MessageHandler(filters.Regex("^🗑️ Delete Media$"), lambda u, c: admin_handle_callback(u, c)),

        # Star management
        MessageHandler(filters.Regex("^⭐ Add Stars$"), lambda u, c: admin_handle_callback(u, c)),
        MessageHandler(filters.Regex("^❌ Remove Stars$"), lambda u, c: admin_handle_callback(u, c)),

        # Broadcast
        MessageHandler(filters.Regex("^📣 Broadcast Message$"), lambda u, c: admin_handle_callback(u, c)),
        MessageHandler(filters.Regex("^🔄 Retry Failed Messages$"), retry_broadcast),

        # Navigation
        MessageHandler(filters.Regex("^🔙 Back to Admin Menu$"), lambda u, c: admin_handle_callback(u, c)),
        MessageHandler(filters.Regex("^🏠 Exit Admin Panel$"), lambda u, c: show_home_menu(u, c))
    ]

    for handler in admin_handlers:
        application.add_handler(handler)

    # Add text message handler for keyboard buttons (after other handlers to avoid conflicts)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))

    # Add proper error handler
    async def error_handler(update, context):
        """Log the error and continue"""
        if update:
            logger.error(f"Update {update} caused error {context.error}")
        else:
            logger.error(f"Error occurred: {context.error}")

    application.add_error_handler(error_handler)

    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()