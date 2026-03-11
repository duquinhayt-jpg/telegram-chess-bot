import os
import chess
import chess.engine
import sqlite3
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
ENGINE_PATH = "./stockfish"

engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)

jogos = {}

# =============================
# BASE DE DADOS
# =============================

db = sqlite3.connect("xadrez.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS stats(
user_id INTEGER PRIMARY KEY,
wins INTEGER DEFAULT 0,
losses INTEGER DEFAULT 0,
draws INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS games(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
result TEXT,
moves TEXT,
date TEXT
)
""")

db.commit()

# =============================
# MENUS
# =============================

def menu_principal():

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Novo jogo", callback_data="novo")],
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="stats"),
            InlineKeyboardButton("📜 Histórico", callback_data="hist")
        ],
        [InlineKeyboardButton("⚙️ Configurações", callback_data="config")]
    ])


def menu_pecas():

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♔ Brancas", callback_data="white")],
        [InlineKeyboardButton("♚ Pretas", callback_data="black")]
    ])


def botao_tabuleiro():

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Mostrar tabuleiro", callback_data="board")]
    ])

# =============================
# TABULEIRO
# =============================

pecas = {
"P":"♙","N":"♘","B":"♗","R":"♖","Q":"♕","K":"♔",
"p":"♟","n":"♞","b":"♝","r":"♜","q":"♛","k":"♚"
}


def board_unicode(board):

    rows = str(board).split("\n")

    out = []

    for r in rows:

        linha=[]

        for c in r.split():

            if c==".":
                linha.append("·")
            else:
                linha.append(pecas[c])

        out.append(" ".join(linha))

    return "\n".join(out)

# =============================
# STOCKFISH
# =============================

def jogada_bot(board):

    result = engine.play(board, chess.engine.Limit(time=0.5))

    return result.move

# =============================
# START
# =============================

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "♟️ Bot de Xadrez",
        reply_markup=menu_principal()
    )

# =============================
# BOTÕES
# =============================

async def botoes(update:Update, context:ContextTypes.DEFAULT_TYPE):

    query=update.callback_query
    await query.answer()

    user=query.from_user.id

    if query.data=="novo":

        await query.edit_message_text(
            "Escolhe as peças",
            reply_markup=menu_pecas()
        )


    elif query.data in ["white","black"]:

        board=chess.Board()

        jogos[user]={
            "board":board,
            "color":query.data,
            "show":True
        }

        texto=f"""
♟️ Partida iniciada

Dificuldade: Difícil
Tu jogas com: {"Brancas" if query.data=="white" else "Pretas"}
"""

        texto+=f"\nEstado: {'Tua vez' if query.data=='white' else 'Vez do bot'}\n\n"

        texto+="```\n"+board_unicode(board)+"\n```"

        await query.edit_message_text(
            texto,
            parse_mode="Markdown"
        )

        if query.data=="black":

            move=jogada_bot(board)

            board.push(move)

            await context.bot.send_message(
                query.message.chat_id,
                f"🤖 Bot jogou: {move}",
                reply_markup=botao_tabuleiro()
            )


    elif query.data=="board":

        jogo=jogos[user]

        board=jogo["board"]

        await query.edit_message_text(
            "```\n"+board_unicode(board)+"\n```",
            parse_mode="Markdown"
        )

# =============================
# JOGADAS
# =============================

async def jogada(update:Update, context:ContextTypes.DEFAULT_TYPE):

    user=update.message.from_user.id

    if user not in jogos:
        return

    board=jogos[user]["board"]

    texto=update.message.text.strip()

    try:

        move=chess.Move.from_uci(texto)

        if move not in board.legal_moves:
            return

        board.push(move)

    except:
        return


    if board.is_game_over():

        await update.message.reply_text("🏁 Jogo terminado")

        del jogos[user]

        return


    bot=jogada_bot(board)

    board.push(bot)

    await context.bot.send_message(
        update.message.chat_id,
        f"🤖 Bot jogou: {bot}",
        reply_markup=botao_tabuleiro()
    )

# =============================
# MAIN
# =============================

def main():

    app=ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CallbackQueryHandler(botoes))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,jogada))

    print("Bot iniciado")

    app.run_polling()


if __name__=="__main__":
    main()

