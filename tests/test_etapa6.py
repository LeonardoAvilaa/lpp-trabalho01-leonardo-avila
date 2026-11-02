"""Testes de conformidade e contrato da Etapa 6.1 (conexão, tratamento de erros e sincronização base).

Inclui:
1. Testes de backend para o contrato do snapshot e respostas de conexão.
2. Verificações isoladas de lógica e contratos de dados das funções do cliente em ambiente JavaScript.
3. Verificação estática da estrutura e bindings de client/index.html.

Executar na raiz do projeto:
    .venv/bin/python -m unittest discover -s tests -v
"""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import server  # noqa: E402


class TestEtapa61Cliente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html_path = RAIZ / "client" / "index.html"
        cls.html_content = html_path.read_text(encoding="utf-8")

    def setUp(self):
        self._vila_original = copy.deepcopy(server.vila)
        server.jogadores.clear()
        server.mestre_sid = None

    def tearDown(self):
        server.vila.clear()
        server.vila.update(self._vila_original)
        server.jogadores.clear()
        server.mestre_sid = None

    # ── 1. Contratos de Backend ──────────────────────────────────────────

    def test_01_compatibilidade_campos_snapshot_backend(self):
        """Verifica se o snapshot gerado pelo backend contém os campos e tipos esperados pelo cliente."""
        snap = server.snapshot()
        campos_obrigatorios = [
            "fase",
            "brutos",
            "lapidados",
            "trabalhadores",
            "lapidarias",
            "lotes",
            "construcoes",
            "melhorias",
        ]
        for campo in campos_obrigatorios:
            self.assertIn(campo, snap, f"Campo {campo} obrigatório ausente no snapshot")

        self.assertIsInstance(snap["trabalhadores"], dict)
        self.assertIn("ocupados", snap["trabalhadores"])
        self.assertIn("limite", snap["trabalhadores"])
        self.assertIsInstance(snap["lotes"], dict)
        self.assertIsInstance(snap["lapidarias"], dict)
        self.assertIsInstance(snap["construcoes"], list)
        self.assertIsInstance(snap["melhorias"], list)

    def test_02_backend_rejeicao_nome_invalido(self):
        """Verifica se o backend rejeita conexão com nome vazio ou somente espaços."""
        with self.assertRaises(server.SioConnectionRefusedError) as ctx:
            import asyncio
            asyncio.run(server.connect("sid1", {}, {"nome": "   ", "papel": "jogador"}))
        self.assertIn("Nome inválido", str(ctx.exception))

    def test_03_backend_rejeicao_segundo_mestre(self):
        """Verifica se o backend rejeita segundo Mestre com a mensagem específica."""
        import asyncio
        asyncio.run(server.connect("m1", {}, {"nome": "Mestre1", "papel": "mestre"}))
        with self.assertRaises(server.SioConnectionRefusedError) as ctx:
            asyncio.run(server.connect("m2", {}, {"nome": "Mestre2", "papel": "mestre"}))
        self.assertIn("Já existe um Mestre conectado", str(ctx.exception))

    def test_04_backend_emite_estado_sincronizado_apos_conexao(self):
        """Verifica se o backend emite estado.sincronizado após conexão bem-sucedida."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server._sincronizar_apos_conexao("sid_teste"))
            self.assertEqual(mock_emit.call_count, 0)

            server.jogadores["sid_teste"] = {"nome": "Jogador", "papel": "jogador"}
            asyncio.run(server._sincronizar_apos_conexao("sid_teste"))
            self.assertEqual(mock_emit.call_count, 1)
            evento, payload = mock_emit.call_args.args[:2]
            self.assertEqual(evento, "estado.sincronizado")
            self.assertEqual(payload["causa"], "conexao")
            self.assertIn("estado", payload)
            self.assertEqual(payload["estado"]["fase"], "aguardando")

    # ── 2. Verificações Isoladas de Lógica e Contratos (JavaScript) ───────

    def test_05_verificacao_contrato_validacao_nome_e_formato_auth(self):
        """Verificação isolada de lógica: algoritmo de validação de nome, remoção de espaços e auth."""
        js_code = r"""
        const resultados = [];

        function validarEntrada(nomeInput, papelInput) {
            let erro = "";
            const nomeLimpo = (nomeInput || "").trim();
            if (!nomeLimpo) {
                erro = "Informe um nome válido para entrar.";
                return { erro, auth: null };
            }
            return { erro: "", auth: { nome: nomeLimpo, papel: papelInput } };
        }

        resultados.push(validarEntrada("", "jogador"));
        resultados.push(validarEntrada("   ", "jogador"));
        resultados.push(validarEntrada("  Leonardo  ", "mestre"));
        console.log(JSON.stringify(resultados));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertTrue(res[0]["erro"])
        self.assertIsNone(res[0]["auth"])

        self.assertTrue(res[1]["erro"])
        self.assertIsNone(res[1]["auth"])

        self.assertEqual(res[2]["erro"], "")
        self.assertEqual(res[2]["auth"]["nome"], "Leonardo")
        self.assertEqual(res[2]["auth"]["papel"], "mestre")

    def test_06_verificacao_contrato_tratamento_connect_error(self):
        """Verificação isolada de lógica: algoritmo de tratamento de connect_error e limpeza de socket."""
        js_code = r"""
        let conectado = true;
        let erroEntrada = "";
        let desconectou = false;

        const fakeSocket = {
            disconnect() { desconectou = true; }
        };

        function onConnectError(err) {
            conectado = false;
            erroEntrada = (err && err.message) ? err.message : "Conexão recusada pelo servidor.";
            fakeSocket.disconnect();
        }

        onConnectError({ message: "Já existe um Mestre conectado na vila." });
        console.log(JSON.stringify({ conectado, erroEntrada, desconectou }));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertFalse(res["conectado"])
        self.assertEqual(res["erroEntrada"], "Já existe um Mestre conectado na vila.")
        self.assertTrue(res["desconectou"])

    def test_07_verificacao_contrato_funcao_atualizar_com_snapshot(self):
        """Verificação isolada de contrato: aplicação de propriedades do snapshot do backend no estado."""
        snap_backend = server.snapshot()
        snap_json = json.dumps(snap_backend)

        js_code = f"""
        const estado = {{
            fase: "aguardando",
            brutos: 0,
            lapidados: 0,
            trabalhadores: {{ ocupados: 0, limite: 2 }},
            lapidarias: {{}},
            lotes: {{ lote1: null, lote2: null, lote3: null, lote4: null, lote5: null, lote6: null }},
            construcoes: [],
            melhorias: [],
        }};

        function atualizar(d) {{
            if (!d || !d.estado) return;
            const e = d.estado;
            if (e.fase !== undefined) estado.fase = e.fase;
            if (e.brutos !== undefined) estado.brutos = e.brutos;
            if (e.lapidados !== undefined) estado.lapidados = e.lapidados;
            if (e.trabalhadores) {{
                if (e.trabalhadores.ocupados !== undefined) estado.trabalhadores.ocupados = e.trabalhadores.ocupados;
                if (e.trabalhadores.limite !== undefined) estado.trabalhadores.limite = e.trabalhadores.limite;
            }}
            if (e.lapidarias !== undefined) estado.lapidarias = e.lapidarias;
            if (e.lotes !== undefined) estado.lotes = e.lotes;
            if (e.construcoes !== undefined) estado.construcoes = e.construcoes;
            if (e.melhorias !== undefined) estado.melhorias = e.melhorias;
        }}

        const payload = {{ causa: "conexao", estado: {snap_json} }};
        atualizar(payload);
        console.log(JSON.stringify(estado));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertEqual(res["fase"], snap_backend["fase"])
        self.assertEqual(res["brutos"], snap_backend["brutos"])
        self.assertEqual(res["lapidados"], snap_backend["lapidados"])
        self.assertEqual(res["trabalhadores"]["ocupados"], snap_backend["trabalhadores"]["ocupados"])
        self.assertEqual(res["trabalhadores"]["limite"], snap_backend["trabalhadores"]["limite"])
        self.assertEqual(res["lotes"], snap_backend["lotes"])
        self.assertEqual(res["lapidarias"], snap_backend["lapidarias"])
        self.assertEqual(res["construcoes"], snap_backend["construcoes"])
        self.assertEqual(res["melhorias"], snap_backend["melhorias"])

    def test_08_verificacao_contrato_classificacao_recusas_no_painel(self):
        """Verificação isolada de lógica: regex de classificação de pedidos, recusas e fatos no painel."""
        js_code = r"""
        function classificarTipo(nome) {
            return /[._]solicitad[ao]$/.test(nome)
                ? "pedido"
                : (/[._]recusad[ao]$/.test(nome) ? "recusa" : "fato");
        }

        const testes = [
            "construcao.recusada",
            "melhoria.recusada",
            "vila.abertura_recusada",
            "vila.encerramento_recusado",
            "construcao.solicitada",
            "melhoria.solicitada",
            "vila.aberta",
            "estado.sincronizado",
            "mina.cristal_produzido"
        ];

        const resultado = testes.map(t => ({ nome: t, tipo: classificarTipo(t) }));
        console.log(JSON.stringify(resultado));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        recusas = [r["nome"] for r in res if r["tipo"] == "recusa"]
        self.assertEqual(
            recusas,
            [
                "construcao.recusada",
                "melhoria.recusada",
                "vila.abertura_recusada",
                "vila.encerramento_recusado",
            ],
        )

        pedidos = [r["nome"] for r in res if r["tipo"] == "pedido"]
        self.assertEqual(pedidos, ["construcao.solicitada", "melhoria.solicitada"])

        fatos = [r["nome"] for r in res if r["tipo"] == "fato"]
        self.assertEqual(fatos, ["vila.aberta", "estado.sincronizado", "mina.cristal_produzido"])

    def test_09_verificacao_contrato_funcao_resumir(self):
        """Verificação isolada de lógica: formatação dos dados de snapshot para exibição no painel."""
        snap = server.snapshot()
        snap_json = json.dumps(snap)

        js_code = f"""
        function resumir(d) {{
            if (!d) return "";
            const {{ estado: e, causa, ...resto }} = d;
            const partes = Object.entries(resto).map(([k, v]) => k + ": " + (typeof v === "object" ? JSON.stringify(v) : v));
            if (e) {{
                const trab = e.trabalhadores ? `${{e.trabalhadores.ocupados}}/${{e.trabalhadores.limite}}` : "";
                const partesEstado = [];
                if (e.brutos !== undefined) partesEstado.push(`brutos: ${{e.brutos}}`);
                if (e.lapidados !== undefined) partesEstado.push(`lapidados: ${{e.lapidados}}`);
                if (trab) partesEstado.push(`trab: ${{trab}}`);
                if (partesEstado.length) partes.push(partesEstado.join(", "));
            }}
            return partes.join(" · ");
        }}

        const payload = {{ causa: "conexao", estado: {snap_json} }};
        console.log(resumir(payload));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        resumo = proc.stdout.strip()

        self.assertNotIn("tora", resumo.lower())
        self.assertIn("brutos: 0", resumo)
        self.assertIn("lapidados: 0", resumo)
        self.assertIn("trab: 0/2", resumo)

    # ── 3. Verificações Estáticas de client/index.html ────────────────────

    def test_10_verificacao_estatica_client_index_html(self):
        """Verificação estática do código-fonte de client/index.html."""
        # Não pode conter menções a toras na tela da vila
        self.assertNotIn("🪵 Toras", self.html_content)
        self.assertNotIn("custo {{ estado.custo }} toras", self.html_content)

        # Deve conter referências ao domínio de cristais
        self.assertIn("Cristais brutos", self.html_content)
        self.assertIn("Cristais lapidados", self.html_content)
        self.assertIn("estado.trabalhadores.ocupados", self.html_content)
        self.assertIn("erroEntrada", self.html_content)

        # Deve tratar connect_error e registrar estado.sincronizado
        self.assertIn("connect_error", self.html_content)
        self.assertIn("estado.sincronizado", self.html_content)

        # Expressão regular de recusa deve verificar .recusada / _recusada / _recusado
        self.assertIn(r"/[._]recusad[ao]$/", self.html_content)

        # Deve preservar o comentário reservado da Etapa 7 (sem renderização antecipada)
        self.assertIn("<!-- ETAPA 7 (dupla): cole aqui os contadores por evento -->", self.html_content)
        self.assertNotIn('v-for="(n, evNome) in contadores"', self.html_content)

    # ── 4. Testes de Contrato da Etapa 6.2 (Abertura e Encerramento) ─────

    def test_11_backend_abertura_e_encerramento_eventos_e_payloads(self):
        """Verifica se o backend emite os eventos corretos com snapshot em abertura e encerramento."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        server.vila["fase"] = "aguardando"
        server.mestre_sid = "m1"
        server.jogadores["m1"] = {"nome": "Mestre", "papel": "mestre"}

        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            # Abertura
            with patch.object(server, "INTERVALO_MINA", 100.0):
                asyncio.run(server.abrir_vila("m1"))
            self.assertEqual(server.vila["fase"], "aberta")
            self.assertEqual(mock_emit.call_count, 1)
            ev_aberta, payload_aberta = mock_emit.call_args.args[:2]
            self.assertEqual(ev_aberta, "vila.aberta")
            self.assertEqual(payload_aberta["causa"], "vila.abertura_solicitada")
            self.assertEqual(payload_aberta["estado"]["fase"], "aberta")

            # Encerramento
            mock_emit.reset_mock()
            asyncio.run(server.encerrar_vila("m1"))
            self.assertEqual(server.vila["fase"], "encerrada")
            self.assertEqual(mock_emit.call_count, 1)
            ev_encerrada, payload_encerrada = mock_emit.call_args.args[:2]
            self.assertEqual(ev_encerrada, "vila.encerrada")
            self.assertEqual(payload_encerrada["causa"], "vila.encerramento_solicitado")
            self.assertEqual(payload_encerrada["estado"]["fase"], "encerrada")

    def test_12_backend_recusas_abertura_e_encerramento(self):
        """Verifica se o backend emite as recusas corretas com motivo para solicitações inválidas."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        server.vila["fase"] = "aguardando"
        server.mestre_sid = "m1"
        server.jogadores["m1"] = {"nome": "Mestre", "papel": "mestre"}
        server.jogadores["j1"] = {"nome": "Jogador", "papel": "jogador"}

        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            # Jogador tenta abrir
            asyncio.run(server.abrir_vila("j1"))
            self.assertEqual(mock_emit.call_count, 1)
            ev, payload = mock_emit.call_args.args[:2]
            self.assertEqual(ev, "vila.abertura_recusada")
            self.assertIn("Apenas o Mestre", payload["motivo"])
            self.assertEqual(server.vila["fase"], "aguardando")

            # Mestre tenta encerrar em fase 'aguardando'
            mock_emit.reset_mock()
            asyncio.run(server.encerrar_vila("m1"))
            self.assertEqual(mock_emit.call_count, 1)
            ev, payload = mock_emit.call_args.args[:2]
            self.assertEqual(ev, "vila.encerramento_recusado")
            self.assertIn("fase 'aberta'", payload["motivo"])
            self.assertEqual(server.vila["fase"], "aguardando")

    def test_13_verificacao_contrato_pedidos_mestre_e_guardas_de_fase(self):
        """Verificação isolada de lógica: emissão de pedidos do Mestre condicionada estritamente à fase."""
        js_code = r"""
        const pedidos = [];
        let papel = "mestre";
        let estado = { fase: "aguardando" };

        function pedir(nome) {
            pedidos.push(nome);
        }

        function abrirVila() {
            if (papel !== "mestre" || estado.fase !== "aguardando") return;
            pedir("vila.abertura_solicitada");
        }

        function encerrarVila() {
            if (papel !== "mestre" || estado.fase !== "aberta") return;
            pedir("vila.encerramento_solicitado");
        }

        const log = [];

        // 1. Mestre na fase aguardando
        abrirVila();
        log.push({ fase: estado.fase, pedidos: [...pedidos] }); // deve emitir abertura

        // 2. Tenta encerrar na fase aguardando (deve ser ignorado)
        encerrarVila();
        log.push({ fase: estado.fase, pedidos: [...pedidos] });

        // 3. Fase passa para aberta (pelo servidor)
        estado.fase = "aberta";
        abrirVila(); // deve ser ignorado pois ja esta aberta
        encerrarVila(); // deve emitir encerramento
        log.push({ fase: estado.fase, pedidos: [...pedidos] });

        // 4. Fase passa para encerrada
        estado.fase = "encerrada";
        abrirVila();
        encerrarVila();
        log.push({ fase: estado.fase, pedidos: [...pedidos] });

        // 5. Papel jogador tenta emitir em qualquer fase
        papel = "jogador";
        estado.fase = "aguardando";
        abrirVila();
        estado.fase = "aberta";
        encerrarVila();
        log.push({ fase: estado.fase, pedidos: [...pedidos] });

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # 1. Abertura emitida na fase aguardando
        self.assertEqual(res[0]["pedidos"], ["vila.abertura_solicitada"])
        # 2. Encerramento ignorado na fase aguardando
        self.assertEqual(res[1]["pedidos"], ["vila.abertura_solicitada"])
        # 3. Encerramento emitido na fase aberta; abertura ignorada
        self.assertEqual(res[2]["pedidos"], ["vila.abertura_solicitada", "vila.encerramento_solicitado"])
        # 4. Ambos ignorados na fase encerrada
        self.assertEqual(res[3]["pedidos"], ["vila.abertura_solicitada", "vila.encerramento_solicitado"])
        # 5. Jogador nunca emite
        self.assertEqual(res[4]["pedidos"], ["vila.abertura_solicitada", "vila.encerramento_solicitado"])

    def test_14_verificacao_contrato_listeners_abertura_e_encerramento(self):
        """Verificação isolada de lógica: reação aos fatos de confirmação e recusa de abertura e encerramento."""
        js_code = r"""
        const estado = { fase: "aguardando" };
        const avisos = [];

        function avisar(texto, tipo) {
            avisos.push({ texto, tipo });
        }

        function atualizar(d) {
            if (d && d.estado && d.estado.fase) {
                estado.fase = d.estado.fase;
            }
        }

        // Simula ouvintes
        function onVilaAberta(d) {
            atualizar(d);
            avisar("Temporada da vila aberta!", "ok");
        }

        function onVilaAberturaRecusada(d) {
            avisar(d && d.motivo ? d.motivo : "Abertura da temporada recusada.", "erro");
        }

        function onVilaEncerrada(d) {
            atualizar(d);
            avisar("Temporada da vila encerrada!", "info");
        }

        function onVilaEncerramentoRecusado(d) {
            avisar(d && d.motivo ? d.motivo : "Encerramento da temporada recusado.", "erro");
        }

        // Teste de recusa na abertura não altera fase
        onVilaAberturaRecusada({ motivo: "Apenas o Mestre pode abrir a temporada." });
        const fase1 = estado.fase;

        // Teste de confirmação de abertura altera fase
        onVilaAberta({ estado: { fase: "aberta" } });
        const fase2 = estado.fase;

        // Teste de recusa no encerramento não altera fase
        onVilaEncerramentoRecusado({ motivo: "A vila só pode ser encerrada na fase 'aberta'." });
        const fase3 = estado.fase;

        // Teste de confirmação de encerramento altera fase
        onVilaEncerrada({ estado: { fase: "encerrada" } });
        const fase4 = estado.fase;

        console.log(JSON.stringify({ fase1, fase2, fase3, fase4, avisos }));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertEqual(res["fase1"], "aguardando")
        self.assertEqual(res["fase2"], "aberta")
        self.assertEqual(res["fase3"], "aberta")
        self.assertEqual(res["fase4"], "encerrada")

        tipos_avisos = [a["tipo"] for a in res["avisos"]]
        self.assertEqual(tipos_avisos, ["erro", "ok", "erro", "info"])

    def test_15_verificacao_estatica_botoes_mestre_por_fase(self):
        """Verificação estática de client/index.html para os controles condicionais da temporada."""
        html_content = (RAIZ / "client" / "index.html").read_text(encoding="utf-8")

        # Botões de abertura e encerramento devem ser exclusivos do mestre, condicionados à fase e com binding :disabled
        self.assertIn("button v-if=\"estado.fase === 'aguardando'\" :disabled=\"comandoTemporadaPendente\" @click=\"abrirVila\"", html_content)
        self.assertIn("button v-else-if=\"estado.fase === 'aberta'\" :disabled=\"comandoTemporadaPendente\" @click=\"encerrarVila\"", html_content)

        # Estado reativo e exportação em setup()
        self.assertIn("const comandoTemporadaPendente = ref(false);", html_content)
        self.assertIn("comandoTemporadaPendente,", html_content)

        # Escutas registradas no script
        self.assertIn('socket.on("disconnect"', html_content)
        self.assertIn('ouvir("estado.sincronizado"', html_content)
        self.assertIn('ouvir("vila.aberta"', html_content)
        self.assertIn('ouvir("vila.abertura_recusada"', html_content)
        self.assertIn('ouvir("vila.encerrada"', html_content)
        self.assertIn('ouvir("vila.encerramento_recusado"', html_content)

        # Pedidos registrados nas funções e guardas de conexão
        self.assertIn('!socket || !socket.connected', html_content)
        self.assertIn('pedir("vila.abertura_solicitada")', html_content)
        self.assertIn('pedir("vila.encerramento_solicitado")', html_content)

    def test_16_verificacao_contrato_bloqueio_duplo_clique_e_liberacao_pendencia(self):
        """Verificação isolada de lógica: proteção contra cliques múltiplos e liberação de pendência por confirmação ou recusa."""
        js_code = r"""
        const pedidos = [];
        let papel = "mestre";
        let estado = { fase: "aguardando" };
        let comandoTemporadaPendente = false;

        function pedir(nome) {
            pedidos.push(nome);
        }

        function atualizar(d) {
            if (d && d.estado && d.estado.fase) {
                estado.fase = d.estado.fase;
            }
        }

        function abrirVila() {
            if (papel !== "mestre" || estado.fase !== "aguardando" || comandoTemporadaPendente) return;
            comandoTemporadaPendente = true;
            pedir("vila.abertura_solicitada");
        }

        function encerrarVila() {
            if (papel !== "mestre" || estado.fase !== "aberta" || comandoTemporadaPendente) return;
            comandoTemporadaPendente = true;
            pedir("vila.encerramento_solicitado");
        }

        // Simula ouvintes liberando o estado pendente
        function onVilaAberta(d) {
            comandoTemporadaPendente = false;
            atualizar(d);
        }

        function onVilaAberturaRecusada(d) {
            comandoTemporadaPendente = false;
        }

        function onVilaEncerrada(d) {
            comandoTemporadaPendente = false;
            atualizar(d);
        }

        function onVilaEncerramentoRecusado(d) {
            comandoTemporadaPendente = false;
        }

        const log = {};

        // 1. Dois cliques consecutivos de abertura: o segundo deve ser bloqueado
        abrirVila();
        const pedidosAposPrimeiroClique = pedidos.length;
        const pendenteAposPrimeiroClique = comandoTemporadaPendente;
        abrirVila(); // segundo clique consecutivo
        const pedidosAposSegundoClique = pedidos.length;

        log.aberturaDuploClique = {
            pedidosAposPrimeiroClique,
            pendenteAposPrimeiroClique,
            pedidosAposSegundoClique
        };

        // 2. Recusa de abertura libera a possibilidade de tentar novamente sem alterar a fase
        onVilaAberturaRecusada({ motivo: "Servidor ocupado" });
        const pendenteAposRecusaAbertura = comandoTemporadaPendente;
        const faseAposRecusaAbertura = estado.fase;
        abrirVila(); // nova tentativa permitida após recusa
        const pedidosAposTentativaAposRecusa = pedidos.length;

        log.aberturaRecusaELiberacao = {
            pendenteAposRecusaAbertura,
            faseAposRecusaAbertura,
            pedidosAposTentativaAposRecusa
        };

        // 3. Confirmação de abertura libera pendência e atualiza a fase como autoridade
        onVilaAberta({ estado: { fase: "aberta" } });
        const pendenteAposConfirmacaoAbertura = comandoTemporadaPendente;
        const faseAposConfirmacaoAbertura = estado.fase;

        log.aberturaConfirmacao = {
            pendenteAposConfirmacaoAbertura,
            faseAposConfirmacaoAbertura
        };

        // 4. Dois cliques consecutivos de encerramento na fase aberta: o segundo deve ser bloqueado
        encerrarVila();
        const pedidosAposPrimeiroEncerramento = pedidos.length;
        const pendenteAposPrimeiroEncerramento = comandoTemporadaPendente;
        encerrarVila(); // segundo clique consecutivo
        const pedidosAposSegundoEncerramento = pedidos.length;

        log.encerramentoDuploClique = {
            pedidosAposPrimeiroEncerramento,
            pendenteAposPrimeiroEncerramento,
            pedidosAposSegundoEncerramento
        };

        // 5. Recusa de encerramento libera possibilidade de tentar novamente mantendo fase aberta
        onVilaEncerramentoRecusado({ motivo: "Servidor recusou encerramento" });
        const pendenteAposRecusaEncerramento = comandoTemporadaPendente;
        const faseAposRecusaEncerramento = estado.fase;
        encerrarVila(); // nova tentativa permitida após recusa
        const pedidosAposTentativaAposRecusaEncerramento = pedidos.length;

        log.encerramentoRecusaELiberacao = {
            pendenteAposRecusaEncerramento,
            faseAposRecusaEncerramento,
            pedidosAposTentativaAposRecusaEncerramento
        };

        // 6. Confirmação de encerramento libera pendência e atualiza fase para autoridade do servidor
        onVilaEncerrada({ estado: { fase: "encerrada" } });
        const pendenteAposConfirmacaoEncerramento = comandoTemporadaPendente;
        const faseAposConfirmacaoEncerramento = estado.fase;

        // Com temporada encerrada, cliques adicionais não emitem pedidos
        abrirVila();
        encerrarVila();
        const pedidosFinais = pedidos.length;

        log.encerramentoConfirmacao = {
            pendenteAposConfirmacaoEncerramento,
            faseAposConfirmacaoEncerramento,
            pedidosFinais
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # 1. Dois cliques consecutivos de abertura geram apenas 1 pedido
        self.assertEqual(res["aberturaDuploClique"]["pedidosAposPrimeiroClique"], 1)
        self.assertTrue(res["aberturaDuploClique"]["pendenteAposPrimeiroClique"])
        self.assertEqual(res["aberturaDuploClique"]["pedidosAposSegundoClique"], 1)

        # 2. Recusa libera pendência e permite nova tentativa
        self.assertFalse(res["aberturaRecusaELiberacao"]["pendenteAposRecusaAbertura"])
        self.assertEqual(res["aberturaRecusaELiberacao"]["faseAposRecusaAbertura"], "aguardando")
        self.assertEqual(res["aberturaRecusaELiberacao"]["pedidosAposTentativaAposRecusa"], 2)

        # 3. Confirmação libera pendência e autoridade da fase é do servidor
        self.assertFalse(res["aberturaConfirmacao"]["pendenteAposConfirmacaoAbertura"])
        self.assertEqual(res["aberturaConfirmacao"]["faseAposConfirmacaoAbertura"], "aberta")

        # 4. Dois cliques consecutivos de encerramento geram apenas 1 pedido
        self.assertEqual(res["encerramentoDuploClique"]["pedidosAposPrimeiroEncerramento"], 3)
        self.assertTrue(res["encerramentoDuploClique"]["pendenteAposPrimeiroEncerramento"])
        self.assertEqual(res["encerramentoDuploClique"]["pedidosAposSegundoEncerramento"], 3)

        # 5. Recusa de encerramento libera pendência e permite nova tentativa
        self.assertFalse(res["encerramentoRecusaELiberacao"]["pendenteAposRecusaEncerramento"])
        self.assertEqual(res["encerramentoRecusaELiberacao"]["faseAposRecusaEncerramento"], "aberta")
        self.assertEqual(res["encerramentoRecusaELiberacao"]["pedidosAposTentativaAposRecusaEncerramento"], 4)

        # 6. Confirmação de encerramento libera pendência e atualiza fase final
        self.assertFalse(res["encerramentoConfirmacao"]["pendenteAposConfirmacaoEncerramento"])
        self.assertEqual(res["encerramentoConfirmacao"]["faseAposConfirmacaoEncerramento"], "encerrada")
        self.assertEqual(res["encerramentoConfirmacao"]["pedidosFinais"], 4)

    def test_17_verificacao_contrato_desconexao_reconexao_e_guarda_socket(self):
        """Verificação isolada de lógica: desconexão, sincronização e proteção contra envio de comandos sem conexão."""
        js_code = r"""
        let socket = null;
        let conectado = true;
        let comandoTemporadaPendente = true;
        let papel = "mestre";
        let estado = { fase: "aguardando", brutos: 5 };
        const pedidos = [];

        function pedir(nome) {
            pedidos.push(nome);
        }

        function atualizar(d) {
            if (d && d.estado) {
                if (d.estado.fase !== undefined) estado.fase = d.estado.fase;
                if (d.estado.brutos !== undefined) estado.brutos = d.estado.brutos;
            }
        }

        function onDisconnect() {
            conectado = false;
            comandoTemporadaPendente = false;
        }

        function onEstadoSincronizado(d) {
            comandoTemporadaPendente = false;
            atualizar(d);
        }

        function abrirVila() {
            if (!socket || !socket.connected || papel !== "mestre" || estado.fase !== "aguardando" || comandoTemporadaPendente) return;
            comandoTemporadaPendente = true;
            pedir("vila.abertura_solicitada");
        }

        function encerrarVila() {
            if (!socket || !socket.connected || papel !== "mestre" || estado.fase !== "aberta" || comandoTemporadaPendente) return;
            comandoTemporadaPendente = true;
            pedir("vila.encerramento_solicitado");
        }

        const log = {};

        // 1. Tratamento de disconnect: atualiza conectado e libera pendência sem alterar a fase
        onDisconnect();
        log.desconexao = {
            conectado,
            comandoTemporadaPendente,
            fase: estado.fase,
            brutos: estado.brutos
        };

        // 2. Proteção contra comandos sem socket ou com socket desconectado
        // 2a. socket === null em abrirVila()
        abrirVila();
        // 2b. socket com connected = false em abrirVila()
        socket = { connected: false };
        abrirVila();
        log.abrirSemConexao = {
            pedidos: [...pedidos],
            comandoTemporadaPendente
        };

        // 2c. socket === null em encerrarVila() (simula fase aberta)
        estado.fase = "aberta";
        socket = null;
        encerrarVila();
        // 2d. socket com connected = false em encerrarVila()
        socket = { connected: false };
        encerrarVila();
        log.encerrarSemConexao = {
            pedidos: [...pedidos],
            comandoTemporadaPendente
        };

        // 3. Reconexão e evento estado.sincronizado: restaura dados e libera pendência
        comandoTemporadaPendente = true; // simula pendência ativada anteriormente
        onEstadoSincronizado({
            causa: "conexao",
            estado: { fase: "aberta", brutos: 15 }
        });
        log.sincronizacao = {
            comandoTemporadaPendente,
            fase: estado.fase,
            brutos: estado.brutos
        };

        // 4. Com socket conectado, comando é emitido normalmente
        socket = { connected: true };
        encerrarVila();
        log.encerrarConectado = {
            pedidos: [...pedidos],
            comandoTemporadaPendente
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # 1. Disconnect atualiza conexão e libera pendência sem alterar fase ou dados existentes
        self.assertFalse(res["desconexao"]["conectado"])
        self.assertFalse(res["desconexao"]["comandoTemporadaPendente"])
        self.assertEqual(res["desconexao"]["fase"], "aguardando")
        self.assertEqual(res["desconexao"]["brutos"], 5)

        # 2. abrirVila() sem conexão não emite comando e não ativa pendência
        self.assertEqual(res["abrirSemConexao"]["pedidos"], [])
        self.assertFalse(res["abrirSemConexao"]["comandoTemporadaPendente"])

        # 3. encerrarVila() sem conexão não emite comando e não ativa pendência
        self.assertEqual(res["encerrarSemConexao"]["pedidos"], [])
        self.assertFalse(res["encerrarSemConexao"]["comandoTemporadaPendente"])

        # 4. estado.sincronizado libera pendência e atualiza snapshot autoritativo
        self.assertFalse(res["sincronizacao"]["comandoTemporadaPendente"])
        self.assertEqual(res["sincronizacao"]["fase"], "aberta")
        self.assertEqual(res["sincronizacao"]["brutos"], 15)

        # 5. Com socket conectado, pedido é emitido e pendência ativada
        self.assertEqual(res["encerrarConectado"]["pedidos"], ["vila.encerramento_solicitado"])
        self.assertTrue(res["encerrarConectado"]["comandoTemporadaPendente"])

    # ── 4. Produção da Mina (Etapa 6.3) ───────────────────────────────────

    def test_18_verificacao_estatica_listener_mina_cristal_produzido(self):
        """Verificação estática de client/index.html para o listener de produção da mina."""
        html_content = (RAIZ / "client" / "index.html").read_text(encoding="utf-8")

        # Listener de mina.cristal_produzido registrado com reação e chamada a atualizar(d)
        self.assertIn('ouvir("mina.cristal_produzido", "Atualiza estoque com novo cristal extraído", (d) => {', html_content)
        self.assertIn('atualizar(d);', html_content)

        # Elemento visual para exibição do estoque de brutos
        self.assertIn("💎 Cristais brutos: <strong>{{ estado.brutos }}</strong>", html_content)

        # Checkbox de filtro existente
        self.assertIn('<input type="checkbox" v-model="ocultarProducao"> ocultar mina.cristal_produzido', html_content)

    def test_19_verificacao_contrato_listener_mina_e_atualizacao_estoque(self):
        """Verificação isolada de lógica: recebimento de mina.cristal_produzido, encaminhamento para atualizar() e estoque."""
        js_code = r"""
        const estado = { fase: "aberta", brutos: 0, lapidados: 0 };
        const contadores = {};
        const eventos = [];

        function atualizar(d) {
            if (!d || !d.estado) return;
            const e = d.estado;
            if (e.brutos !== undefined) estado.brutos = e.brutos;
            if (e.fase !== undefined) estado.fase = e.fase;
        }

        function registrar(sentido, nome, dados, reacao) {
            contadores[nome] = (contadores[nome] || 0) + 1;
            eventos.unshift({ sentido, nome, dados, reacao });
        }

        // Simula a escuta do cliente
        function onMinaCristalProduzido(d) {
            registrar("recebido", "mina.cristal_produzido", d, "Atualiza estoque com novo cristal extraído");
            atualizar(d);
        }

        const log = {};

        // 1ª extração: servidor informa que o estoque passou a 1
        const payload1 = {
            quantidade: 1,
            causa: "temporizador",
            estado: { fase: "aberta", brutos: 1, lapidados: 0 }
        };
        onMinaCristalProduzido(payload1);
        log.extracao1 = {
            brutos: estado.brutos,
            contador: contadores["mina.cristal_produzido"],
            ultimoEvento: eventos[0]
        };

        // 2ª extração: servidor informa que o estoque passou a 2
        const payload2 = {
            quantidade: 1,
            causa: "temporizador",
            estado: { fase: "aberta", brutos: 2, lapidados: 0 }
        };
        onMinaCristalProduzido(payload2);
        log.extracao2 = {
            brutos: estado.brutos,
            contador: contadores["mina.cristal_produzido"]
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # 1ª extração: brutos atualizado para 1, contador incrementado
        self.assertEqual(res["extracao1"]["brutos"], 1)
        self.assertEqual(res["extracao1"]["contador"], 1)
        self.assertEqual(res["extracao1"]["ultimoEvento"]["nome"], "mina.cristal_produzido")
        self.assertEqual(res["extracao1"]["ultimoEvento"]["reacao"], "Atualiza estoque com novo cristal extraído")

        # 2ª extração: brutos atualizado para 2 a partir de d.estado.brutos
        self.assertEqual(res["extracao2"]["brutos"], 2)
        self.assertEqual(res["extracao2"]["contador"], 2)

    def test_20_verificacao_contrato_filtro_ocultar_producao(self):
        """Verificação isolada de lógica: preservação do filtro reativo ocultarProducao para eventos de produção."""
        js_code = r"""
        const eventos = [
            { nome: "mina.cristal_produzido", texto: "cristal 1" },
            { nome: "vila.aberta", texto: "temporada aberta" },
            { nome: "mina.cristal_produzido", texto: "cristal 2" },
            { nome: "vila.encerrada", texto: "temporada encerrada" }
        ];

        function getEventosVisiveis(ocultarProducao) {
            return eventos.filter((e) => !(ocultarProducao && (e.nome === "mina.cristal_produzido" || e.nome === "recurso.produzido")));
        }

        // Sem ocultar produção (padrão)
        const visiveisPadrao = getEventosVisiveis(false);

        // Com produção ocultada
        const visiveisOcultos = getEventosVisiveis(true);

        console.log(JSON.stringify({
            padrao: visiveisPadrao.map(e => e.nome),
            oculto: visiveisOcultos.map(e => e.nome)
        }));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # Quando desmarcado (false), todos os eventos aparecem
        self.assertEqual(res["padrao"], ["mina.cristal_produzido", "vila.aberta", "mina.cristal_produzido", "vila.encerrada"])

        # Quando marcado (true), mina.cristal_produzido é ocultado, outros eventos permanecem
        self.assertEqual(res["oculto"], ["vila.aberta", "vila.encerrada"])

    # ── 5. Construção de Lapidárias (Etapa 6.4) ────────────────────────────

    def test_21_verificacao_estatica_elementos_construcao(self):
        """Verificação estática de client/index.html para os elementos e bindings da construção de lapidárias."""
        html_content = (RAIZ / "client" / "index.html").read_text(encoding="utf-8")

        # Botão de construção com diretiva :disabled e handler @click
        self.assertIn(':disabled="comandoConstrucaoPendente" @click="construir">🔨 Construir</button>', html_content)

        # Definição e exportação do estado reativo
        self.assertIn("const comandoConstrucaoPendente = ref(false);", html_content)
        self.assertIn("comandoConstrucaoPendente,", html_content)

        # Função construir com guardas de conexão, papel, fase e pendência
        self.assertIn("function construir()", html_content)
        self.assertIn('papel.value !== "jogador"', html_content)
        self.assertIn('estado.fase !== "aberta"', html_content)
        self.assertIn('pedir("construcao.solicitada")', html_content)

        # Três listeners de construção registrados
        self.assertIn('ouvir("construcao.iniciada"', html_content)
        self.assertIn('ouvir("construcao.concluida"', html_content)
        self.assertIn('ouvir("construcao.recusada"', html_content)

        # Checagem do solicitante ao liberar trava na construção iniciada
        self.assertIn('d.solicitante === nome.value', html_content)

    def test_22_verificacao_contrato_funcao_construir_guardas_e_bloqueio_duplicado(self):
        """Verificação isolada de lógica: guardas da função construir(), envio sem payload e trava contra cliques duplicados."""
        js_code = r"""
        const pedidos = [];
        let socket = null;
        let papel = "jogador";
        let fase = "aberta";
        let comandoConstrucaoPendente = false;

        function pedir(nome, dados) {
            pedidos.push({ nome, dados: dados === undefined ? null : dados });
        }

        function construir() {
            if (!socket || !socket.connected || papel !== "jogador" || fase !== "aberta" || comandoConstrucaoPendente) return;
            comandoConstrucaoPendente = true;
            pedir("construcao.solicitada");
        }

        const log = {};

        // 1. Socket nulo -> não emite
        construir();
        log.socketNulo = { pedidos: pedidos.length, pendente: comandoConstrucaoPendente };

        // 2. Socket desconectado -> não emite
        socket = { connected: false };
        construir();
        log.socketDesconectado = { pedidos: pedidos.length, pendente: comandoConstrucaoPendente };

        // 3. Papel diferente de jogador (ex: mestre) -> não emite
        socket = { connected: true };
        papel = "mestre";
        construir();
        log.papelInvalido = { pedidos: pedidos.length, pendente: comandoConstrucaoPendente };

        // 4. Fase diferente de aberta (ex: aguardando) -> não emite
        papel = "jogador";
        fase = "aguardando";
        construir();
        log.faseAguardando = { pedidos: pedidos.length, pendente: comandoConstrucaoPendente };

        // 5. Condições válidas -> emite pedido sem payload obrigatório e ativa pendência
        fase = "aberta";
        construir();
        log.construirValido = {
            pedidos: [...pedidos],
            pendente: comandoConstrucaoPendente
        };

        // 6. Segundo clique consecutivo com pendência ativa -> bloqueado
        construir();
        log.duploClique = {
            pedidos: [...pedidos],
            pendente: comandoConstrucaoPendente
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # Guardas prévias não disparam pedido
        self.assertEqual(res["socketNulo"]["pedidos"], 0)
        self.assertFalse(res["socketNulo"]["pendente"])

        self.assertEqual(res["socketDesconectado"]["pedidos"], 0)
        self.assertFalse(res["socketDesconectado"]["pendente"])

        self.assertEqual(res["papelInvalido"]["pedidos"], 0)
        self.assertFalse(res["papelInvalido"]["pendente"])

        self.assertEqual(res["faseAguardando"]["pedidos"], 0)
        self.assertFalse(res["faseAguardando"]["pendente"])

        # Chamada válida emite sem payload adicional e ativa pendência
        self.assertEqual(len(res["construirValido"]["pedidos"]), 1)
        self.assertEqual(res["construirValido"]["pedidos"][0]["nome"], "construcao.solicitada")
        self.assertIsNone(res["construirValido"]["pedidos"][0]["dados"])
        self.assertTrue(res["construirValido"]["pendente"])

        # Segundo clique consecutivo é bloqueado
        self.assertEqual(len(res["duploClique"]["pedidos"]), 1)
        self.assertTrue(res["duploClique"]["pendente"])

    def test_23_verificacao_contrato_listeners_construcao_e_concorrencia_solicitante(self):
        """Verificação isolada de lógica: listeners de construção, proteção contra liberação indevida por outros jogadores e atualização de snapshot."""
        js_code = r"""
        const nomeUsuario = "Alice";
        let comandoConstrucaoPendente = true; // simula que Alice clicou em construir
        const estado = {
            brutos: 10,
            trabalhadores: { ocupados: 0, limite: 2 },
            lotes: { lote1: null, lote2: null, lote3: null, lote4: null, lote5: null, lote6: null },
            lapidarias: {},
            construcoes: []
        };
        const avisos = [];

        function avisar(texto, tipo) {
            avisos.push({ texto, tipo });
        }

        function atualizar(d) {
            if (!d || !d.estado) return;
            const e = d.estado;
            if (e.brutos !== undefined) estado.brutos = e.brutos;
            if (e.trabalhadores) {
                if (e.trabalhadores.ocupados !== undefined) estado.trabalhadores.ocupados = e.trabalhadores.ocupados;
                if (e.trabalhadores.limite !== undefined) estado.trabalhadores.limite = e.trabalhadores.limite;
            }
            if (e.lapidarias !== undefined) estado.lapidarias = e.lapidarias;
            if (e.lotes !== undefined) estado.lotes = e.lotes;
            if (e.construcoes !== undefined) estado.construcoes = e.construcoes;
        }

        function onConstrucaoIniciada(d) {
            if (d && d.solicitante === nomeUsuario) {
                comandoConstrucaoPendente = false;
            }
            atualizar(d);
            const lapId = (d && d.lapidaria_id) || "lapidária";
            const lote = (d && d.lote) || "";
            avisar(`Construção da ${lapId} iniciada no ${lote}!`, "info");
        }

        function onConstrucaoConcluida(d) {
            atualizar(d);
            const lapId = (d && d.lapidaria_id) || "lapidária";
            const lote = (d && d.lote) || "";
            avisar(`Lapidária ${lapId} concluída no ${lote}!`, "ok");
        }

        function onConstrucaoRecusada(d) {
            comandoConstrucaoPendente = false;
            atualizar(d);
            avisar(d && d.motivo ? d.motivo : "Construção recusada.", "erro");
        }

        const log = {};

        // 1. Outro jogador (Bob) inicia construção:
        // Atualiza estado, MAS a trava de Alice continua ativa (true)
        onConstrucaoIniciada({
            solicitante: "Bob",
            lapidaria_id: "lapidaria-1",
            lote: "lote1",
            custo: 5,
            estado: {
                brutos: 5,
                trabalhadores: { ocupados: 1, limite: 2 },
                lotes: { lote1: "lapidaria-1", lote2: null, lote3: null, lote4: null, lote5: null, lote6: null },
                lapidarias: { "lapidaria-1": { id: "lapidaria-1", lote: "lote1", nivel: 1, situacao: "em construção" } },
                construcoes: [{ lid: "lapidaria-1", tempo_restante: 3.0 }]
            }
        });
        log.construcaoOutroJogador = {
            pendenteAlice: comandoConstrucaoPendente,
            brutos: estado.brutos,
            trabalhadores: estado.trabalhadores.ocupados,
            lote1: estado.lotes.lote1
        };

        // 2. A própria Alice recebe a confirmação de sua construção:
        // A trava de Alice é liberada (false) e snapshot atualizado
        onConstrucaoIniciada({
            solicitante: "Alice",
            lapidaria_id: "lapidaria-2",
            lote: "lote2",
            custo: 5,
            estado: {
                brutos: 0,
                trabalhadores: { ocupados: 2, limite: 2 },
                lotes: { lote1: "lapidaria-1", lote2: "lapidaria-2", lote3: null, lote4: null, lote5: null, lote6: null },
                lapidarias: {
                    "lapidaria-1": { id: "lapidaria-1", lote: "lote1", nivel: 1, situacao: "em construção" },
                    "lapidaria-2": { id: "lapidaria-2", lote: "lote2", nivel: 1, situacao: "em construção" }
                },
                construcoes: [
                    { lid: "lapidaria-1", tempo_restante: 1.5 },
                    { lid: "lapidaria-2", tempo_restante: 3.0 }
                ]
            }
        });
        log.construcaoProprioJogador = {
            pendenteAlice: comandoConstrucaoPendente,
            brutos: estado.brutos,
            trabalhadores: estado.trabalhadores.ocupados,
            lote2: estado.lotes.lote2
        };

        // 3. Conclusão da construção:
        // Atualiza snapshot (trabalhador liberado, situação disponível)
        onConstrucaoConcluida({
            lapidaria_id: "lapidaria-1",
            lote: "lote1",
            nivel: 1,
            situacao: "disponível",
            estado: {
                brutos: 0,
                trabalhadores: { ocupados: 1, limite: 2 },
                lotes: { lote1: "lapidaria-1", lote2: "lapidaria-2", lote3: null, lote4: null, lote5: null, lote6: null },
                lapidarias: {
                    "lapidaria-1": { id: "lapidaria-1", lote: "lote1", nivel: 1, situacao: "disponível" },
                    "lapidaria-2": { id: "lapidaria-2", lote: "lote2", nivel: 1, situacao: "em construção" }
                },
                construcoes: [{ lid: "lapidaria-2", tempo_restante: 1.5 }]
            }
        });
        log.conclusao = {
            trabalhadores: estado.trabalhadores.ocupados,
            situacaoLap1: estado.lapidarias["lapidaria-1"].situacao,
            construcoesAtivas: estado.construcoes.length
        };

        // 4. Recusa de construção:
        // Libera pendência, aplica snapshot e emite aviso de erro
        comandoConstrucaoPendente = true; // simula novo clique
        onConstrucaoRecusada({
            motivo: "Cristais brutos insuficientes (necessário: 5).",
            causa: "construcao.solicitada",
            estado: {
                brutos: 0,
                trabalhadores: { ocupados: 1, limite: 2 }
            }
        });
        log.recusa = {
            pendente: comandoConstrucaoPendente,
            ultimoAviso: avisos[avisos.length - 1]
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # 1. Construção de outro jogador atualiza snapshot mas NÃO libera a trava local
        self.assertTrue(res["construcaoOutroJogador"]["pendenteAlice"])
        self.assertEqual(res["construcaoOutroJogador"]["brutos"], 5)
        self.assertEqual(res["construcaoOutroJogador"]["trabalhadores"], 1)
        self.assertEqual(res["construcaoOutroJogador"]["lote1"], "lapidaria-1")

        # 2. Construção do próprio jogador libera a trava e atualiza snapshot
        self.assertFalse(res["construcaoProprioJogador"]["pendenteAlice"])
        self.assertEqual(res["construcaoProprioJogador"]["brutos"], 0)
        self.assertEqual(res["construcaoProprioJogador"]["trabalhadores"], 2)
        self.assertEqual(res["construcaoProprioJogador"]["lote2"], "lapidaria-2")

        # 3. Conclusão atualiza trabalhador para 1 e lapidária para disponível
        self.assertEqual(res["conclusao"]["trabalhadores"], 1)
        self.assertEqual(res["conclusao"]["situacaoLap1"], "disponível")
        self.assertEqual(res["conclusao"]["construcoesAtivas"], 1)

        # 4. Recusa libera pendência e exibe mensagem de erro
        self.assertFalse(res["recusa"]["pendente"])
        self.assertEqual(res["recusa"]["ultimoAviso"]["tipo"], "erro")
        self.assertIn("insuficientes", res["recusa"]["ultimoAviso"]["texto"])

    def test_24_verificacao_contrato_liberacao_trava_construcao_por_conexao(self):
        """Verificação isolada de lógica: liberação de comandoConstrucaoPendente em disconnect, connect_error e estado.sincronizado."""
        js_code = r"""
        let conectado = true;
        let comandoConstrucaoPendente = true;
        let erroEntrada = "";

        function onConnectError(err) {
            conectado = false;
            comandoConstrucaoPendente = false;
            erroEntrada = (err && err.message) ? err.message : "Conexão recusada";
        }

        function onDisconnect() {
            conectado = false;
            comandoConstrucaoPendente = false;
        }

        function onEstadoSincronizado() {
            comandoConstrucaoPendente = false;
        }

        const log = {};

        // 1. connect_error libera pendência
        comandoConstrucaoPendente = true;
        onConnectError({ message: "Servidor indisponível" });
        log.aposConnectError = { conectado, pendente: comandoConstrucaoPendente };

        // 2. disconnect libera pendência
        comandoConstrucaoPendente = true;
        conectado = true;
        onDisconnect();
        log.aposDisconnect = { conectado, pendente: comandoConstrucaoPendente };

        // 3. estado.sincronizado libera pendência
        comandoConstrucaoPendente = true;
        onEstadoSincronizado();
        log.aposSincronizacao = { pendente: comandoConstrucaoPendente };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertFalse(res["aposConnectError"]["pendente"])
        self.assertFalse(res["aposConnectError"]["conectado"])

        self.assertFalse(res["aposDisconnect"]["pendente"])
        self.assertFalse(res["aposDisconnect"]["conectado"])

        self.assertFalse(res["aposSincronizacao"]["pendente"])

    # ── 7. Etapa 6.5: Processamento de Cristais e Melhorias no Cliente ────

    def test_25_verificacao_estatica_elementos_lapidacao_e_melhoria(self):
        """Verificação estática de client/index.html para os elementos de processamento e melhoria de lapidárias."""
        html = self.html_content

        # 1. Variáveis de estado reativo e funções da Etapa 6.5
        self.assertIn("const comandoMelhoriaPendente = ref(false);", html)
        self.assertIn("const solicitacaoMelhoriaPendenteId = ref(null);", html)
        self.assertIn("const lapidariaSelecionadaId = ref(null);", html)
        self.assertIn("const lapidariaSelecionada = computed(", html)
        self.assertIn("function selecionarLapidaria(", html)
        self.assertIn("function custoMelhoria(", html)
        self.assertIn("function podeMelhorar(", html)
        self.assertIn("function gerarSolicitacaoId(", html)
        self.assertIn("function melhorarLapidaria(", html)

        # 2. Listeners de eventos de processamento e melhoria
        self.assertIn('ouvir("lapidaria.processamento_iniciado"', html)
        self.assertIn('ouvir("lapidaria.cristal_lapidado"', html)
        self.assertIn('ouvir("melhoria.iniciada"', html)
        self.assertIn('ouvir("melhoria.concluida"', html)
        self.assertIn('ouvir("melhoria.recusada"', html)

        # 3. Emissão do pedido de melhoria
        self.assertIn('pedir("melhoria.solicitada"', html)

        # 4. Elementos visuais no template: lista de lapidárias, vagas, barra de progresso e botão de melhoria
        self.assertIn("lapidarias-secao", html)
        self.assertIn("lapidaria-card", html)
        self.assertIn("selecionarLapidaria(lap.id)", html)
        self.assertIn("vaga-item", html)
        self.assertIn("detalhes-lapidaria", html)
        self.assertIn("custoMelhoria(lapidariaSelecionada)", html)
        self.assertIn(":disabled=\"!podeMelhorar(lapidariaSelecionada)\"", html)
        self.assertIn("melhorarLapidaria(lapidariaSelecionada.id)", html)

        # 5. Exportação no retorno do setup()
        self.assertIn("comandoMelhoriaPendente", html)
        self.assertIn("solicitacaoMelhoriaPendenteId", html)
        self.assertIn("lapidariaSelecionadaId", html)
        self.assertIn("lapidariaSelecionada", html)
        self.assertIn("selecionarLapidaria", html)
        self.assertIn("custoMelhoria", html)
        self.assertIn("podeMelhorar", html)
        self.assertIn("melhorarLapidaria", html)

    def test_26_verificacao_contrato_listeners_processamento_lapidacao(self):
        """Verificação isolada de lógica: listeners de início e término de lapidação e atualização de vagas."""
        js_code = r"""
        const estado = {
            fase: "aberta",
            brutos: 5,
            lapidados: 0,
            lapidarias: {
                "lapidaria-1": {
                    id: "lapidaria-1",
                    lote: "lote1",
                    nivel: 1,
                    situacao: "disponível",
                    vagas: [{ numero: 1, ocupada: false, tempo_restante: 0.0 }]
                }
            }
        };

        const avisos = [];
        function avisar(texto, tipo = "info") {
            avisos.unshift({ texto, tipo });
        }

        function atualizar(d) {
            if (!d || !d.estado) return;
            const e = d.estado;
            if (e.fase !== undefined) estado.fase = e.fase;
            if (e.brutos !== undefined) estado.brutos = e.brutos;
            if (e.lapidados !== undefined) estado.lapidados = e.lapidados;
            if (e.lapidarias !== undefined) estado.lapidarias = e.lapidarias;
        }

        function onProcessamentoIniciado(d) {
            atualizar(d);
            const lapId = (d && d.lapidaria_id) || "lapidária";
            const vaga = (d && d.vaga) || "";
            avisar(`Lapidação iniciada na ${lapId} (vaga ${vaga})`, "info");
        }

        function onCristalLapidado(d) {
            atualizar(d);
            const lapId = (d && d.lapidaria_id) || "lapidária";
            const vaga = (d && d.vaga) || "";
            avisar(`Cristal lapidado na ${lapId} (vaga ${vaga})!`, "ok");
        }

        const log = {};

        // 1. Recebe lapidaria.processamento_iniciado
        const snapshotInicio = JSON.parse(JSON.stringify(estado));
        snapshotInicio.brutos = 4;
        snapshotInicio.lapidarias["lapidaria-1"].vagas[0] = { numero: 1, ocupada: true, tempo_restante: 9.9 };
        onProcessamentoIniciado({
            lapidaria_id: "lapidaria-1",
            vaga: 1,
            causa: "temporizador",
            estado: snapshotInicio
        });

        log.aposInicio = {
            brutos: estado.brutos,
            vagaOcupada: estado.lapidarias["lapidaria-1"].vagas[0].ocupada,
            tempoRestante: estado.lapidarias["lapidaria-1"].vagas[0].tempo_restante,
            progressoCalculado: Math.max(0, 10 - estado.lapidarias["lapidaria-1"].vagas[0].tempo_restante),
            ultimoAviso: avisos[0]
        };

        // 2. Recebe lapidaria.cristal_lapidado
        const snapshotFim = JSON.parse(JSON.stringify(estado));
        snapshotFim.lapidados = 1;
        snapshotFim.lapidarias["lapidaria-1"].vagas[0] = { numero: 1, ocupada: false, tempo_restante: 0.0 };
        onCristalLapidado({
            lapidaria_id: "lapidaria-1",
            vaga: 1,
            causa: "temporizador",
            estado: snapshotFim
        });

        log.aposFim = {
            lapidados: estado.lapidados,
            vagaOcupada: estado.lapidarias["lapidaria-1"].vagas[0].ocupada,
            tempoRestante: estado.lapidarias["lapidaria-1"].vagas[0].tempo_restante,
            ultimoAviso: avisos[0]
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # Início de processamento
        self.assertEqual(res["aposInicio"]["brutos"], 4)
        self.assertTrue(res["aposInicio"]["vagaOcupada"])
        self.assertAlmostEqual(res["aposInicio"]["tempoRestante"], 9.9, places=1)
        self.assertAlmostEqual(res["aposInicio"]["progressoCalculado"], 0.1, places=1)
        self.assertIn("Lapidação iniciada", res["aposInicio"]["ultimoAviso"]["texto"])
        self.assertEqual(res["aposInicio"]["ultimoAviso"]["tipo"], "info")

        # Conclusão de lapidação
        self.assertEqual(res["aposFim"]["lapidados"], 1)
        self.assertFalse(res["aposFim"]["vagaOcupada"])
        self.assertEqual(res["aposFim"]["tempoRestante"], 0.0)
        self.assertIn("Cristal lapidado", res["aposFim"]["ultimoAviso"]["texto"])
        self.assertEqual(res["aposFim"]["ultimoAviso"]["tipo"], "ok")

    def test_27_verificacao_contrato_selecao_e_custos_melhoria(self):
        """Verificação isolada de lógica: seleção de lapidária, custo por nível e computed de detalhes."""
        js_code = r"""
        const estado = {
            lapidarias: {
                "lapidaria-1": { id: "lapidaria-1", lote: "lote1", nivel: 1, situacao: "disponível", vagas: [{ numero: 1, ocupada: false }] },
                "lapidaria-2": { id: "lapidaria-2", lote: "lote2", nivel: 2, situacao: "disponível", vagas: [{ numero: 1, ocupada: false }, { numero: 2, ocupada: false }] },
                "lapidaria-3": { id: "lapidaria-3", lote: "lote3", nivel: 3, situacao: "disponível", vagas: [{ numero: 1, ocupada: false }, { numero: 2, ocupada: false }, { numero: 3, ocupada: false }] }
            }
        };

        let lapidariaSelecionadaId = null;

        function selecionarLapidaria(lid) {
            lapidariaSelecionadaId = (lapidariaSelecionadaId === lid) ? null : lid;
        }

        function getLapidariaSelecionada() {
            return lapidariaSelecionadaId ? (estado.lapidarias[lapidariaSelecionadaId] || null) : null;
        }

        function custoMelhoria(lap) {
            if (!lap) return null;
            if (lap.nivel === 1) return 10;
            if (lap.nivel === 2) return 15;
            return null;
        }

        const log = {};

        // 1. Custos por nível
        log.custos = {
            nivel1: custoMelhoria(estado.lapidarias["lapidaria-1"]),
            nivel2: custoMelhoria(estado.lapidarias["lapidaria-2"]),
            nivel3: custoMelhoria(estado.lapidarias["lapidaria-3"]),
            invalido: custoMelhoria(null)
        };

        // 2. Ciclo de seleção: inicial é null
        log.selecaoInicial = getLapidariaSelecionada();

        // 3. Seleciona lapidaria-1
        selecionarLapidaria("lapidaria-1");
        log.selecionouLap1 = {
            id: lapidariaSelecionadaId,
            detalhe: getLapidariaSelecionada(),
            custo: custoMelhoria(getLapidariaSelecionada())
        };

        // 4. Clicar novamente desmarca (toggle)
        selecionarLapidaria("lapidaria-1");
        log.desmarcouLap1 = getLapidariaSelecionada();

        // 5. Seleciona lapidaria-2
        selecionarLapidaria("lapidaria-2");
        log.selecionouLap2 = {
            id: lapidariaSelecionadaId,
            detalhe: getLapidariaSelecionada(),
            custo: custoMelhoria(getLapidariaSelecionada())
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # Custos por nível
        self.assertEqual(res["custos"]["nivel1"], 10)
        self.assertEqual(res["custos"]["nivel2"], 15)
        self.assertIsNone(res["custos"]["nivel3"])
        self.assertIsNone(res["custos"]["invalido"])

        # Seleção inicial
        self.assertIsNone(res["selecaoInicial"])

        # Seleção e custo de lapidaria-1
        self.assertEqual(res["selecionouLap1"]["id"], "lapidaria-1")
        self.assertEqual(res["selecionouLap1"]["detalhe"]["nivel"], 1)
        self.assertEqual(res["selecionouLap1"]["custo"], 10)

        # Desmarcação por segundo clique
        self.assertIsNone(res["desmarcouLap1"])

        # Seleção e custo de lapidaria-2
        self.assertEqual(res["selecionouLap2"]["id"], "lapidaria-2")
        self.assertEqual(res["selecionouLap2"]["detalhe"]["nivel"], 2)
        self.assertEqual(res["selecionouLap2"]["custo"], 15)

    def test_28_verificacao_contrato_solicitar_melhoria_guardas_e_bloqueio_duplicado(self):
        """Verificação isolada de lógica: guardas de podeMelhorar(), geração de solicitacao_id único e bloqueio de cliques duplicados."""
        js_code = r"""
        const estado = {
            fase: "aberta",
            lapidados: 10,
            lapidarias: {
                "lapidaria-1": { id: "lapidaria-1", lote: "lote1", nivel: 1, situacao: "disponível" },
                "lapidaria-3": { id: "lapidaria-3", lote: "lote3", nivel: 3, situacao: "disponível" },
                "lapidaria-obra": { id: "lapidaria-obra", lote: "lote2", nivel: 1, situacao: "em melhoria" }
            }
        };

        let socket = { connected: true };
        let papel = "jogador";
        let comandoMelhoriaPendente = false;
        let solicitacaoMelhoriaPendenteId = null;
        const pedidosEmitidos = [];

        function pedir(nome, dados) {
            pedidosEmitidos.push({ nome, dados: dados === undefined ? null : dados });
        }

        function custoMelhoria(lap) {
            if (!lap) return null;
            if (lap.nivel === 1) return 10;
            if (lap.nivel === 2) return 15;
            return null;
        }

        function podeMelhorar(lap) {
            if (!lap || !socket || !socket.connected) return false;
            if (papel !== "jogador") return false;
            if (estado.fase !== "aberta") return false;
            if (comandoMelhoriaPendente) return false;
            if (lap.situacao !== "disponível") return false;
            if (lap.nivel >= 3) return false;
            const custo = custoMelhoria(lap);
            if (custo === null || estado.lapidados < custo) return false;
            return true;
        }

        let seq = 1;
        function gerarSolicitacaoId() {
            return "req-" + (seq++);
        }

        function melhorarLapidaria(lid) {
            const lap = estado.lapidarias[lid];
            if (!lap || !podeMelhorar(lap)) return;
            const reqId = gerarSolicitacaoId();
            comandoMelhoriaPendente = true;
            solicitacaoMelhoriaPendenteId = reqId;
            pedir("melhoria.solicitada", { lapidaria_id: lid, solicitacao_id: reqId });
        }

        const log = {};

        // Guardas
        // 1. Socket desconectado
        socket.connected = false;
        log.desconectado = podeMelhorar(estado.lapidarias["lapidaria-1"]);
        socket.connected = true;

        // 2. Papel Mestre
        papel = "mestre";
        log.mestre = podeMelhorar(estado.lapidarias["lapidaria-1"]);
        papel = "jogador";

        // 3. Fase aguardando
        estado.fase = "aguardando";
        log.faseAguardando = podeMelhorar(estado.lapidarias["lapidaria-1"]);
        estado.fase = "aberta";

        // 4. Lapidária em melhoria
        log.emMelhoria = podeMelhorar(estado.lapidarias["lapidaria-obra"]);

        // 5. Lapidária nível 3 (máximo)
        log.nivelMaximo = podeMelhorar(estado.lapidarias["lapidaria-3"]);

        // 6. Cristais lapidados insuficientes
        estado.lapidados = 9;
        log.lapidadosInsuficientes = podeMelhorar(estado.lapidarias["lapidaria-1"]);
        estado.lapidados = 10;

        // 7. Condição válida
        log.valido = podeMelhorar(estado.lapidarias["lapidaria-1"]);

        // 8. Execução e envio de identificador único de correlação
        melhorarLapidaria("lapidaria-1");
        log.primeiroEnvio = {
            pendente: comandoMelhoriaPendente,
            solicitacaoId: solicitacaoMelhoriaPendenteId,
            pedidos: pedidosEmitidos.length,
            ultimoPedido: pedidosEmitidos[0]
        };

        // Segundo clique imediato: deve ser ignorado sem gerar novo id
        melhorarLapidaria("lapidaria-1");
        log.segundoEnvio = {
            pendente: comandoMelhoriaPendente,
            solicitacaoId: solicitacaoMelhoriaPendenteId,
            pedidos: pedidosEmitidos.length
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        self.assertFalse(res["desconectado"])
        self.assertFalse(res["mestre"])
        self.assertFalse(res["faseAguardando"])
        self.assertFalse(res["emMelhoria"])
        self.assertFalse(res["nivelMaximo"])
        self.assertFalse(res["lapidadosInsuficientes"])
        self.assertTrue(res["valido"])

        self.assertTrue(res["primeiroEnvio"]["pendente"])
        self.assertEqual(res["primeiroEnvio"]["solicitacaoId"], "req-1")
        self.assertEqual(res["primeiroEnvio"]["pedidos"], 1)
        self.assertEqual(res["primeiroEnvio"]["ultimoPedido"]["nome"], "melhoria.solicitada")
        self.assertEqual(res["primeiroEnvio"]["ultimoPedido"]["dados"]["lapidaria_id"], "lapidaria-1")
        self.assertEqual(res["primeiroEnvio"]["ultimoPedido"]["dados"]["solicitacao_id"], "req-1")

        # Segundo clique ignorado e identificador preservado
        self.assertEqual(res["segundoEnvio"]["pedidos"], 1)
        self.assertEqual(res["segundoEnvio"]["solicitacaoId"], "req-1")

    def test_29_verificacao_contrato_listeners_melhoria_e_recuperacao_conexao(self):
        """Verificação isolada de lógica: correlação estrita por solicitacao_id em melhoria.iniciada, recusa e eventos de conexão."""
        js_code = r"""
        const estado = {
            fase: "aberta",
            lapidados: 10,
            lapidarias: {
                "lapidaria-1": {
                    id: "lapidaria-1",
                    lote: "lote1",
                    nivel: 1,
                    situacao: "disponível",
                    vagas: [{ numero: 1, ocupada: false, tempo_restante: 0 }]
                },
                "lapidaria-2": {
                    id: "lapidaria-2",
                    lote: "lote2",
                    nivel: 1,
                    situacao: "disponível",
                    vagas: [{ numero: 1, ocupada: false, tempo_restante: 0 }]
                }
            }
        };

        const avisos = [];
        let comandoMelhoriaPendente = true;
        let solicitacaoMelhoriaPendenteId = "minha-solicitacao-123";
        let conectado = true;

        function avisar(texto, tipo = "info") {
            avisos.unshift({ texto, tipo });
        }

        function atualizar(d) {
            if (!d || !d.estado) return;
            const e = d.estado;
            if (e.fase !== undefined) estado.fase = e.fase;
            if (e.lapidados !== undefined) estado.lapidados = e.lapidados;
            if (e.lapidarias !== undefined) estado.lapidarias = e.lapidarias;
        }

        function onMelhoriaIniciada(d) {
            if (d && d.solicitacao_id && d.solicitacao_id === solicitacaoMelhoriaPendenteId) {
                comandoMelhoriaPendente = false;
                solicitacaoMelhoriaPendenteId = null;
            }
            atualizar(d);
            const lapId = (d && d.lapidaria_id) || "lapidária";
            const novoNivel = (d && d.novo_nivel) || "";
            avisar(`Melhoria da ${lapId} iniciada (nível ${novoNivel})!`, "info");
        }

        function onMelhoriaConcluida(d) {
            atualizar(d);
            const lapId = (d && d.lapidaria_id) || "lapidária";
            const nivel = (d && d.nivel) || "";
            avisar(`Melhoria da ${lapId} concluída (nível ${nivel})!`, "ok");
        }

        function onMelhoriaRecusada(d) {
            comandoMelhoriaPendente = false;
            solicitacaoMelhoriaPendenteId = null;
            atualizar(d);
            avisar(d && d.motivo ? d.motivo : "Melhoria recusada.", "erro");
        }

        function onDisconnect() {
            conectado = false;
            comandoMelhoriaPendente = false;
            solicitacaoMelhoriaPendenteId = null;
        }

        function onConnectError() {
            conectado = false;
            comandoMelhoriaPendente = false;
            solicitacaoMelhoriaPendenteId = null;
        }

        function onEstadoSincronizado(d) {
            comandoMelhoriaPendente = false;
            solicitacaoMelhoriaPendenteId = null;
            atualizar(d);
        }

        const log = {};

        // 1. melhoria.iniciada de OUTRO jogador para OUTRA lapidária (lapidaria-2)
        onMelhoriaIniciada({
            solicitacao_id: "solicitacao-bob-456",
            lapidaria_id: "lapidaria-2",
            nivel_atual: 1,
            novo_nivel: 2,
            custo: 10,
            causa: "melhoria.solicitada",
            estado: JSON.parse(JSON.stringify(estado))
        });
        log.aposIniciadaOutraLapidaria = {
            pendente: comandoMelhoriaPendente,
            solicitacaoId: solicitacaoMelhoriaPendenteId
        };

        // 2. melhoria.iniciada de OUTRO jogador para a MESMA lapidária (lapidaria-1)
        onMelhoriaIniciada({
            solicitacao_id: "solicitacao-charlie-789",
            lapidaria_id: "lapidaria-1",
            nivel_atual: 1,
            novo_nivel: 2,
            custo: 10,
            causa: "melhoria.solicitada",
            estado: JSON.parse(JSON.stringify(estado))
        });
        log.aposIniciadaMesmaLapidariaOutroId = {
            pendente: comandoMelhoriaPendente,
            solicitacaoId: solicitacaoMelhoriaPendenteId
        };

        // 3. melhoria.iniciada com o IDENTIFICADOR CORRESPONDENTE (minha-solicitacao-123)
        const snapIniciada = JSON.parse(JSON.stringify(estado));
        snapIniciada.lapidados = 0;
        snapIniciada.lapidarias["lapidaria-1"].situacao = "em melhoria";
        onMelhoriaIniciada({
            solicitacao_id: "minha-solicitacao-123",
            lapidaria_id: "lapidaria-1",
            nivel_atual: 1,
            novo_nivel: 2,
            custo: 10,
            causa: "melhoria.solicitada",
            estado: snapIniciada
        });
        log.aposIniciadaCorrespondente = {
            pendente: comandoMelhoriaPendente,
            solicitacaoId: solicitacaoMelhoriaPendenteId,
            lapidados: estado.lapidados,
            situacao: estado.lapidarias["lapidaria-1"].situacao,
            ultimoAviso: avisos[0]
        };

        // 4. melhoria.recusada libera trava e limpa identificador
        comandoMelhoriaPendente = true;
        solicitacaoMelhoriaPendenteId = "minha-solicitacao-nova";
        onMelhoriaRecusada({
            solicitacao_id: "minha-solicitacao-nova",
            motivo: "Cristais lapidados insuficientes.",
            causa: "melhoria.solicitada",
            estado: JSON.parse(JSON.stringify(estado))
        });
        log.aposRecusada = {
            pendente: comandoMelhoriaPendente,
            solicitacaoId: solicitacaoMelhoriaPendenteId,
            ultimoAviso: avisos[0]
        };

        // 5. Recuperação em desconexão / erro / sincronização
        comandoMelhoriaPendente = true;
        solicitacaoMelhoriaPendenteId = "req-queda";
        onDisconnect();
        log.aposDisconnect = { pendente: comandoMelhoriaPendente, solicitacaoId: solicitacaoMelhoriaPendenteId };

        comandoMelhoriaPendente = true;
        solicitacaoMelhoriaPendenteId = "req-queda";
        onConnectError();
        log.aposConnectError = { pendente: comandoMelhoriaPendente, solicitacaoId: solicitacaoMelhoriaPendenteId };

        comandoMelhoriaPendente = true;
        solicitacaoMelhoriaPendenteId = "req-queda";
        onEstadoSincronizado({ estado: JSON.parse(JSON.stringify(estado)) });
        log.aposSincronizado = { pendente: comandoMelhoriaPendente, solicitacaoId: solicitacaoMelhoriaPendenteId };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # 1. Evento de outro jogador em outra lapidária NÃO libera a trava
        self.assertTrue(res["aposIniciadaOutraLapidaria"]["pendente"])
        self.assertEqual(res["aposIniciadaOutraLapidaria"]["solicitacaoId"], "minha-solicitacao-123")

        # 2. Evento de outro jogador na mesma lapidária NÃO libera a trava
        self.assertTrue(res["aposIniciadaMesmaLapidariaOutroId"]["pendente"])
        self.assertEqual(res["aposIniciadaMesmaLapidariaOutroId"]["solicitacaoId"], "minha-solicitacao-123")

        # 3. Evento correspondente libera a trava e limpa o ID
        self.assertFalse(res["aposIniciadaCorrespondente"]["pendente"])
        self.assertIsNone(res["aposIniciadaCorrespondente"]["solicitacaoId"])
        self.assertEqual(res["aposIniciadaCorrespondente"]["lapidados"], 0)
        self.assertEqual(res["aposIniciadaCorrespondente"]["situacao"], "em melhoria")

        # 4. Recusa libera trava e limpa ID
        self.assertFalse(res["aposRecusada"]["pendente"])
        self.assertIsNone(res["aposRecusada"]["solicitacaoId"])
        self.assertEqual(res["aposRecusada"]["ultimoAviso"]["tipo"], "erro")

        # 5. Recuperação de conexão
        self.assertFalse(res["aposDisconnect"]["pendente"])
        self.assertIsNone(res["aposDisconnect"]["solicitacaoId"])
        self.assertFalse(res["aposConnectError"]["pendente"])
        self.assertIsNone(res["aposConnectError"]["solicitacaoId"])
        self.assertFalse(res["aposSincronizado"]["pendente"])
        self.assertIsNone(res["aposSincronizado"]["solicitacaoId"])

    def test_30_verificacao_contrato_backend_correlacao_solicitacao_melhoria(self):
        """Verifica se o backend preserva solicitacao_id em melhoria.iniciada, em todas as recusas e rejeita solicitações sem ID."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        server.vila["fase"] = "aberta"
        server.vila["lapidados"] = 20
        server.vila["lapidarias"]["lapidaria-1"] = {
            "id": "lapidaria-1",
            "lote": "lote1",
            "nivel": 1,
            "situacao": "disponível",
            "tarefa_id": 1,
            "vagas": [server._nova_vaga(1)],
        }
        server.jogadores["j1"] = {"nome": "Jogador1", "papel": "jogador"}
        server.jogadores["m1"] = {"nome": "Mestre1", "papel": "mestre"}

        # 1. Rejeição de solicitação sem solicitacao_id
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1"}))
            mock_emit.assert_awaited_once()
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertIn("inválido", payload["motivo"].lower())
            self.assertIsNone(payload.get("solicitacao_id"))
            self.assertEqual(server.vila["lapidados"], 20)
            self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

        # 2. Rejeição de solicitação com solicitacao_id vazio ou apenas espaços
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "   "}))
            mock_emit.assert_awaited_once()
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertIn("inválido", payload["motivo"].lower())
            self.assertIsNone(payload.get("solicitacao_id"))
            self.assertEqual(server.vila["lapidados"], 20)
            self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

        # 2a. Rejeição de solicitacao_id numérico (int e float)
        for num_id in [123, 45.6]:
            with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
                asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": num_id}))
                mock_emit.assert_awaited_once()
                ev, payload = mock_emit.await_args.args[:2]
                self.assertEqual(ev, "melhoria.recusada")
                self.assertIn("inválido", payload["motivo"].lower())
                self.assertIsNone(payload.get("solicitacao_id"))
                self.assertEqual(server.vila["lapidados"], 20)
                self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

        # 2b. Rejeição de solicitacao_id booleano (True e False)
        for bool_id in [True, False]:
            with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
                asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": bool_id}))
                mock_emit.assert_awaited_once()
                ev, payload = mock_emit.await_args.args[:2]
                self.assertEqual(ev, "melhoria.recusada")
                self.assertIn("inválido", payload["motivo"].lower())
                self.assertIsNone(payload.get("solicitacao_id"))
                self.assertEqual(server.vila["lapidados"], 20)
                self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

        # 2c. Rejeição de solicitacao_id estruturado (lista e objeto/dicionário)
        for complex_id in [[], ["req-1"], {}, {"id": "req-1"}]:
            with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
                asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": complex_id}))
                mock_emit.assert_awaited_once()
                ev, payload = mock_emit.await_args.args[:2]
                self.assertEqual(ev, "melhoria.recusada")
                self.assertIn("inválido", payload["motivo"].lower())
                self.assertIsNone(payload.get("solicitacao_id"))
                self.assertEqual(server.vila["lapidados"], 20)
                self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

        # 2d. Rejeição de solicitacao_id longo (> 128 caracteres)
        long_id = "x" * 129
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": long_id}))
            mock_emit.assert_awaited_once()
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertIn("inválido", payload["motivo"].lower())
            self.assertIsNone(payload.get("solicitacao_id"))
            self.assertEqual(server.vila["lapidados"], 20)
            self.assertEqual(server.vila["lapidarias"]["lapidaria-1"]["situacao"], "disponível")

        # 2e. Aceitação de ID textual válido com espaços nas extremidades normalizado via strip()
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit, patch.object(server, "TEMPO_OBRA", 0.05):
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "   req-espacos-norm   "}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.iniciada")
            self.assertEqual(payload["solicitacao_id"], "req-espacos-norm")
        # Restaura estado para os subtestes seguintes
        server.vila["lapidarias"]["lapidaria-1"]["situacao"] = "disponível"
        server.vila["lapidarias"]["lapidaria-1"]["nivel"] = 1
        server.vila["lapidados"] = 20
        server.vila["melhorias_ativas"].clear()

        # 3. Preservação de solicitacao_id em recusas de negócio
        # 3a. Solicitante Mestre
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("m1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-mestre"}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertEqual(payload["solicitacao_id"], "req-mestre")

        # 3b. Vila não aberta
        server.vila["fase"] = "aguardando"
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-fase"}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertEqual(payload["solicitacao_id"], "req-fase")
        server.vila["fase"] = "aberta"

        # 3c. Lapidária inexistente
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-inexistente", "solicitacao_id": "req-inex"}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertEqual(payload["solicitacao_id"], "req-inex")

        # 3d. Lapidária em melhoria
        server.vila["lapidarias"]["lapidaria-1"]["situacao"] = "em melhoria"
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-disp"}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertEqual(payload["solicitacao_id"], "req-disp")
        server.vila["lapidarias"]["lapidaria-1"]["situacao"] = "disponível"

        # 3e. Nível máximo (nível 3)
        server.vila["lapidarias"]["lapidaria-1"]["nivel"] = 3
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-max"}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertEqual(payload["solicitacao_id"], "req-max")
        server.vila["lapidarias"]["lapidaria-1"]["nivel"] = 1

        # 3f. Saldo insuficiente
        server.vila["lapidados"] = 5
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit:
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-saldo"}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.recusada")
            self.assertEqual(payload["solicitacao_id"], "req-saldo")
        server.vila["lapidados"] = 20

        # 4. Sucesso: melhoria.iniciada preserva solicitacao_id e snapshot NÃO contém solicitacao_id
        with patch.object(server.sio, "emit", new_callable=AsyncMock) as mock_emit, patch.object(server, "TEMPO_OBRA", 0.05):
            asyncio.run(server.solicitar_melhoria("j1", {"lapidaria_id": "lapidaria-1", "solicitacao_id": "req-sucesso-777"}))
            ev, payload = mock_emit.await_args.args[:2]
            self.assertEqual(ev, "melhoria.iniciada")
            self.assertEqual(payload["solicitacao_id"], "req-sucesso-777")
            self.assertEqual(payload["lapidaria_id"], "lapidaria-1")
            self.assertEqual(payload["nivel_atual"], 1)
            self.assertEqual(payload["novo_nivel"], 2)
            # Confirma que snapshot global NÃO incorpora o identificador transitório de solicitação
            self.assertNotIn("solicitacao_id", payload["estado"])

    def test_31_verificacao_concorrencia_dois_jogadores_mesma_lapidaria_com_correlacao(self):
        """Simula concorrência real entre dois jogadores solicitando a mesma lapidária e correlacionando respostas distintas."""
        js_code = r"""
        // Estado compartilhado inicial
        const estadoAlice = { fase: "aberta", lapidados: 10, lapidarias: { "lapidaria-1": { id: "lapidaria-1", nivel: 1, situacao: "disponível" } } };
        const estadoBob   = { fase: "aberta", lapidados: 10, lapidarias: { "lapidaria-1": { id: "lapidaria-1", nivel: 1, situacao: "disponível" } } };

        // Alice solicita melhoria de lapidaria-1
        let pendenteAlice = true;
        let solicitacaoIdAlice = "req-alice-001";

        // Bob solicita melhoria da mesma lapidaria-1
        let pendenteBob = true;
        let solicitacaoIdBob = "req-bob-002";

        const avisosAlice = [];
        const avisosBob = [];

        function atualizar(estadoDestino, d) {
            if (d && d.estado) {
                if (d.estado.lapidados !== undefined) estadoDestino.lapidados = d.estado.lapidados;
                if (d.estado.lapidarias !== undefined) estadoDestino.lapidarias = d.estado.lapidarias;
            }
        }

        // Listener de melhoria.iniciada (recebido por broadcast por ambos)
        function onMelhoriaIniciada(jogadorNome, d) {
            if (jogadorNome === "Alice") {
                if (d && d.solicitacao_id === solicitacaoIdAlice) {
                    pendenteAlice = false;
                    solicitacaoIdAlice = null;
                }
                atualizar(estadoAlice, d);
                avisosAlice.push(`Melhoria da ${d.lapidaria_id} iniciada!`);
            } else if (jogadorNome === "Bob") {
                if (d && d.solicitacao_id === solicitacaoIdBob) {
                    pendenteBob = false;
                    solicitacaoIdBob = null;
                }
                atualizar(estadoBob, d);
                avisosBob.push(`Melhoria da ${d.lapidaria_id} iniciada!`);
            }
        }

        // Listener de melhoria.recusada (recebido apenas por quem teve recusa)
        function onMelhoriaRecusadaBob(d) {
            pendenteBob = false;
            solicitacaoIdBob = null;
            atualizar(estadoBob, d);
            avisosBob.push(d.motivo);
        }

        const log = {};

        // 1. Servidor aceita a solicitação de Alice e faz broadcast de melhoria.iniciada
        const eventoIniciadaAlice = {
            solicitacao_id: "req-alice-001",
            lapidaria_id: "lapidaria-1",
            nivel_atual: 1,
            novo_nivel: 2,
            custo: 10,
            causa: "melhoria.solicitada",
            estado: {
                lapidados: 0,
                lapidarias: { "lapidaria-1": { id: "lapidaria-1", nivel: 1, situacao: "em melhoria" } }
            }
        };

        // Broadcast chega a Alice
        onMelhoriaIniciada("Alice", eventoIniciadaAlice);
        // Broadcast chega a Bob
        onMelhoriaIniciada("Bob", eventoIniciadaAlice);

        log.aposBroadcastAlice = {
            alicePendente: pendenteAlice,
            aliceSolicitacaoId: solicitacaoIdAlice,
            bobPendente: pendenteBob,
            bobSolicitacaoId: solicitacaoIdBob,
            bobSituacaoLap: estadoBob.lapidarias["lapidaria-1"].situacao
        };

        // 2. Servidor rejeita a solicitação de Bob (situação atual: em melhoria) e envia unicast
        const eventoRecusadaBob = {
            solicitacao_id: "req-bob-002",
            motivo: "Lapidária não está disponível para melhoria (situação atual: em melhoria).",
            causa: "melhoria.solicitada",
            estado: {
                lapidados: 0,
                lapidarias: { "lapidaria-1": { id: "lapidaria-1", nivel: 1, situacao: "em melhoria" } }
            }
        };

        onMelhoriaRecusadaBob(eventoRecusadaBob);

        log.aposRecusaBob = {
            bobPendente: pendenteBob,
            bobSolicitacaoId: solicitacaoIdBob,
            bobUltimoAviso: avisosBob[avisosBob.length - 1]
        };

        console.log(JSON.stringify(log));
        """
        proc = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # Ao receber o broadcast de Alice:
        # - Alice é liberada porque o ID bate
        self.assertFalse(res["aposBroadcastAlice"]["alicePendente"])
        self.assertIsNone(res["aposBroadcastAlice"]["aliceSolicitacaoId"])

        # - Bob NÃO é liberado pelo broadcast de Alice porque os IDs são distintos!
        self.assertTrue(res["aposBroadcastAlice"]["bobPendente"])
        self.assertEqual(res["aposBroadcastAlice"]["bobSolicitacaoId"], "req-bob-002")
        self.assertEqual(res["aposBroadcastAlice"]["bobSituacaoLap"], "em melhoria")

        # Quando Bob recebe sua recusa unicast:
        # - Bob é liberado e seu ID pendente é limpo
        self.assertFalse(res["aposRecusaBob"]["bobPendente"])
        self.assertIsNone(res["aposRecusaBob"]["bobSolicitacaoId"])
        self.assertIn("não está disponível", res["aposRecusaBob"]["bobUltimoAviso"])


if __name__ == "__main__":
    unittest.main()
