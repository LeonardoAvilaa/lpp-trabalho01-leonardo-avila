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
_tarefa_dispatcher = None
_dispatcher_pendente = False
_vagas_coalescidas = []

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
    global tarefa_mina, _tarefa_dispatcher, _dispatcher_pendente, _vagas_coalescidas
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

    _dispatcher_pendente = False
    _vagas_coalescidas.clear()
    if _tarefa_dispatcher is not None and not _tarefa_dispatcher.done():
        _tarefa_dispatcher.cancel()
        _tarefa_dispatcher = None

    # Estorno e invalidação de todas as lapidações ativas
    for lap in vila["lapidarias"].values():
        for vaga in lap["vagas"]:
            if vaga["ocupada"]:
                vila["brutos"] += 1
                vaga["ocupada"] = False
                vaga["inicio_monotonic"] = None
                vaga["ciclo_id"] += 1
            vaga["disponivel_desde"] = None

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
            agendar_dispatcher_fifo()
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

    ev_conclusao = None
    if vila["fase"] == "aberta":
        lap["vagas"][0]["disponivel_desde"] = time.monotonic()
        ev_conclusao = asyncio.Event()
        registrar_vaga_liberada(lid, 1, ev_conclusao)
    else:
        lap["vagas"][0]["disponivel_desde"] = None

    try:
        await sio.emit("construcao.concluida", fato(
            "temporizador",
            lapidaria_id=lid,
            lote=lap["lote"],
            nivel=1,
            situacao="disponível",
        ))
    finally:
        if ev_conclusao is not None:
            ev_conclusao.set()
        if vila["fase"] == "aberta":
            agendar_dispatcher_fifo()


# ── Processamento de lapidação e fila FIFO ────────────────────────────
def _vagas_disponiveis_ordenadas() -> list[tuple[str, dict]]:
    """Retorna lista de (lid, vaga) ordenada pela política FIFO global."""
    resultado = []
    if vila["fase"] != "aberta":
        return resultado
    for lid, lap in vila["lapidarias"].items():
        if lap["situacao"] != "disponível":
            continue
        try:
            numero_lote = int(lap["lote"].replace("lote", ""))
        except (ValueError, AttributeError):
            numero_lote = 999
        for vaga in lap["vagas"]:
            if not vaga["ocupada"] and vaga["disponivel_desde"] is not None:
                resultado.append((lid, vaga, numero_lote))
    resultado.sort(key=lambda x: (x[1]["disponivel_desde"], x[2], x[1]["numero"]))
    return [(lid, vaga) for lid, vaga, _ in resultado]


def _alocar_fifo() -> list[dict]:
    """Síncrona. Aloca cristais brutos às vagas disponíveis pela ordem FIFO."""
    alocacoes = []
    if vila["fase"] != "aberta":
        return alocacoes
    vagas = _vagas_disponiveis_ordenadas()
    for lid, vaga in vagas:
        if vila["brutos"] <= 0 or vila["fase"] != "aberta":
            break
        vila["brutos"] -= 1
        vaga["ocupada"] = True
        vaga["ciclo_id"] += 1
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["disponivel_desde"] = None
        alocacoes.append({
            "lid": lid,
            "numero_vaga": vaga["numero"],
            "ciclo_id": vaga["ciclo_id"],
        })
    return alocacoes


def registrar_vaga_liberada(lid: str, vaga_num: int, ev_conclusao: asyncio.Event):
    """Registra síncronamente uma vaga em processo de liberação antes de qualquer await."""
    if vila["fase"] == "aberta":
        _vagas_coalescidas.append((lid, vaga_num, ev_conclusao))


def agendar_dispatcher_fifo():
    """Agenda o dispatcher com coalescing em background se a vila estiver aberta."""
    global _dispatcher_pendente, _tarefa_dispatcher
    if vila["fase"] != "aberta":
        return
    _dispatcher_pendente = True
    if _tarefa_dispatcher is None or _tarefa_dispatcher.done():
        _tarefa_dispatcher = sio.start_background_task(_ciclo_dispatcher_fifo)


async def _ciclo_dispatcher_fifo():
    """Ciclo de execução do dispatcher com agendamento agrupado (coalescing)."""
    global _dispatcher_pendente, _tarefa_dispatcher, _vagas_coalescidas
    try:
        while _dispatcher_pendente and vila["fase"] == "aberta":
            _dispatcher_pendente = False

            # Aguarda a conclusão efetiva da emissão na rede de todas as vagas registradas neste lote
            while _vagas_coalescidas:
                pendentes = [ev for _, _, ev in _vagas_coalescidas if not ev.is_set()]
                if not pendentes:
                    break
                await asyncio.gather(*(ev.wait() for ev in pendentes))

            if vila["fase"] != "aberta":
                break

            # Vagas liberadas no mesmo lote de coalescing recebem o mesmo timestamp
            # para desempate determinístico por lote e vaga, sem depender de microssegundos.
            if len(_vagas_coalescidas) > 1:
                ts_lote = time.monotonic()
                for lid, num, _ in _vagas_coalescidas:
                    lap = vila["lapidarias"].get(lid)
                    if lap and num <= len(lap["vagas"]):
                        v = lap["vagas"][num - 1]
                        if not v["ocupada"]:
                            v["disponivel_desde"] = ts_lote
            _vagas_coalescidas.clear()

            alocacoes = _alocar_fifo()
            for a in alocacoes:
                if vila["fase"] != "aberta":
                    break

                lap = vila["lapidarias"].get(a["lid"])
                if not lap or a["numero_vaga"] > len(lap["vagas"]):
                    continue
                vaga = lap["vagas"][a["numero_vaga"] - 1]
                if not vaga["ocupada"] or vaga["ciclo_id"] != a["ciclo_id"]:
                    continue

                await sio.emit("lapidaria.processamento_iniciado", fato(
                    "temporizador",
                    lapidaria_id=a["lid"],
                    vaga=a["numero_vaga"],
                ))

                if vila["fase"] == "aberta" and vaga["ocupada"] and vaga["ciclo_id"] == a["ciclo_id"]:
                    sio.start_background_task(lapidacao, a["lid"], a["numero_vaga"], a["ciclo_id"])
    except asyncio.CancelledError:
        pass
    finally:
        _tarefa_dispatcher = None


async def dispatcher_fifo():
    """Interface assíncrona para acionamento do dispatcher com garantia de execução."""
    agendar_dispatcher_fifo()
    while _tarefa_dispatcher is not None and not _tarefa_dispatcher.done():
        try:
            await asyncio.shield(_tarefa_dispatcher)
        except asyncio.CancelledError:
            break


async def lapidacao(lid: str, numero_vaga: int, ciclo_id_param: int):
    """Corrotina de ciclo de lapidação em uma vaga."""
    lap = vila["lapidarias"].get(lid)
    if not lap or numero_vaga > len(lap["vagas"]):
        return
    vaga = lap["vagas"][numero_vaga - 1]
    token_local = ciclo_id_param

    await sio.sleep(TEMPO_LAPIDACAO)

    if vaga["ciclo_id"] != token_local or vila["fase"] != "aberta":
        return

    vila["lapidados"] += 1
    vaga["ocupada"] = False
    vaga["inicio_monotonic"] = None
    vaga["disponivel_desde"] = time.monotonic()

    ev_conclusao = asyncio.Event()
    registrar_vaga_liberada(lid, numero_vaga, ev_conclusao)

    try:
        await sio.emit("lapidaria.cristal_lapidado", fato(
            "temporizador",
            lapidaria_id=lid,
            vaga=numero_vaga,
        ))
    finally:
        ev_conclusao.set()
        agendar_dispatcher_fifo()
