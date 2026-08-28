import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

IMAGE_PATH = Path(__file__).parent / "assets_samurai.png"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "👋 BIENVENUE CHER SAMOURAI :\n\n"
    "Avant d'entrer, une étape rapide. En continuant, tu acceptes :\n"
    "• <a href=\"https://telegram.org/tos/eu\">les Conditions de Telegram</a>\n"
    "• les règles du bot — lien personnel, aucun partage.\n\n"
    "🔒 Appuie sur « J'accepte » pour te vérifier."
)

VALIDATED_TEXT = (
    "✅ C'EST VALIDÉ, {pseudo}! 🎉\n\n"
    "Tu as passé la vérification.\n"
    "Choisis un canal ci-dessous pour demander l'accès.\n\n"
    "⌛ Ta demande passe ensuite en validation par le staff."
)

CHANNELS = [
    ("🔗 SHIRO BOX!NG", "https://t.me/+Yyz9O69XCAc0NTU0"),
    ("🔗 SHIRO VOUCHES", "https://t.me/+nTIzbbDr8VoyMTdk"),
    ("🔗 SIGNAL BACKUP", "https://signal.group/#CjQKINiXQg5CaQ3wvkZ7gmHC88deQQtG9P7wU9FacZMQrswHEhATB86QuJPSsIuYPqC9O4RM"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ J'accepte", callback_data="accept")]]
    )
    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    pseudo = query.from_user.username
    display_name = f"@{pseudo}" if pseudo else query.from_user.first_name

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, url=url)] for label, url in CHANNELS]
    )

    await query.message.delete()
    with open(IMAGE_PATH, "rb") as photo:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo,
            caption=VALIDATED_TEXT.format(pseudo=display_name),
            reply_markup=keyboard,
        )


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(accept, pattern="^accept$"))
    logger.info("Bot démarré.")
    app.run_polling()


if __name__ == "__main__":
    main()
