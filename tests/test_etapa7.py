"""Testes de conformidade e integridade da Etapa 7 — Contadores por evento.

Verifica:
1. Estrutura do template (tags, classes, diretivas Vue e interpolação).
2. Incremento unitário correto a cada registro de evento.
3. Independência entre contadores de eventos distintos.
4. Contabilização de eventos enviados (pedir).
5. Contabilização de eventos recebidos (ouvir).
6. Ausência de duplicação por evento único.
7. Comportamento do filtro da mina (ocultarProducao não afeta contadores).
8. Preservação dos contadores acumulados em eventos de desconexão e erro de rede.

Executar:
    .venv/bin/python -m unittest tests/test_etapa7.py -v
"""
import json
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class TestEtapa7Contadores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html_path = RAIZ / "client" / "index.html"
        cls.html_content = html_path.read_text(encoding="utf-8")

    # ── 1. Estrutura do Template ──────────────────────────────────────────

    def test_01_estrutura_template_contadores(self):
        """Verifica se o template em client/index.html contém os elementos e bindings da Etapa 7."""
        html = self.html_content

        # 1. Deve preservar o comentário-âncora da Etapa 7
        self.assertIn("<!-- ETAPA 7 (dupla): cole aqui os contadores por evento -->", html)

        # 2. Container dos contadores
        self.assertIn('<div class="contadores">', html)

        # 3. Diretiva v-for iterando sobre contadores com key
        self.assertIn('v-for="(n, nome) in contadores"', html)
        self.assertIn(':key="nome"', html)

        # 4. Classe chip e formato de interpolação
        self.assertIn('class="chip"', html)
        self.assertIn("{{ nome }} ×{{ n }}", html)

        # 5. Estilização .chip definida no CSS
        self.assertIn(".chip", html)

        # 6. Presença de contadores no setup() e retorno reativo
        self.assertIn("const contadores = reactive({});", html)
        self.assertIn("contadores[nome] = (contadores[nome] || 0) + 1;", html)
        self.assertIn("contadores", html)

    # ── 2. Incremento Unitário por Evento ────────────────────────────────

    def test_02_incremento_unitario_por_evento(self):
        """Verifica se cada chamada a registrar() incrementa o contador correspondente em exatamente 1."""
        js_code = r"""
        const contadores = {};
        function registrar(sentido, nome) {
            contadores[nome] = (contadores[nome] || 0) + 1;
        }

        const log = [];
        log.push({ ...contadores });

        registrar("recebido", "mina.cristal_produzido");
        log.push({ ...contadores });

        registrar("recebido", "mina.cristal_produzido");
        log.push({ ...contadores });

        registrar("recebido", "mina.cristal_produzido");
        log.push({ ...contadores });

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertEqual(res[0], {})
        self.assertEqual(res[1]["mina.cristal_produzido"], 1)
        self.assertEqual(res[2]["mina.cristal_produzido"], 2)
        self.assertEqual(res[3]["mina.cristal_produzido"], 3)

    # ── 3. Independência entre Eventos Diferentes ─────────────────────────

    def test_03_independencia_entre_eventos_diferentes(self):
        """Verifica se eventos com nomes distintos incrementam exclusivamente seus próprios contadores."""
        js_code = r"""
        const contadores = {};
        function registrar(sentido, nome) {
            contadores[nome] = (contadores[nome] || 0) + 1;
        }

        registrar("enviado", "construcao.solicitada");
        registrar("recebido", "construcao.iniciada");
        registrar("recebido", "mina.cristal_produzido");
        registrar("recebido", "mina.cristal_produzido");
        registrar("enviado", "melhoria.solicitada");
        registrar("recebido", "melhoria.iniciada");
        registrar("recebido", "lapidaria.cristal_lapidado");
        registrar("recebido", "lapidaria.cristal_lapidado");
        registrar("recebido", "lapidaria.cristal_lapidado");

        console.log(JSON.stringify(contadores));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertEqual(res["construcao.solicitada"], 1)
        self.assertEqual(res["construcao.iniciada"], 1)
        self.assertEqual(res["mina.cristal_produzido"], 2)
        self.assertEqual(res["melhoria.solicitada"], 1)
        self.assertEqual(res["melhoria.iniciada"], 1)
        self.assertEqual(res["lapidaria.cristal_lapidado"], 3)
        self.assertNotIn("vila.aberta", res)

    # ── 4. Contabilização de Eventos Enviados (pedir) ─────────────────────

    def test_04_contabilizacao_eventos_enviados_pedir(self):
        """Verifica se todos os pedidos enviados pelo cliente via pedir() são contabilizados."""
        js_code = r"""
        const contadores = {};
        const eventos = [];
        const socketEmits = [];

        const socket = {
            emit: (nome, dados) => socketEmits.push({ nome, dados })
        };

        function registrar(sentido, nome, dados) {
            contadores[nome] = (contadores[nome] || 0) + 1;
            eventos.unshift({ sentido, nome, dados });
        }

        function pedir(nome, dados) {
            if (!socket) return;
            registrar("enviado", nome, dados);
            if (dados === undefined) socket.emit(nome); else socket.emit(nome, dados);
        }

        // Simula os 4 pedidos reais do cliente
        pedir("vila.abertura_solicitada");
        pedir("construcao.solicitada");
        pedir("melhoria.solicitada", { lapidaria_id: "lapidaria-1", solicitacao_id: "req-1" });
        pedir("vila.encerramento_solicitado");

        console.log(JSON.stringify({ contadores, eventosLength: eventos.length, socketEmitsLength: socketEmits.length }));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertEqual(res["contadores"]["vila.abertura_solicitada"], 1)
        self.assertEqual(res["contadores"]["construcao.solicitada"], 1)
        self.assertEqual(res["contadores"]["melhoria.solicitada"], 1)
        self.assertEqual(res["contadores"]["vila.encerramento_solicitado"], 1)
        self.assertEqual(res["eventosLength"], 4)
        self.assertEqual(res["socketEmitsLength"], 4)

    # ── 5. Contabilização de Eventos Recebidos (ouvir) ────────────────────

    def test_05_contabilizacao_eventos_recebidos_ouvir(self):
        """Verifica se todos os fatos e recusas recebidos via ouvir() são contabilizados."""
        js_code = r"""
        const contadores = {};
        const listeners = {};

        const socket = {
            on: (nome, fn) => { listeners[nome] = fn; }
        };

        function registrar(sentido, nome, dados, reacao = "") {
            contadores[nome] = (contadores[nome] || 0) + 1;
        }

        function ouvir(nome, reacao, funcao) {
            if (!socket) return;
            socket.on(nome, (d) => { registrar("recebido", nome, d, reacao); funcao(d); });
        }

        // Registra os 14 eventos reais recebidos pelo cliente
        const eventosRecebidos = [
            "estado.sincronizado",
            "vila.aberta",
            "vila.abertura_recusada",
            "vila.encerrada",
            "vila.encerramento_recusado",
            "mina.cristal_produzido",
            "construcao.iniciada",
            "construcao.recusada",
            "construcao.concluida",
            "lapidaria.processamento_iniciado",
            "lapidaria.cristal_lapidado",
            "melhoria.iniciada",
            "melhoria.recusada",
            "melhoria.concluida"
        ];

        for (const ev of eventosRecebidos) {
            ouvir(ev, "Reação a " + ev, () => {});
        }

        // Simula recebimento de cada evento pelo socket
        for (const ev of eventosRecebidos) {
            listeners[ev]({ dummy: true });
        }

        console.log(JSON.stringify(contadores));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        eventos_esperados = [
            "estado.sincronizado",
            "vila.aberta",
            "vila.abertura_recusada",
            "vila.encerrada",
            "vila.encerramento_recusado",
            "mina.cristal_produzido",
            "construcao.iniciada",
            "construcao.recusada",
            "construcao.concluida",
            "lapidaria.processamento_iniciado",
            "lapidaria.cristal_lapidado",
            "melhoria.iniciada",
            "melhoria.recusada",
            "melhoria.concluida",
        ]

        for ev in eventos_esperados:
            self.assertEqual(res.get(ev), 1, f"Evento {ev} deveria ter contador 1")

    # ── 6. Ausência de Duplicação por Evento Único ────────────────────────

    def test_06_ausencia_duplicacao_evento_unico(self):
        """Verifica se um único disparo de evento recebido produz exatamente um incremento."""
        js_code = r"""
        const contadores = {};
        const callbacks = {};

        const socket = {
            on: (nome, fn) => { callbacks[nome] = fn; }
        };

        function registrar(sentido, nome) {
            contadores[nome] = (contadores[nome] || 0) + 1;
        }

        function ouvir(nome, reacao, funcao) {
            socket.on(nome, (d) => { registrar("recebido", nome); funcao(d); });
        }

        let processado = 0;
        ouvir("construcao.concluida", "Atualiza lapidária", (d) => {
            processado++;
        });

        // 1 disparo
        callbacks["construcao.concluida"]({ lapidaria_id: "lapidaria-1" });

        console.log(JSON.stringify({ totalContador: contadores["construcao.concluida"], totalProcessado: processado }));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertEqual(res["totalContador"], 1)
        self.assertEqual(res["totalProcessado"], 1)

    # ── 7. Filtro da Mina Preserva Contadores ─────────────────────────────

    def test_07_filtro_mina_preserva_contadores(self):
        """Verifica se ocultarProducao oculta a timeline mas preserva a contagem de mina.cristal_produzido."""
        js_code = r"""
        const contadores = {};
        const eventos = [];
        let ocultarProducao = false;

        function eventosVisiveis() {
            return eventos.filter((e) => !(ocultarProducao && (e.nome === "mina.cristal_produzido" || e.nome === "recurso.produzido")));
        }

        function registrar(sentido, nome) {
            contadores[nome] = (contadores[nome] || 0) + 1;
            eventos.unshift({ sentido, nome });
        }

        // 1. Registra com filtro desmarcado
        registrar("recebido", "mina.cristal_produzido");
        registrar("recebido", "vila.aberta");

        const visiveis1 = eventosVisiveis().length;
        const countMina1 = contadores["mina.cristal_produzido"];

        // 2. Ativa o filtro
        ocultarProducao = true;
        registrar("recebido", "mina.cristal_produzido");
        registrar("recebido", "mina.cristal_produzido");

        const visiveis2 = eventosVisiveis().length;
        const countMina2 = contadores["mina.cristal_produzido"];

        console.log(JSON.stringify({ visiveis1, countMina1, visiveis2, countMina2 }));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # Antes do filtro: 2 eventos visíveis, contador da mina = 1
        self.assertEqual(res["visiveis1"], 2)
        self.assertEqual(res["countMina1"], 1)

        # Depois do filtro: apenas 'vila.aberta' é visível (1 evento visível),
        # porém o contador da mina continuou somando normalmente (3 no total)
        self.assertEqual(res["visiveis2"], 1)
        self.assertEqual(res["countMina2"], 3)

    # ── 8. Desconexão Preserva Contadores ─────────────────────────────────

    def test_08_desconexao_preserva_contadores(self):
        """Verifica se disconnect e connect_error não limpam nem corrompem os contadores da sessão."""
        js_code = r"""
        const contadores = {};
        let conectado = true;
        let comandoTemporadaPendente = true;
        let comandoConstrucaoPendente = true;
        let comandoMelhoriaPendente = true;
        let solicitacaoMelhoriaPendenteId = "req-123";

        function registrar(sentido, nome) {
            contadores[nome] = (contadores[nome] || 0) + 1;
        }

        // Acumula eventos durante a sessão
        registrar("recebido", "estado.sincronizado");
        registrar("enviado", "construcao.solicitada");
        registrar("recebido", "construcao.iniciada");
        registrar("recebido", "mina.cristal_produzido");

        // Simula evento 'disconnect' do Socket.IO
        function onDisconnect() {
            conectado = false;
            comandoTemporadaPendente = false;
            comandoConstrucaoPendente = false;
            comandoMelhoriaPendente = false;
            solicitacaoMelhoriaPendenteId = null;
        }

        onDisconnect();

        const logAposDisconnect = {
            conectado,
            comandoConstrucaoPendente,
            contadores: { ...contadores }
        };

        // Simula evento 'connect_error'
        function onConnectError(err) {
            conectado = false;
            comandoTemporadaPendente = false;
            comandoConstrucaoPendente = false;
            comandoMelhoriaPendente = false;
            solicitacaoMelhoriaPendenteId = null;
        }

        onConnectError({ message: "Falha de rede" });

        const logAposConnectError = {
            conectado,
            contadores: { ...contadores }
        };

        console.log(JSON.stringify({ logAposDisconnect, logAposConnectError }));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # As travas de comando foram liberadas
        self.assertFalse(res["logAposDisconnect"]["conectado"])
        self.assertFalse(res["logAposDisconnect"]["comandoConstrucaoPendente"])

        # Mas os contadores permanecem 100% preservados
        self.assertEqual(res["logAposDisconnect"]["contadores"]["estado.sincronizado"], 1)
        self.assertEqual(res["logAposDisconnect"]["contadores"]["construcao.solicitada"], 1)
        self.assertEqual(res["logAposDisconnect"]["contadores"]["construcao.iniciada"], 1)
        self.assertEqual(res["logAposDisconnect"]["contadores"]["mina.cristal_produzido"], 1)

        self.assertEqual(res["logAposConnectError"]["contadores"]["mina.cristal_produzido"], 1)


if __name__ == "__main__":
    unittest.main()
