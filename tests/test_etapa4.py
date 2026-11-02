"""Testes de aceitação da Etapa 4 (processamento automático e FIFO das lapidárias).

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
from tests.test_etapa3 import ClienteEngineIO, tem_evento


class TestEtapa4EmProcesso(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._vila_original = copy.deepcopy(server.vila)
        server.jogadores.clear()
        server.mestre_sid = None
        server.tarefa_mina = None
        server._tarefa_dispatcher = None
        server._dispatcher_pendente = False
        server._vagas_coalescidas.clear()

        patcher = patch.object(server.sio, "emit", new_callable=AsyncMock)
        self.emit = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        if server.tarefa_mina and not server.tarefa_mina.done():
            server.tarefa_mina.cancel()
        server.tarefa_mina = None

        if server._tarefa_dispatcher and not server._tarefa_dispatcher.done():
            server._tarefa_dispatcher.cancel()
        server._tarefa_dispatcher = None
        server._dispatcher_pendente = False
        server._vagas_coalescidas.clear()

        server.vila.clear()
        server.vila.update(self._vila_original)
        server.jogadores.clear()
        server.mestre_sid = None

    async def conectar_mestre(self, sid="m1", nome="Mestre"):
        await server.connect(sid, {}, {"nome": nome, "papel": "mestre"})
        return sid

    async def abrir_vila_com_lapidaria(self, lote="lote1", lid="lapidaria-1", nivel=1, brutos=1):
        m1 = await self.conectar_mestre()
        with patch.object(server, "INTERVALO_MINA", 100.0):
            await server.abrir_vila(m1)

        server.vila["brutos"] = brutos
        server.vila["lotes"][lote] = lid
        server.vila["lapidarias"][lid] = {
            "id": lid,
            "lote": lote,
            "nivel": nivel,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": i + 1,
                    "ocupada": False,
                    "inicio_monotonic": None,
                    "disponivel_desde": 100.0,
                    "ciclo_id": 0,
                }
                for i in range(nivel)
            ],
        }
        return m1

    # 1. Início automático de lapidação quando há bruto e vaga livre
    async def test_01_inicio_automatico_lapidacao(self):
        await self.abrir_vila_com_lapidaria("lote1", "lapidaria-1", nivel=1, brutos=1)

        await server.dispatcher_fifo()

        self.assertEqual(server.vila["brutos"], 0)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        self.assertTrue(vaga["ocupada"])
        self.assertEqual(vaga["ciclo_id"], 1)
        self.assertIsNotNone(vaga["inicio_monotonic"])
        self.assertIsNone(vaga["disponivel_desde"])

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.processamento_iniciado"]
        self.assertEqual(len(chamadas), 1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["lapidaria_id"], "lapidaria-1")
        self.assertEqual(payload["vaga"], 1)
        self.assertEqual(payload["causa"], "temporizador")
        self.assertIn("estado", payload)
        self.assertEqual(payload["estado"]["brutos"], 0)

    # 2. Conclusão da lapidação credita lapidado e desocupa vaga
    async def test_02_conclusao_lapidacao_credita_e_desocupa(self):
        await self.abrir_vila_com_lapidaria("lote1", "lapidaria-1", nivel=1, brutos=0)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga["ocupada"] = True
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["ciclo_id"] = 1
        vaga["disponivel_desde"] = None

        with patch.object(server, "TEMPO_LAPIDACAO", 0.02):
            await server.lapidacao("lapidaria-1", 1, 1)

        self.assertEqual(server.vila["lapidados"], 1)
        self.assertFalse(vaga["ocupada"])
        self.assertIsNone(vaga["inicio_monotonic"])
        self.assertIsNotNone(vaga["disponivel_desde"])

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.cristal_lapidado"]
        self.assertEqual(len(chamadas), 1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["lapidaria_id"], "lapidaria-1")
        self.assertEqual(payload["vaga"], 1)
        self.assertEqual(payload["causa"], "temporizador")
        self.assertEqual(payload["estado"]["lapidados"], 1)

    # 3. Auto-renovação: inicia novo ciclo imediatamente se houver bruto em estoque
    async def test_03_auto_renovacao_continua_se_houver_bruto(self):
        await self.abrir_vila_com_lapidaria("lote1", "lapidaria-1", nivel=1, brutos=1)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga["ocupada"] = True
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["ciclo_id"] = 1
        vaga["disponivel_desde"] = None

        with patch.object(server, "TEMPO_LAPIDACAO", 0.04):
            await server.lapidacao("lapidaria-1", 1, 1)
            # Permite execução do dispatcher agendado sem dar tempo do segundo ciclo de 0.04s concluir
            await asyncio.sleep(0.01)

        # 1 produzido, e o bruto disponível foi consumido no novo ciclo
        self.assertEqual(server.vila["lapidados"], 1)
        self.assertEqual(server.vila["brutos"], 0)
        self.assertTrue(vaga["ocupada"])
        self.assertEqual(vaga["ciclo_id"], 2)

        chamadas_ini = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.processamento_iniciado"]
        self.assertEqual(len(chamadas_ini), 1)

    # 4. Vaga permanece ociosa se não houver bruto disponível após conclusão
    async def test_04_vaga_ociosa_quando_sem_bruto(self):
        await self.abrir_vila_com_lapidaria("lote1", "lapidaria-1", nivel=1, brutos=0)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga["ocupada"] = True
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["ciclo_id"] = 1
        vaga["disponivel_desde"] = None

        with patch.object(server, "TEMPO_LAPIDACAO", 0.02):
            await server.lapidacao("lapidaria-1", 1, 1)
            await asyncio.sleep(0.03)

        self.assertEqual(server.vila["lapidados"], 1)
        self.assertFalse(vaga["ocupada"])
        self.assertIsNotNone(vaga["disponivel_desde"])

        chamadas_ini = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.processamento_iniciado"]
        self.assertEqual(len(chamadas_ini), 0)

    # 5. Independência operacional: vagas de lapidárias distintas processam em paralelo
    async def test_05_independencia_entre_lapidarias(self):
        await self.abrir_vila_com_lapidaria("lote1", "lapidaria-1", nivel=1, brutos=2)
        # Segunda lapidária
        server.vila["lotes"]["lote2"] = "lapidaria-2"
        server.vila["lapidarias"]["lapidaria-2"] = {
            "id": "lapidaria-2",
            "lote": "lote2",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": False,
                    "inicio_monotonic": None,
                    "disponivel_desde": 105.0,
                    "ciclo_id": 0,
                }
            ],
        }

        await server.dispatcher_fifo()

        self.assertEqual(server.vila["brutos"], 0)
        self.assertTrue(server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]["ocupada"])
        self.assertTrue(server.vila["lapidarias"]["lapidaria-2"]["vagas"][0]["ocupada"])

    # 6. Prioridade FIFO por timestamp mais antigo
    async def test_06_prioridade_fifo_por_tempo(self):
        # lapidaria-1 no lote2 ficou disponível em t=10.0
        # lapidaria-2 no lote1 ficou disponível em t=20.0
        await self.abrir_vila_com_lapidaria("lote2", "lapidaria-1", nivel=1, brutos=1)
        server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]["disponivel_desde"] = 10.0

        server.vila["lotes"]["lote1"] = "lapidaria-2"
        server.vila["lapidarias"]["lapidaria-2"] = {
            "id": "lapidaria-2",
            "lote": "lote1",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": False,
                    "inicio_monotonic": None,
                    "disponivel_desde": 20.0,
                    "ciclo_id": 0,
                }
            ],
        }

        await server.dispatcher_fifo()

        self.assertEqual(server.vila["brutos"], 0)
        # lapidaria-1 tem timestamp mais antigo (10.0 < 20.0), então ganha mesmo estando no lote2
        self.assertTrue(server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]["ocupada"])
        self.assertFalse(server.vila["lapidarias"]["lapidaria-2"]["vagas"][0]["ocupada"])

    # 7. Desempate agrupado (coalescing) por lote e vaga com múltiplas conclusões simultâneas
    async def test_07_desempate_simultaneo_coalescing_lote_e_vaga(self):
        m1 = await self.conectar_mestre()
        with patch.object(server, "INTERVALO_MINA", 100.0):
            await server.abrir_vila(m1)

        # Configura duas lapidárias: lapidaria-1 no lote2 e lapidaria-2 no lote1
        server.vila["lotes"]["lote2"] = "lapidaria-1"
        server.vila["lapidarias"]["lapidaria-1"] = {
            "id": "lapidaria-1",
            "lote": "lote2",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": True,
                    "inicio_monotonic": 100.0,
                    "disponivel_desde": None,
                    "ciclo_id": 1,
                }
            ],
        }

        server.vila["lotes"]["lote1"] = "lapidaria-2"
        server.vila["lapidarias"]["lapidaria-2"] = {
            "id": "lapidaria-2",
            "lote": "lote1",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": True,
                    "inicio_monotonic": 100.0,
                    "disponivel_desde": None,
                    "ciclo_id": 1,
                }
            ],
        }

        # Há apenas 1 cristal bruto para 2 vagas que concluem simultaneamente
        server.vila["brutos"] = 1

        # Ambas tarefas de lapidação concluem no mesmo instante
        with patch.object(server, "TEMPO_LAPIDACAO", 0.04):
            # Inicia corrotinas simultaneamente
            t1 = server.sio.start_background_task(server.lapidacao, "lapidaria-1", 1, 1)
            t2 = server.sio.start_background_task(server.lapidacao, "lapidaria-2", 1, 1)

            # Timeout diagnóstico de 1.0s para evitar travamento indefinido
            await asyncio.wait_for(asyncio.gather(t1, t2), timeout=1.0)
            # Permite execução do dispatcher agrupado sem que a nova lapidação (0.04s) conclua
            await asyncio.sleep(0.01)

        # Ambas concluíram seu primeiro ciclo (+2 lapidados)
        self.assertEqual(server.vila["lapidados"], 2)
        # O único bruto disponível foi alocado
        self.assertEqual(server.vila["brutos"], 0)

        # Desempate determinístico: lote1 (lapidaria-2) deve ganhar sobre lote2 (lapidaria-1)
        vaga_lote1 = server.vila["lapidarias"]["lapidaria-2"]["vagas"][0]
        vaga_lote2 = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]

        self.assertTrue(vaga_lote1["ocupada"], "A vaga do lote1 deveria ter sido alocada pelo desempate.")
        self.assertFalse(vaga_lote2["ocupada"], "A vaga do lote2 deveria ter ficado livre pela falta de estoque.")

        # Verificação explícita da ordem estrita dos eventos:
        # Todos os eventos de conclusão (cristal_lapidado) devem anteceder o início de novo processamento
        nomes_eventos = [
            c.args[0] for c in self.emit.call_args_list
            if c.args[0] in ("lapidaria.cristal_lapidado", "lapidaria.processamento_iniciado")
        ]
        self.assertEqual(len(nomes_eventos), 3)
        self.assertEqual(nomes_eventos[0], "lapidaria.cristal_lapidado")
        self.assertEqual(nomes_eventos[1], "lapidaria.cristal_lapidado")
        self.assertEqual(nomes_eventos[2], "lapidaria.processamento_iniciado")

        # Desempate complementar por vaga: vaga 1 antes de vaga 2 na mesma lapidária
        server.vila["lapidarias"]["lapidaria-1"]["vagas"] = [
            {"numero": 1, "ocupada": False, "disponivel_desde": 200.0, "ciclo_id": 0, "inicio_monotonic": None},
            {"numero": 2, "ocupada": False, "disponivel_desde": 200.0, "ciclo_id": 0, "inicio_monotonic": None},
        ]
        server.vila["brutos"] = 1
        await server.dispatcher_fifo()
        self.assertTrue(server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]["ocupada"])
        self.assertFalse(server.vila["lapidarias"]["lapidaria-1"]["vagas"][1]["ocupada"])

    # 7b. Garantia de ordem de eventos mesmo com latência na emissão de rede
    async def test_07b_ordem_estrita_eventos_com_latencia_de_emissao(self):
        m1 = await self.conectar_mestre()
        with patch.object(server, "INTERVALO_MINA", 100.0):
            await server.abrir_vila(m1)

        server.vila["lotes"]["lote1"] = "lapidaria-1"
        server.vila["lapidarias"]["lapidaria-1"] = {
            "id": "lapidaria-1",
            "lote": "lote1",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": True,
                    "inicio_monotonic": 100.0,
                    "disponivel_desde": None,
                    "ciclo_id": 1,
                }
            ],
        }
        server.vila["brutos"] = 1

        ordem_recebida = []

        async def emit_com_latencia(evento, payload=None, **kwargs):
            if evento == "lapidaria.cristal_lapidado":
                # Simula latência no envio do evento de conclusão
                await asyncio.sleep(0.03)
            ordem_recebida.append(evento)

        self.emit.side_effect = emit_com_latencia

        with patch.object(server, "TEMPO_LAPIDACAO", 0.02):
            t = server.sio.start_background_task(server.lapidacao, "lapidaria-1", 1, 1)
            await asyncio.wait_for(t, timeout=1.0)
            await asyncio.sleep(0.01)

        self.assertIn("lapidaria.cristal_lapidado", ordem_recebida)
        self.assertIn("lapidaria.processamento_iniciado", ordem_recebida)
        idx_conclusao = ordem_recebida.index("lapidaria.cristal_lapidado")
        idx_inicio = ordem_recebida.index("lapidaria.processamento_iniciado")
        self.assertLess(
            idx_conclusao,
            idx_inicio,
            f"O evento de conclusão deve anteceder o de início. Ordem obtida: {ordem_recebida}",
        )

    # 8. Encerramento da vila com lapidação ativa: estorno de brutos e invalidação de ciclo
    async def test_08_encerramento_estorna_bruto_e_invalida_ciclo(self):
        m1 = await self.abrir_vila_com_lapidaria("lote1", "lapidaria-1", nivel=1, brutos=0)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga["ocupada"] = True
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["ciclo_id"] = 1
        vaga["disponivel_desde"] = None

        tarefa_lap = None
        with patch.object(server, "TEMPO_LAPIDACAO", 0.05):
            tarefa_lap = server.sio.start_background_task(server.lapidacao, "lapidaria-1", 1, 1)

            # Cede o laço brevemente para a tarefa entrar no sleep
            await asyncio.sleep(0.01)

            # Mestre encerra a vila durante a lapidação
            await server.encerrar_vila(m1)

            # 1. Fase encerrada
            self.assertEqual(server.vila["fase"], "encerrada")

            # 2. Estorno imediato de cristais brutos
            self.assertEqual(server.vila["brutos"], 1)

            # 3. Vaga desocupada e ciclo invalidado
            self.assertFalse(vaga["ocupada"])
            self.assertIsNone(vaga["inicio_monotonic"])
            self.assertEqual(vaga["ciclo_id"], 2)
            self.assertIsNone(vaga["disponivel_desde"])

            # 4. Aguarda a tarefa acordar
            await tarefa_lap
            await asyncio.sleep(0.02)

            # 5. NENHUM cristal lapidado deve ter sido creditado
            self.assertEqual(server.vila["lapidados"], 0)

            # 6. Evento lapidaria.cristal_lapidado NÃO deve ter sido emitido
            chamadas_lap = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.cristal_lapidado"]
            self.assertEqual(len(chamadas_lap), 0)

    # 9. Lapidária em construção não processa cristais
    async def test_09_lapidaria_em_construcao_nao_processa(self):
        m1 = await self.conectar_mestre()
        with patch.object(server, "INTERVALO_MINA", 100.0):
            await server.abrir_vila(m1)

        # Lapidária ainda em construção
        server.vila["brutos"] = 3
        server.vila["lotes"]["lote1"] = "lapidaria-1"
        server.vila["lapidarias"]["lapidaria-1"] = {
            "id": "lapidaria-1",
            "lote": "lote1",
            "nivel": 1,
            "situacao": "em construção",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": False,
                    "inicio_monotonic": None,
                    "disponivel_desde": None,
                    "ciclo_id": 0,
                }
            ],
        }

        await server.dispatcher_fifo()

        # Nada deve ser consumido
        self.assertEqual(server.vila["brutos"], 3)
        self.assertFalse(server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]["ocupada"])

        chamadas_ini = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.processamento_iniciado"]
        self.assertEqual(len(chamadas_ini), 0)

    # 10. Encerramento durante emissão do dispatcher aborta alocações restantes e ciclos inválidos
    async def test_10_encerramento_durante_emissao_aborta_alocacoes_e_ciclos(self):
        m1 = await self.conectar_mestre()
        with patch.object(server, "INTERVALO_MINA", 100.0):
            await server.abrir_vila(m1)

        # Configura duas lapidárias livres e 2 cristais brutos
        server.vila["brutos"] = 2
        server.vila["lotes"]["lote1"] = "lapidaria-1"
        server.vila["lapidarias"]["lapidaria-1"] = {
            "id": "lapidaria-1",
            "lote": "lote1",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": False,
                    "inicio_monotonic": None,
                    "disponivel_desde": 100.0,
                    "ciclo_id": 0,
                }
            ],
        }
        server.vila["lotes"]["lote2"] = "lapidaria-2"
        server.vila["lapidarias"]["lapidaria-2"] = {
            "id": "lapidaria-2",
            "lote": "lote2",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [
                {
                    "numero": 1,
                    "ocupada": False,
                    "inicio_monotonic": None,
                    "disponivel_desde": 105.0,
                    "ciclo_id": 0,
                }
            ],
        }

        eventos_iniciados = []
        tarefas_lapidacao = []

        orig_start = server.sio.start_background_task

        def mock_start(target, *args, **kwargs):
            if target == server.lapidacao:
                tarefas_lapidacao.append(args)
            return orig_start(target, *args, **kwargs)

        with patch.object(server.sio, "start_background_task", side_effect=mock_start):
            async def emit_com_encerramento(evento, payload=None, **kwargs):
                if evento == "lapidaria.processamento_iniciado":
                    eventos_iniciados.append(payload.get("lapidaria_id"))
                    if payload.get("lapidaria_id") == "lapidaria-1":
                        # Simula latência na rede e encerramento provocado durante a emissão
                        await asyncio.sleep(0.02)
                        await server.encerrar_vila(m1)

            self.emit.side_effect = emit_com_encerramento

            server.agendar_dispatcher_fifo()
            await asyncio.sleep(0.06)

        # 1. A fase deve ser encerrada
        self.assertEqual(server.vila["fase"], "encerrada")

        # 2. Apenas a primeira lapidária emitiu início (lapidaria-2 foi abortada)
        self.assertEqual(eventos_iniciados, ["lapidaria-1"])

        # 3. Nenhuma tarefa de lapidação inválida foi iniciada
        self.assertEqual(tarefas_lapidacao, [])

        # 4. Ambos os cristais foram devidamente estornados ao estoque
        self.assertEqual(server.vila["brutos"], 2)


class TestProtocoloSocketIOEtapa4(unittest.TestCase):
    """Teste de integração real via Socket.IO para processamento e eventos."""

    @classmethod
    def setUpClass(cls):
        s = socket.socket()
        s.bind(("", 0))
        cls.porta = s.getsockname()[1]
        s.close()

        cls.proc = subprocess.Popen(
            [
                str(RAIZ / ".venv" / "bin" / "python"),
                "-m",
                "uvicorn",
                "server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.porta),
                "--log-level",
                "warning",
            ],
            cwd=str(RAIZ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        limite = time.time() + 10.0
        pronto = False
        while time.time() < limite:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cls.porta}/", timeout=0.5):
                    pronto = True
                    break
            except (urllib.error.URLError, ConnectionResetError):
                time.sleep(0.1)

        if not pronto:
            cls.proc.terminate()
            stdout, stderr = cls.proc.communicate()
            raise RuntimeError(f"Servidor não subiu na porta {cls.porta}:\n{stderr.decode('utf-8', errors='replace')}")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.wait(timeout=3.0)

    def test_integracao_processamento_via_socketio(self):
        mestre = ClienteEngineIO(f"http://127.0.0.1:{self.porta}").abrir()
        mestre.conectar({"nome": "Mestre1", "papel": "mestre"})
        mestre.coletar_ate(tem_evento("estado.sincronizado"))
        mestre.emitir("vila.abertura_solicitada")
        mestre.coletar_ate(tem_evento("vila.aberta"))

        jogador = ClienteEngineIO(f"http://127.0.0.1:{self.porta}").abrir()
        jogador.conectar({"nome": "Jogador1", "papel": "jogador"})
        jogador.coletar_ate(tem_evento("estado.sincronizado"))

        def tem_5_producoes(pacotes):
            prods = [e for e in ClienteEngineIO.eventos(pacotes) if e[0] == "mina.cristal_produzido"]
            return len(prods) >= 5

        jogador.coletar_ate(tem_5_producoes, limite=12.0)

        # Solicita construção de lapidária com cristais brutos
        jogador.emitir("construcao.solicitada", {"modalidade": "brutos"})
        jogador.coletar_ate(tem_evento("construcao.concluida"), limite=6.0)

        # Aguarda o próximo cristal da mina para disparar a lapidação e o evento lapidaria.processamento_iniciado
        jogador.coletar_ate(tem_evento("lapidaria.processamento_iniciado"), limite=5.0)

        eventos = ClienteEngineIO.eventos(jogador.pacotes)
        nomes = [e[0] for e in eventos]
        self.assertIn("lapidaria.processamento_iniciado", nomes)

        mestre.emitir("vila.encerramento_solicitado")
        mestre.coletar_ate(tem_evento("vila.encerrada"), limite=3.0)


if __name__ == "__main__":
    unittest.main()
