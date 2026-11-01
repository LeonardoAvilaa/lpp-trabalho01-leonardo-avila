import socketio

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = socketio.ASGIApp(sio, static_files={
    "/": "client/index.html",
    "/assets": "client/assets",      # mapa, tileset e sprites da vila
})

# A partir da Etapa 1, adicione o seu código ABAIXO desta linha.

import time
import asyncio
from socketio.exceptions import ConnectionRefusedError as SioConnectionRefusedError

# ── Constantes de domínio ─────────────────────────────────────────────
CUSTO_CONSTRUCAO     = 5    # cristais brutos
CUSTO_MELHORIA_N2    = 10   # cristais lapidados (nível 1 -> 2)
CUSTO_MELHORIA_N3    = 15   # cristais lapidados (nível 2 -> 3)
TEMPO_OBRA           = 3    # segundos (construção e melhoria)
TEMPO_LAPIDACAO      = 10   # segundos por vaga
INTERVALO_MINA       = 2    # segundos entre extrações
LIMITE_TRABALHADORES = 2
LIMITE_LOTES         = 6
LOTES = [f"lote{n}" for n in range(1, LIMITE_LOTES + 1)]

# ── Participantes ─────────────────────────────────────────────────────
jogadores = {}      # sid -> {"nome": str, "papel": "mestre" | "jogador"}
mestre_sid = None   # SID do Mestre atual (None se nenhum)
tarefa_mina = None  # Task da mina em execução (None se inativa)

# ── Estado da vila ────────────────────────────────────────────────────
vila = {
    "fase": "aguardando",            # "aguardando" | "aberta" | "encerrada"
    "brutos": 0,                     # estoque de cristais brutos
    "lapidados": 0,                  # estoque de cristais lapidados
    "trabalhadores": 0,              # construções em andamento (0..LIMITE_TRABALHADORES)
    "lapidarias": {},                # "lapidaria-N" -> estrutura da lapidária
    "lotes": {lote: None for lote in LOTES},   # lote -> id da lapidária ou None
    "proximo_id": 1,                 # gerador de "lapidaria-N"
    "construcoes_ativas": [],        # [{"lid": str, "inicio_monotonic": float}]
    "melhorias_ativas": [],          # [{"lid": str, "inicio_monotonic": float}]
}


# ── Snapshot e payloads ───────────────────────────────────────────────
def _tempo_restante(inicio_monotonic, duracao, agora):
    return round(max(0.0, duracao - (agora - inicio_monotonic)), 1)


def snapshot():
    """Retorna fotografia pública e serializável em JSON do estado da vila."""
    agora = time.monotonic()
    lapidarias = {}
    for lid, lap in vila["lapidarias"].items():
        lapidarias[lid] = {
            "id": lap["id"],
            "lote": lap["lote"],
            "nivel": lap["nivel"],
            "situacao": lap["situacao"],
            "vagas": [
                {
                    "numero": v["numero"],
                    "ocupada": v["ocupada"],
                    "tempo_restante": (
                        _tempo_restante(v["inicio_monotonic"], TEMPO_LAPIDACAO, agora)
                        if v["ocupada"] and v["inicio_monotonic"] is not None else 0.0
                    ),
                }
                for v in lap["vagas"]
            ],
        }

    return {
        "fase": vila["fase"],
        "brutos": vila["brutos"],
        "lapidados": vila["lapidados"],
        "trabalhadores": {"ocupados": vila["trabalhadores"], "limite": LIMITE_TRABALHADORES},
        "lapidarias": lapidarias,
        "lotes": dict(vila["lotes"]),
        "construcoes": [
            {"lid": c["lid"], "tempo_restante": _tempo_restante(c["inicio_monotonic"], TEMPO_OBRA, agora)}
            for c in vila["construcoes_ativas"]
        ],
        "melhorias": [
            {"lid": m["lid"], "tempo_restante": _tempo_restante(m["inicio_monotonic"], TEMPO_OBRA, agora)}
            for m in vila["melhorias_ativas"]
        ],
    }


def fato(causa, /, **extras):
    """Payload padrão com snapshot em 'estado' e a 'causa'.

    'extras' não pode sobrescrever 'estado' e 'causa'.
    """
    return {**extras, "estado": snapshot(), "causa": causa}


# ── Helpers de domínio ────────────────────────────────────────────────
def proximo_lote_livre() -> str | None:
    """Retorna o primeiro lote vago em ordem numérica crescente, ou None."""
    for lote in LOTES:
        if vila["lotes"][lote] is None:
            return lote
    return None


def _nova_vaga(numero: int) -> dict:
    """Cria a estrutura inicial padrão de uma vaga de lapidação."""
    return {
        "numero": numero,
        "ocupada": False,
        "inicio_monotonic": None,
        "disponivel_desde": None,
        "ciclo_id": 0,
    }


def _remover_obra_ativa(lista: list, lid: str):
    """Remove registro de obra ativa por `lid` no lugar."""
    lista[:] = [r for r in lista if r["lid"] != lid]


# ── Conexão e sincronização ───────────────────────────────────────────
@sio.event
async def connect(sid, environ, auth):
    global mestre_sid

    dados = auth if isinstance(auth, dict) else {}
    nome = dados.get("nome")
    nome = nome.strip() if isinstance(nome, str) else ""
    papel = dados.get("papel")

    if not nome:
        raise SioConnectionRefusedError("Nome inválido: não pode ser vazio nem conter apenas espaços.")
    if papel not in ("mestre", "jogador"):
        raise SioConnectionRefusedError("Papel inválido: deve ser 'mestre' ou 'jogador'.")
    if papel == "mestre" and mestre_sid is not None:
        raise SioConnectionRefusedError("Já existe um Mestre conectado na vila.")

    jogadores[sid] = {"nome": nome, "papel": papel}
    if papel == "mestre":
        mestre_sid = sid

    sio.start_background_task(_sincronizar_apos_conexao, sid)


async def _sincronizar_apos_conexao(sid):
    await sio.sleep(0)
    if sid not in jogadores:
        return
    await sio.emit("estado.sincronizado", fato("conexao"), to=sid)


@sio.event
async def disconnect(sid, reason=None):
    global mestre_sid
    jogadores.pop(sid, None)
    if sid == mestre_sid:
        mestre_sid = None


# ── Abertura e encerramento da temporada ──────────────────────────────
@sio.on("vila.abertura_solicitada")
async def abrir_vila(sid, dados=None):
    global tarefa_mina
    pedido = "vila.abertura_solicitada"

    if sid != mestre_sid:
        await sio.emit("vila.abertura_recusada", fato(pedido, motivo="Apenas o Mestre pode abrir a temporada."), to=sid)
        return
    if vila["fase"] != "aguardando":
        await sio.emit("vila.abertura_recusada", fato(pedido, motivo="A vila só pode ser aberta na fase 'aguardando'."), to=sid)
        return

    vila["fase"] = "aberta"
    if tarefa_mina is None or tarefa_mina.done():
        tarefa_mina = sio.start_background_task(mina)
    await sio.emit("vila.aberta", fato(pedido))


@sio.on("vila.encerramento_solicitado")
async def encerrar_vila(sid, dados=None):
    global tarefa_mina
    pedido = "vila.encerramento_solicitado"

    if sid != mestre_sid:
        await sio.emit("vila.encerramento_recusado", fato(pedido, motivo="Apenas o Mestre pode encerrar a temporada."), to=sid)
        return
    if vila["fase"] != "aberta":
        await sio.emit("vila.encerramento_recusado", fato(pedido, motivo="A vila só pode ser encerrada na fase 'aberta'."), to=sid)
        return

    vila["fase"] = "encerrada"
    if tarefa_mina is not None and not tarefa_mina.done():
        tarefa_mina.cancel()
        tarefa_mina = None
    await sio.emit("vila.encerrada", fato(pedido))


# ── Temporizador da mina ──────────────────────────────────────────────
async def mina():
    try:
        while vila["fase"] == "aberta":
            await sio.sleep(INTERVALO_MINA)
            if vila["fase"] != "aberta":
                break
            vila["brutos"] += 1
            await sio.emit("mina.cristal_produzido", fato("temporizador", quantidade=1))
    except asyncio.CancelledError:
        pass


# ── Construção de lapidárias ──────────────────────────────────────────
@sio.on("construcao.solicitada")
async def solicitar_construcao(sid, dados=None):
    pedido = "construcao.solicitada"

    # 1. Validar solicitante: deve ser exatamente jogador conectado
    jogador = jogadores.get(sid)
    if not jogador or jogador.get("papel") != "jogador":
        await sio.emit("construcao.recusada", fato(pedido, motivo="Apenas jogadores podem solicitar construções."), to=sid)
        return

    # 2. Validar fase da vila
    if vila["fase"] != "aberta":
        await sio.emit("construcao.recusada", fato(pedido, motivo="Construções só são permitidas com a vila aberta."), to=sid)
        return

    # 3. Validar recursos
    if vila["brutos"] < CUSTO_CONSTRUCAO:
        await sio.emit("construcao.recusada", fato(pedido, motivo="Cristais brutos insuficientes (necessário: 5)."), to=sid)
        return

    # 4. Validar trabalhadores
    if vila["trabalhadores"] >= LIMITE_TRABALHADORES:
        await sio.emit("construcao.recusada", fato(pedido, motivo="Todos os trabalhadores estão ocupados (limite: 2)."), to=sid)
        return

    # 5. Validar lotes
    lote = proximo_lote_livre()
    if lote is None:
        await sio.emit("construcao.recusada", fato(pedido, motivo="Não há lotes disponíveis para construção (limite: 6)."), to=sid)
        return

    # Mutação atômica e agendamento da tarefa (sem await no meio):
    inicio = time.monotonic()
    lid = f"lapidaria-{vila['proximo_id']}"
    vila["proximo_id"] += 1
    vila["brutos"] -= CUSTO_CONSTRUCAO
    vila["trabalhadores"] += 1
    vila["lotes"][lote] = lid
    lap = {
        "id": lid,
        "lote": lote,
        "nivel": 1,
        "situacao": "em construção",
        "tarefa_id": 1,
        "vagas": [_nova_vaga(1)],
    }
    vila["lapidarias"][lid] = lap
    vila["construcoes_ativas"].append({"lid": lid, "inicio_monotonic": inicio})

    inicio_emitido = asyncio.Event()
    sio.start_background_task(obra_construcao, lid, lap["tarefa_id"], inicio, inicio_emitido)

    try:
        await sio.emit("construcao.iniciada", fato(
            pedido,
            solicitante=jogador["nome"],
            lapidaria_id=lid,
            lote=lote,
            custo=CUSTO_CONSTRUCAO,
        ))
    finally:
        inicio_emitido.set()


async def obra_construcao(lid, token_obra, inicio_monotonic, inicio_emitido):
    restante = max(0.0, TEMPO_OBRA - (time.monotonic() - inicio_monotonic))
    await sio.sleep(restante)
    await inicio_emitido.wait()

    lap = vila["lapidarias"].get(lid)
    if not lap or lap["tarefa_id"] != token_obra:
        return

    _remover_obra_ativa(vila["construcoes_ativas"], lid)
    vila["trabalhadores"] -= 1
    lap["situacao"] = "disponível"

    if vila["fase"] == "aberta":
        lap["vagas"][0]["disponivel_desde"] = time.monotonic()
    else:
        lap["vagas"][0]["disponivel_desde"] = None

    await sio.emit("construcao.concluida", fato(
        "temporizador",
        lapidaria_id=lid,
        lote=lap["lote"],
        nivel=1,
        situacao="disponível",
    ))
