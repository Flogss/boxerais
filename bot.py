import os
import time
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
    MessageHandler,
    filters,
    ContextTypes,
)

load_dotenv()
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

VIDEO_PATH = Path(__file__).parent / "assets_samurai.mp4"

BOXING_CHANNEL_ID = int(os.environ["BOXING_CHANNEL_ID"])
VOUCHES_CHANNEL_ID = int(os.environ["VOUCHES_CHANNEL_ID"])

ADMIN_SESSION_SECONDS = 30 * 60
PASSWORD_COOLDOWN_BASE = 60  # secondes, double à chaque échec

ANNOUNCE_ORDER_URL = "https://t.me/shirobx"
ANNOUNCE_VOUCHES_URL = "https://t.me/+nTIzbbDr8VoyMTdk"

# État admin en mémoire, par user_id : session, cooldown mot de passe, annonce en cours.
admin_state: dict[int, dict] = {}

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
    with open(VIDEO_PATH, "rb") as video:
        await context.bot.send_video(
            chat_id=query.message.chat_id,
            video=video,
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


def is_authed(user_id: int) -> bool:
    return admin_state.get(user_id, {}).get("authed_until", 0) > time.time()


async def send_admin_menu(update: Update) -> None:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📢 Nouvelle annonce SHIRO BOX!NG", callback_data="new_announcement")]]
    )
    await update.message.reply_text("Panneau admin :", reply_markup=keyboard)


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    state = admin_state.setdefault(user_id, {})
    now = time.time()

    if is_authed(user_id):
        await send_admin_menu(update)
        return

    locked_until = state.get("locked_until", 0)
    if locked_until > now:
        await update.message.reply_text(f"⏳ Trop de tentatives. Réessaie dans {int(locked_until - now)}s.")
        return

    state["awaiting_password"] = True
    await update.message.reply_text("🔑 Entre le mot de passe admin :")


async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    state = admin_state.setdefault(user_id, {})
    text = update.message.text

    if state.get("awaiting_password"):
        state["awaiting_password"] = False
        if text == ADMIN_PASSWORD:
            state["authed_until"] = time.time() + ADMIN_SESSION_SECONDS
            state["fail_count"] = 0
            await update.message.reply_text("✅ Authentifié.")
            await send_admin_menu(update)
        else:
            fails = state.get("fail_count", 0) + 1
            state["fail_count"] = fails
            cooldown = PASSWORD_COOLDOWN_BASE * (2 ** (fails - 1))
            state["locked_until"] = time.time() + cooldown
            await update.message.reply_text(f"❌ Mot de passe incorrect. Réessaie dans {cooldown}s.")
        return

    if state.get("awaiting_announcement") and is_authed(user_id):
        state["awaiting_announcement"] = False
        state["pending_text"] = text
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎥 Avec vidéo", callback_data="announce_video_yes"),
                    InlineKeyboardButton("📝 Texte seul", callback_data="announce_video_no"),
                ]
            ]
        )
        await update.message.reply_text("Inclure la vidéo de bienvenue avec l'annonce ?", reply_markup=keyboard)


async def new_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_authed(user_id):
        await query.edit_message_text("Session expirée, refais /admin.")
        return

    admin_state.setdefault(user_id, {})["awaiting_announcement"] = True
    await query.edit_message_text("✍️ Envoie le texte de l'annonce.")


async def publish_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_authed(user_id):
        await query.edit_message_text("Session expirée, refais /admin.")
        return

    state = admin_state.setdefault(user_id, {})
    text = state.pop("pending_text", None)
    if not text:
        await query.edit_message_text("Aucune annonce en attente.")
        return

    with_video = query.data == "announce_video_yes"
    announce_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🛒 COMMANDER", url=ANNOUNCE_ORDER_URL),
                InlineKeyboardButton("✅ VOUCHES", url=ANNOUNCE_VOUCHES_URL),
            ]
        ]
    )

    try:
        if with_video:
            with open(VIDEO_PATH, "rb") as video:
                await context.bot.send_video(
                    chat_id=BOXING_CHANNEL_ID,
                    video=video,
                    caption=text,
                    reply_markup=announce_keyboard,
                )
        else:
            await context.bot.send_message(
                chat_id=BOXING_CHANNEL_ID,
                text=text,
                reply_markup=announce_keyboard,
            )
        await query.edit_message_text("✅ Annonce publiée sur SHIRO BOX!NG.")
    except TelegramError:
        logger.exception("Échec de publication de l'annonce")
        await query.edit_message_text("❌ Échec de la publication (le bot est-il admin du canal ?).")


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(accept, pattern="^accept$"))
    app.add_handler(CallbackQueryHandler(new_announcement, pattern="^new_announcement$"))
    app.add_handler(CallbackQueryHandler(publish_announcement, pattern="^announce_video_(yes|no)$"))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private_text))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    logger.info("Bot démarré.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
