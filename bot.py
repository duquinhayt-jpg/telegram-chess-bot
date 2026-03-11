import chess
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

TOKEN = "8625933223:AAH4SppnDG5LqIfn-k3bN35KOOB_JoKRWGc"

jogos = {}


# -----------------------------
# MENUS
# -----------------------------

def menu_inicial():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Novo jogo", callback_data="novo")]
    ])


def menu_jogo():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Ver tabuleiro", callback_data="tab"),
            InlineKeyboardButton("❌ Terminar jogo", callback_data="sair")
        ]
    ])


# -----------------------------
# STOCKFISH API
# -----------------------------

def stockfish_move(board: chess.Board):

    try:
        url = "https://stockfish.online/api/s/v2.php"

        params = {
            "fen": board.fen(),
            "depth": 15
        }

        r = requests.get(url, params=params, timeout=10)

        data = r.json()

        bestmove = data["bestmove"].split(" ")[1]

        return chess.Move.from_uci(bestmove)

    except Exception:
        return None


# -----------------------------
# START
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "♟️ *Bot de Xadrez*\n\n"
        "Joga contra a IA.\n\n"
        "*Como jogar:*\n"
        "Envia a jogada no formato:\n"
        "`e2e4`\n\n"
        "*Comandos disponíveis:*\n"
        "/start — abrir menu\n"
        "/novo — iniciar novo jogo\n"
        "/tabuleiro — mostrar tabuleiro",
        parse_mode="Markdown",
        reply_markup=menu_inicial()
    )


# -----------------------------
# NOVO JOGO
# -----------------------------

async def novo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id

    jogos[user] = {
        "board": chess.Board()
    }

    await update.message.reply_text(
        "♟️ *Novo jogo iniciado!*\n\n"
        "Tu jogas com as *brancas*.\n"
        "Envia a tua jogada, por exemplo: `e2e4`",
        parse_mode="Markdown",
        reply_markup=menu_jogo()
    )


# -----------------------------
# TABULEIRO
# -----------------------------

async def tabuleiro(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id

    if user not in jogos:
        await update.message.reply_text(
            "❗ Não existe jogo ativo.",
            reply_markup=menu_inicial()
        )
        return

    board = jogos[user]["board"]

    await update.message.reply_text(
        f"```\n{board}\n```",
        parse_mode="Markdown",
        reply_markup=menu_jogo()
    )


# -----------------------------
# BOTÕES
# -----------------------------

async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user.id

    if query.data == "novo":

        jogos[user] = {
            "board": chess.Board()
        }

        await query.edit_message_text(
            "♟️ *Novo jogo iniciado!*\n\n"
            "Tu jogas com as *brancas*.\n"
            "Envia a tua jogada, por exemplo: `e2e4`",
            parse_mode="Markdown",
            reply_markup=menu_jogo()
        )

    elif query.data == "tab":

        if user not in jogos:
            await query.message.reply_text(
                "❗ Não existe jogo ativo.",
                reply_markup=menu_inicial()
            )
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
            "❌ *Jogo terminado.*",
            parse_mode="Markdown",
            reply_markup=menu_inicial()
        )


# -----------------------------
# JOGADA DO JOGADOR
# -----------------------------

async def jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id

    if user not in jogos:
        await update.message.reply_text(
            "❗ Não existe jogo ativo.\nUsa /novo para começar.",
            reply_markup=menu_inicial()
        )
        return

    board = jogos[user]["board"]
    texto = update.message.text.strip().lower()

    try:

        move = chess.Move.from_uci(texto)

        if move not in board.legal_moves:
            await update.message.reply_text(
                "❌ Jogada inválida.\nUsa um formato como `e2e4`.",
                parse_mode="Markdown",
                reply_markup=menu_jogo()
            )
            return

        board.push(move)

        if board.is_checkmate():
            await update.message.reply_text(
                "🏆 *Checkmate! Ganhastes o jogo!*",
                parse_mode="Markdown",
                reply_markup=menu_inicial()
            )
            del jogos[user]
            return

        if board.is_stalemate() or board.is_insufficient_material():
            await update.message.reply_text(
                "🤝 *Empate!*",
                parse_mode="Markdown",
                reply_markup=menu_inicial()
            )
            del jogos[user]
            return


        # -----------------------------
        # BOT MOVE (STOCKFISH)
        # -----------------------------

        bot_move = stockfish_move(board)

        if bot_move is None:
            await update.message.reply_text(
                "⚠️ Erro ao contactar a IA.",
                reply_markup=menu_jogo()
            )
            return

        board.push(bot_move)


        if board.is_checkmate():
            await update.message.reply_text(
                f"🤖 Bot jogou: *{bot_move}*\n\n💀 *Checkmate! O bot venceu.*",
                parse_mode="Markdown",
                reply_markup=menu_inicial()
            )
            del jogos[user]
            return

        if board.is_stalemate() or board.is_insufficient_material():
            await update.message.reply_text(
                f"🤖 Bot jogou: *{bot_move}*\n\n🤝 *Empate!*",
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

    except Exception:

        await update.message.reply_text(
            "❗ Formato inválido.\nUsa algo como `e2e4`.",
            parse_mode="Markdown",
            reply_markup=menu_jogo()
        )


# -----------------------------
# APP
# -----------------------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("novo", novo))
app.add_handler(CommandHandler("tabuleiro", tabuleiro))
app.add_handler(CallbackQueryHandler(botoes))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

print("Bot iniciado")

app.run_polling()
