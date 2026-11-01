"""Testes de aceitação da Etapa 1 (conexão, papéis e sincronização).

Executar na raiz do projeto:
    .venv/bin/python -m unittest discover -s tests -v
"""
import asyncio
import copy
import json
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import AsyncMock, patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import server  # noqa: E402

CAMPOS_PUBLICOS = {"fase", "brutos", "lapidados", "trabalhadores",
                   "lapidarias", "lotes", "construcoes", "melhorias"}
CHAVES_INTERNAS = {"inicio_monotonic", "disponivel_desde", "ciclo_id", "tarefa_id",
                   "construcoes_ativas", "melhorias_ativas", "proximo_id"}
MOTIVO_SEGUNDO_MESTRE = "Já existe um Mestre conectado na vila."
MOTIVO_PAPEL_INVALIDO = "Papel inválido: deve ser 'mestre' ou 'jogador'."


def chaves_recursivas(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from chaves_recursivas(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from chaves_recursivas(item)


class TestServidorEmProcesso(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._vila_original = copy.deepcopy(server.vila)
        server.jogadores.clear()
        server.mestre_sid = None
        patcher = patch.object(server.sio, "emit", new_callable=AsyncMock)
        self.emit = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        server.vila.clear()
        server.vila.update(self._vila_original)
        server.jogadores.clear()
        server.mestre_sid = None

    async def entrar(self, sid, nome, papel):
        return await server.connect(sid, {}, {"nome": nome, "papel": papel})

    async def deixar_tarefas_rodarem(self):
        await asyncio.sleep(0.05)

    def eventos_para(self, sid):
        return [c for c in self.emit.call_args_list
                if c.args[0] == "estado.sincronizado" and c.kwargs.get("to") == sid]

    # 0. Configuração
    def test_always_connect_continua_false(self):
        self.assertIs(server.sio.always_connect, False)

    # 1. Jogador com nome válido
    async def test_01_jogador_conecta_com_nome_valido(self):
        self.assertIsNone(await self.entrar("s1", "  Ana  ", "jogador"))
        self.assertEqual(server.jogadores["s1"], {"nome": "Ana", "papel": "jogador"})
        self.assertIsNone(server.mestre_sid)

    # 2. Mestre quando não há outro
    async def test_02_mestre_conecta_quando_nao_ha_outro(self):
        self.assertIsNone(await self.entrar("m1", "Mia", "mestre"))
        self.assertEqual(server.mestre_sid, "m1")
        self.assertEqual(server.jogadores["m1"]["papel"], "mestre")

    # 3. Segundo Mestre rejeitado
    async def test_03_segundo_mestre_e_rejeitado(self):
        await self.entrar("m1", "Mia", "mestre")
        await self.deixar_tarefas_rodarem()
        self.emit.reset_mock()
        with self.assertRaises(server.SioConnectionRefusedError) as ctx:
            await self.entrar("m2", "Outro", "mestre")
        self.assertEqual(ctx.exception.error_args["message"], MOTIVO_SEGUNDO_MESTRE)
        self.assertEqual(server.mestre_sid, "m1")
        self.assertNotIn("m2", server.jogadores)
        await self.deixar_tarefas_rodarem()
        self.emit.assert_not_called()

    # 4. Papel inválido explicitamente rejeitado
    async def test_04_papel_invalido_e_rejeitado(self):
        papeis_invalidos = ["admin", "espectador", "", None, 123, True]
        for p in papeis_invalidos:
            with self.subTest(papel=p):
                with self.assertRaises(server.SioConnectionRefusedError) as ctx:
                    await server.connect("sx", {}, {"nome": "Teste", "papel": p})
                self.assertEqual(ctx.exception.error_args["message"], MOTIVO_PAPEL_INVALIDO)
        self.assertEqual(server.jogadores, {})
        await self.deixar_tarefas_rodarem()
        self.emit.assert_not_called()

    # 5. Nome vazio / só espaços / ausente / tipo inválido
    async def test_05_nome_invalido_e_rejeitado(self):
        casos = [{"nome": ""}, {"nome": "   "}, {"nome": "\t\n"}, {"nome": None},
                 {"nome": 123}, {"papel": "jogador"}, {}, None]
        for auth in casos:
            with self.subTest(auth=auth):
                with self.assertRaises(server.SioConnectionRefusedError) as ctx:
                    await server.connect("sx", {}, auth)
                self.assertIn("Nome inválido", ctx.exception.error_args["message"])
        self.assertEqual(server.jogadores, {})
        await self.deixar_tarefas_rodarem()
        self.emit.assert_not_called()

    # 6 e 7. Nomes duplicados + sincronização individual
    async def test_06_07_nomes_duplicados_e_sincronizacao_individual(self):
        await self.entrar("s1", "Ana", "jogador")
        await self.entrar("s2", "Ana", "jogador")
        self.assertEqual(set(server.jogadores), {"s1", "s2"})
        self.emit.assert_not_called()
        await self.deixar_tarefas_rodarem()
        self.assertEqual(self.emit.await_count, 2)
        for sid in ("s1", "s2"):
            chamadas = self.eventos_para(sid)
            self.assertEqual(len(chamadas), 1, sid)
            payload = chamadas[0].args[1]
            self.assertEqual(payload["causa"], "conexao")
            self.assertEqual(set(payload["estado"]), CAMPOS_PUBLICOS)

    # 8. Desconectado antes da sincronização
    async def test_08_desconectado_antes_da_sincronizacao_nao_recebe(self):
        await self.entrar("s1", "Ana", "jogador")
        await server.disconnect("s1")
        await self.deixar_tarefas_rodarem()
        self.emit.assert_not_called()

    # 9. Mestre desconecta -> outro assume
    async def test_09_mestre_desconecta_e_outro_assume(self):
        await self.entrar("m1", "Mia", "mestre")
        await server.disconnect("m1", "client disconnect")
        self.assertIsNone(server.mestre_sid)
        self.assertNotIn("m1", server.jogadores)
        await self.entrar("m2", "Nova", "mestre")
        self.assertEqual(server.mestre_sid, "m2")

    # 9b. Desconexão do Mestre não altera a fase
    async def test_09b_desconexao_do_mestre_nao_altera_fase(self):
        await self.entrar("m1", "Mia", "mestre")
        server.vila["fase"] = "aberta"
        antes = copy.deepcopy(server.vila)
        await server.disconnect("m1")
        self.assertEqual(server.vila, antes)

    # 10. Desconexão de jogador comum não altera a vila nem o Mestre
    async def test_10_desconexao_de_jogador_nao_altera_a_vila(self):
        await self.entrar("m1", "Mia", "mestre")
        await self.entrar("s1", "Ana", "jogador")
        antes = copy.deepcopy(server.vila)
        await server.disconnect("s1")
        self.assertEqual(server.vila, antes)
        self.assertEqual(server.mestre_sid, "m1")
        self.assertEqual(set(server.jogadores), {"m1"})

    # 11. Snapshot: só campos públicos e serializável em JSON (vila vazia)
    def test_11_snapshot_vazio_publico_e_serializavel(self):
        snap = server.snapshot()
        self.assertEqual(set(snap), CAMPOS_PUBLICOS)
        json.dumps(snap)
        self.assertEqual(snap["fase"], "aguardando")
        self.assertEqual((snap["brutos"], snap["lapidados"]), (0, 0))
        self.assertEqual(snap["trabalhadores"], {"ocupados": 0, "limite": 2})
        self.assertEqual(snap["lotes"], {f"lote{n}": None for n in range(1, 7)})
        self.assertEqual((snap["lapidarias"], snap["construcoes"], snap["melhorias"]), ({}, [], []))

    # 11b. Snapshot com estrutura interna povoada: nada interno vaza
    def test_11b_snapshot_nao_expoe_campos_internos(self):
        agora = time.monotonic()
        server.vila["lapidarias"]["lapidaria-1"] = {
            "id": "lapidaria-1", "lote": "lote1", "nivel": 2, "situacao": "disponível",
            "tarefa_id": 7,
            "vagas": [
                {"numero": 1, "ocupada": True, "inicio_monotonic": agora - 4,
                 "disponivel_desde": None, "ciclo_id": 3},
                {"numero": 2, "ocupada": False, "inicio_monotonic": None,
                 "disponivel_desde": agora - 1, "ciclo_id": 0},
            ],
        }
        server.vila["lapidarias"]["lapidaria-2"] = {
            "id": "lapidaria-2", "lote": "lote2", "nivel": 1, "situacao": "em construção",
            "tarefa_id": 1,
            "vagas": [{"numero": 1, "ocupada": False, "inicio_monotonic": None,
                       "disponivel_desde": None, "ciclo_id": 0}],
        }
        server.vila["lotes"]["lote1"] = "lapidaria-1"
        server.vila["lotes"]["lote2"] = "lapidaria-2"
        server.vila["trabalhadores"] = 1
        server.vila["construcoes_ativas"].append({"lid": "lapidaria-2", "inicio_monotonic": agora - 1})
        server.vila["melhorias_ativas"].append({"lid": "lapidaria-1", "inicio_monotonic": agora - 2})

        snap = server.snapshot()
        json.dumps(snap)
        self.assertEqual(set(snap), CAMPOS_PUBLICOS)
        self.assertFalse(CHAVES_INTERNAS & set(chaves_recursivas(snap)))

        vagas = snap["lapidarias"]["lapidaria-1"]["vagas"]
        self.assertEqual([set(v) for v in vagas], [{"numero", "ocupada", "tempo_restante"}] * 2)
        self.assertAlmostEqual(vagas[0]["tempo_restante"], 6.0, delta=0.5)
        self.assertEqual(vagas[1]["tempo_restante"], 0.0)
        self.assertEqual(set(snap["lapidarias"]["lapidaria-1"]),
                         {"id", "lote", "nivel", "situacao", "vagas"})
        self.assertEqual([set(c) for c in snap["construcoes"]], [{"lid", "tempo_restante"}])
        self.assertAlmostEqual(snap["construcoes"][0]["tempo_restante"], 2.0, delta=0.5)
        self.assertEqual([set(m) for m in snap["melhorias"]], [{"lid", "tempo_restante"}])
        self.assertAlmostEqual(snap["melhorias"][0]["tempo_restante"], 1.0, delta=0.5)

    # 12. fato() protege chaves essenciais contra extras
    def test_fato_protege_estado_e_causa_contra_sobrescrita(self):
        f = server.fato("conexao_original", estado="tentativa_hack", causa="tentativa_hack", outro="ok")
        self.assertEqual(f["causa"], "conexao_original")
        self.assertIsInstance(f["estado"], dict)
        self.assertEqual(set(f["estado"]), CAMPOS_PUBLICOS)
        self.assertEqual(f["outro"], "ok")


# ── Camada de protocolo (servidor real) ───────────────────────────────
class ClienteEngineIO:
    """Cliente mínimo Engine.IO v4 / Socket.IO v4 por long-polling (só stdlib)."""

    def __init__(self, base):
        self.base = base
        self.sid = None
        self.pacotes = []

    def _url(self):
        sid = f"&sid={self.sid}" if self.sid else ""
        return f"{self.base}/socket.io/?EIO=4&transport=polling{sid}"

    def _requisicao(self, metodo, corpo=None, timeout=5):
        req = urllib.request.Request(self._url(), method=metodo,
                                     data=None if corpo is None else corpo.encode())
        if corpo is not None:
            req.add_header("Content-Type", "text/plain;charset=UTF-8")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()

    def abrir(self):
        self.sid = json.loads(self._requisicao("GET")[1:])["sid"]
        return self

    def conectar(self, auth):
        self._requisicao("POST", "40" + json.dumps(auth))

    def desconectar(self):
        self._requisicao("POST", "41")

    def coletar_ate(self, condicao, limite=5.0):
        fim = time.monotonic() + limite
        while not condicao(self.pacotes) and time.monotonic() < fim:
            try:
                self.pacotes += self._requisicao("GET", timeout=max(0.5, fim - time.monotonic())).split("\x1e")
            except (socket.timeout, TimeoutError):
                break
        return self.pacotes

    @staticmethod
    def eventos(pacotes):
        return [json.loads(p[2:]) for p in pacotes if p.startswith("42")]


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def aceitou(pacotes):
    return any(p.startswith("44") for p in pacotes) or any(
        p.startswith("42") and "estado.sincronizado" in p for p in pacotes)


class TestProtocoloSocketIO(unittest.TestCase):
    def setUp(self):
        porta = porta_livre()
        self.base = f"http://127.0.0.1:{porta}"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
             "--port", str(porta), "--log-level", "warning"],
            cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self._parar)
        fim = time.monotonic() + 15
        while True:
            try:
                ClienteEngineIO(self.base).abrir()
                break
            except (urllib.error.URLError, ConnectionError, socket.timeout):
                if time.monotonic() > fim or self.proc.poll() is not None:
                    self.fail("servidor não subiu")
                time.sleep(0.2)

    def _parar(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def novo(self, nome, papel="jogador"):
        c = ClienteEngineIO(self.base).abrir()
        c.conectar({"nome": nome, "papel": papel})
        c.coletar_ate(aceitou)
        return c

    # 1, 2, 7: aceite + CONNECT chega ANTES de estado.sincronizado
    def test_aceite_envia_connect_antes_do_estado_sincronizado(self):
        for nome, papel in (("Ana", "jogador"), ("Mia", "mestre")):
            with self.subTest(papel=papel):
                c = self.novo(nome, papel)
                nomes = [p[:2] for p in c.pacotes]
                self.assertEqual(nomes[0], "40", c.pacotes)
                eventos = ClienteEngineIO.eventos(c.pacotes)
                self.assertEqual([e[0] for e in eventos], ["estado.sincronizado"])
                self.assertEqual(set(eventos[0][1]["estado"]), CAMPOS_PUBLICOS)
                self.assertEqual(eventos[0][1]["causa"], "conexao")

    # 3, 4: segundo Mestre -> CONNECT_ERROR (connect_error) com motivo legível
    def test_segundo_mestre_gera_connect_error_com_motivo(self):
        self.novo("Mia", "mestre")
        c = ClienteEngineIO(self.base).abrir()
        c.conectar({"nome": "Outro", "papel": "mestre"})
        c.coletar_ate(aceitou)
        self.assertEqual(c.pacotes[0][:2], "44", c.pacotes)
        self.assertEqual(json.loads(c.pacotes[0][2:])["message"], MOTIVO_SEGUNDO_MESTRE)
        self.assertEqual(ClienteEngineIO.eventos(c.pacotes), [])

    # 4b: papel inválido no protocolo -> CONNECT_ERROR com motivo
    def test_papel_invalido_gera_connect_error_com_motivo(self):
        c = ClienteEngineIO(self.base).abrir()
        c.conectar({"nome": "Ana", "papel": "admin"})
        c.coletar_ate(aceitou)
        self.assertEqual(c.pacotes[0][:2], "44", c.pacotes)
        self.assertEqual(json.loads(c.pacotes[0][2:])["message"], MOTIVO_PAPEL_INVALIDO)
        self.assertEqual(ClienteEngineIO.eventos(c.pacotes), [])

    # 4, 5: nome vazio -> CONNECT_ERROR com motivo legível
    def test_nome_vazio_gera_connect_error_com_motivo(self):
        for nome in ("", "   "):
            with self.subTest(nome=nome):
                c = ClienteEngineIO(self.base).abrir()
                c.conectar({"nome": nome, "papel": "jogador"})
                c.coletar_ate(aceitou)
                self.assertEqual(c.pacotes[0][:2], "44", c.pacotes)
                self.assertIn("Nome inválido", json.loads(c.pacotes[0][2:])["message"])
                self.assertEqual(ClienteEngineIO.eventos(c.pacotes), [])

    # 6, 7: nomes duplicados aceitos; cada cliente recebe o seu próprio evento
    def test_nomes_duplicados_recebem_cada_um_seu_estado(self):
        a, b = self.novo("Ana"), self.novo("Ana")
        self.assertNotEqual(a.sid, b.sid)
        for c in (a, b):
            self.assertEqual([e[0] for e in ClienteEngineIO.eventos(c.pacotes)], ["estado.sincronizado"])

    # 9: Mestre desconecta -> outro assume
    def test_mestre_desconecta_e_outro_assume(self):
        m1 = self.novo("Mia", "mestre")
        m1.desconectar()
        time.sleep(0.4)
        m2 = self.novo("Nova", "mestre")
        self.assertEqual(m2.pacotes[0][:2], "40", m2.pacotes)
        self.assertEqual([e[0] for e in ClienteEngineIO.eventos(m2.pacotes)], ["estado.sincronizado"])


if __name__ == "__main__":
    unittest.main()
