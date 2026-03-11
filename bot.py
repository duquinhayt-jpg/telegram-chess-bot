import os
import stat
import chess
import chess.engine
import atexit
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = "SEU_TOKEN"

ENGINE_PATH = "./stockfish"

os.chmod(ENGINE_PATH, stat.S_IRWXU)

engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)

atexit.register(engine.quit)

jogos = {}


def menu_inicial():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Novo jogo", callback_data="novo")]
    ])


def menu_dificuldade():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Fácil", callback_data="dif_1"),
            InlineKeyboardButton("🟡 Médio", callback_data="dif_2"),
            InlineKeyboardButton("🔴 Difícil", callback_data="dif_3")
        ]
    ])


def menu_jogo():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Ver tabuleiro", callback_data="tab"),
            InlineKeyboardButton("❌ Terminar jogo", callback_data="sair")
        ]
    ])


def stockfish_move(board, level):

    if level == 1:
        engine.configure({"Skill Level": 3})
        result = engine.play(board, chess.engine.Limit(time=0.05))

    elif level == 2:
        engine.configure({"Skill Level": 10})
        result = engine.play(board, chess.engine.Limit(time=0.2))

    else:
        engine.configure({"Skill Level": 20})
        result = engine.play(board, chess.engine.Limit(time=1.0))

    return result.move


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "♟️ *Bot de Xadrez*\n\n"
        "Joga contra o bot.\n\n"
        "Envia jogadas como:\n"
        "`e2e4`",
        parse_mode="Markdown",
        reply_markup=menu_inicial()
    )


async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user.id

    if query.data == "novo":

        await query.edit_message_text(
            "Escolhe a dificuldade:",
            reply_markup=menu_dificuldade()
        )

    elif query.data.startswith("dif_"):

        nivel = int(query.data.split("_")[1])

        jogos[user] = {
            "board": chess.Board(),
            "dificuldade": nivel
        }

        await query.edit_message_text(
            "♟️ *Jogo iniciado!*\n\n"
            "Tu jogas com as brancas.",
            parse_mode="Markdown",
            reply_markup=menu_jogo()
        )

    elif query.data == "tab":

        if user not in jogos:
            await query.message.reply_text("❗ Não existe jogo ativo.")
            return

        board = jogos[user]["board"]

        await query.message.reply_text(
            f"```\n{board}\n```",
            parse_mode="Markdown",
            reply_markup=menu_jogo()
        )

    elif query.data == "sair":

        if user in jogos:
            del jogos[user]

        await query.edit_message_text(
            "❌ Jogo terminado.",
            reply_markup=menu_inicial()
        )


async def jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id

    if user not in jogos:

        await update.message.reply_text(
            "Usa /start para iniciar um jogo."
        )
        return

    board = jogos[user]["board"]
    dificuldade = jogos[user]["dificuldade"]

    texto = update.message.text.strip()

    try:

        move = chess.Move.from_uci(texto)

        if move not in board.legal_moves:

            await update.message.reply_text(
                "❌ Jogada inválida.",
                reply_markup=menu_jogo()
            )
            return

        board.push(move)

        if board.is_game_over():

            await update.message.reply_text(
                "🏆 Tu ganhaste!",
                reply_markup=menu_inicial()
            )

            del jogos[user]
            return

        bot_move = stockfish_move(board, dificuldade)

        board.push(bot_move)

        await update.message.reply_text(
            f"🤖 Bot jogou: *{bot_move}*",
            parse_mode="Markdown",
            reply_markup=menu_jogo()
        )

    except:

        await update.message.reply_text(
            "Formato inválido. Usa `e2e4`.",
            parse_mode="Markdown",
            reply_markup=menu_jogo()
        )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(botoes))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

print("Bot iniciado")

app.run_polling()

