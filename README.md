# Vila em Tempo Real — Vila dos Cristais

## Integrantes
- Leonardo Ávila — @LeonardoAvilaa

## Descrição
A **Vila dos Cristais** é uma aplicação cooperativa em tempo real desenvolvida sob o paradigma orientado a eventos. A vila opera em regime comunitário e compartilhado, sustentada pela extração contínua de **cristais brutos** (produzidos automaticamente pela Mina a cada 2 segundos) e pelo seu beneficiamento em **cristais lapidados** (recurso refinado obtido pelo processamento de cristais brutos nas Lapidárias, com duração de 10 segundos por unidade).

O sistema conta com gestão autoritativa centralizada no servidor, controle de temporada pelo Mestre, fila global FIFO determinística para distribuição de cristais entre vagas, limite físico de 6 lapidárias (com níveis de 1 a 3), limite global de 2 trabalhadores para construções simultâneas e sincronização de estado em tempo real entre todos os participantes via WebSockets (Socket.IO).

## Como instalar e executar

### Requisitos prévios
- Python 3.10 ou superior
- Git

### Instalação (Linux)
1. Clone o repositório e acesse a pasta raiz:
   ```bash
   git clone https://github.com/LeonardoAvilaa/lpp-trabalho01-leonardo-avila.git
   cd lpp-trabalho01-leonardo-avila
   ```

2. Crie e ative o ambiente virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Instale as dependências do projeto:
   ```bash
   pip install -r requirements.txt
   ```

### Execução
Inicie o servidor ASGI com recarregamento automático:
```bash
uvicorn server:app --reload
```

O servidor estará disponível no endereço:
```text
http://localhost:8000
```
(ou `http://127.0.0.1:8000`). Acesse essa URL diretamente no navegador.

---

## Como testar com duas abas

Para vivenciar a cooperação e a concorrência em tempo real, abra duas abas (ou duas janelas do navegador) em `http://localhost:8000`:

1. **Aba 1 (Mestre):**
   - Informe o nome (ex.: `Mestre`) e selecione o papel **Mestre**.
   - O painel exibirá o estado inicial da vila na fase `aguardando` e o botão **"Abrir temporada"** estará habilitado.
2. **Aba 2 (Jogador):**
   - Em outra aba ou janela anônima, informe o nome (ex.: `Ana`) e selecione o papel **Jogador**.
   - A vila estará sincronizada no mesmo estado da Aba 1.
3. **Abertura da Temporada:**
   - Na Aba 1, clique em **"Abrir temporada"**.
   - O servidor emite `vila.aberta` para todos. A fase transita para `aberta`, o botão do Mestre muda para "Encerrar temporada" e a Mina inicia sua contagem de produção.
4. **Extração Automática da Mina:**
   - A cada 2 segundos, a Mina emite `mina.cristal_produzido`, adicionando +1 cristal bruto ao estoque comunitário visível em ambas as abas e incrementando o respectivo contador de eventos.
5. **Solicitação de Construção:**
   - Na Aba 2, quando o estoque acumular pelo menos 5 cristais brutos e houver trabalhador livre (`0/2` ou `1/2`), o botão **"Construir lapidária (5 cristais brutos)"** ficará ativo.
   - Clique em **"Construir lapidária"**. O servidor valida a requisição, debita 5 cristais brutos, reserva o primeiro lote disponível (`lote1`), aloca 1 trabalhador (`1/2`) e emite `construcao.iniciada` para todos, iniciando uma obra de 3 segundos.
6. **Conclusão da Obra:**
   - Decorridos os 3 segundos da obra, o servidor emite `construcao.concluida`. A `lapidaria-1` (nível 1) surge na seção de lapidárias na situação `disponível`, e o trabalhador é automaticamente liberado (`0/2`).
7. **Processamento Automático (FIFO):**
   - Havendo cristais brutos no estoque e a lapidária estando disponível, o servidor consome 1 cristal bruto e emite `lapidaria.processamento_iniciado`. Uma barra de progresso de 10 segundos avança no card da estrutura.
   - Ao término dos 10 segundos, o servidor emite `lapidaria.cristal_lapidado`, creditando 1 cristal lapidado ao estoque geral.
8. **Melhoria de Lapidária:**
   - Quando o estoque atingir 10 cristais lapidados, o Jogador na Aba 2 clica no card da `lapidaria-1` para abrir seus detalhes e clica em **"⬆️ Melhorar para Nível 2"**.
   - O cliente gera um `solicitacao_id` e emite `melhoria.solicitada`. O servidor debita 10 cristais lapidados, cancela processamentos ativos estornando cristais brutos ao estoque geral e emite `melhoria.iniciada`.
   - Após 3 segundos de obra, o servidor emite `melhoria.concluida`, promovendo a estrutura ao Nível 2 (com 2 vagas simultâneas de processamento).
9. **Painel de Eventos e Contadores:**
   - Em ambas as abas, acompanhe a timeline registrando todos os eventos emitidos (`⬆ emit`) e escutados (`⬇ on`) com suas causas e reações, bem como as etiquetas no topo acumulando a contagem de cada evento.
10. **Encerramento da Temporada:**
    - Na Aba 1, o Mestre clica em **"Encerrar temporada"**. O servidor emite `vila.encerrada` para todos e a fase transita para `encerrada`.
    - A Mina para imediatamente, cessando a extração de novos cristais.
    - Todos os processamentos ativos nas lapidárias são interrompidos no mesmo instante, e os cristais brutos que estavam sendo lapidados retornam integralmente ao estoque geral comunitário.
    - Construções e melhorias que já haviam sido iniciadas continuam sua contagem normalmente até a conclusão. Suas conclusões posteriores entregam as estruturas e liberam os trabalhadores, mas não reiniciam o processamento de cristais com a temporada encerrada.
    - Quaisquer novos pedidos de abertura, construção ou melhoria emitidos após o encerramento são categoricamente recusados pelo servidor.

---

## Perguntas

### 1. Quais eventos o seu sistema emite e escuta?

O sistema opera sobre um catálogo unificado de **18 eventos de aplicação**, estruturados sob o padrão formal do paradigma orientado a eventos (`objeto.acao_solicitada` para pedidos, `objeto.acao_no_passado` para fatos/confirmações e `objeto.recusada` para recusas):

#### A. Pedidos enviados pelo cliente ao servidor (`pedir` / emit)
1. `vila.abertura_solicitada`: Emitido pelo Mestre para transitar a temporada de `aguardando` para `aberta`.
2. `vila.encerramento_solicitado`: Emitido pelo Mestre para transitar a temporada de `aberta` para `encerrada`.
3. `construcao.solicitada`: Emitido por um Jogador para construir uma nova lapidária de Nível 1 no primeiro lote vago.
4. `melhoria.solicitada`: Emitido por um Jogador para evoluir o nível de uma lapidária (enviando `lapidaria_id` e o token `solicitacao_id`).

#### B. Fatos e recusas recebidos pelo cliente do servidor (`ouvir` / on)
5. `estado.sincronizado`: Fato unicast enviado a cada novo participante conectado, entregando o snapshot integral da vila.
6. `vila.aberta`: Fato broadcast confirmando a abertura pública da temporada e ativando a Mina.
7. `vila.abertura_recusada`: Recusa unicast informando ao solicitante o motivo da falha ao abrir a vila.
8. `vila.encerrada`: Fato broadcast confirmando o fechamento definitivo da temporada e parando a Mina.
9. `vila.encerramento_recusado`: Recusa unicast informando ao solicitante o motivo da falha ao encerrar a vila.
10. `mina.cristal_produzido`: Fato broadcast emitido a cada 2 segundos pela Mina, adicionando +1 cristal bruto ao estoque.
11. `construcao.iniciada`: Fato broadcast confirmando a aceitação da obra de 3 segundos, debitando recursos e ocupando trabalhador e lote.
12. `construcao.concluida`: Fato broadcast informando a entrega da lapidária e a liberação automática do trabalhador.
13. `construcao.recusada`: Recusa unicast informando falha na construção (saldo insuficiente, sem trabalhadores ou sem lotes).
14. `lapidaria.processamento_iniciado`: Fato broadcast informando início de lapidação (10s) em vaga alocada via FIFO global.
15. `lapidaria.cristal_lapidado`: Fato broadcast informando término da lapidação e crédito de +1 cristal lapidado.
16. `melhoria.iniciada`: Fato broadcast confirmando o início da obra de melhoria de 3 segundos e preservando o `solicitacao_id`.
17. `melhoria.concluida`: Fato broadcast confirmando a conclusão da melhoria e expansão da capacidade de vagas.
18. `melhoria.recusada`: Recusa unicast informando falha na melhoria (saldo insuficiente, nível máximo atingido ou estrutura ocupada).

*Nota sobre a recusa de conexão:* No protocolo Socket.IO, a recusa de entrada (nome vazio ou tentativa de conectar um segundo Mestre) é tratada nativamente durante a fase de handshake através da exceção `ConnectionRefusedError(motivo)` no servidor. O cliente a intercepta no listener de transporte `socket.on("connect_error")`, exibindo o motivo na tela sem contabilizá-la como um evento da aplicação em execução.

---

### 2. Como o sistema sabe quando deve atualizar os outros jogadores?

O servidor atua como a única fonte da verdade e despachante central de eventos da aplicação:

1. **Recepção e Processamento Centralizado:** Todas as interações dos participantes chegam ao servidor como mensagens assíncronas do Socket.IO (`@sio.on(...)`). O servidor valida as regras de negócio de forma atômica e atualiza o estado interno da vila.
2. **Decisão entre Broadcast e Unicast:**
   - **Broadcast (Atualização pública):** Quando uma operação altera o estado comunitário da vila (ex.: abertura de temporada, início ou fim de obra, extração da mina, avanço de vagas de lapidação ou encerramento), o servidor invoca `await sio.emit(nome_evento, fato, ...)` sem especificar o parâmetro `to`. O Socket.IO transmite imediatamente o evento a **todos os clientes conectados**.
   - **Unicast (Resposta privada):** Quando a mensagem interessa exclusivamente ao solicitante (como eventos de recusa `*.recusada` ou a sincronização inicial `estado.sincronizado`), o servidor especifica `to=sid`, garantindo que apenas aquele participante receba o pacote.
3. **Sincronização por Snapshots Autoritativos:** Cada evento emitido pelo servidor carrega em seu payload o campo `estado: snapshot()`, contendo a fotografia atualizada de todos os estoques, fases, trabalhadores, lotes e lapidárias. No cliente, a função central `atualizar(d)` consome esse snapshot e atualiza o estado reativo do Vue 3, que automaticamente recalcula a interface de forma instantânea para todos os jogadores, sem necessidade de polling ou recarregamento de página.

---

### 3. Que parte do código mostra claramente o uso do paradigma orientado a eventos?

O uso do paradigma orientado a eventos é evidenciado pela comunicação desacoplada por eventos, na qual clientes e servidor reagem a mensagens assíncronas sem depender de chamadas diretas entre as rotinas de cada componente:

1. **No Cliente (`client/index.html`):**
   - **Disparo de pedidos desacoplado e trava local:** Ao clicar no botão de construção, a interface **não cria a obra nem modifica o estado local**. Ela apenas emite o pedido por meio de `pedir("construcao.solicitada")` (linhas 391 e 557) e ativa imediatamente uma trava reativa local (`comandoConstrucaoPendente = true`) para evitar cliques repetidos e solicitações duplicadas enquanto aguarda resposta. Essa trava local é uma proteção de interface e não significa que a construção foi aceita pelo servidor.
   - **Confirmação e reação visual baseada em estado autoritativo:** A aceitação da obra é decidida e confirmada exclusivamente pelo servidor ao emitir o fato assíncrono `construcao.iniciada` (linhas 484-492). Ao receber esse evento, o cliente atualiza a representação visual da construção com base no estado autoritativo enviado no snapshot (`atualizar(d)`) e libera a trava local caso o campo `solicitante` corresponda ao nome do jogador local (`d.solicitante === nome.value`).
   - **Liberação da trava em caso de recusa:** Caso a solicitação seja rejeitada pelo servidor (por saldo insuficiente, limite de trabalhadores ou falta de lotes), o servidor emite o evento `construcao.recusada` diretamente ao solicitante, que então libera a trava (`comandoConstrucaoPendente = false`) e exibe o aviso com o motivo da recusa sem alterar o estado da vila. O fluxo demonstra a comunicação desacoplada por eventos: a interface envia solicitações e reage às confirmações ou recusas recebidas, enquanto o servidor mantém a autoridade sobre as alterações no estado da vila.
   - O barramento padronizado em `registrar(...)` (linhas 374-383) inspeciona o sentido do fluxo (`enviado` ou `recebido`) e atualiza os contadores reativos e a timeline de eventos.

2. **No Servidor (`server.py`):**
   - **Tratamento Reativo:** As rotinas de negócio não são chamadas proceduralmente, mas despertadas por decoradores de eventos, como `@sio.on("melhoria.solicitada")` (linha 340).
   - **Eventos Temporizados Autônomos:** A produção e as obras são regidas por corrotinas assíncronas que suspendem a execução via `sio.sleep(...)` e disparam eventos quando o tempo transcorre. Por exemplo, na função `lapidacao(...)` (linhas 622-650):
     ```python
     await sio.sleep(TEMPO_LAPIDACAO)
     if vaga["ciclo_id"] != token_local or vila["fase"] != "aberta":
         return
     vila["lapidados"] += 1
     await sio.emit("lapidaria.cristal_lapidado", fato(
         "temporizador",
         lapidaria_id=lid,
         vaga=numero_vaga,
     ))
     ```
     O evento `lapidaria.cristal_lapidado` é disparado de forma autônoma pelo temporizador e, ao concluir, aciona o dispatcher FIFO que imediatamente aloca o próximo cristal e emite `lapidaria.processamento_iniciado`, ilustrando o encadeamento de eventos sem qualquer intervenção humana.

---

## Uso de IA

Ferramentas de inteligência artificial, incluindo ChatGPT e Antigravity, foram utilizadas como apoio ao planejamento, à elaboração de instruções de implementação, à análise técnica e à revisão do projeto. As funcionalidades foram implementadas e integradas no repositório do projeto, com acompanhamento, avaliação dos resultados, execução dos testes e validação das alterações pelo integrante.

---

## Extras

Além dos requisitos mínimos das Etapas 1 a 7, o projeto incorpora:
1. **Correlação Estrita de Solicitações Concorrentes (`solicitacao_id`):** Implementação de identificador único via `crypto.randomUUID()` nas solicitações de melhoria, garantindo que disputas concorrentes entre jogadores pela mesma lapidária liberem exclusivamente a trava local do jogador correspondente.
2. **Suíte de Testes Automatizados (108 testes):** Testes unitários, de contrato e de integração cobrindo as etapas do ciclo de vida, com verificações de limites de trabalhadores, políticas FIFO e comunicação entre componentes.
3. **Interface Visual Aprimorada com Cards e Progress Bars:** Cards interativos para cada lapidária exibindo status, nível, vagas e barras nativas de progresso de lapidação (`<progress>`), além de painel de detalhes contextual.
4. **Validação Defensiva Estrita no Backend:** Rejeição rigorosa de tipos não textuais, strings vazias e payloads excessivos sem conversão automática, garantindo a integridade dos dados trafegados.
