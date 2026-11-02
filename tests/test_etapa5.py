"""Testes de aceitação da Etapa 5 (melhorias de nível das lapidárias).

Executar na raiz do projeto:
    .venv/bin/python -m unittest discover -s tests -v
"""
import asyncio
import copy
import json
import os
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


class TestEtapa5EmProcesso(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._vila_original = copy.deepcopy(server.vila)
        server.jogadores.clear()
        server.mestre_sid = None
        server.tarefa_mina = None
        server._tarefa_dispatcher = None
        server._dispatcher_pendente = False
        server._vagas_coalescidas.clear()
        server._barreiras_emissao.clear()

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
        server._barreiras_emissao.clear()

        server.vila.clear()
        server.vila.update(self._vila_original)
        server.jogadores.clear()
        server.mestre_sid = None

    async def conectar_mestre(self, sid="m1", nome="Mestre"):
        await server.connect(sid, {}, {"nome": nome, "papel": "mestre"})
        return sid

    async def conectar_jogador(self, sid="j1", nome="Jogador1"):
        await server.connect(sid, {}, {"nome": nome, "papel": "jogador"})
        return sid

    async def preparar_vila_aberta_com_lapidaria(self, lote="lote1", lid="lapidaria-1", nivel=1, lapidados=0, brutos=0):
        m1 = await self.conectar_mestre()
        j1 = await self.conectar_jogador()
        with patch.object(server, "INTERVALO_MINA", 100.0):
            await server.abrir_vila(m1)

        server.vila["brutos"] = brutos
        server.vila["lapidados"] = lapidados
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
        return m1, j1

    # 1. Solicitação de melhoria do nível 1 para 2, com débito correto (10 lapidados)
    async def test_01_solicitar_melhoria_n1_para_n2_debito_e_transicao(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10)

        with patch.object(server, "TEMPO_OBRA", 0.05):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-01"})

        self.assertEqual(server.vila["lapidados"], 0)
        lap = server.vila["lapidarias"]["lapidaria-1"]
        self.assertEqual(lap["situacao"], "em melhoria")
        self.assertEqual(len(server.vila["melhorias_ativas"]), 1)
        self.assertEqual(server.vila["melhorias_ativas"][0]["lid"], "lapidaria-1")

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.iniciada"]
        self.assertEqual(len(chamadas), 1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["solicitacao_id"], "req-01")
        self.assertEqual(payload["lapidaria_id"], "lapidaria-1")
        self.assertEqual(payload["nivel_atual"], 1)
        self.assertEqual(payload["novo_nivel"], 2)
        self.assertEqual(payload["custo"], 10)
        self.assertEqual(payload["causa"], "melhoria.solicitada")

    # 2. Solicitação de melhoria do nível 2 para 3, com débito correto (15 lapidados)
    async def test_02_solicitar_melhoria_n2_para_n3_debito_e_transicao(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=2, lapidados=20)

        with patch.object(server, "TEMPO_OBRA", 0.05):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-02"})

        self.assertEqual(server.vila["lapidados"], 5)  # 20 - 15 = 5
        lap = server.vila["lapidarias"]["lapidaria-1"]
        self.assertEqual(lap["situacao"], "em melhoria")

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.iniciada"]
        self.assertEqual(len(chamadas), 1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["solicitacao_id"], "req-02")
        self.assertEqual(payload["nivel_atual"], 2)
        self.assertEqual(payload["novo_nivel"], 3)
        self.assertEqual(payload["custo"], 15)

    # 3. Recusa de melhoria no nível máximo (nível 3)
    async def test_03_recusa_nivel_maximo(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=3, lapidados=50)

        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-03"})

        self.assertEqual(server.vila["lapidados"], 50)
        lap = server.vila["lapidarias"]["lapidaria-1"]
        self.assertEqual(lap["situacao"], "disponível")
        self.assertEqual(lap["nivel"], 3)

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].args[1]["solicitacao_id"], "req-03")
        self.assertIn("nível máximo", chamadas[0].args[1]["motivo"].lower())

    # 4. Recusa por saldo insuficiente
    async def test_04_recusa_saldo_insuficiente(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=9)

        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-04a"})

        self.assertEqual(server.vila["lapidados"], 9)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].args[1]["solicitacao_id"], "req-04a")
        self.assertIn("insuficientes", chamadas[0].args[1]["motivo"].lower())

        # Teste para nível 2 com 14 lapidados
        self.emit.reset_mock()
        server.vila["lapidarias"]["lapidaria-1"]["nivel"] = 2
        server.vila["lapidados"] = 14
        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-04b"})
        self.assertEqual(server.vila["lapidados"], 14)
        chamadas2 = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas2), 1)
        self.assertEqual(chamadas2[0].args[1]["solicitacao_id"], "req-04b")

    # 5. Recusa de solicitante inválido (Mestre ou não-jogador)
    async def test_05_recusa_solicitante_invalido(self):
        m1, _ = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10)

        # Mestre tentando solicitar
        await server.solicitar_melhoria(m1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-05a"})
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].args[1]["solicitacao_id"], "req-05a")
        self.assertIn("apenas jogadores", chamadas[0].args[1]["motivo"].lower())

        # SID inexistente
        self.emit.reset_mock()
        await server.solicitar_melhoria("fantasma", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-05b"})
        chamadas_fantasma = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas_fantasma), 1)
        self.assertEqual(chamadas_fantasma[0].args[1]["solicitacao_id"], "req-05b")

    # 6. Recusa nas fases aguardando e encerrada
    async def test_06_recusa_fases_aguardando_e_encerrada(self):
        j1 = await self.conectar_jogador()
        server.vila["fase"] = "aguardando"
        server.vila["lapidados"] = 20
        server.vila["lapidarias"]["lapidaria-1"] = {
            "id": "lapidaria-1",
            "lote": "lote1",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [server._nova_vaga(1)],
        }

        # Na fase aguardando
        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-06a"})
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].args[1]["solicitacao_id"], "req-06a")
        self.assertIn("aberta", chamadas[0].args[1]["motivo"].lower())

        # Na fase encerrada
        self.emit.reset_mock()
        server.vila["fase"] = "encerrada"
        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-06b"})
        chamadas2 = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas2), 1)
        self.assertEqual(chamadas2[0].args[1]["solicitacao_id"], "req-06b")

    # 7. Recusa para lapidaria inexistente, em construção ou em melhoria
    async def test_07_recusa_lapidaria_inexistente_ou_ocupada(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=20)

        # Inexistente
        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-999", "solicitacao_id": "req-07a"})
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].args[1]["solicitacao_id"], "req-07a")
        self.assertIn("não encontrada", chamadas[0].args[1]["motivo"].lower())

        # Em construção
        self.emit.reset_mock()
        server.vila["lapidarias"]["lapidaria-1"]["situacao"] = "em construção"
        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-07b"})
        chamadas2 = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas2), 1)
        self.assertEqual(chamadas2[0].args[1]["solicitacao_id"], "req-07b")
        self.assertIn("não está disponível", chamadas2[0].args[1]["motivo"].lower())

        # Em melhoria
        self.emit.reset_mock()
        server.vila["lapidarias"]["lapidaria-1"]["situacao"] = "em melhoria"
        await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-07c"})
        chamadas3 = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.recusada"]
        self.assertEqual(len(chamadas3), 1)
        self.assertEqual(chamadas3[0].args[1]["solicitacao_id"], "req-07c")

    # 8. Confirmação de que melhorias não ocupam trabalhadores
    async def test_08_melhoria_nao_ocupa_trabalhadores(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10)
        server.vila["trabalhadores"] = 0

        with patch.object(server, "TEMPO_OBRA", 0.02):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-08"})
            self.assertEqual(server.vila["trabalhadores"], 0)
            await asyncio.sleep(0.04)

        self.assertEqual(server.vila["trabalhadores"], 0)
        self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

    # 9. Interrupção dos processamentos ativos e estorno integral dos cristais brutos
    async def test_09_interrupcao_de_lapidacao_com_estorno_de_brutos(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=2, lapidados=15, brutos=0)
        lap = server.vila["lapidarias"]["lapidaria-1"]
        # Ambas as vagas em processamento
        vaga1 = lap["vagas"][0]
        vaga1["ocupada"] = True
        vaga1["inicio_monotonic"] = time.monotonic()
        vaga1["ciclo_id"] = 5
        vaga1["disponivel_desde"] = None

        vaga2 = lap["vagas"][1]
        vaga2["ocupada"] = True
        vaga2["inicio_monotonic"] = time.monotonic()
        vaga2["ciclo_id"] = 7
        vaga2["disponivel_desde"] = None

        with patch.object(server, "TEMPO_OBRA", 0.05):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-09"})

        # Ambos os brutos foram devolvidos ao estoque global
        self.assertEqual(server.vila["brutos"], 2)
        # Ambas as vagas foram desocupadas e seus ciclo_id incrementados
        self.assertFalse(vaga1["ocupada"])
        self.assertIsNone(vaga1["inicio_monotonic"])
        self.assertEqual(vaga1["ciclo_id"], 6)

        self.assertFalse(vaga2["ocupada"])
        self.assertIsNone(vaga2["inicio_monotonic"])
        self.assertEqual(vaga2["ciclo_id"], 8)

    # 10. Garantia de que ciclos invalidados não creditam cristais lapidados
    async def test_10_ciclos_invalidados_nao_creditam_lapidados(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10, brutos=0)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga["ocupada"] = True
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["ciclo_id"] = 10

        with patch.object(server, "TEMPO_OBRA", 0.05):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-10"})

        # Simula o término do temporizador de lapidação anterior (com ciclo_id antigo = 10)
        with patch.object(server, "TEMPO_LAPIDACAO", 0.01):
            await server.lapidacao("lapidaria-1", 1, 10)

        # Não deve creditar cristal lapidado
        self.assertEqual(server.vila["lapidados"], 0)
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.cristal_lapidado"]
        self.assertEqual(len(chamadas), 0)

    # 11. Redistribuição dos cristais estornados às demais lapidárias pelo FIFO global
    async def test_11_redistribuicao_brutos_estornados_via_fifo(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(lote="lote1", lid="lapidaria-1", nivel=1, lapidados=10, brutos=0)

        # Adiciona lapidaria-2 no lote 2, disponível e aguardando bruto
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
                    "disponivel_desde": 50.0,
                    "ciclo_id": 0,
                }
            ],
        }

        # Lapidaria-1 está processando 1 bruto
        vaga1 = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga1["ocupada"] = True
        vaga1["inicio_monotonic"] = time.monotonic()
        vaga1["ciclo_id"] = 1
        vaga1["disponivel_desde"] = None

        with patch.object(server, "TEMPO_OBRA", 0.05):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-11"})

        # Aguarda a tarefa do dispatcher distribuir o cristal estornado
        await asyncio.sleep(0.02)

        # O cristal bruto foi consumido pela lapidaria-2
        self.assertEqual(server.vila["brutos"], 0)
        vaga2 = server.vila["lapidarias"]["lapidaria-2"]["vagas"][0]
        self.assertTrue(vaga2["ocupada"])
        self.assertEqual(vaga2["ciclo_id"], 1)

        # Evento de processamento iniciado foi emitido para a lapidaria-2
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "lapidaria.processamento_iniciado"]
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].args[1]["lapidaria_id"], "lapidaria-2")

    # 12. Expansão correta das vagas ao concluir uma melhoria
    async def test_12_expansao_correta_das_vagas_ao_concluir_melhoria(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10)

        with patch.object(server, "TEMPO_OBRA", 0.02):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-12"})
            await asyncio.sleep(0.04)

        lap = server.vila["lapidarias"]["lapidaria-1"]
        self.assertEqual(lap["nivel"], 2)
        self.assertEqual(lap["situacao"], "disponível")
        self.assertEqual(len(lap["vagas"]), 2)
        self.assertEqual(lap["vagas"][0]["numero"], 1)
        self.assertEqual(lap["vagas"][1]["numero"], 2)
        self.assertIsNotNone(lap["vagas"][0]["disponivel_desde"])
        self.assertIsNotNone(lap["vagas"][1]["disponivel_desde"])
        self.assertEqual(lap["vagas"][0]["disponivel_desde"], lap["vagas"][1]["disponivel_desde"])

        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.concluida"]
        self.assertEqual(len(chamadas), 1)
        payload = chamadas[0].args[1]
        self.assertEqual(payload["nivel"], 2)
        self.assertEqual(payload["situacao"], "disponível")

    # 13. Ordem estrita entre melhoria.concluida e os processamentos iniciados em consequência dela
    async def test_13_ordem_estrita_entre_melhoria_concluida_e_processamento_iniciado(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10, brutos=2)

        ordem_eventos = []

        async def emit_com_latencia(evento, payload, to=None):
            if evento == "melhoria.concluida":
                await asyncio.sleep(0.03)
            ordem_eventos.append(evento)

        self.emit.side_effect = emit_com_latencia

        with patch.object(server, "TEMPO_OBRA", 0.02):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-13"})
            await asyncio.sleep(0.08)

        self.assertIn("melhoria.concluida", ordem_eventos)
        self.assertIn("lapidaria.processamento_iniciado", ordem_eventos)

        idx_concluida = ordem_eventos.index("melhoria.concluida")
        primeiro_inicio = ordem_eventos.index("lapidaria.processamento_iniciado")
        self.assertLess(
            idx_concluida,
            primeiro_inicio,
            f"'melhoria.concluida' ({idx_concluida}) deve preceder 'lapidaria.processamento_iniciado' ({primeiro_inicio}). Ordem: {ordem_eventos}",
        )

    # 14. Encerramento durante uma melhoria, garantindo conclusão estrutural sem retomada de processamento
    async def test_14_encerramento_durante_melhoria_conclui_sem_processar(self):
        m1, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10, brutos=5)

        with patch.object(server, "TEMPO_OBRA", 0.05):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-14"})

            # Encerra a vila enquanto a obra de melhoria está em andamento
            await asyncio.sleep(0.01)
            await server.encerrar_vila(m1)

            # Aguarda a obra de melhoria concluir
            await asyncio.sleep(0.06)

        lap = server.vila["lapidarias"]["lapidaria-1"]
        # Conclusão estrutural realizada com sucesso
        self.assertEqual(lap["nivel"], 2)
        self.assertEqual(lap["situacao"], "disponível")
        self.assertEqual(len(lap["vagas"]), 2)
        # Nenhuma vaga deve receber timestamp de disponibilidade
        self.assertIsNone(lap["vagas"][0]["disponivel_desde"])
        self.assertIsNone(lap["vagas"][1]["disponivel_desde"])
        # Nenhuma vaga deve iniciar processamento após encerramento
        self.assertFalse(lap["vagas"][0]["ocupada"])
        self.assertFalse(lap["vagas"][1]["ocupada"])
        self.assertEqual(server.vila["brutos"], 5)

        # melhoria.concluida deve ter sido emitida
        chamadas = [c for c in self.emit.call_args_list if c.args[0] == "melhoria.concluida"]
        self.assertEqual(len(chamadas), 1)

    # 15. Concorrência entre conclusão de lapidação e solicitação de melhoria:
    # Caso A — Conclusão da lapidação processada primeiro
    async def test_15a_concorrencia_conclusao_lapidacao_processada_primeiro(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=9, brutos=0)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga["ocupada"] = True
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["ciclo_id"] = 1
        vaga["disponivel_desde"] = None

        # Lapidação completa primeiro, creditando o 10º cristal lapidado
        with patch.object(server, "TEMPO_LAPIDACAO", 0.01):
            await server.lapidacao("lapidaria-1", 1, 1)

        self.assertEqual(server.vila["lapidados"], 10)
        self.assertFalse(vaga["ocupada"])

        # Solicitação de melhoria chega em seguida e é aceita com o saldo atualizado
        with patch.object(server, "TEMPO_OBRA", 0.02):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-15a"})

        self.assertEqual(server.vila["lapidados"], 0)
        self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "em melhoria")

    # Caso B — Solicitação de melhoria processada primeiro
    async def test_15b_concorrencia_melhoria_processada_primeiro(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(nivel=1, lapidados=10, brutos=0)
        vaga = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga["ocupada"] = True
        vaga["inicio_monotonic"] = time.monotonic()
        vaga["ciclo_id"] = 1
        vaga["disponivel_desde"] = None

        # Solicitação de melhoria é processada primeiro
        with patch.object(server, "TEMPO_OBRA", 0.05):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-15b"})

        # O cristal bruto da vaga foi estornado e ciclo incrementado para 2
        self.assertEqual(server.vila["brutos"], 1)
        self.assertEqual(vaga["ciclo_id"], 2)

        # Em seguida, a corrotina do ciclo 1 acorda
        with patch.object(server, "TEMPO_LAPIDACAO", 0.01):
            await server.lapidacao("lapidaria-1", 1, 1)

        # Nenhum cristal lapidado adicional é creditado
        self.assertEqual(server.vila["lapidados"], 0)
        # O estoque de brutos não é duplicado
        self.assertEqual(server.vila["brutos"], 1)

    # 16. Ordem dos eventos durante o início da melhoria, garantindo que melhoria.iniciada
    # preceda qualquer processamento iniciado em outras lapidárias em consequência dos estornos
    async def test_16_ordem_eventos_inicio_melhoria_com_latencia_de_emissao(self):
        _, j1 = await self.preparar_vila_aberta_com_lapidaria(lote="lote1", lid="lapidaria-1", nivel=1, lapidados=10, brutos=0)

        # Lapidária-2 pronta no lote 2 aguardando bruto
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
                    "disponivel_desde": 10.0,
                    "ciclo_id": 0,
                }
            ],
        }

        # Lapidária-1 ocupada processando
        vaga1 = server.vila["lapidarias"]["lapidaria-1"]["vagas"][0]
        vaga1["ocupada"] = True
        vaga1["inicio_monotonic"] = time.monotonic()
        vaga1["ciclo_id"] = 1

        ordem_eventos = []

        async def emit_com_latencia_iniciada(evento, payload, to=None):
            if evento == "melhoria.iniciada":
                await asyncio.sleep(0.04)
            ordem_eventos.append(evento)

        self.emit.side_effect = emit_com_latencia_iniciada

        with patch.object(server, "TEMPO_OBRA", 0.1):
            await server.solicitar_melhoria(j1, {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-16"})
            await asyncio.sleep(0.08)
            await asyncio.sleep(0.08)

        self.assertIn("melhoria.iniciada", ordem_eventos)
        self.assertIn("lapidaria.processamento_iniciado", ordem_eventos)

        idx_iniciada = ordem_eventos.index("melhoria.iniciada")
        idx_processamento = ordem_eventos.index("lapidaria.processamento_iniciado")
        self.assertLess(
            idx_iniciada,
            idx_processamento,
            f"'melhoria.iniciada' ({idx_iniciada}) deve preceder 'lapidaria.processamento_iniciado' ({idx_processamento}). Ordem: {ordem_eventos}",
        )


class TestProtocoloSocketIOEtapa5(unittest.TestCase):
    """Teste de integração real via Socket.IO para melhoria de lapidárias."""

    @classmethod
    def setUpClass(cls):
        s = socket.socket()
        s.bind(("", 0))
        cls.porta = s.getsockname()[1]
        s.close()

        # Configura variáveis de ambiente para tempos rápidos no teste de integração
        env = {
            **os.environ,
            "TEMPO_OBRA": "0.5",
            "CUSTO_MELHORIA_N2": "0",  # Permite melhoria imediata no teste de integração
            "INTERVALO_MINA": "1.0",
        }

        cls.proc = subprocess.Popen(
            [
                sys.executable,
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
            env=env,
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

    # 17. Integração real via Socket.IO, validando solicitação, início e conclusão de uma melhoria
    def test_17_integracao_melhoria_via_socketio(self):
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

        jogador.coletar_ate(tem_5_producoes, limite=10.0)

        # Solicita construção da lapidária de nível 1
        jogador.emitir("construcao.solicitada")
        jogador.coletar_ate(tem_evento("construcao.concluida"), limite=5.0)

        # Solicita melhoria para nível 2
        jogador.emitir("melhoria.solicitada", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-socketio"})
        jogador.coletar_ate(tem_evento("melhoria.iniciada"), limite=3.0)
        jogador.coletar_ate(tem_evento("melhoria.concluida"), limite=5.0)

        eventos = ClienteEngineIO.eventos(jogador.pacotes)
        nomes = [e[0] for e in eventos]
        self.assertIn("melhoria.iniciada", nomes)
        self.assertIn("melhoria.concluida", nomes)

        # Confere o snapshot da melhoria concluída
        evento_concluida = [e for e in eventos if e[0] == "melhoria.concluida"][-1]
        payload = evento_concluida[1]
        self.assertEqual(payload["nivel"], 2)
        self.assertEqual(payload["situacao"], "disponível")
        self.assertEqual(payload["estado"]["lapidarias"]["lapidaria-1"]["nivel"], 2)
        self.assertEqual(len(payload["estado"]["lapidarias"]["lapidaria-1"]["vagas"]), 2)

        mestre.emitir("vila.encerramento_solicitado")
        mestre.coletar_ate(tem_evento("vila.encerrada"), limite=3.0)


if __name__ == "__main__":
    unittest.main()
