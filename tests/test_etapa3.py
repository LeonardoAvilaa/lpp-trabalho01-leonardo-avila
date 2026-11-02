"""Testes de aceitação da Etapa 3 (construção de lapidárias).

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


class TestEtapa3EmProcesso(unittest.IsolatedAsyncioTestCase):
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

    async def abrir_vila_com_saldo(self, saldo_brutos=5):
        m1 = await self.conectar_mestre()
        with patch.object(server, "INTERVALO_MINA", 100.0):
            await server.abrir_vila(m1)
        server.vila["brutos"] = saldo_brutos
        return m1

    # 1. Construção válida completa: início, transição e conclusão (cristais brutos)
    async def test_01_construcao_valida_completa(self):
        await self.abrir_vila_com_saldo(5)
        j1 = await self.conectar_jogador("j1", "Ana")

        with patch.object(server, "TEMPO_OBRA", 0.03):
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})

            # Estado imediato no início da obra
            self.assertEqual(server.vila["brutos"], 0)
            self.assertEqual(server.vila["trabalhadores"], 1)
            self.assertEqual(server.vila["lotes"]["lote1"], "lapidaria-1")
            self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "em construção")
            self.assertEqual(len(server.vila["construcoes_ativas"]), 1)

            # Evento construcao.iniciada
            chamadas_ini = [c for c in self.emit.call_args_list if c.args[0] == "construcao.iniciada"]
            self.assertEqual(len(chamadas_ini), 1)
            p_ini = chamadas_ini[0].args[1]
            self.assertEqual(p_ini["solicitante"], "Ana")
            self.assertEqual(p_ini["lapidaria_id"], "lapidaria-1")
            self.assertEqual(p_ini["lote"], "lote1")
            self.assertEqual(p_ini["custo"], 5)
            self.assertEqual(p_ini["modalidade"], "brutos")
            self.assertEqual(p_ini["causa"], "construcao.solicitada")
            self.assertIn("estado", p_ini)

            # Aguarda a conclusão da obra (0.03s + margem)
            await asyncio.sleep(0.06)

            # Estado após conclusão
            self.assertEqual(server.vila["trabalhadores"], 0)
            lap = server.vila["lapidarias"]["lapidaria-1"]
            self.assertEqual(lap["situacao"], "disponível")
            self.assertEqual(lap["nivel"], 1)
            self.assertEqual(len(lap["vagas"]), 1)
            self.assertFalse(lap["vagas"][0]["ocupada"])
            self.assertIsNotNone(lap["vagas"][0]["disponivel_desde"])
            self.assertEqual(len(server.vila["construcoes_ativas"]), 0)

            # Evento construcao.concluida
            chamadas_conc = [c for c in self.emit.call_args_list if c.args[0] == "construcao.concluida"]
            self.assertEqual(len(chamadas_conc), 1)
            p_conc = chamadas_conc[0].args[1]
            self.assertEqual(p_conc["lapidaria_id"], "lapidaria-1")
            self.assertEqual(p_conc["lote"], "lote1")
            self.assertEqual(p_conc["nivel"], 1)
            self.assertEqual(p_conc["situacao"], "disponível")
            self.assertEqual(p_conc["causa"], "temporizador")
            self.assertEqual(p_conc["estado"]["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

    # 1b. Construção válida completa com cristais lapidados
    async def test_01b_construcao_valida_completa_lapidados(self):
        await self.abrir_vila_com_saldo(0)
        server.vila["lapidados"] = 5
        j1 = await self.conectar_jogador("j1", "Bruno")

        with patch.object(server, "TEMPO_OBRA", 0.03):
            await server.solicitar_construcao(j1, {"modalidade": "lapidados"})

            # Estado imediato no início da obra: consome lapidados, preserva brutos
            self.assertEqual(server.vila["lapidados"], 0)
            self.assertEqual(server.vila["brutos"], 0)
            self.assertEqual(server.vila["trabalhadores"], 1)
            self.assertEqual(server.vila["lotes"]["lote1"], "lapidaria-1")
            self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "em construção")

            # Evento construcao.iniciada
            chamadas_ini = [c for c in self.emit.call_args_list if c.args[0] == "construcao.iniciada"]
            self.assertEqual(len(chamadas_ini), 1)
            p_ini = chamadas_ini[0].args[1]
            self.assertEqual(p_ini["solicitante"], "Bruno")
            self.assertEqual(p_ini["lapidaria_id"], "lapidaria-1")
            self.assertEqual(p_ini["lote"], "lote1")
            self.assertEqual(p_ini["custo"], 5)
            self.assertEqual(p_ini["modalidade"], "lapidados")
            self.assertEqual(p_ini["causa"], "construcao.solicitada")

            await asyncio.sleep(0.06)

            self.assertEqual(server.vila["trabalhadores"], 0)
            lap = server.vila["lapidarias"]["lapidaria-1"]
            self.assertEqual(lap["situacao"], "disponível")
            self.assertEqual(lap["nivel"], 1)

    # 2. Recusa quando solicitante não tem papel "jogador"
    async def test_02_recusa_solicitante_nao_jogador(self):
        m1 = await self.abrir_vila_com_saldo(5)

        # Mestre tenta construir
        await server.solicitar_construcao(m1)
        self.assertEqual(server.vila["brutos"], 5)
        self.assertEqual(server.vila["trabalhadores"], 0)

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].kwargs.get("to"), m1)
        self.assertIn("Apenas jogadores", chamadas[0].args[1]["motivo"])

        # SID inexistente / não conectado
        self.emit.reset_mock()
        await server.solicitar_construcao("fantasma")
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].kwargs.get("to"), "fantasma")

    # 3. Recusa quando fase != aberta
    async def test_03_recusa_fase_nao_aberta(self):
        j1 = await self.conectar_jogador("j1")
        server.vila["brutos"] = 10

        # Fase aguardando
        self.assertEqual(server.vila["fase"], "aguardando")
        await server.solicitar_construcao(j1)
        self.assertEqual(server.vila["brutos"], 10)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].kwargs.get("to"), j1)
        self.assertIn("aberta", chamadas[0].args[1]["motivo"])

        # Fase encerrada
        server.vila["fase"] = "encerrada"
        self.emit.reset_mock()
        await server.solicitar_construcao(j1)
        self.assertEqual(server.vila["brutos"], 10)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)

    # 4. Recusa por saldo insuficiente
    async def test_04_recusa_saldo_insuficiente(self):
        await self.abrir_vila_com_saldo(4)  # 4 < 5
        j1 = await self.conectar_jogador("j1")

        # Recusa para brutos com saldo 4
        await server.solicitar_construcao(j1, {"modalidade": "brutos"})
        self.assertEqual(server.vila["brutos"], 4)
        self.assertEqual(server.vila["trabalhadores"], 0)

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertIn("insuficientes", chamadas[0].args[1]["motivo"])

        # Recusa para lapidados com saldo 4
        self.emit.reset_mock()
        server.vila["lapidados"] = 4
        await server.solicitar_construcao(j1, {"modalidade": "lapidados"})
        self.assertEqual(server.vila["lapidados"], 4)
        self.assertEqual(server.vila["trabalhadores"], 0)

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertIn("insuficientes", chamadas[0].args[1]["motivo"])

    # 4b. Ausência de débito no recurso não escolhido
    async def test_04b_ausencia_de_debito_no_recurso_nao_escolhido(self):
        await self.abrir_vila_com_saldo(10)
        server.vila["lapidados"] = 10
        j1 = await self.conectar_jogador("j1")

        with patch.object(server, "TEMPO_OBRA", 10.0):
            # Constrói com brutos: apenas brutos são debitados
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})
            self.assertEqual(server.vila["brutos"], 5)
            self.assertEqual(server.vila["lapidados"], 10)

            # Constrói com lapidados: apenas lapidados são debitados
            await server.solicitar_construcao(j1, {"modalidade": "lapidados"})
            self.assertEqual(server.vila["brutos"], 5)
            self.assertEqual(server.vila["lapidados"], 5)

    # 4c. Recusa de modalidade inválida
    async def test_04c_recusa_modalidade_invalida(self):
        await self.abrir_vila_com_saldo(10)
        server.vila["lapidados"] = 10
        j1 = await self.conectar_jogador("j1")

        # Modalidade None / ausente
        await server.solicitar_construcao(j1, None)
        self.assertEqual(server.vila["brutos"], 10)
        self.assertEqual(server.vila["lapidados"], 10)
        self.assertEqual(server.vila["trabalhadores"], 0)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertIn("inválida", chamadas[0].args[1]["motivo"])

        # Modalidade desconhecida
        self.emit.reset_mock()
        await server.solicitar_construcao(j1, {"modalidade": "ouro"})
        self.assertEqual(server.vila["brutos"], 10)
        self.assertEqual(server.vila["lapidados"], 10)
        self.assertEqual(server.vila["trabalhadores"], 0)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertIn("inválida", chamadas[0].args[1]["motivo"])

        # Formato string direta (recusado pelo contrato exclusivo)
        self.emit.reset_mock()
        await server.solicitar_construcao(j1, "brutos")
        self.assertEqual(server.vila["brutos"], 10)
        self.assertEqual(server.vila["lapidados"], 10)
        self.assertEqual(server.vila["trabalhadores"], 0)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertIn("inválida", chamadas[0].args[1]["motivo"])

        # Formato com campo alternativo 'recurso' (recusado pelo contrato exclusivo)
        self.emit.reset_mock()
        await server.solicitar_construcao(j1, {"recurso": "brutos"})
        self.assertEqual(server.vila["brutos"], 10)
        self.assertEqual(server.vila["lapidados"], 10)
        self.assertEqual(server.vila["trabalhadores"], 0)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertIn("inválida", chamadas[0].args[1]["motivo"])

    # 5. Recusa por limite de trabalhadores atingido (2/2)
    async def test_05_recusa_limite_trabalhadores(self):
        await self.abrir_vila_com_saldo(20)
        j1 = await self.conectar_jogador("j1")

        with patch.object(server, "TEMPO_OBRA", 10.0):
            # Inicia 2 construções
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})
            self.assertEqual(server.vila["trabalhadores"], 2)

            self.emit.reset_mock()
            # Tenta terceira
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})
            self.assertEqual(server.vila["trabalhadores"], 2)
            self.assertEqual(server.vila["brutos"], 10)

            chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
            self.assertEqual(len(chamadas), 1)
            self.assertIn("trabalhadores", chamadas[0].args[1]["motivo"])

    # 6. Recusa por falta de lotes livres
    async def test_06_recusa_falta_de_lotes(self):
        await self.abrir_vila_com_saldo(10)
        j1 = await self.conectar_jogador("j1")

        # Ocupa todos os 6 lotes
        for lote in server.LOTES:
            server.vila["lotes"][lote] = "outra-lapidaria"

        await server.solicitar_construcao(j1, {"modalidade": "brutos"})
        self.assertEqual(server.vila["brutos"], 10)
        self.assertEqual(server.vila["trabalhadores"], 0)

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertIn("lotes", chamadas[0].args[1]["motivo"])

    # 7. Validação sequencial de concorrência sem gasto duplicado
    async def test_07_concorrencia_sequencial_sem_gasto_duplicado(self):
        await self.abrir_vila_com_saldo(5)  # saldo para apenas 1 obra
        j1 = await self.conectar_jogador("j1", "Jogador1")
        j2 = await self.conectar_jogador("j2", "Jogador2")

        with patch.object(server, "TEMPO_OBRA", 10.0):
            # Dispara duas solicitações quase simultâneas
            await asyncio.gather(
                server.solicitar_construcao(j1, {"modalidade": "brutos"}),
                server.solicitar_construcao(j2, {"modalidade": "brutos"}),
            )

        # Apenas 1 obra deve ter sido iniciada
        self.assertEqual(server.vila["brutos"], 0)
        self.assertEqual(server.vila["trabalhadores"], 1)
        self.assertEqual(len(server.vila["construcoes_ativas"]), 1)

        chamadas_ini = [c for c in self.emit.call_args_list if c.args[0] == "construcao.iniciada"]
        chamadas_rec = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas_ini), 1)
        self.assertEqual(len(chamadas_rec), 1)

    # 7b. Concorrência sequencial com cristais lapidados
    async def test_07b_concorrencia_sequencial_lapidados_sem_gasto_duplicado(self):
        await self.abrir_vila_com_saldo(0)
        server.vila["lapidados"] = 5
        j1 = await self.conectar_jogador("j1", "Jogador1")
        j2 = await self.conectar_jogador("j2", "Jogador2")

        with patch.object(server, "TEMPO_OBRA", 10.0):
            await asyncio.gather(
                server.solicitar_construcao(j1, {"modalidade": "lapidados"}),
                server.solicitar_construcao(j2, {"modalidade": "lapidados"}),
            )

        self.assertEqual(server.vila["lapidados"], 0)
        self.assertEqual(server.vila["brutos"], 0)
        self.assertEqual(server.vila["trabalhadores"], 1)

        chamadas_ini = [c for c in self.emit.call_args_list if c.args[0] == "construcao.iniciada"]
        chamadas_rec = [c for c in self.emit.call_args_list if c.args[0] == "construcao.recusada"]
        self.assertEqual(len(chamadas_ini), 1)
        self.assertEqual(len(chamadas_rec), 1)

    # 8. Construções simultâneas em lotes distintos
    async def test_08_construcoes_simultaneas_em_lotes_distintos(self):
        await self.abrir_vila_com_saldo(5)
        server.vila["lapidados"] = 5
        j1 = await self.conectar_jogador("j1")

        with patch.object(server, "TEMPO_OBRA", 10.0):
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})
            await server.solicitar_construcao(j1, {"modalidade": "lapidados"})

        self.assertEqual(server.vila["brutos"], 0)
        self.assertEqual(server.vila["lapidados"], 0)
        self.assertEqual(server.vila["trabalhadores"], 2)
        self.assertEqual(server.vila["lotes"]["lote1"], "lapidaria-1")
        self.assertEqual(server.vila["lotes"]["lote2"], "lapidaria-2")
        self.assertEqual(len(server.vila["construcoes_ativas"]), 2)

    # 9. Desconexão do jogador não interrompe a obra
    async def test_09_desconexao_nao_interrompe_obra(self):
        await self.abrir_vila_com_saldo(5)
        j1 = await self.conectar_jogador("j1")

        with patch.object(server, "TEMPO_OBRA", 0.03):
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})
            # Jogador desconecta durante a obra
            await server.disconnect(j1)

            await asyncio.sleep(0.06)

        # Lapidária concluiu normalmente
        self.assertEqual(server.vila["trabalhadores"], 0)
        self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")
        chamadas_conc = [c for c in self.emit.call_args_list if c.args[0] == "construcao.concluida"]
        self.assertEqual(len(chamadas_conc), 1)

    # 10. Conclusão pós-encerramento
    async def test_10_conclusao_pos_encerramento(self):
        m1 = await self.abrir_vila_com_saldo(5)
        j1 = await self.conectar_jogador("j1")

        with patch.object(server, "TEMPO_OBRA", 0.04):
            await server.solicitar_construcao(j1, {"modalidade": "brutos"})

            # Mestre encerra a temporada durante a obra
            await asyncio.sleep(0.01)
            await server.encerrar_vila(m1)
            self.assertEqual(server.vila["fase"], "encerrada")

            # Aguarda a obra concluir pós-encerramento
            await asyncio.sleep(0.05)

        self.assertEqual(server.vila["trabalhadores"], 0)
        lap = server.vila["lapidarias"]["lapidaria-1"]
        self.assertEqual(lap["situacao"], "disponível")
        # Na fase encerrada, a vaga não recebe timestamp para participar da FIFO
        self.assertIsNone(lap["vagas"][0]["disponivel_desde"])
        self.assertEqual(len(server.vila["construcoes_ativas"]), 0)

        chamadas_conc = [c for c in self.emit.call_args_list if c.args[0] == "construcao.concluida"]
        self.assertEqual(len(chamadas_conc), 1)


# ── Teste de integração real com Socket.IO ────────────────────────────
class ClienteEngineIO:
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

    def coletar_ate(self, condicao, limite=6.0):
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


class TestProtocoloSocketIOEtapa3(unittest.TestCase):
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

    def test_integracao_construcao_via_socketio(self):
        # Mestre conecta e abre a vila
        mestre = ClienteEngineIO(self.base).abrir()
        mestre.conectar({"nome": "Mestre1", "papel": "mestre"})
        mestre.coletar_ate(tem_evento("estado.sincronizado"))
        mestre.emitir("vila.abertura_solicitada")
        mestre.coletar_ate(tem_evento("vila.aberta"))

        # Jogador conecta
        jogador = ClienteEngineIO(self.base).abrir()
        jogador.conectar({"nome": "Jogador1", "papel": "jogador"})
        jogador.coletar_ate(tem_evento("estado.sincronizado"))

        # Aguarda 5 produções da mina (10 segundos nominais; coletamos até 5 produções)
        # Para acelerar o teste de integração sem alterar arquivos, apenas aguardamos a mina acumular
        # ou aguardamos acumular 5 cristais
        def tem_5_producoes(pacotes):
            prods = [e for e in ClienteEngineIO.eventos(pacotes) if e[0] == "mina.cristal_produzido"]
            return len(prods) >= 5

        jogador.coletar_ate(tem_5_producoes, limite=12.0)

        # Jogador solicita construção com cristais brutos
        jogador.emitir("construcao.solicitada", {"modalidade": "brutos"})
        jogador.coletar_ate(tem_evento("construcao.iniciada"), limite=3.0)

        eventos = ClienteEngineIO.eventos(jogador.pacotes)
        nomes = [e[0] for e in eventos]
        self.assertIn("construcao.iniciada", nomes)

        # Aguarda conclusão (3s da obra)
        jogador.coletar_ate(tem_evento("construcao.concluida"), limite=5.0)
        eventos = ClienteEngineIO.eventos(jogador.pacotes)
        nomes = [e[0] for e in eventos]
        self.assertIn("construcao.concluida", nomes)


if __name__ == "__main__":
    unittest.main()
