"""Testes de aceitação da Etapa 2 (abertura e encerramento da vila).

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


class TestEtapa2EmProcesso(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._vila_original = copy.deepcopy(server.vila)
        server.jogadores.clear()
        server.mestre_sid = None
        server.tarefa_mina = None
        patcher = patch.object(server.sio, "emit", new_callable=AsyncMock)
        self.emit = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        if server.tarefa_mina and not server.tarefa_mina.done():
            server.tarefa_mina.cancel()
        server.tarefa_mina = None
        server.vila.clear()
        server.vila.update(self._vila_original)
        server.jogadores.clear()
        server.mestre_sid = None

    async def conectar_mestre(self, sid="m1", nome="Mestre"):
        await server.connect(sid, {}, {"nome": nome, "papel": "mestre"})
        return sid

    async def conectar_jogador(self, sid="j1", nome="Jogador"):
        await server.connect(sid, {}, {"nome": nome, "papel": "jogador"})
        return sid

    # 1. Abertura válida pelo Mestre
    async def test_01_abertura_valida_pelo_mestre(self):
        m1 = await self.conectar_mestre()
        self.assertEqual(server.vila["fase"], "aguardando")

        # Controla tempo da mina para não produzir durante o teste de abertura
        with patch.object(server, "INTERVALO_MINA", 10.0):
            await server.abrir_vila(m1)

        self.assertEqual(server.vila["fase"], "aberta")
        self.assertIsNotNone(server.tarefa_mina)
        self.assertFalse(server.tarefa_mina.done())

        # Verifica emissão de vila.aberta para todos
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "vila.aberta"]
        self.assertEqual(len(chamadas), 1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["causa"], "vila.abertura_solicitada")
        self.assertEqual(payload["estado"]["fase"], "aberta")

    # 2. Abertura recusada para não-Mestre
    async def test_02_abertura_recusada_para_nao_mestre(self):
        await self.conectar_mestre("m1")
        j1 = await self.conectar_jogador("j1")

        await server.abrir_vila(j1)

        self.assertEqual(server.vila["fase"], "aguardando")
        self.assertIsNone(server.tarefa_mina)

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "vila.abertura_recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].kwargs.get("to"), j1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["causa"], "vila.abertura_solicitada")
        self.assertIn("Apenas o Mestre", payload["motivo"])
        self.assertIn("estado", payload)
        self.assertEqual(payload["estado"]["fase"], "aguardando")

    # 3. Abertura recusada quando fase != aguardando (já aberta ou encerrada)
    async def test_03_abertura_recusada_quando_ja_aberta_ou_encerrada(self):
        m1 = await self.conectar_mestre()

        with patch.object(server, "INTERVALO_MINA", 10.0):
            await server.abrir_vila(m1)
            self.emit.reset_mock()

            # Tenta abrir novamente quando já aberta
            await server.abrir_vila(m1)
            self.assertEqual(server.vila["fase"], "aberta")
            chamadas = [c for c in self.emit.call_args_list if c.args[0] == "vila.abertura_recusada"]
            self.assertEqual(len(chamadas), 1)
            self.assertEqual(chamadas[0].kwargs.get("to"), m1)
            payload_aberta = chamadas[0].args[1]
            self.assertEqual(payload_aberta["causa"], "vila.abertura_solicitada")
            self.assertIn("aguardando", payload_aberta["motivo"])
            self.assertEqual(payload_aberta["estado"]["fase"], "aberta")

            # Encerra
            await server.encerrar_vila(m1)
            self.assertEqual(server.vila["fase"], "encerrada")
            self.emit.reset_mock()

            # Tenta abrir quando encerrada (não-reabertura)
            await server.abrir_vila(m1)
            self.assertEqual(server.vila["fase"], "encerrada")
            chamadas = [c for c in self.emit.call_args_list if c.args[0] == "vila.abertura_recusada"]
            self.assertEqual(len(chamadas), 1)
            self.assertEqual(chamadas[0].kwargs.get("to"), m1)
            payload_enc = chamadas[0].args[1]
            self.assertEqual(payload_enc["causa"], "vila.abertura_solicitada")
            self.assertIn("aguardando", payload_enc["motivo"])
            self.assertEqual(payload_enc["estado"]["fase"], "encerrada")

    # 4. Mina: tempo controlado produz cristal e emite evento
    async def test_04_mina_produz_com_tempo_controlado(self):
        m1 = await self.conectar_mestre()
        self.assertEqual(server.vila["brutos"], 0)

        # Usamos intervalo de 0.02s para o teste ser rápido e determinístico
        with patch.object(server, "INTERVALO_MINA", 0.02):
            await server.abrir_vila(m1)
            await asyncio.sleep(0.05)  # tempo suficiente para 2 extrações
            await server.encerrar_vila(m1)

        self.assertGreaterEqual(server.vila["brutos"], 1)
        chamadas_mina = [c for c in self.emit.call_args_list if c.args[0] == "mina.cristal_produzido"]
        self.assertGreaterEqual(len(chamadas_mina), 1)
        payload = chamadas_mina[0].args[1]
        self.assertEqual(payload["causa"], "temporizador")
        self.assertEqual(payload["quantidade"], 1)
        self.assertIn("estado", payload)

    # 5. Encerramento válido pelo Mestre e interrupção imediata da mina
    async def test_05_encerramento_valido_interrompe_mina(self):
        m1 = await self.conectar_mestre()

        with patch.object(server, "INTERVALO_MINA", 0.02):
            await server.abrir_vila(m1)
            await asyncio.sleep(0.03)  # produz 1
            await server.encerrar_vila(m1)
            self.assertEqual(server.vila["fase"], "encerrada")

            # Verifica tarefa cancelada / limpa
            self.assertTrue(server.tarefa_mina is None or server.tarefa_mina.done())

            brutos_no_encerramento = server.vila["brutos"]
            chamadas_no_encerramento = len([c for c in self.emit.call_args_list if c.args[0] == "mina.cristal_produzido"])

            # Aguarda mais tempo para garantir que nada mais é produzido
            await asyncio.sleep(0.05)
            self.assertEqual(server.vila["brutos"], brutos_no_encerramento)
            self.assertEqual(
                len([c for c in self.emit.call_args_list if c.args[0] == "mina.cristal_produzido"]),
                chamadas_no_encerramento
            )

        chamadas_enc = [c for c in self.emit.call_args_list if c.args[0] == "vila.encerrada"]
        self.assertEqual(len(chamadas_enc), 1)
        self.assertEqual(chamadas_enc[0].args[1]["causa"], "vila.encerramento_solicitado")
        self.assertEqual(chamadas_enc[0].args[1]["estado"]["fase"], "encerrada")

    # 6. Encerramento recusado para não-Mestre
    async def test_06_encerramento_recusado_para_nao_mestre(self):
        m1 = await self.conectar_mestre()
        j1 = await self.conectar_jogador()

        with patch.object(server, "INTERVALO_MINA", 10.0):
            await server.abrir_vila(m1)
            self.emit.reset_mock()

            await server.encerrar_vila(j1)
            self.assertEqual(server.vila["fase"], "aberta")

            chamadas = [c for c in self.emit.call_args_list if c.args[0] == "vila.encerramento_recusado"]
            self.assertEqual(len(chamadas), 1)
            self.assertEqual(chamadas[0].kwargs.get("to"), j1)
            payload = chamadas[0].args[1]
            self.assertEqual(payload["causa"], "vila.encerramento_solicitado")
            self.assertIn("Apenas o Mestre", payload["motivo"])
            self.assertIn("estado", payload)
            self.assertEqual(payload["estado"]["fase"], "aberta")

    # 7. Encerramento recusado quando fase != aberta
    async def test_07_encerramento_recusado_quando_fase_nao_e_aberta(self):
        m1 = await self.conectar_mestre()

        # Na fase aguardando
        await server.encerrar_vila(m1)
        self.assertEqual(server.vila["fase"], "aguardando")
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "vila.encerramento_recusado"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].kwargs.get("to"), m1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["causa"], "vila.encerramento_solicitado")
        self.assertIn("aberta", payload["motivo"])
        self.assertIn("estado", payload)
        self.assertEqual(payload["estado"]["fase"], "aguardando")


# ── Teste de integração real com Socket.IO ────────────────────────────
class ClienteEngineIO:
    """Cliente mínimo Engine.IO v4 / Socket.IO v4 por long-polling."""

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

    def emitir(self, evento, dados=None):
        payload = [evento]
        if dados is not None:
            payload.append(dados)
        self._requisicao("POST", "42" + json.dumps(payload))

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


def tem_evento(nome):
    def _checar(pacotes):
        return any(p.startswith("42") and nome in p for p in pacotes)
    return _checar


class TestProtocoloSocketIOEtapa2(unittest.TestCase):
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

    def test_integracao_abertura_e_encerramento_via_socketio(self):
        # Mestre conecta
        mestre = ClienteEngineIO(self.base).abrir()
        mestre.conectar({"nome": "Mestre1", "papel": "mestre"})
        mestre.coletar_ate(tem_evento("estado.sincronizado"))

        # Mestre envia vila.abertura_solicitada
        mestre.emitir("vila.abertura_solicitada")
        mestre.coletar_ate(tem_evento("vila.aberta"))

        eventos = ClienteEngineIO.eventos(mestre.pacotes)
        nomes_eventos = [e[0] for e in eventos]
        self.assertIn("vila.aberta", nomes_eventos)

        # Mestre envia vila.encerramento_solicitado
        mestre.emitir("vila.encerramento_solicitado")
        mestre.coletar_ate(tem_evento("vila.encerrada"))

        eventos = ClienteEngineIO.eventos(mestre.pacotes)
        nomes_eventos = [e[0] for e in eventos]
        self.assertIn("vila.encerrada", nomes_eventos)


if __name__ == "__main__":
    unittest.main()
