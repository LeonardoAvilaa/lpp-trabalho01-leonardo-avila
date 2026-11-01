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
