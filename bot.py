import chess
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = "8625933223:AAH4SppnDG5LqIfn-k3bN35KOOB_JoKRWGc"

jogos = {}

valores = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0
}


def avaliar(board):

    score = 0

    for piece in board.piece_map().values():

        value = valores[piece.piece_type]

        if piece.color == chess.WHITE:
            score += value
        else:
            score -= value

    return score


def melhor_jogada(board):

    melhor_score = -9999
    melhor_move = None

    for move in board.legal_moves:

        board.push(move)
        score = avaliar(board)
        board.pop()

        if score > melhor_score:
            melhor_score = score
            melhor_move = move

    return melhor_move


def menu():

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Novo jogo", callback_data="novo")],
        [InlineKeyboardButton("📋 Ver tabuleiro", callback_data="tab")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "♟️ *Bot de Xadrez*\n\n"
        "Joga xadrez contra o bot.\n\n"
        "Exemplo de jogada:\n"
        "`e2e4`",
        parse_mode="Markdown",
        reply_markup=menu()
    )


async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user.id

    if query.data == "novo":

        jogos[user] = chess.Board()

        await query.edit_message_text(
            "♟️ *Novo jogo iniciado!*\n\n"
            "Tu jogas com as peças brancas.",
            parse_mode="Markdown",
            reply_markup=menu()
        )

    elif query.data == "tab":

        if user not in jogos:
            await query.message.reply_text("❗ Não existe jogo ativo.")
            return

        board = jogos[user]

        await query.message.reply_text(
            f"```\n{board}\n```",
            parse_mode="Markdown"
        )


async def jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id

    if user not in jogos:

        await update.message.reply_text("Usa /start para iniciar um jogo.")
        return

    board = jogos[user]
    texto = update.message.text

    try:

        move = chess.Move.from_uci(texto)

        if move not in board.legal_moves:

            await update.message.reply_text("❌ Jogada inválida.")
            return

        board.push(move)

        if board.is_checkmate():

            await update.message.reply_text("🏆 Checkmate! Tu ganhaste.")
            del jogos[user]
            return

        bot_move = melhor_jogada(board)

        board.push(bot_move)

        if board.is_checkmate():

            await update.message.reply_text(
                f"🤖 Bot jogou: {bot_move}\n\n💀 Checkmate! O bot venceu."
            )
            del jogos[user]
            return

        await update.message.reply_text(
            f"🤖 Bot jogou: *{bot_move}*",
            parse_mode="Markdown"
        )

        await update.message.reply_text(
            f"```\n{board}\n```",
            parse_mode="Markdown"
        )

    except:

        await update.message.reply_text("Formato inválido. Usa `e2e4`.", parse_mode="Markdown")


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(botoes))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

print("Bot iniciado")

app.run_polling()
