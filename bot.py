import os
import stat
import atexit
import sqlite3
import random
from datetime import datetime

import chess
import chess.engine

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
TOKEN = "8625933223:AAH4SppnDG5LqIfn-k3bN35KOOB_JoKRWGc"
ENGINE_PATH = "./stockfish"
DB_PATH = "xadrez_bot.db"

# =========================
# STOCKFISH
# =========================
os.chmod(ENGINE_PATH, stat.S_IRWXU)
engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
atexit.register(engine.quit)

# =========================
# BASE DE DADOS
# =========================
db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY,
    difficulty INTEGER DEFAULT 2
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    user_id INTEGER PRIMARY KEY,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    player_color TEXT,
    difficulty INTEGER,
    result TEXT,
    pgn_moves TEXT
)
""")

db.commit()

# =========================
# ESTADO EM MEMÓRIA
# =========================
# jogos[user_id] = {
#   "board": chess.Board(),
#   "color": "white" / "black",
#   "difficulty": 1/2/3,
#   "game_id": int
# }
jogos = {}

# menu_message[user_id] = {"chat_id": ..., "message_id": ...}
menu_message = {}

# =========================
# UTILITÁRIOS DB
# =========================
def garantir_user(user_id: int, username: str | None, first_name: str | None):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        cursor.execute("""
            INSERT INTO settings (user_id, difficulty)
            VALUES (?, 2)
        """, (user_id,))

        cursor.execute("""
            INSERT INTO stats (user_id, wins, losses, draws)
            VALUES (?, 0, 0, 0)
        """, (user_id,))
    else:
        cursor.execute("""
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
        """, (username, first_name, user_id))

    db.commit()


def get_difficulty(user_id: int) -> int:
    cursor.execute("SELECT difficulty FROM settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 2


def set_difficulty(user_id: int, difficulty: int):
    cursor.execute("""
        INSERT INTO settings (user_id, difficulty)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET difficulty = excluded.difficulty
    """, (user_id, difficulty))
    db.commit()


def get_stats(user_id: int):
    cursor.execute("SELECT wins, losses, draws FROM stats WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row
    return (0, 0, 0)


def add_result(user_id: int, result: str):
    if result == "win":
        cursor.execute("UPDATE stats SET wins = wins + 1 WHERE user_id = ?", (user_id,))
    elif result == "loss":
        cursor.execute("UPDATE stats SET losses = losses + 1 WHERE user_id = ?", (user_id,))
    elif result == "draw":
        cursor.execute("UPDATE stats SET draws = draws + 1 WHERE user_id = ?", (user_id,))
    db.commit()


def create_game(user_id: int, player_color: str, difficulty: int) -> int:
    cursor.execute("""
        INSERT INTO games (user_id, started_at, player_color, difficulty, result, pgn_moves)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        player_color,
        difficulty,
        "unfinished",
        ""
    ))
    db.commit()
    return cursor.lastrowid


def finish_game(game_id: int, result: str, pgn_moves: str):
    cursor.execute("""
        UPDATE games
        SET ended_at = ?, result = ?, pgn_moves = ?
        WHERE game_id = ?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        result,
        pgn_moves,
        game_id
    ))
    db.commit()


def get_history(user_id: int, limit: int = 10):
    cursor.execute("""
        SELECT game_id, started_at, player_color, difficulty, result
        FROM games
        WHERE user_id = ?
        ORDER BY game_id DESC
        LIMIT ?
    """, (user_id, limit))
    return cursor.fetchall()

# =========================
# TABULEIRO
# =========================
pecas_unicode = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}

def board_to_unicode(board: chess.Board, perspective: str = "white") -> str:
    rows = str(board).split("\n")

    if perspective == "black":
        rows = rows[::-1]
        rows = [" ".join(r.split()[::-1]) for r in rows]

    linhas = []
    for i, row in enumerate(rows):
        cols = row.split()
        converted = []
        for c in cols:
            if c == ".":
                converted.append("·")
            else:
                converted.append(pecas_unicode.get(c, c))

        if perspective == "white":
            rank_label = str(8 - i)
        else:
            rank_label = str(i + 1)

        linhas.append(f"{rank_label} {' '.join(converted)}")

    if perspective == "white":
        footer = "  a b c d e f g h"
    else:
        footer = "  h g f e d c b a"

    return "\n".join(linhas) + "\n" + footer


def game_status_text(board: chess.Board, user_id: int) -> str:
    jogo = jogos[user_id]
    color = jogo["color"]
    difficulty = jogo["difficulty"]

    diff_nome = {1: "Fácil", 2: "Médio", 3: "Difícil"}[difficulty]
    cor_nome = "Brancas" if color == "white" else "Pretas"

    turno = "Tua vez" if (
        (color == "white" and board.turn == chess.WHITE) or
        (color == "black" and board.turn == chess.BLACK)
    ) else "Vez do bot"

    tab = board_to_unicode(board, color)

    return (
        f"♟️ *Bot de Xadrez*\n\n"
        f"🎨 Peças: *{cor_nome}*\n"
        f"🤖 Dificuldade: *{diff_nome}*\n"
        f"⏳ Estado: *{turno}*\n\n"
        f"```text\n{tab}\n```\n"
        f"Envia a tua jogada em formato `e2e4`."
    )

# =========================
# MENUS
# =========================
def menu_principal():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Novo jogo", callback_data="novo")],
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="stats"),
            InlineKeyboardButton("📜 Histórico", callback_data="historico")
        ],
        [InlineKeyboardButton("⚙️ Configurações", callback_data="config")]
    ])


def menu_escolher_pecas():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("♔ Jogar com Brancas", callback_data="cor_white"),
        ],
        [
            InlineKeyboardButton("♚ Jogar com Pretas", callback_data="cor_black"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
    ])


def menu_config():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Dificuldade do bot", callback_data="config_dif")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
    ])


def menu_dificuldade():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Fácil", callback_data="cfg_1"),
            InlineKeyboardButton("🟡 Médio", callback_data="cfg_2"),
            InlineKeyboardButton("🔴 Difícil", callback_data="cfg_3"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="config")]
    ])


def menu_jogo():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Atualizar tabuleiro", callback_data="tab"),
            InlineKeyboardButton("🏳️ Desistir", callback_data="sair")
        ],
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="stats_jogo"),
            InlineKeyboardButton("📜 Histórico", callback_data="historico_jogo")
        ]
    ])

# =========================
# MOTOR
# =========================
def stockfish_move(board: chess.Board, difficulty: int):
    if difficulty == 1:
        engine.configure({"Skill Level": 3})
        limit = chess.engine.Limit(time=0.08)
        multipv = 4

    elif difficulty == 2:
        engine.configure({"Skill Level": 10})
        limit = chess.engine.Limit(time=0.25)
        multipv = 3

    else:
        engine.configure({"Skill Level": 18})
        limit = chess.engine.Limit(time=0.8)
        multipv = 2

    info = engine.analyse(board, limit, multipv=multipv)

    if not isinstance(info, list):
        return engine.play(board, limit).move

    jogadas = []
    for item in info:
        pv = item.get("pv")
        if pv and len(pv) > 0:
            jogadas.append(pv[0])

    if not jogadas:
        return engine.play(board, limit).move

    # remove repetidas
    jogadas_unicas = []
    for move in jogadas:
        if move not in jogadas_unicas:
            jogadas_unicas.append(move)

    return random.choice(jogadas_unicas)


def get_game_result_for_user(board: chess.Board, user_color: str) -> str:
    if board.is_checkmate():
        winner_is_white = not board.turn
        if (winner_is_white and user_color == "white") or ((not winner_is_white) and user_color == "black"):
            return "win"
        return "loss"

    if (
        board.is_stalemate() or
        board.is_insufficient_material() or
        board.is_seventyfive_moves() or
        board.is_fivefold_repetition()
    ):
        return "draw"

    return "draw"

# =========================
# MENSAGEM ÚNICA DO MENU
# =========================
async def enviar_ou_editar_painel(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    texto: str,
    reply_markup: InlineKeyboardMarkup
):
    info = menu_message.get(user_id)

    if info and info["chat_id"] == chat_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=info["message_id"],
                text=texto,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return
        except Exception:
            pass

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=texto,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    menu_message[user_id] = {"chat_id": chat_id, "message_id": sent.message_id}


async def editar_pelo_callback(query, texto, reply_markup):
    await query.edit_message_text(
        text=texto,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    menu_message[query.from_user.id] = {
        "chat_id": query.message.chat_id,
        "message_id": query.message.message_id
    }

# =========================
# TELAS
# =========================
def texto_menu_inicial(nome: str | None):
    saudacao = f"Olá, {nome}!" if nome else "Olá!"
    return (
        f"♟️ *Bot de Xadrez*\n\n"
        f"{saudacao}\n"
        f"Bem-vindo ao menu principal.\n\n"
        f"Usa os botões abaixo para navegar.\n"
        f"Só podes escrever quando for para enviar uma jogada."
    )


def texto_config(user_id: int):
    dificuldade = get_difficulty(user_id)
    diff_nome = {1: "Fácil", 2: "Médio", 3: "Difícil"}[dificuldade]
    return (
        f"⚙️ *Configurações*\n\n"
        f"🤖 Dificuldade atual do bot: *{diff_nome}*\n\n"
        f"Escolhe uma opção abaixo."
    )


def texto_stats(user_id: int):
    wins, losses, draws = get_stats(user_id)
    total = wins + losses + draws
    taxa = (wins / total * 100) if total > 0 else 0

    return (
        f"📊 *Estatísticas*\n\n"
        f"🎮 Partidas: *{total}*\n"
        f"🏆 Vitórias: *{wins}*\n"
        f"❌ Derrotas: *{losses}*\n"
        f"🤝 Empates: *{draws}*\n"
        f"📈 Taxa de vitória: *{taxa:.1f}%*"
    )


def texto_historico(user_id: int):
    historico = get_history(user_id, 10)

    texto = "📜 *Últimas partidas*\n\n"

    if not historico:
        texto += "Ainda não tens partidas guardadas."
        return texto

    for game_id, started_at, player_color, difficulty, result in historico:
        cor = "Brancas" if player_color == "white" else "Pretas"
        dif = {1: "Fácil", 2: "Médio", 3: "Difícil"}.get(difficulty, str(difficulty))
        res = {
            "win": "Vitória",
            "loss": "Derrota",
            "draw": "Empate",
            "resign": "Desistência",
            "unfinished": "Inacabada"
        }.get(result, result)

        data = started_at[:16] if started_at else "-"
        texto += (
            f"#{game_id} • {data}\n"
            f"Peças: {cor} | Dificuldade: {dif}\n"
            f"Resultado: *{res}*\n\n"
        )

    return texto.strip()

# =========================
# COMANDOS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    garantir_user(user.id, user.username, user.first_name)

    await enviar_ou_editar_painel(
        context=context,
        user_id=user.id,
        chat_id=update.effective_chat.id,
        texto=texto_menu_inicial(user.first_name),
        reply_markup=menu_principal()
    )

    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass


# =========================
# BOTÕES
# =========================
async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = user.id
    garantir_user(user_id, user.username, user.first_name)

    if query.data == "menu":
        await editar_pelo_callback(
            query,
            texto_menu_inicial(user.first_name),
            menu_principal()
        )
        return

    if query.data == "novo":
        if user_id in jogos:
            await editar_pelo_callback(
                query,
                "⚠️ *Já tens um jogo em curso.*\n\nTermina ou desiste da partida atual antes de começar outra.",
                menu_jogo()
            )
            return

        await editar_pelo_callback(
            query,
            "♟️ *Novo jogo*\n\nEscolhe com que peças queres começar:",
            menu_escolher_pecas()
        )
        return

    if query.data.startswith("cor_"):
        cor = query.data.split("_")[1]
        difficulty = get_difficulty(user_id)

        board = chess.Board()
        game_id = create_game(user_id, cor, difficulty)

        jogos[user_id] = {
            "board": board,
            "color": cor,
            "difficulty": difficulty,
            "game_id": game_id
        }

        # se escolher pretas, o bot joga primeiro
        if cor == "black":
            try:
                bot_move = stockfish_move(board, difficulty)
                board.push(bot_move)
            except Exception:
                await editar_pelo_callback(
                    query,
                    "❌ Erro ao comunicar com o Stockfish.\n\nVerifica se o ficheiro `stockfish` existe e tem permissões de execução.",
                    menu_principal()
                )
                del jogos[user_id]
                return

        await editar_pelo_callback(
            query,
            game_status_text(board, user_id),
            menu_jogo()
        )
        return

    if query.data == "tab":
        if user_id not in jogos:
            await editar_pelo_callback(
                query,
                "❗ *Não existe jogo ativo.*",
                menu_principal()
            )
            return

        board = jogos[user_id]["board"]
        await editar_pelo_callback(
            query,
            game_status_text(board, user_id),
            menu_jogo()
        )
        return

    if query.data == "sair":
        if user_id in jogos:
            jogo = jogos[user_id]
            finish_game(jogo["game_id"], "resign", jogo["board"].move_stack.__str__())
            add_result(user_id, "loss")
            del jogos[user_id]

        await editar_pelo_callback(
            query,
            "🏳️ *Partida terminada.*\n\nA partida foi registada como derrota por desistência.",
            menu_principal()
        )
        return

    if query.data == "stats":
        await editar_pelo_callback(
            query,
            texto_stats(user_id),
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]])
        )
        return

    if query.data == "historico":
        await editar_pelo_callback(
            query,
            texto_historico(user_id),
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]])
        )
        return

    if query.data == "stats_jogo":
        await editar_pelo_callback(
            query,
            texto_stats(user_id),
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar ao jogo", callback_data="tab")]])
        )
        return

    if query.data == "historico_jogo":
        await editar_pelo_callback(
            query,
            texto_historico(user_id),
            InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar ao jogo", callback_data="tab")]])
        )
        return

    if query.data == "config":
        await editar_pelo_callback(
            query,
            texto_config(user_id),
            menu_config()
        )
        return

    if query.data == "config_dif":
        dificuldade = get_difficulty(user_id)
        diff_nome = {1: "Fácil", 2: "Médio", 3: "Difícil"}[dificuldade]

        await editar_pelo_callback(
            query,
            f"🤖 *Dificuldade do bot*\n\nAtualmente: *{diff_nome}*\n\nEscolhe a nova dificuldade:",
            menu_dificuldade()
        )
        return

    if query.data.startswith("cfg_"):
        nivel = int(query.data.split("_")[1])
        set_difficulty(user_id, nivel)

        diff_nome = {1: "Fácil", 2: "Médio", 3: "Difícil"}[nivel]

        await editar_pelo_callback(
            query,
            f"✅ *Configuração atualizada*\n\nNova dificuldade do bot: *{diff_nome}*",
            menu_config()
        )
        return


# =========================
# JOGADAS
# =========================
async def jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    garantir_user(user_id, user.username, user.first_name)

    texto = update.message.text.strip().lower()

    # apagar sempre a mensagem do utilizador para manter o chat limpo
    try:
        await update.message.delete()
    except Exception:
        pass

    # se não estiver num jogo, ignora tudo
    if user_id not in jogos:
        return

    jogo = jogos[user_id]
    board = jogo["board"]
    color = jogo["color"]
    difficulty = jogo["difficulty"]

    # impedir jogar fora do seu turno
    if (color == "white" and board.turn != chess.WHITE) or (color == "black" and board.turn != chess.BLACK):
        await enviar_ou_editar_painel(
            context,
            user_id,
            chat_id,
            "⏳ *Ainda não é a tua vez.*",
            menu_jogo()
        )
        return

    try:
        move = chess.Move.from_uci(texto)
    except Exception:
        await enviar_ou_editar_painel(
            context,
            user_id,
            chat_id,
            "❌ *Formato inválido.*\n\nUsa o formato `e2e4`.",
            menu_jogo()
        )
        return

    if move not in board.legal_moves:
        await enviar_ou_editar_painel(
            context,
            user_id,
            chat_id,
            "❌ *Jogada inválida.*\n\nTenta outra jogada no formato `e2e4`.",
            menu_jogo()
        )
        return

    # jogada do jogador
    board.push(move)

    # terminou após jogada do jogador?
    if board.is_game_over():
        resultado = get_game_result_for_user(board, color)
        finish_game(jogo["game_id"], resultado, " ".join([m.uci() for m in board.move_stack]))
        add_result(user_id, resultado)

        texto_final = {
            "win": "🏆 *Tu ganhaste!*",
            "loss": "🤖 *O bot ganhou.*",
            "draw": "🤝 *Empate.*"
        }[resultado]

        del jogos[user_id]

        await enviar_ou_editar_painel(
            context,
            user_id,
            chat_id,
            f"{texto_final}\n\nPartida guardada no histórico.",
            menu_principal()
        )
        return

    # jogada do bot
    try:
        bot_move = stockfish_move(board, difficulty)
        board.push(bot_move)
    except Exception:
        finish_game(jogo["game_id"], "unfinished", " ".join([m.uci() for m in board.move_stack]))
        del jogos[user_id]

        await enviar_ou_editar_painel(
            context,
            user_id,
            chat_id,
            "❌ *Erro ao contactar o Stockfish.*\n\nA partida foi encerrada.",
            menu_principal()
        )
        return

    # terminou após jogada do bot?
    if board.is_game_over():
        resultado = get_game_result_for_user(board, color)
        finish_game(jogo["game_id"], resultado, " ".join([m.uci() for m in board.move_stack]))
        add_result(user_id, resultado)

        texto_final = {
            "win": f"🏆 *Tu ganhaste!*\n\n🤖 Última jogada do bot: *{bot_move.uci()}*",
            "loss": f"🤖 *O bot ganhou.*\n\n🤖 Última jogada do bot: *{bot_move.uci()}*",
            "draw": f"🤝 *Empate.*\n\n🤖 Última jogada do bot: *{bot_move.uci()}*"
        }[resultado]

        del jogos[user_id]

        await enviar_ou_editar_painel(
            context,
            user_id,
            chat_id,
            f"{texto_final}\n\nPartida guardada no histórico.",
            menu_principal()
        )
        return

    # jogo continua
    await enviar_ou_editar_painel(
        context,
        user_id,
        chat_id,
        f"🤖 Bot jogou: *{bot_move.uci()}*\n\n" + game_status_text(board, user_id),
        menu_jogo()
    )


# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(botoes))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

    print("Bot iniciado")
    app.run_polling()


if __name__ == "__main__":
    main()


