import chess
from stockfish import Stockfish
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = "8625933223:AAH4SppnDG5LqIfn-k3bN35KOOB_JoKRWGc"

jogos = {}

stockfish = Stockfish(path="/usr/games/stockfish")


def menu_inicial():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Começar jogo", callback_data="novo_jogo")]
    ])


def menu_jogo():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Ver tabuleiro", callback_data="tabuleiro"),
            InlineKeyboardButton("❌ Terminar jogo", callback_data="sair")
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "♟️ Bot de Xadrez\n\n"
        "Joga contra a IA.\n\n"
        "Exemplo de jogada:\n"
        "e2e4"
    )

    await update.message.reply_text(
        texto,
        reply_markup=menu_inicial()
    )


async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()
    user = query.from_user.id

    if query.data == "novo_jogo":

        teclado = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Fácil", callback_data="facil"),
                InlineKeyboardButton("🟡 Médio", callback_data="medio"),
                InlineKeyboardButton("🔴 Difícil", callback_data="dificil")
            ]
        ])

        await query.edit_message_text(
            "Escolhe a dificuldade:",
            reply_markup=teclado
        )

    elif query.data in ["facil", "medio", "dificil"]:

        jogos[user] = chess.Board()

        if query.data == "facil":
            stockfish.set_skill_level(1)

        elif query.data == "medio":
            stockfish.set_skill_level(10)

        else:
            stockfish.set_skill_level(20)

        await query.edit_message_text(
            "Jogo iniciado!\n\n"
            "Tu jogas com as brancas.\n"
            "Envia jogadas como: e2e4",
            reply_markup=menu_jogo()
        )

    elif query.data == "tabuleiro":

        if user not in jogos:
            await query.message.reply_text("Não existe jogo ativo.")
            return

        board = jogos[user]

        await query.message.reply_text(
            f"```\n{board}\n```",
            parse_mode="Markdown",
            reply_markup=menu_jogo()
        )

    elif query.data == "sair":

        if user in jogos:
            del jogos[user]

        await query.edit_message_text(
            "Jogo terminado.",
            reply_markup=menu_inicial()
        )


async def jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.id

    if user not in jogos:
        return

    board = jogos[user]
    texto = update.message.text

    try:

        move = chess.Move.from_uci(texto)

        if move not in board.legal_moves:
            await update.message.reply_text("Jogada inválida.")
            return

        board.push(move)

        stockfish.set_fen_position(board.fen())
        bot_move = stockfish.get_best_move()

        if bot_move:
            board.push(chess.Move.from_uci(bot_move))

        await update.message.reply_text(
            f"🤖 Bot jogou: {bot_move}",
            reply_markup=menu_jogo()
        )

    except:
        await update.message.reply_text("Formato inválido. Use e2e4")


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(botoes))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

print("Bot iniciado...")

app.run_polling()
