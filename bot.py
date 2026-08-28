import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ContextTypes,
)

load_dotenv()
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

IMAGE_PATH = Path(__file__).parent / "assets_samurai.png"

BOXING_CHANNEL_ID = int(os.environ["BOXING_CHANNEL_ID"])
VOUCHES_CHANNEL_ID = int(os.environ["VOUCHES_CHANNEL_ID"])

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

# Canaux Telegram : un lien d'invitation personnel est généré à la volée pour
# chaque utilisateur. Il exige une demande d'adhésion (validation manuelle par
# le staff) et est révoqué dès la première demande reçue, donc non réutilisable.
TELEGRAM_CHANNELS = [
    ("🔗 SHIRO BOX!NG", BOXING_CHANNEL_ID),
    ("🔗 SHIRO VOUCHES", VOUCHES_CHANNEL_ID),
]

# Signal n'est pas géré par l'API Telegram : lien fixe.
SIGNAL_CHANNEL = (
    "🔗 SIGNAL BACKUP",
    "https://signal.group/#CjQKINiXQg5CaQ3wvkZ7gmHC88deQQtG9P7wU9FacZMQrswHEhATB86QuJPSsIuYPqC9O4RM",
)


async def build_channel_keyboard(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for label, chat_id in TELEGRAM_CHANNELS:
        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=chat_id,
                creates_join_request=True,
                name=f"user-{user_id}",
            )
            url = invite.invite_link
        except TelegramError:
            logger.exception("Échec de création du lien d'invitation pour %s (chat_id=%s)", label, chat_id)
            continue
        buttons.append([InlineKeyboardButton(label, url=url)])

    signal_label, signal_url = SIGNAL_CHANNEL
    buttons.append([InlineKeyboardButton(signal_label, url=signal_url)])
    return InlineKeyboardMarkup(buttons)


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

    keyboard = await build_channel_keyboard(context, query.from_user.id)

    await query.message.delete()
    with open(IMAGE_PATH, "rb") as photo:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo,
            caption=VALIDATED_TEXT.format(pseudo=display_name),
            reply_markup=keyboard,
        )


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    request = update.chat_join_request
    invite_link = request.invite_link
    if invite_link and invite_link.name and invite_link.name.startswith("user-"):
        try:
            await context.bot.revoke_chat_invite_link(
                chat_id=request.chat.id,
                invite_link=invite_link.invite_link,
            )
        except TelegramError:
            logger.exception(
                "Impossible de révoquer le lien après la demande de %s dans %s",
                request.from_user.id,
                request.chat.id,
            )


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(accept, pattern="^accept$"))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    logger.info("Bot démarré.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
