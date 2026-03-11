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

TOKEN = "8625933223:AAH4SppnDG5LqIfn-k3bN35KOOB_JoKRWGc"

# Caminho do Stockfish local
ENGINE_PATH = "./stockfish.exe"

engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
atexit.register(engine.quit)

# Guardar jogos por utilizador
jogos = {}


# ---------------- MENUS ---------------- #

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


# ---------------- STOCKFISH ---------------- #

def stockfish_move(board, level):

    skill = {1: 3, 2: 10, 3: 20}
    think = {1: 0.05, 2: 0.2, 3: 0.6}

    engine.configure({"Skill Level": skill[level]})

    result = engine.play(board, chess.engine.Limit(time=think[level]))

    return result.move


# ---------------- COMANDOS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "♟️ *Bot de Xadrez*\n\n"
        "Joga contra o bot.\n\n"
        "Envia jogadas como:\n"
        "`e2e4`",
        parse_mode="Markdown",
        reply_markup=menu_inicial()
    )


# ---------------- BOTÕES ---------------- #

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


# ---------------- JOGADAS ---------------- #

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

        if board.is_checkmate():

            await update.message.reply_text(
                f"🤖 Bot jogou: *{bot_move}*\n\n💀 Checkmate! O bot venceu.",
                parse_mode="Markdown",
                reply_markup=menu_inicial()
            )

            del jogos[user]
            return

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


# ---------------- APP ---------------- #

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(botoes))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

print("Bot iniciado")

app.run_polling()
