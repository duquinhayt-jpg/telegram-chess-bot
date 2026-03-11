import chess
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

valores = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}


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


def avaliar_tabuleiro(board: chess.Board) -> int:
    if board.is_checkmate():
        if board.turn == chess.WHITE:
            return -999999
        else:
            return 999999

    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0

    for _, piece in board.piece_map().items():
        valor = valores[piece.piece_type]
        if piece.color == chess.WHITE:
            score += valor
        else:
            score -= valor

    return score


def minimax(board: chess.Board, depth: int, alpha: int, beta: int, maximizing: bool) -> int:
    if depth == 0 or board.is_game_over():
        return avaliar_tabuleiro(board)

    if maximizing:
        max_eval = -9999999

        for move in board.legal_moves:
            board.push(move)
            eval_score = minimax(board, depth - 1, alpha, beta, False)
            board.pop()

            if eval_score > max_eval:
                max_eval = eval_score

            if eval_score > alpha:
                alpha = eval_score

            if beta <= alpha:
                break

        return max_eval

    else:
        min_eval = 9999999

        for move in board.legal_moves:
            board.push(move)
            eval_score = minimax(board, depth - 1, alpha, beta, True)
            board.pop()

            if eval_score < min_eval:
                min_eval = eval_score

            if eval_score < beta:
                beta = eval_score

            if beta <= alpha:
                break

        return min_eval


def melhor_jogada(board: chess.Board, dificuldade: int = 2):
    melhor_move = None

    if board.turn == chess.WHITE:
        melhor_score = -9999999

        for move in board.legal_moves:
            board.push(move)
            score = minimax(board, dificuldade - 1, -9999999, 9999999, False)
            board.pop()

            if score > melhor_score:
                melhor_score = score
                melhor_move = move
    else:
        melhor_score = 9999999

        for move in board.legal_moves:
            board.push(move)
            score = minimax(board, dificuldade - 1, -9999999, 9999999, True)
            board.pop()

            if score < melhor_score:
                melhor_score = score
                melhor_move = move

    return melhor_move


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


async def novo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id

    jogos[user] = {
        "board": chess.Board(),
        "dificuldade": 2
    }

    await update.message.reply_text(
        "♟️ *Novo jogo iniciado!*\n\n"
        "Tu jogas com as *brancas*.\n"
        "Envia a tua jogada, por exemplo: `e2e4`",
        parse_mode="Markdown",
        reply_markup=menu_jogo()
    )


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


async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user.id

    if query.data == "novo":
        jogos[user] = {
            "board": chess.Board(),
            "dificuldade": 2
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


async def jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.id

    if user not in jogos:
        await update.message.reply_text(
            "❗ Não existe jogo ativo.\nUsa /novo para começar.",
            reply_markup=menu_inicial()
        )
        return

    board = jogos[user]["board"]
    dificuldade = jogos[user]["dificuldade"]
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

        bot_move = melhor_jogada(board, dificuldade)

        if bot_move is None:
            await update.message.reply_text(
                "🤝 *Empate!*",
                parse_mode="Markdown",
                reply_markup=menu_inicial()
            )
            del jogos[user]
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


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("novo", novo))
app.add_handler(CommandHandler("tabuleiro", tabuleiro))
app.add_handler(CallbackQueryHandler(botoes))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

print("Bot iniciado")

app.run_polling()
