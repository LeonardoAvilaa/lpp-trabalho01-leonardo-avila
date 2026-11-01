# Vila em Tempo Real — Projeto Cristais
## Documento de referência das decisões do projeto

**Status:** Consolidado (com a regra de 2 trabalhadores aprovada e incorporada)  
**Finalidade:** Registrar as decisões aprovadas do projeto Cristais para fundamentar a especificação formal em `docs/especificacao.md`.  
**Importante:** Este documento serve como base canônica das regras da versão temática de Cristais.

---

## 1. Conceito geral

O projeto representa uma vila especializada na extração e lapidação de cristais.

O servidor Python é responsável por manter o estado da vila, validar pedidos, controlar recursos, executar temporizadores e emitir eventos. Os clientes recebem os eventos e atualizam suas interfaces.

O projeto utiliza dois recursos:
- **Cristal bruto:** extraído pela mina.
- **Cristal lapidado:** produzido pelas lapidarias a partir dos cristais brutos.

Todos os recursos e estruturas são compartilhados entre os participantes.

## 2. Estruturas

Existem somente duas estruturas nesta versão:

### 2.1 Mina

- Já começa construída, representada pelo acampamento existente no mapa.
- Não possui custo de construção.
- Não precisa de trabalhadores.
- Produz automaticamente 1 cristal bruto a cada 2 segundos.
- A primeira produção ocorre 2 segundos depois da abertura da temporada.
- Produção equivalente a 30 cristais brutos por minuto.
- Continua produzindo durante construções e melhorias.
- Para imediatamente quando a temporada é encerrada.

### 2.2 Lapidaria

- Processa cristais brutos e produz cristais lapidados.
- A primeira lapidaria custa 5 cristais brutos.
- Não exige cristais lapidados para ser construída.
- O mapa original possui seis lotes (`lote1` até `lote6`).
- O limite é de seis lapidarias, uma por lote.
- O servidor escolhe automaticamente o primeiro lote livre. O jogador não escolhe o lote.
- Cada lapidaria recebe um identificador estável gerado pelo servidor: `lapidaria-1`, `lapidaria-2` etc.
- O identificador, o lote, o nível e a situação são atributos separados.
- Situações possíveis: `em construção`, `disponível` e `em melhoria`.
- Todas as lapidarias são compartilhadas. Qualquer jogador pode solicitar melhoria de qualquer uma.
- A construção de uma nova lapidaria ocupa 1 trabalhador durante sua execução (limite global de 2 trabalhadores).

O mapa original será mantido, sem personalização pelo Tiled nesta versão. A representação visual da mina aproveitará o acampamento já existente, sem modificar o primeiro bloco `<script>` do Phaser por padrão.

## 3. Construção

- O custo da primeira lapidaria é de 5 cristais brutos.
- A construção dura 3 segundos.
- O custo é descontado imediatamente quando o servidor aceita o pedido.
- O lote fica ocupado desde o início da construção.
- Ao terminar, a lapidaria passa ao nível 1 e fica disponível.
- Se o pedido for recusado, nenhum recurso é descontado.
- Podem existir construções simultâneas, desde que cada uma ocupe um lote diferente.
- **Limite global de trabalhadores:** A vila opera com um limite global compartilhado de 2 trabalhadores para construções simultâneas (`0/2` a `2/2`).
- A vila inicia com zero trabalhadores ocupados de um total de dois (`0/2`).
- Quando um pedido de construção é aceito pelo servidor, ocupa imediatamente 1 trabalhador (`+1`).
- O trabalhador permanece ocupado durante os 3 segundos de duração da obra.
- Ao concluir a construção, o servidor libera automaticamente o trabalhador (`-1`), e a lapidaria passa ao nível 1 ficando disponível.
- Se os dois trabalhadores já estiverem ocupados no momento da validação do pedido, a construção é recusada com o motivo `Sem trabalhador livre`.
- Trabalhadores não são contratados, comprados, destruídos ou alocados manualmente. O controle é realizado exclusivamente pelo servidor.
- **Distinção fundamental:**
  - Limite de trabalhadores: no máximo 2 construções simultâneas em andamento na vila.
  - Limite de estruturas: no máximo 6 lapidarias no total (uma por lote do mapa).
- O limite de seis lapidarias inclui as que estão em construção.

Construções não podem ser canceladas. Depois de iniciadas, terminam normalmente, e o custo descontado não é reembolsado.

## 4. Níveis e melhorias

Cada lapidaria possui três níveis:

| Nível | Cristais processados simultaneamente | Custo para alcançar o nível |
|---|---:|---:|
| 1 | 1 | 5 cristais brutos para construção |
| 2 | 2 | 10 cristais lapidados |
| 3 | 3 | 15 cristais lapidados |

- Cada cristal demora 10 segundos para ser lapidado, independentemente do nível.
- O nível determina quantos cristais podem ser processados simultaneamente.
- A melhoria de cada nível dura 3 segundos.
- O custo é descontado no início da melhoria.
- **Melhorias não ocupam trabalhadores nesta versão.** A ocupação de trabalhadores vincula-se exclusivamente ao ciclo de construção de novas lapidarias.
- A lapidaria não processa cristais durante a melhoria.
- Ao iniciar uma melhoria, todos os processamentos ativos são interrompidos.
- Os cristais brutos que estavam em processamento retornam ao estoque geral.
- O progresso parcial é descartado, sem gerar cristais lapidados.
- Não são iniciados novos processamentos até a conclusão da melhoria.
- Ao concluir, a lapidaria passa ao novo nível e retoma automaticamente o processamento.
- O lote da lapidaria não muda durante a melhoria.
- Melhorias não podem ser canceladas.
- Qualquer jogador pode melhorar qualquer lapidaria.

## 5. Processamento automático

- Quando uma lapidaria está disponível e possui vagas livres, o servidor inicia automaticamente o processamento se houver cristais brutos disponíveis.
- Cada processamento dura 10 segundos.
- Os temporizadores de cada vaga são independentes.
- Quando um processamento termina, o servidor acrescenta um cristal lapidado ao estoque e, se houver cristal bruto disponível, inicia imediatamente outro processamento naquela vaga.
- O processamento é automático, sem necessidade de clique do jogador.

Capacidade teórica de produção:

| Nível | Capacidade por minuto |
|---|---:|
| 1 | 6 cristais |
| 2 | 12 cristais |
| 3 | 18 cristais |

A mina produz 30 cristais brutos por minuto. Portanto, uma única lapidaria de nível 3 não consegue acompanhar a produção da mina.

## 6. Estoques e concorrência por recursos

- Estoques de cristais brutos e lapidados são compartilhados e ilimitados.
- Ambos começam em zero.
- Existe um estoque geral de cristais brutos, sem estoques separados por lapidaria.
- Cristais brutos podem ser usados tanto para construir lapidarias quanto para processamento.
- Quando uma lapidaria inicia um processamento, o servidor retira o cristal do estoque geral.
- A prioridade de encaminhamento para processamento é FIFO: a lapidaria disponível há mais tempo tem prioridade. Em caso de empate, tem prioridade o menor número do lote.
- Cristais devolvidos após interrupção por melhoria retornam ao fim da fila de processamento.
- Não existe estoque separado de cristais reservados.

Pedidos concorrentes são processados sequencialmente, na ordem de recebimento, e cada pedido é validado com base no estado atualizado.

Construção e processamento disputam o mesmo estoque de cristais brutos. A ordem de recebimento e efetivação determina qual operação consegue utilizar os recursos disponíveis.

Melhorias utilizam cristais lapidados e disputam esse estoque separadamente.

Um jogador pode enviar vários pedidos consecutivos sem esperar a conclusão do anterior. Cada pedido é validado individualmente pelo servidor.

Operações em estruturas diferentes não se bloqueiam. Uma mesma lapidaria, entretanto, só pode executar uma operação estrutural por vez.

## 7. Temporada e fases

A vila possui três fases:

- `aguardando`
- `aberta`
- `encerrada`

O Mestre pode abrir e encerrar a temporada.

- A abertura só é permitida quando a fase é `aguardando`.
- A temporada encerrada não pode ser reaberta na mesma execução do servidor.
- Uma nova execução do servidor começa com o estado inicial.
- Somente a fase `aberta` permite construir ou melhorar estruturas.
- Pedidos de construção e melhoria nas demais fases são recusados sem alterar o estado.

### Encerramento

Quando o Mestre encerra a temporada:

- A fase passa imediatamente para `encerrada`.
- A mina para imediatamente.
- Processamentos de lapidação são interrompidos.
- Cristais brutos que estavam em processamento retornam ao estoque geral.
- O progresso parcial dos processamentos é descartado.
- Os estoques são preservados.
- Construções já concluídas permanecem.
- Nenhuma nova construção ou melhoria pode começar.
- Construções e melhorias que já haviam começado continuam até concluir os respectivos 3 segundos.
- Os custos dessas operações já foram descontados e não são reembolsados.
- Depois que as operações já iniciadas terminarem, o estado permanece sem novas operações até o reinício do servidor.

A fase permanece `encerrada` durante a conclusão dessas operações pendentes. Isso não autoriza novos pedidos.

## 8. Participantes e papéis

### Mestre

- Existe apenas um Mestre conectado por vez.
- Um segundo participante que tentar entrar como Mestre é recusado.
- O Mestre pode abrir e encerrar a temporada.
- O Mestre não pode construir nem melhorar estruturas.
- Quando o Mestre se desconecta, a vaga de Mestre é liberada.
- A desconexão do Mestre não altera a fase da temporada nem interrompe operações.

### Jogadores

- Podem construir e melhorar lapidarias quando a fase está aberta.
- Não precisam de conta ou senha.
- O nome é obrigatório e não pode estar vazio ou conter somente espaços.
- Nomes duplicados são permitidos.
- A identificação individual é feita pelo ID da conexão.

### Entrada e desconexão

- Um participante pode entrar em qualquer fase da temporada.
- Ao entrar, recebe uma sincronização individual do estado atual.
- A desconexão de um jogador não cancela construções, melhorias ou processamentos.
- As operações pertencem à vila, e não à conexão que solicitou seu início.
- A desconexão de qualquer participante não interrompe as operações enquanto a temporada está aberta.

## 9. Eventos

Convenção geral do painel:
- Pedidos (`emit`) aparecem em azul.
- Escutas de confirmação (`on`) aparecem em verde.
- Escutas de recusa (`on`) aparecem em vermelho.
- O painel deve registrar evento, origem/destino, causa, dados e reação.
- O painel de eventos original do kit deve ser preservado.
- Os eventos de confirmação emitidos pelo servidor devem conter a causa, os dados específicos, o participante responsável quando aplicável e o estado atualizado da vila.
- Recusas devem informar o motivo e os dados relevantes e ser enviadas somente ao solicitante.

### Entrada e sincronização

| Evento | Direção | Finalidade |
|---|---|---|
| `estado.sincronizado` | Servidor → participante | Enviar o estado atual individualmente após entrada aceita |
| `entrada.recusada` | Servidor → conexão solicitante | Informar motivo da recusa de entrada |

A sincronização deve incluir:
- Fase da temporada.
- Estoques de cristais brutos e lapidados.
- Estado da mina.
- Lapidarias, com ID, lote, nível e situação.
- Construções e melhorias em andamento, com tempo restante.
- Processamentos em andamento, com identificação da lapidaria e tempo restante.

A entrada recusada deve informar se o motivo foi nome inválido ou tentativa de entrada de um segundo Mestre.

### Abertura e encerramento

| Evento | Direção | Finalidade |
|---|---|---|
| `vila.abertura_solicitada` | Mestre → servidor | Solicitar abertura |
| `vila.aberta` | Servidor → todos | Confirmar abertura |
| `vila.abertura_recusada` | Servidor → Mestre | Recusar abertura quando a fase não for `aguardando` |
| `vila.encerramento_solicitado` | Mestre → servidor | Solicitar encerramento |
| `vila.encerrada` | Servidor → todos | Confirmar encerramento |
| `vila.encerramento_recusado` | Servidor → Mestre | Recusar encerramento quando a fase não for `aberta` |

### Construção

| Evento | Direção | Finalidade |
|---|---|---|
| `construcao.solicitada` | Jogador → servidor | Solicitar construção |
| `construcao.iniciada` | Servidor → todos | Confirmar início, informando solicitante, ID, lote, custo debitado, ocupação de 1 trabalhador e estoque |
| `construcao.concluida` | Servidor → todos | Informar conclusão, ID, lote, nível 1 disponível e liberação de 1 trabalhador |
| `construcao.recusada` | Servidor → solicitante | Informar motivo da recusa (recursos insuficientes, lote indisponível, sem trabalhador livre ou temporada não aberta) |

### Melhoria

| Evento | Direção | Finalidade |
|---|---|---|
| `melhoria.solicitada` | Jogador → servidor | Solicitar melhoria |
| `melhoria.iniciada` | Servidor → todos | Informar ID, nível atual, nível pretendido e custo |
| `melhoria.concluida` | Servidor → todos | Informar ID e novo nível |
| `melhoria.recusada` | Servidor → solicitante | Informar motivo da recusa |

### Produção e lapidação

| Evento | Direção | Finalidade |
|---|---|---|
| `mina.cristal_produzido` | Servidor → todos | Informar produção de um cristal bruto |
| `lapidaria.processamento_iniciado` | Servidor → todos | Informar ID da lapidaria e quantidade em processamento |
| `lapidaria.cristal_lapidado` | Servidor → todos | Informar ID da lapidaria e estoque lapidado atualizado |

Os nomes dos eventos devem ser idênticos na especificação, no servidor e no cliente.

## 10. Cenários de teste

### Cenário 1 — Recusa por falta de recursos

**Condição inicial:**
- Temporada aberta.
- Estoque de cristais brutos: 3.
- Nenhuma lapidaria construída.

**Ação:**
- Um jogador solicita a construção de uma lapidaria, cujo custo é 5 cristais brutos.

**Resultado esperado:**
- O servidor emite `construcao.recusada` somente ao solicitante.
- A recusa informa a falta de 2 cristais brutos.
- O estoque permanece em 3.
- Nenhum lote é ocupado e nenhuma estrutura é criada.

### Cenário 2 — Passagem do tempo e produção

**Condição inicial:**
- Temporada aberta.
- Existe uma lapidaria de nível 1 disponível.
- Há cristais brutos suficientes para iniciar o processamento.

**Ação:**
- Aguardar os temporizadores.

**Resultado esperado:**
- Após 2 segundos da abertura, a mina produz um cristal bruto.
- Quando houver cristal bruto disponível e vaga livre, a lapidaria inicia o processamento automaticamente.
- Após 10 segundos de processamento, é produzido um cristal lapidado.
- Os eventos de produção, início e conclusão são emitidos para todos.
- Os estoques são atualizados corretamente.

### Cenário 3 — Disputa por recursos

**Condição inicial:**
- Temporada aberta.
- Estoque de cristais brutos: 5.
- Dois jogadores conectados.

**Ação:**
- Os dois jogadores solicitam a construção de uma lapidaria quase simultaneamente.

**Resultado esperado:**
- O servidor processa os pedidos sequencialmente.
- O primeiro pedido é aceito e desconta 5 cristais brutos.
- O segundo pedido é recusado por falta de recursos.
- O estoque final é zero.
- Não ocorre gasto duplicado nem estoque negativo.

### Cenário 4 — Limite global de trabalhadores e concorrência de obras

**Condição inicial:**
- Temporada aberta.
- Dois trabalhadores disponíveis (`0/2`).
- Recursos suficientes (mínimo de 15 cristais brutos) e lotes livres.

**Ações e resultados sequenciais:**
1. O jogador A solicita uma construção via `construcao.solicitada`. O servidor aceita sequencialmente, debita 5 cristais brutos, ocupa 1 lote e 1 trabalhador (`1/2`), emitindo `construcao.iniciada` para todos.
2. O jogador B solicita outra construção via `construcao.solicitada` antes do término da primeira obra. O servidor aceita sequencialmente, debita 5 cristais brutos, ocupa 1 lote e o segundo trabalhador (`2/2`), emitindo `construcao.iniciada` para todos.
3. O jogador C solicita uma terceira construção via `construcao.solicitada` enquanto as duas anteriores estão em andamento. O servidor avalia sequencialmente o pedido e emite `construcao.recusada` exclusivamente para C com o motivo `Sem trabalhador livre`. Nenhum recurso é descontado e nenhum lote é reservado.
4. Transcorrem os 3 segundos da obra de A. O servidor emite `construcao.concluida` para todos, entrega a lapidaria no nível 1 e libera automaticamente 1 trabalhador (`1/2`).
5. O jogador C emite nova solicitação `construcao.solicitada`. Havendo agora 1 trabalhador livre (`1/2`), recursos e lote, o servidor aceita a construção e o contador retorna para `2/2`.

O servidor processa e valida todos os pedidos sequencialmente.

## 11. Escopo e restrições

- Não incluir cofre ou outras estruturas nesta versão.
- Adotar limite global fixo de 2 trabalhadores compartilhados exclusivamente para construções simultâneas, sem mecânicas de contratação, compra, alocação manual ou ocupação em melhorias.
- Não incluir contas, senhas ou autenticação de usuários.
- Não permitir cancelamento de construções ou melhorias.
- Não permitir escolha manual de lote.
- Não permitir que o cliente altere diretamente o estado da vila.
- Não implementar funcionalidades extras sem autorização.
- Manter o mapa original e o primeiro bloco `<script>` do Phaser, salvo necessidade identificada e validada.
- Preservar o kit original e sua estrutura.
- Não iniciar implementação antes da especificação revisada e commitada.

---

## 12. Pontos técnicos que ainda precisam ser conferidos

Estes itens não são decisões funcionais novas. São verificações necessárias antes de implementar:

1. **Recusa de entrada:** verificar no kit e na documentação do Socket.IO como tratar nome inválido ou segundo Mestre durante o evento de conexão. O evento `entrada.recusada` foi definido como nome funcional, mas o mecanismo técnico de envio antes da conexão ser aceita precisa ser validado.
2. **Sincronização de temporizadores:** verificar como o servidor fornecerá o tempo restante das construções, melhorias e processamentos aos participantes que entrarem no meio da temporada.
3. **Encerramento e operações pendentes:** garantir que o controle dos temporizadores permita concluir construções e melhorias iniciadas antes do encerramento, sem permitir novas operações.
4. **Integração visual:** verificar como os IDs estáveis das lapidarias e os lotes escolhidos pelo servidor serão relacionados aos métodos visuais já existentes no Phaser. Não alterar o primeiro bloco de script sem necessidade comprovada.
5. **Fila FIFO:** detalhar a implementação da prioridade de encaminhamento dos cristais às lapidarias sem contrariar a regra de estoque geral compartilhado.

---

## 13. Instruções para a conferência

O agente deve:
- Ler os documentos do professor em `docs/referencias/`.
- Ler o modelo `vila/docs/especificacao.md`.
- Ler `vila/README.md`, `vila/server.py` e `vila/client/index.html`.
- Examinar os arquivos e comentários relevantes em `vila/client/`.
- Comparar cada regra deste documento com as exigências do professor e as limitações do kit.
- Apontar contradições, ambiguidades e incompatibilidades.
- Distinguir claramente exigências do professor, decisões já aprovadas e verificações técnicas pendentes.
- Não inventar requisitos ou funcionalidades.
- Não alterar, criar, excluir ou renomear arquivos.
- Não escrever código nem iniciar a implementação.

O resultado esperado é um relatório de conferência que permita revisar este rascunho antes de preencher a especificação oficial do kit.
