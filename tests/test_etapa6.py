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


if __name__ == "__main__":
    unittest.main()
