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

# =========================================================
# CONFIG
# =========================================================
TOKEN = "8625933223:AAH4SppnDG5LqIfn-k3bN35KOOB_JoKRWGc"
ENGINE_PATH = "./stockfish"
DB_PATH = "xadrez_bot.db"

# =========================================================
# BASE DE DADOS
# =========================================================
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
    difficulty INTEGER DEFAULT 3
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
    moves TEXT
)
""")

db.commit()

# =========================================================
# ESTADO EM MEMÓRIA
# =========================================================
# jogos[user_id] = {
#     "board": chess.Board(),
#     "color": "white" / "black",
#     "difficulty": 1/2/3,
#     "game_id": int
# }
jogos = {}

# mensagens_controladas[user_id] = set(message_ids)
mensagens_controladas = {}

# utilizadores à espera do número da partida para resumo
esperando_resumo = set()
mensagem_historico = {}

# =========================================================
# STOCKFISH
# =========================================================
engine = None


def iniciar_engine():
    global engine

    if not os.path.exists(ENGINE_PATH):
        raise FileNotFoundError(
            f"O ficheiro do motor não foi encontrado em: {ENGINE_PATH}"
        )

    os.chmod(ENGINE_PATH, stat.S_IRWXU)
    engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
    return engine


def fechar_engine():
    global engine
    if engine is not None:
        try:
            engine.quit()
        except Exception:
            pass
        engine = None


atexit.register(fechar_engine)

# =========================================================
# UTILITÁRIOS DB
# =========================================================
def garantir_user(user_id: int, username: str | None, first_name: str | None):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            username,
            first_name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        cursor.execute("""
            INSERT INTO settings (user_id, difficulty)
            VALUES (?, 3)
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
    return row[0] if row else 3


def set_difficulty(user_id: int, difficulty: int):
    cursor.execute("""
        INSERT INTO settings (user_id, difficulty)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET difficulty = excluded.difficulty
    """, (user_id, difficulty))
    db.commit()


def get_stats(user_id: int):
    cursor.execute("""
        SELECT wins, losses, draws
        FROM stats
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    return row if row else (0, 0, 0)


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
        INSERT INTO games (user_id, started_at, ended_at, player_color, difficulty, result, moves)
        VALUES (?, ?, NULL, ?, ?, 'unfinished', '')
    """, (
        user_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        player_color,
        difficulty
    ))
    db.commit()
    return cursor.lastrowid


def finish_game(game_id: int, result: str, moves: str):
    cursor.execute("""
        UPDATE games
        SET ended_at = ?, result = ?, moves = ?
        WHERE game_id = ?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        result,
        moves,
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


def get_game_moves(user_id: int, game_id: int):
    cursor.execute("""
        SELECT moves
        FROM games
        WHERE user_id = ? AND game_id = ?
    """, (user_id, game_id))
    row = cursor.fetchone()
    return row[0] if row else None

def reset_stats(user_id: int):
    cursor.execute("""
        INSERT INTO stats (user_id, wins, losses, draws)
        VALUES (?, 0, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET
            wins = 0,
            losses = 0,
            draws = 0
    """, (user_id,))
    db.commit()


def reset_history(user_id: int):
    cursor.execute("DELETE FROM games WHERE user_id = ?", (user_id,))
    db.commit()


def reset_history_and_stats(user_id: int):
    reset_history(user_id)
    reset_stats(user_id)

# =========================================================
# TRACKING DE MENSAGENS
# =========================================================
def registar_mensagem(user_id: int, message_id: int):
    if user_id not in mensagens_controladas:
        mensagens_controladas[user_id] = set()
    mensagens_controladas[user_id].add(message_id)


async def limpar_mensagens_controladas(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    ids = list(mensagens_controladas.get(user_id, set()))
    ids.sort(reverse=True)

    for message_id in ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    mensagens_controladas[user_id] = set()

# =========================================================
# MENUS
# =========================================================
def menu_principal():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Novo jogo", callback_data="novo")],
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="stats"),
            InlineKeyboardButton("📜 Histórico", callback_data="historico"),
        ],
        [InlineKeyboardButton("⚙️ Configurações", callback_data="config")]
    ])


def menu_escolher_pecas():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♔ Jogar com Brancas", callback_data="cor_white")],
        [InlineKeyboardButton("♚ Jogar com Pretas", callback_data="cor_black")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
    ])


def menu_config():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Dificuldade do bot", callback_data="config_dif")],
        [InlineKeyboardButton("🗑 Reset histórico", callback_data="reset_dados")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
    ])


def menu_dificuldade():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Fácil", callback_data="cfg_1")],
        [InlineKeyboardButton("🟡 Médio", callback_data="cfg_2")],
        [InlineKeyboardButton("🔴 Difícil", callback_data="cfg_3")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="config")]
    ])
    

def menu_confirmar_reset():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmar reset", callback_data="confirmar_reset")],
        [InlineKeyboardButton("⬅️ Cancelar", callback_data="config")]
    ])


def menu_historico_com_resumo():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Ver resumo", callback_data="ver_resumo")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
    ])


def menu_historico_sem_resumo():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
    ])


def menu_jogo():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Mostrar tabuleiro", callback_data="show_board")],
        [InlineKeyboardButton("🏳️ Desistir", callback_data="resign")]
    ])

# =========================================================
# TABULEIRO
# =========================================================
pecas_unicode = {
    "P": "♟", "N": "♞", "B": "♝", "R": "♜", "Q": "♛", "K": "♚",
    "p": "♙", "n": "♘", "b": "♗", "r": "♖", "q": "♕", "k": "♔",
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

        rank_label = str(8 - i) if perspective == "white" else str(i + 1)
        linhas.append(f"{rank_label} {' '.join(converted)}")

    footer = "  a b c d e f g h" if perspective == "white" else "  h g f e d c b a"
    return "\n".join(linhas) + "\n" + footer


def estado_turno(board: chess.Board, color: str) -> str:
    if (color == "white" and board.turn == chess.WHITE) or (color == "black" and board.turn == chess.BLACK):
        return "Tua vez"
    return "Vez do bot"


def nome_dificuldade(nivel: int) -> str:
    return {1: "Fácil", 2: "Médio", 3: "Difícil"}.get(nivel, str(nivel))


def nome_resultado(result: str) -> str:
    return {
        "win": "Vitória",
        "loss": "Derrota",
        "draw": "Empate",
        "resign": "Desistência",
        "unfinished": "Inacabada",
    }.get(result, result)

# =========================================================
# NORMALIZAÇÃO SAN
# =========================================================
def normalizar_san(texto: str) -> str:
    texto = texto.strip()

    if not texto:
        return texto

    # remover espaços internos tipo "N f3"
    texto = texto.replace(" ", "")

    # roques com letra O ou zero
    t = texto.lower()
    if t in ("o-o", "0-0"):
        return "O-O"
    if t in ("o-o-o", "0-0-0"):
        return "O-O-O"

    # promoção: e8=q -> e8=Q
    if "=" in texto:
        partes = texto.split("=")
        if len(partes) == 2 and partes[1]:
            texto = partes[0] + "=" + partes[1].upper()

    # primeira letra da peça em maiúscula, se existir
    if texto and texto[0].lower() in {"k", "q", "r", "b", "n"}:
        texto = texto[0].upper() + texto[1:]

    return texto

# =========================================================
# MOTOR
# =========================================================
def stockfish_move(board: chess.Board, difficulty: int):
    if engine is None:
        raise RuntimeError("Engine não inicializada.")

    if difficulty == 1:
        engine.configure({"Skill Level": 3})
        limit = chess.engine.Limit(time=0.10)
        multipv = 4
    elif difficulty == 2:
        engine.configure({"Skill Level": 10})
        limit = chess.engine.Limit(time=0.30)
        multipv = 3
    else:
        engine.configure({"Skill Level": 18})
        limit = chess.engine.Limit(time=0.80)
        multipv = 2

    try:
        info = engine.analyse(board, limit, multipv=multipv)

        if isinstance(info, list):
            jogadas = []
            for item in info:
                pv = item.get("pv")
                if pv and len(pv) > 0 and pv[0] not in jogadas:
                    jogadas.append(pv[0])

            if jogadas:
                if difficulty == 1:
                    return random.choice(jogadas)
                if difficulty == 2:
                    pesos = [60, 25, 15][:len(jogadas)]
                    return random.choices(jogadas, weights=pesos, k=1)[0]
                return random.choices(jogadas[:2], weights=[85, 15][:len(jogadas[:2])], k=1)[0]

        result = engine.play(board, limit)
        return result.move

    except Exception:
        result = engine.play(board, limit)
        return result.move


def get_game_result_for_user(board: chess.Board, user_color: str) -> str:
    if board.is_checkmate():
        winner_is_white = not board.turn
        if (winner_is_white and user_color == "white") or ((not winner_is_white) and user_color == "black"):
            return "win"
        return "loss"

    if (
        board.is_stalemate()
        or board.is_insufficient_material()
        or board.is_seventyfive_moves()
        or board.is_fivefold_repetition()
    ):
        return "draw"

    return "draw"

# =========================================================
# TEXTOS
# =========================================================
def texto_menu_inicial(nome: str | None):
    saudacao = f"Olá, {nome}!" if nome else "Olá!"
    return (
        "♟️ *Bot de Xadrez*\n\n"
        f"{saudacao}\n"
        "Bem-vindo ao menu principal.\n\n"
        "Escolhe uma opção abaixo."
    )


def texto_stats(user_id: int):
    wins, losses, draws = get_stats(user_id)
    total = wins + losses + draws
    taxa = (wins / total * 100) if total > 0 else 0

    return (
        "📊 *Estatísticas*\n\n"
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
        return texto + "Ainda não tens partidas guardadas."

    for game_id, started_at, player_color, difficulty, result in historico:
        cor = "Brancas" if player_color == "white" else "Pretas"
        dif = nome_dificuldade(difficulty)
        res = nome_resultado(result)
        data = started_at[:16] if started_at else "-"

        texto += (
            f"#{game_id} • {data}\n"
            f"Peças: {cor} | Dificuldade: {dif}\n"
            f"Resultado: *{res}*\n\n"
        )

    return texto.strip()


def texto_config(user_id: int):
    nivel = get_difficulty(user_id)
    diff_nome = nome_dificuldade(nivel)
    return (
        "⚙️ *Configurações*\n\n"
        f"🤖 Dificuldade atual do bot: *{diff_nome}*"
    )


def texto_inicio_partida(user_id: int) -> str:
    jogo = jogos[user_id]
    board = jogo["board"]
    color = jogo["color"]
    difficulty = jogo["difficulty"]

    cor_nome = "Brancas" if color == "white" else "Pretas"
    diff_nome = nome_dificuldade(difficulty)
    tab = board_to_unicode(board, color)

    return (
        "♟️ *Partida iniciada*\n\n"
        f"🤖 Dificuldade: *{diff_nome}*\n"
        f"🎨 Tu jogas com: *{cor_nome}*\n"
        f"⏳ Quem joga: *{estado_turno(board, color)}*\n\n"
        "Escreve a tua jogada em notação normal, por exemplo:\n"
        "`e4`, `Nf3`, `Bxc6`, `O-O`\n\n"
        f"```text\n{tab}\n```"
    )


def texto_jogada_bot(user_id: int, bot_move: str, incluir_tabuleiro: bool) -> str:
    jogo = jogos[user_id]
    board = jogo["board"]
    color = jogo["color"]

    linhas = [
        f"🤖 *Bot jogou:* *{bot_move}*",
        f"⏳ Quem joga: *{estado_turno(board, color)}*",
    ]

    if incluir_tabuleiro:
        linhas.append(f"```text\n{board_to_unicode(board, color)}\n```")

    return "\n".join(linhas)


def resumo_jogadas_para_texto(moves_str: str, limite_chars: int = 3500) -> str:
    if not moves_str.strip():
        return "Esta partida não tem jogadas guardadas."

    board = chess.Board()
    moves = moves_str.split()
    linhas = []
    par_atual = []
    numero = 1

    for uci in moves:
        try:
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                san = uci
            else:
                san = board.san(move)
                board.push(move)
        except Exception:
            san = uci

        par_atual.append(san)

        if len(par_atual) == 2:
            linhas.append(f"{numero}. {par_atual[0]} {par_atual[1]}")
            numero += 1
            par_atual = []

    if par_atual:
        linhas.append(f"{numero}. {par_atual[0]}")

    texto = "📝 *Resumo das jogadas*\n\n" + "\n".join(linhas)

    if len(texto) > limite_chars:
        texto = texto[:limite_chars - 20] + "\n\n_(resumo cortado)_"

    return texto

# =========================================================
# ENVIO DE MENSAGENS
# =========================================================
async def enviar_menu_principal(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, nome: str | None):
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=texto_menu_inicial(nome),
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )
    registar_mensagem(user_id, msg.message_id)


async def enviar_mensagem_inicio_partida(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=texto_inicio_partida(user_id),
        parse_mode="Markdown"
    )
    registar_mensagem(user_id, msg.message_id)


async def enviar_mensagem_jogada_bot(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    bot_move: str,
    mostrar_tabuleiro: bool = False
):
    reply_markup = None if mostrar_tabuleiro else menu_jogo()

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=texto_jogada_bot(user_id, bot_move, mostrar_tabuleiro),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    registar_mensagem(user_id, msg.message_id)
    return msg

# =========================================================
# COMANDO /start
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_id = user.id

    garantir_user(user_id, user.username, user.first_name)

    if update.message:
        registar_mensagem(user_id, update.message.message_id)

    # se houver jogo ativo, encerra como desistência ao reiniciar
    if user_id in jogos:
        jogo = jogos[user_id]
        moves = " ".join([m.uci() for m in jogo["board"].move_stack])
        finish_game(jogo["game_id"], "resign", moves)
        add_result(user_id, "loss")
        del jogos[user_id]

    esperando_resumo.discard(user_id)

    await limpar_mensagens_controladas(context, chat_id, user_id)
    await enviar_menu_principal(context, chat_id, user_id, user.first_name)

# =========================================================
# BOTÕES
# =========================================================
async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = user.id
    chat_id = query.message.chat_id

    garantir_user(user_id, user.username, user.first_name)
    registar_mensagem(user_id, query.message.message_id)

    # MENU PRINCIPAL
    if query.data == "menu":
        esperando_resumo.discard(user_id)

        await query.edit_message_text(
            text=texto_menu_inicial(user.first_name),
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )
        return

    # NOVO JOGO
    if query.data == "novo":
        esperando_resumo.discard(user_id)

        if user_id in jogos:
            await query.edit_message_text(
                text="⚠️ *Já tens um jogo em curso.*\n\nTermina essa partida primeiro ou usa /start para recomeçar.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
                ])
            )
            return

        await query.edit_message_text(
            text="♟️ *Novo jogo*\n\nEscolhe com que peças queres jogar:",
            parse_mode="Markdown",
            reply_markup=menu_escolher_pecas()
        )
        return

    # ESCOLHER PEÇAS
    if query.data.startswith("cor_"):
        esperando_resumo.discard(user_id)

        cor = query.data.split("_")[1]
        difficulty = get_difficulty(user_id)
        board = chess.Board()
        game_id = create_game(user_id, cor, difficulty)

        jogos[user_id] = {
            "board": board,
            "color": cor,
            "difficulty": difficulty,
            "game_id": game_id,
        }

        await query.edit_message_text(
            text=texto_inicio_partida(user_id),
            parse_mode="Markdown"
        )

        # se joga de pretas, o bot joga primeiro
        if cor == "black":
            try:
                bot_move = stockfish_move(board, difficulty)
                bot_move_san = board.san(bot_move)
                board.push(bot_move)

                await enviar_mensagem_jogada_bot(
                    context=context,
                    chat_id=chat_id,
                    user_id=user_id,
                    bot_move=bot_move_san,
                    mostrar_tabuleiro=False
                )

            except Exception:
                moves = " ".join([m.uci() for m in board.move_stack])

                finish_game(game_id, "unfinished", moves)

                del jogos[user_id]

                erro = await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ *Erro ao comunicar com o Stockfish.*",
                    parse_mode="Markdown",
                    reply_markup=menu_principal()
                )

                registar_mensagem(user_id, erro.message_id)

        return

    # ESTATÍSTICAS
    if query.data == "stats":
        esperando_resumo.discard(user_id)

        await query.edit_message_text(
            text=texto_stats(user_id),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")]
            ])
        )
        return

    # HISTÓRICO
    if query.data == "historico":
        esperando_resumo.discard(user_id)

        historico = get_history(user_id, 10)

        mensagem_historico[user_id] = query.message.message_id

        await query.edit_message_text(
            text=(
                "📜 *Histórico de partidas*\n\n"
                "Para ver o resumo:\n"
                "1️⃣ Clica em *Ver resumo*\n"
                "2️⃣ Escreve o número da partida\n\n"
                + texto_historico(user_id)
            ),
            parse_mode="Markdown",
            reply_markup=menu_historico_com_resumo() if historico else menu_historico_sem_resumo()
        )
        return

    if query.data == "ver_resumo":
        esperando_resumo.add(user_id)

        await query.edit_message_text(
            text=query.message.text + "\n\n✏️ *Escreve o número da partida.*",
            parse_mode="Markdown"
        )

        return

    # CONFIGURAÇÕES
    if query.data == "config":
        esperando_resumo.discard(user_id)

        await query.edit_message_text(
            text=texto_config(user_id),
            parse_mode="Markdown",
            reply_markup=menu_config()
        )
        return

    if query.data == "config_dif":
        esperando_resumo.discard(user_id)

        nivel = get_difficulty(user_id)
        diff_nome = nome_dificuldade(nivel)

        await query.edit_message_text(
            text=(
                "🤖 *Dificuldade do bot*\n\n"
                f"Atual: *{diff_nome}*\n\n"
                "Escolhe a nova dificuldade:"
            ),
            parse_mode="Markdown",
            reply_markup=menu_dificuldade()
        )
        return

    if query.data.startswith("cfg_"):
        esperando_resumo.discard(user_id)

        nivel = int(query.data.split("_")[1])
        set_difficulty(user_id, nivel)

        diff_nome = nome_dificuldade(nivel)

        await query.edit_message_text(
            text=f"✅ *Dificuldade atualizada para:* *{diff_nome}*",
            parse_mode="Markdown",
            reply_markup=menu_config()
        )
        return

    if query.data == "reset_dados":
        esperando_resumo.discard(user_id)

        await query.edit_message_text(
            text=(
                "⚠️ *Reset de dados*\n\n"
                "Isto vai apagar:\n"
                "• todo o histórico de partidas\n"
                "• todas as estatísticas\n\n"
                "Esta ação não pode ser desfeita."
            ),
            parse_mode="Markdown",
            reply_markup=menu_confirmar_reset()
        )
        return

    if query.data == "confirmar_reset":
        esperando_resumo.discard(user_id)

        reset_history_and_stats(user_id)

        if user_id in mensagem_historico:
            del mensagem_historico[user_id]

        await query.edit_message_text(
            text="✅ *Histórico e estatísticas apagados com sucesso.*",
            parse_mode="Markdown",
            reply_markup=menu_config()
        )
        return

    # MOSTRAR TABULEIRO NO PAINEL DA JOGADA DO BOT
    if query.data == "show_board":
        if user_id not in jogos:
            await query.edit_message_text(
                text="❗ *Não existe jogo ativo.*",
                parse_mode="Markdown",
                reply_markup=menu_principal()
            )
            return

        jogo = jogos[user_id]
        board = jogo["board"]
        color = jogo["color"]

        texto_antigo = query.message.text

        novo_texto = (
            texto_antigo +
            "\n\n👁 *Tabuleiro atual*\n\n"
            f"```text\n{board_to_unicode(board, color)}\n```"
        )

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏳️ Desistir", callback_data="resign")]
        ])

        await query.edit_message_text(
            text=novo_texto,
            parse_mode="Markdown",
            reply_markup=teclado
        )

        return

    if query.data == "resign":
        if user_id not in jogos:
            await query.edit_message_text(
                text="❗ Não existe jogo ativo.",
                reply_markup=menu_principal()
            )
            return

        jogo = jogos[user_id]
        board = jogo["board"]

        moves = " ".join([m.uci() for m in board.move_stack])

        finish_game(jogo["game_id"], "resign", moves)
        add_result(user_id, "loss")

        del jogos[user_id]

        await limpar_mensagens_controladas(context, chat_id, user_id)

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="🏳️ *Desististe da partida.*\n\n🤖 O bot venceu.",
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )

        registar_mensagem(user_id, msg.message_id)

        return

# =========================================================
# JOGADAS
# =========================================================
async def jogada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    texto = update.message.text.strip()

    garantir_user(user_id, user.username, user.first_name)
    registar_mensagem(user_id, update.message.message_id)

    # RESUMO DO HISTÓRICO
    if user_id in esperando_resumo:
        try:
            await update.message.delete()
        except Exception:
            pass

        if not texto.isdigit():
            return

        game_id = int(texto)
        moves_str = get_game_moves(user_id, game_id)

        if moves_str is None:
            esperando_resumo.discard(user_id)
            return

        resumo = resumo_jogadas_para_texto(moves_str)

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=mensagem_historico[user_id],
                text=resumo,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Voltar", callback_data="historico")]
                ])
            )
        except Exception:
            pass

        esperando_resumo.discard(user_id)
        return

    if user_id not in jogos:
        return

    jogo = jogos[user_id]
    board = jogo["board"]
    color = jogo["color"]
    difficulty = jogo["difficulty"]

    # só permite jogar na vez do utilizador
    if (color == "white" and board.turn != chess.WHITE) or (color == "black" and board.turn != chess.BLACK):
        aviso = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ *Ainda não é a tua vez.*",
            parse_mode="Markdown"
        )
        registar_mensagem(user_id, aviso.message_id)
        return

    # validar formato em notação normal do xadrez (SAN)
    texto_normalizado = normalizar_san(texto)

    try:
        move = board.parse_san(texto_normalizado)
    except Exception:
        aviso = await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *Formato inválido.*\n\nUsa jogadas como `e4`, `Nf3`, `Bxc6`, `O-O`.",
            parse_mode="Markdown"
        )
        registar_mensagem(user_id, aviso.message_id)
        return

    # validar legalidade
    if move not in board.legal_moves:
        aviso = await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *Jogada inválida.*",
            parse_mode="Markdown"
        )
        registar_mensagem(user_id, aviso.message_id)
        return

    # jogada do utilizador
    board.push(move)

    # fim do jogo após jogada do utilizador
    if board.is_game_over():
        resultado = get_game_result_for_user(board, color)
        moves = " ".join([m.uci() for m in board.move_stack])

        finish_game(jogo["game_id"], resultado, moves)
        add_result(user_id, resultado)
        del jogos[user_id]

        await limpar_mensagens_controladas(context, chat_id, user_id)

        texto_final = {
            "win": "🏆 *Tu ganhaste!*",
            "loss": "🤖 *O bot ganhou.*",
            "draw": "🤝 *Empate.*",
        }[resultado]

        fim = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{texto_final}\n\nA voltar ao menu principal.",
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )
        registar_mensagem(user_id, fim.message_id)
        return

    # jogada do bot
    try:
        bot_move = stockfish_move(board, difficulty)
        bot_move_san = board.san(bot_move)
        board.push(bot_move)
    except Exception:
        moves = " ".join([m.uci() for m in board.move_stack])
        finish_game(jogo["game_id"], "unfinished", moves)
        del jogos[user_id]

        await limpar_mensagens_controladas(context, chat_id, user_id)

        erro = await context.bot.send_message(
            chat_id=chat_id,
            text="❌ *Erro ao comunicar com o Stockfish.*",
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )
        registar_mensagem(user_id, erro.message_id)
        return

    # fim do jogo após jogada do bot
    if board.is_game_over():
        resultado = get_game_result_for_user(board, color)
        moves = " ".join([m.uci() for m in board.move_stack])

        finish_game(jogo["game_id"], resultado, moves)
        add_result(user_id, resultado)
        del jogos[user_id]

        await limpar_mensagens_controladas(context, chat_id, user_id)

        texto_final = {
            "win": f"🏆 *Tu ganhaste!*\n\n🤖 Última jogada do bot: *{bot_move_san}*",
            "loss": f"🤖 *O bot ganhou.*\n\n🤖 Última jogada do bot: *{bot_move_san}*",
            "draw": f"🤝 *Empate.*\n\n🤖 Última jogada do bot: *{bot_move_san}*",
        }[resultado]

        fim = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{texto_final}\n\nA voltar ao menu principal.",
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )
        registar_mensagem(user_id, fim.message_id)
        return

    await enviar_mensagem_jogada_bot(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        bot_move=bot_move_san,
        mostrar_tabuleiro=False
    )

# =========================================================
# MAIN
# =========================================================
def main():
    try:
        iniciar_engine()
    except Exception as e:
        print("Erro ao iniciar o Stockfish:", e)
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(botoes))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jogada))

    print("Bot iniciado")
    app.run_polling()


if __name__ == "__main__":
    main()


