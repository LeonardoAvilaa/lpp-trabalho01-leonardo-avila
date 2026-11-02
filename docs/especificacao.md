# Especificação Formal — Vila em Tempo Real (Projeto Cristais)

**Integrante:** Leonardo Ávila  
**Tipo de vila (sorteio):** Vila dos Cristais (Extração e Lapidação)  

---

## 1. Identificação e Conceito Geral

### 1.1 Identificação do Projeto
A presente especificação formal descreve as regras de negócio, o modelo de concorrência, o fluxo temporal e o catálogo completo de eventos da **Vila dos Cristais**, uma aplicação cooperativa em tempo real baseada no paradigma orientado a eventos.

### 1.2 Conceito Geral da Vila e Recursos
A vila opera em regime comunitário e compartilhado, dedicando-se à extração de cristais brutos e ao seu beneficiamento em cristais lapidados. Todas as estruturas, os estoques e os trabalhadores pertencem coletivamente à vila. Não existem estoques individuais, reservas privadas por participante ou estoques retidos internamente em estruturas.

A economia da vila é sustentada por dois recursos:
- **Cristal bruto:** recurso primário natural, extraído continuamente do solo pela Mina.
- **Cristal lapidado:** recurso refinado de alto valor, gerado pelo processamento de cristais brutos nas Lapidárias.

Ambos os estoques são globais, ilimitados e iniciam em zero (`0`).

---

## 2. Estruturas da Vila

### 2.1 Mina de Cristais
- Representa a fonte primária de recursos e já se encontra erguida desde o início da vila, localizada no acampamento do mapa.
- Não possui custo de construção, não possui níveis de melhoria e **não consome trabalhadores**.
- Extrai automaticamente **1 cristal bruto a cada 2 segundos**, o que equivale a uma produção contínua de 30 cristais brutos por minuto.
- A primeira extração ocorre exatamente 2 segundos após a abertura da temporada pelo Mestre.
- Opera ininterruptamente durante toda a fase aberta da vila, mesmo enquanto construções e melhorias ocorrem em paralelo.
- Cessa sua produção imediatamente no instante em que a temporada é encerrada.

### 2.2 Lapidárias
- São as estruturas especializadas no corte, lapidação e refino dos cristais brutos.
- A vila possui capacidade física para comportar no máximo **seis lapidárias simultâneas**, correspondentes exatamente aos seis lotes fixos do cenário (`lote1` a `lote6`).
- A escolha do terreno é estritamente automática: o servidor aloca a obra no primeiro lote livre na ordem numérica crescente (`lote1`, `lote2`, ..., `lote6`). Os jogadores não selecionam o lote.
- Cada lapidária recebe do servidor um identificador unívoco e estável (`lapidaria-1` a `lapidaria-6`).
- Cada estrutura é caracterizada por quatro atributos de estado independentes:
  1. **Identificador estável:** `lapidaria-N`.
  2. **Lote físico:** `lote1` a `lote6`.
  3. **Nível de capacidade:** 1, 2 ou 3.
  4. **Situação operacional:** `em construção`, `disponível` ou `em melhoria`.
- **Regra de exclusividade estrutural por unidade:** Uma mesma lapidária só pode sofrer uma operação estrutural por vez. Não é permitido solicitar melhoria em uma estrutura que esteja em construção ou que já esteja executando outra melhoria.
- **Independência operacional entre estruturas distintas:** Operações em estruturas diferentes não se bloqueiam mutuamente. Uma melhoria em curso na `lapidaria-1` não impede a construção de uma nova lapidária em outro lote desocupado, nem impede a melhoria de outra lapidária diferente, desde que os requisitos de recursos, lote vago e trabalhador livre sejam atendidos individualmente para cada pedido.

---

## 3. Custos, Tempos e Níveis de Estrutura

### 3.1 Construção de Nova Lapidária
- Uma nova lapidária é sempre construída no **Nível 1**.
- **Modalidades de construção e custos:** O jogador deve escolher explicitamente uma das duas modalidades de pagamento antes de solicitar a construção:
  - **Cristais brutos:** 5 cristais brutos;
  - **Cristais lapidados:** 5 cristais lapidados.
- Não há conversão automática entre recursos nem débito simultâneo dos dois estoques.
- **Duração da obra:** 3 segundos.
- O custo de exatamente 5 unidades do recurso escolhido é debitado imediatamente no momento em que o pedido é validado e aceito pelo servidor de forma atômica. O recurso não selecionado não sofre nenhum débito.
- O lote atribuído fica reservado e ocupado desde o início da obra.
- A construção não pode ser cancelada nem reembolsada.
- Podem ocorrer construções simultâneas em lotes diferentes, desde que respeitado o limite de trabalhadores.

### 3.2 Tabela de Níveis e Custos de Evolução
As lapidárias podem evoluir do Nível 1 até o Nível 3. O custo de construção inicial da estrutura é apresentado separadamente e não se confunde com os custos de melhoria de nível:

| Nível | Vagas simultâneas | Custo para alcançar o nível | Duração da operação |
| :---: | :---------------: | :-------------------------- | :-----------------: |
| **1** | 1 cristal por vez | **Construção:** 5 cristais brutos ou 5 cristais lapidados | 3 segundos          |
| **2** | 2 cristais por vez | **Melhoria:** 10 cristais lapidados | 3 segundos          |
| **3** | 3 cristais por vez | **Melhoria:** 15 cristais lapidados | 3 segundos          |

### 3.3 Regras de Melhoria
- Para que uma melhoria seja aceita, a temporada deve estar aberta, a lapidária deve estar na situação `disponível`, seu nível deve ser inferior a 3 e o estoque geral deve conter a quantidade exigida de cristais lapidados.
- O custo em cristais lapidados é debitado imediatamente na aceitação do pedido.
- Cada melhoria dura rigorosamente **3 segundos**.
- **Melhorias não ocupam trabalhadores nesta versão.** A ocupação de trabalhadores restringe-se exclusivamente à construção de novas estruturas.
- Durante a melhoria, a estrutura assume a situação `em melhoria` e **todos os seus processamentos de lapidação ativos são cancelados de imediato**.
- Os cristais brutos que estavam sendo trabalhados nessas vagas são **estornados integralmente ao estoque geral**. O tempo transcorrido é descartado sem gerar cristais lapidados.
- A lapidária não aceita novos cristais durante a melhoria.
- Ao término dos 3 segundos, a lapidária passa ao novo nível e retorna à situação `disponível` com sua nova capacidade de vagas liberada. A estrutura retoma automaticamente o beneficiamento se, e somente se, a temporada estiver na fase `aberta` e houver cristais brutos disponíveis no estoque geral. Se a conclusão da melhoria ocorrer após o encerramento da temporada (operação pendente que concluiu na fase `encerrada`), a lapidária recebe o novo nível e a situação `disponível`, mas não inicia nenhum processamento, permanecendo em repouso definitivo.
- Melhorias não podem ser canceladas e não há devolução de recursos. Qualquer jogador pode solicitar a melhoria de qualquer lapidária existente.

---

## 4. Limite Global de Trabalhadores e Limite Estrutural

### 4.1 Limite Global de Trabalhadores
- A vila possui um contingente fixo de **2 trabalhadores** que atuam como limite global compartilhado de obras simultâneas (`0/2` a `2/2`).
- A vila inicia a temporada com zero trabalhadores ocupados de um total de dois (`0/2`).
- No instante em que o servidor valida e aceita um pedido de construção, **1 trabalhador é imediatamente ocupado** (`+1`), e o contador passa a refletir a nova ocupação (`1/2` ou `2/2`).
- O trabalhador permanece retido durante os 3 segundos exatos da duração da obra.
- Ao concluir a obra, o servidor **libera automaticamente o trabalhador** (`-1`), reduzindo o contador de ocupação.
- Se os dois trabalhadores estiverem ocupados (`2/2`), qualquer nova solicitação de construção é rejeitada de pronto com a recusa fundamentada pelo motivo:  
  `Sem trabalhador livre`.
- Trabalhadores não são contratados, comprados, treinados, demitidos, destruídos ou alocados manualmente por jogadores. O controle é realizado de forma automática pelo servidor.
- Conforme definido na Seção 3.3, melhorias de nível em lapidárias existentes não ocupam trabalhadores.

### 4.2 Separação entre Limite de Trabalhadores e Limite de Estruturas
A especificação estabelece uma separação obrigatória entre dois limites independentes:
1. **Limite de trabalhadores (2 obras simultâneas):** restringe quantas construções de lapidárias podem ocorrer paralelamente no tempo.
2. **Limite de estruturas (6 lapidárias):** restringe a capacidade física máxima de lapidárias que a vila comporta (uma por lote do mapa).

---

## 5. Processamento Automático de Lapidação e Fila FIFO

### 5.1 Mecânica do Beneficiamento
- O processamento de cristais é um fluxo autônomo conduzido inteiramente pelo servidor, sem intervenção de cliques por parte dos participantes.
- Cada operação de lapidação dura **10 segundos** e consome **1 cristal bruto para produzir 1 cristal lapidado**.
- O tempo de processamento de 10 segundos é invariável e idêntico em todos os níveis. O nível da lapidária determina exclusivamente a quantidade de vagas concorrentes (1 vaga no nível 1, 2 vagas no nível 2 e 3 vagas no nível 3).
- Cada vaga opera de maneira independente, dispondo de seu próprio temporizador assíncrono de 10 segundos.
- Quando uma vaga completa seu ciclo de 10 segundos, o servidor credita 1 cristal lapidado no estoque comunitário. A conclusão de uma lapidação só inicia um novo ciclo se a temporada continuar na fase `aberta` e houver cristal bruto disponível no estoque geral; caso a temporada já esteja encerrada ou não haja cristal bruto disponível, a vaga não inicia novo processamento.

### 5.2 Capacidade Teórica da Vila
- Lapidária Nível 1: 6 cristais lapidados por minuto.
- Lapidária Nível 2: 12 cristais lapidados por minuto.
- Lapidária Nível 3: 18 cristais lapidados por minuto.
- Como a Mina extrai 30 cristais brutos por minuto, uma única lapidária (mesmo em nível 3) não absorve toda a produção da mina. É necessário erguer múltiplas estruturas e elevá-las de nível para equilibrar a taxa de lapidação da vila.

### 5.3 Política de Alocação de Recursos (Fila FIFO Global Determinística)
- A vila adota uma **fila de prioridade única e global** entre todas as lapidárias para o direcionamento de cristais brutos, sem criação de filas isoladas ou estoques reservados por estrutura.
- O critério de ordenação é estritamente determinístico e baseado no ciclo de disponibilidade individual de cada vaga:
  1. **Registro lógico de disponibilidade:** Cada vaga de processamento possui um registro lógico do instante exato em que se tornou disponível para receber um novo cristal bruto.
  2. **Início de processamento:** Quando uma vaga inicia uma lapidação, ela deixa de estar disponível e seu registro de disponibilidade é encerrado.
  3. **Conclusão de processamento:** Ao concluir uma lapidação, a vaga torna-se disponível novamente e recebe um novo registro correspondente ao instante de sua liberação.
  4. **Conclusão de melhoria:** Quando uma lapidária conclui uma melhoria e retorna à situação `disponível`, todas as suas vagas recebem registros de disponibilidade correspondentes ao instante da conclusão da obra, desde que a temporada esteja aberta.
  5. **Conservação da disponibilidade:** Caso não haja cristal bruto disponível no estoque geral, a vaga permanece no estado disponível e conserva inalterado o seu registro de disponibilidade até ser abastecida com um cristal.
- **Critérios de desempate e ordenação global:**
  - A ordenação global prioriza sempre a vaga cujo registro de disponibilidade seja o mais antigo em toda a vila (política *First In, First Out*).
  - Em caso de empate no instante de disponibilidade entre vagas de estruturas distintas, a prioridade é atribuída à lapidária localizada no lote de menor numeração.
  - Em caso de empate entre vagas da mesma lapidária (como ocorre na conclusão de uma melhoria), prevalece a vaga de menor número identificador interno (por exemplo, vaga 1 antes da vaga 2).
  - Quando múltiplas vagas se tornarem disponíveis no mesmo instante, o servidor deverá considerar todas as vagas elegíveis antes de distribuir os cristais brutos disponíveis, aplicando os critérios globais de desempate por número do lote e número da vaga. A distribuição deverá respeitar essa ordenação, independentemente da ordem em que os temporizadores forem processados internamente.
- Cristais brutos devolvidos ao estoque geral após interrupção por melhoria retornam ao estoque geral comunitário e voltam a participar normalmente da política de prioridade global da vila, sem privilégios ou retenções exclusivas.

---

## 6. Temporada e Ciclo de Vida da Vila

A vila transita por três fases sequenciais e irreversíveis em uma mesma sessão:

```
[aguardando]  ──(Mestre abre)──>  [aberta]  ──(Mestre encerra)──>  [encerrada]
```

### 6.1 Fase `aguardando`
- Estado inicial do servidor.
- Os participantes podem se conectar e inspecionar a vila.
- A mina permanece inativa, os temporizadores estão parados e nenhum pedido de construção ou melhoria é aceito.

### 6.2 Fase `aberta`
- Iniciada exclusivamente por solicitação do Mestre.
- A produção da Mina tem início após 2 segundos, disparando o ciclo contínuo de extração.
- Jogadores têm autorização para solicitar construções e melhorias.
- O processamento automático nas lapidárias ocorre livremente.

### 6.3 Fase `encerrada` e Regras de Fechamento
Solicitada exclusivamente pelo Mestre. O encerramento não pode ser desfeito na mesma execução do servidor.

No momento exato em que a temporada é encerrada:
1. A fase da vila é alterada imediatamente para `encerrada`.
2. A Mina interrompe a extração no mesmo instante, sem novas emissões de cristais brutos.
3. **Cancelamento de processamentos:** todas as lapidações ativas são interrompidas; os cristais brutos que estavam nessas vagas retornam imediatamente ao estoque geral, e o progresso parcial de tempo é descartado.
4. **Preservação de obras em curso:** construções e melhorias que já haviam sido aceitas e iniciadas antes do encerramento **continuam sua contagem regressiva até completar seus 3 segundos normais**. Seus custos não são devolvidos.
5. Ao término dos 3 segundos dessas obras pendentes, as lapidárias são entregues no estado final previsto (e os trabalhadores alocados nas construções são liberados), emitindo os respectivos eventos de conclusão (`construcao.concluida` ou `melhoria.concluida`), permanecendo em repouso definitivo sem iniciar novos processamentos.
6. **Bloqueio de novos pedidos:** quaisquer novas tentativas de abertura, construção ou melhoria emitidas após o encerramento são categoricamente recusadas.
7. Os estoques finais permanecem preservados para exibição e a vila entra em estado definitivo de repouso após o término de todas as operações pendentes.

---

## 7. Participantes, Papéis e Conectividade

### 7.1 Mestre
- A vila admite a presença de **no máximo um Mestre** conectado por vez. Qualquer tentativa de um segundo usuário se conectar com o papel de Mestre é rejeitada pelo servidor.
- O Mestre possui como atribuição exclusiva comandar a abertura e o encerramento da temporada.
- O Mestre não constrói, não melhora lapidárias e não interage com recursos.
- Caso o Mestre se desconecte, a vaga de Mestre fica aberta para que outro participante possa assumi-la. A desconexão do Mestre não afeta a fase corrente da temporada nem interrompe obras ou temporizadores.

### 7.2 Jogadores
- Participantes ativos da comunidade que solicitam construções de lapidárias e melhorias de nível.
- O acesso não exige criação de conta ou senha.
- O nome de identificação é de preenchimento obrigatório, não podendo ser vazio ou composto unicamente por espaços em branco.
- Nomes duplicados são tolerados; a distinção de cada participante é realizada no servidor por meio do identificador de conexão.
- As ações de construção e melhoria pertencem à comunidade da vila. A desconexão de um jogador não interrompe, não reverte e não cancela as operações iniciadas por ele.

### 7.3 Entrada e Sincronização
- Todo participante que se conecta com sucesso recebe imediatamente o evento individual `estado.sincronizado`, contendo a fotografia integral do estado da vila:
  - Fase atual da temporada.
  - Estoque de cristais brutos e lapidados.
  - Contagem de trabalhadores ocupados e limite (`trabalhadores/limite`).
  - Lista completa das lapidárias com seus atributos (identificador, lote, nível, situação e temporizadores restantes).
  - Obras em andamento e processamentos ativos com seus respectivos tempos restantes.
- **Questão técnica pendente registrada:** No protocolo Socket.IO, o tratamento formal da recusa de entrada (`entrada.recusada`) motivada por nome inválido ou tentativa de entrada de um segundo Mestre durante a etapa de handshake/conexão deve ser verificado na implementação (por exemplo, emissão de evento seguida de encerramento de conexão ou uso de exceção no handshake), conforme registrado no documento canônico de decisões.

---

## 8. Concorrência e Servidor como Fonte da Verdade

### 8.1 Autoridade Central, Atomicidade e Resolução de Disputas
- O servidor é a autoridade máxima e central da aplicação. Os clientes atuam exclusivamente como interfaces de emissão de pedidos e reação visual a fatos confirmados. O cliente jamais altera o estado de forma autônoma.
- Os pedidos emitidos pelos jogadores são processados no servidor de forma estritamente sequencial, um por vez.
- **Atomicidade e indivisibilidade das operações:** A validação dos requisitos (fase aberta, saldo de recursos, disponibilidade de lotes e trabalhadores livres) e a atualização correspondente do estado da vila devem ocorrer como uma única operação indivisível. Nenhuma outra solicitação pode interferir no estado entre a validação e a confirmação da operação.
- **Resolução de disputas:** Se múltiplos jogadores disputarem o último cristal bruto disponível ou a última vaga livre de trabalhador quase simultaneamente, os eventos serão serializados pelo servidor. A primeira solicitação processada tem seus requisitos atendidos e confirmados; as solicitações subsequentes encontram os recursos esgotados e são respondidas com eventos individuais de recusa, impedindo a ocorrência de saldos negativos, gastos duplicados ou extrapolação de vagas.

### 8.2 Independência Operacional entre Estruturas Distintas
- Operações em estruturas diferentes não se bloqueiam mutuamente. Uma melhoria em andamento em uma lapidária não impede a construção de uma nova lapidária em outro lote desocupado, nem impede a solicitação de melhoria em outra estrutura distinta.
- Cada operação é julgada de forma autônoma pelo servidor com base nos requisitos específicos de cada ação, sem excluir as condições gerais de autorização do participante, fase aberta da temporada e validação prévia pelo servidor:
  - Para a construção de nova estrutura, os requisitos específicos compreendem seleção de modalidade válida (`brutos` ou `lapidados`), saldo suficiente no recurso selecionado (5 cristais brutos ou 5 cristais lapidados), existência de lote vago no mapa e trabalhador disponível (`trabalhadores < limite`).
  - Para a melhoria em uma estrutura existente, os requisitos específicos compreendem saldo suficiente em cristais lapidados, situação `disponível` daquela lapidária específica e nível inferior ao máximo (3), sem demandar alocação de trabalhadores.
- A restrição de bloqueio operacional é rigorosamente circunscrita à mesma estrutura: uma mesma lapidária jamais pode executar duas operações simultâneas (não pode sofrer melhoria enquanto estiver em construção ou executando outra melhoria).

---

## 9. Catálogo Completo de Eventos

Todos os eventos da vila obedecem à convenção do paradigma orientado a eventos:
- Pedidos do cliente: `objeto.acao_solicitada`
- Confirmações de fatos pelo servidor (para todos): `objeto.acao_no_passado`
- Recusas do servidor (enviadas exclusivamente ao solicitante): `objeto.recusada` ou `objeto.recusado`

A tabela a seguir consolida os **19 eventos** que compõem o catálogo canônico da Vila dos Cristais:

| Nº | Nome do Evento | Emissor | Destinatário | Finalidade | Dados Relevantes (Payload) | Alteração de Estado |
| :---: | :--- | :---: | :---: | :--- | :--- | :--- |
| 1 | `estado.sincronizado` | Servidor | Solicitante | Sincroniza o cliente recém-conectado com a situação atual da vila. | Estado completo: fase, estoques, trabalhadores, lapidárias, lotes e temporizadores ativos. | Nenhuma (leitura do estado para o cliente). |
| 2 | `entrada.recusada` | Servidor | Solicitante | Informa a rejeição de entrada do participante na vila. | Motivo da recusa (ex.: nome inválido ou já existe um Mestre conectado). | Nenhuma (a conexão é finalizada). |
| 3 | `vila.abertura_solicitada` | Mestre | Servidor | Pedido do Mestre para iniciar a temporada. | Identificação do Mestre solicitante. | Nenhuma (o pedido não muta o estado). |
| 4 | `vila.aberta` | Servidor | Todos | Confirma publicamente a abertura da temporada da vila. | Causa do fato (`vila.abertura_solicitada`) e estado atualizado. | Fase passa de `aguardando` para `aberta`; inicia o temporizador de 2s da Mina. |
| 5 | `vila.abertura_recusada` | Servidor | Mestre | Informa ao Mestre a recusa de abertura da temporada. | Motivo da recusa (solicitante não é Mestre ou fase não é `aguardando`) e causa. | Nenhuma. |
| 6 | `vila.encerramento_solicitado` | Mestre | Servidor | Pedido do Mestre para encerrar a temporada. | Identificação do Mestre solicitante. | Nenhuma (o pedido não muta o estado). |
| 7 | `vila.encerrada` | Servidor | Todos | Confirma publicamente o encerramento da temporada. | Causa do fato (`vila.encerramento_solicitado`) e estado da vila no instante do encerramento, incluindo operações pendentes em andamento. | Fase passa imediatamente para `encerrada`; mina para; processamentos ativos são interrompidos com estorno de cristais brutos ao estoque. Obras e melhorias em andamento continuam até a conclusão (emitindo `construcao.concluida` ou `melhoria.concluida` ao terminarem); novos pedidos de construção e melhoria são bloqueados. |
| 8 | `vila.encerramento_recusado` | Servidor | Mestre | Informa ao Mestre a recusa do encerramento. | Motivo da recusa (solicitante não é Mestre ou fase não é `aberta`) e causa. | Nenhuma. |
| 9 | `construcao.solicitada` | Jogador | Servidor | Pedido emitido por um jogador para erguer uma nova lapidária. | Modalidade escolhida (`brutos` ou `lapidados`). O solicitante é identificado pelo servidor via `sid` da conexão Socket.IO autenticada (não é enviado pelo cliente no payload). | Nenhuma (o pedido não muta o estado). |
| 10 | `construcao.iniciada` | Servidor | Todos | Confirma o início da obra de uma nova lapidária de nível 1. | Solicitante, identificador da lapidária, lote alocado, custo debitado (5), modalidade utilizada (`brutos` ou `lapidados`), causa e estado atualizado. | Debita 5 unidades do recurso selecionado (cristais brutos ou cristais lapidados); ocupa 1 lote; ocupa 1 trabalhador (`trabalhadores + 1`); inicia obra de 3s. |
| 11 | `construcao.concluida` | Servidor | Todos | Informa a entrega e prontidão de uma lapidária de nível 1. | Identificador da lapidária, lote ocupado, nível inicial (1), situação (`disponível`) e estado atualizado. | Libera 1 trabalhador (`trabalhadores - 1`); lapidária passa à situação `disponível` no nível 1. |
| 12 | `construcao.recusada` | Servidor | Solicitante | Informa a rejeição da solicitação de construção. | Motivo específico da recusa (modalidade inválida, saldo insuficiente no recurso escolhido, `Sem trabalhador livre`, falta de lotes, etc.) e causa. | Nenhuma alteração; nenhum recurso é debitado. |
| 13 | `melhoria.solicitada` | Jogador | Servidor | Pedido emitido por um jogador para elevar o nível de uma lapidária. | Identificador da lapidária-alvo e identificação do solicitante. | Nenhuma (o pedido não muta o estado). |
| 14 | `melhoria.iniciada` | Servidor | Todos | Confirma o início da obra de melhoria da lapidária. | Identificador da lapidária, nível atual, novo nível pretendido, custo debitado, causa e estado. | Debita cristais lapidados (10 ou 15); estrutura assume `em melhoria`; lapidações ativas são canceladas com estorno de brutos; inicia temporizador de 3s. |
| 15 | `melhoria.concluida` | Servidor | Todos | Informa a conclusão da melhoria da lapidária. | Identificador da lapidária, novo nível atingido (2 ou 3), novas vagas liberadas e estado atualizado. | Lapidária retorna à situação `disponível` com nova capacidade. Se a temporada estiver na fase `aberta` e houver cristais brutos disponíveis, o servidor retoma o processamento automático, respeitando a fila FIFO global. Caso contrário, permanece em repouso. |
| 16 | `melhoria.recusada` | Servidor | Solicitante | Informa a rejeição da solicitação de melhoria. | Motivo específico da recusa (recursos insuficientes, nível máximo atingido, estrutura ocupada) e causa. | Nenhuma alteração; nenhum recurso é debitado. |
| 17 | `mina.cristal_produzido` | Servidor | Todos | Notifica a extração automática periódica de um cristal bruto. | Quantidade extraída (+1), causa (`temporizador da mina`) e estoque bruto atualizado. | Estoque de cristais brutos é incrementado em 1 unidade (+1). |
| 18 | `lapidaria.processamento_iniciado` | Servidor | Todos | Notifica o início do ciclo de lapidação em uma vaga de lapidária. | Identificador da lapidária, número da vaga ocupada, causa e estoque bruto atualizado. | Debita 1 cristal bruto do estoque geral (-1); vaga inicia temporizador de 10s. |
| 19 | `lapidaria.cristal_lapidado` | Servidor | Todos | Notifica a conclusão bem-sucedida de um ciclo de lapidação. | Identificador da lapidária, número da vaga liberada, causa e estoque lapidado atualizado. | Credita 1 cristal lapidado no estoque geral (+1) e torna a vaga disponível novamente. Se a temporada estiver aberta e houver cristais brutos disponíveis, o servidor verifica a fila FIFO global e inicia imediatamente um novo processamento na vaga disponível de maior prioridade, debitando 1 cristal bruto e emitindo `lapidaria.processamento_iniciado`. Caso contrário, as vagas permanecem disponíveis aguardando insumo segundo a política FIFO global. |

---

## 10. Cenários Formais de Teste

### Cenário 1 — Recusa por falta de recursos
- **Dado que** a temporada da vila encontra-se na fase `aberta`,
- **e** o estoque comunitário de cristais brutos contém exatamente 3 unidades,
- **e** existem trabalhadores livres na vila (`0/2`) e lotes desocupados disponíveis,
- **quando** um jogador emite o pedido `construcao.solicitada` escolhendo a modalidade de cristais brutos (cujo custo é de 5 cristais brutos),
- **então** o servidor valida o saldo e constata a insuficiência de 2 cristais brutos,
- **e** emite o evento `construcao.recusada` unicamente para o jogador solicitante, informando a carência de recursos,
- **e** o estoque de cristais brutos permanece inalterado em 3 unidades,
- **e** nenhum lote do mapa é reservado e nenhum trabalhador é ocupado (`0/2`).
*(Regra análoga aplica-se à modalidade de cristais lapidados quando o estoque lapidado for inferior a 5 unidades).*

---

### Cenário 2 — Sequência temporal de produção da mina, construção e lapidação contínua
- **Dado que** a vila encontra-se no estado inicial com estoques zerados (`0` cristais brutos e `0` cristais lapidados), nenhum lote ocupado e nenhum trabalhador ocupado (`0/2`),
- **quando** o Mestre emite o pedido `vila.abertura_solicitada` e o servidor emite `vila.aberta` para todos, iniciando a contagem de 2 segundos para a primeira extração da Mina;
- **e** a Mina opera continuamente a cada 2 segundos, emitindo `mina.cristal_produzido` a cada extração até acumular 5 cristais brutos no estoque geral (aos 10 segundos da temporada, após a quinta extração);
- **e** aos 10 segundos um jogador emite o pedido `construcao.solicitada` (modalidade: cristais brutos) para erguer a primeira lapidária da vila;
- **então** o servidor valida os requisitos, aceita a solicitação, debita 5 cristais brutos do estoque (saldo bruto vai a zero), reserva o `lote1`, ocupa 1 trabalhador (`1/2`) e emite `construcao.iniciada` para todos, iniciando a obra de 3 segundos;
- **quando** o tempo avança até os 12 segundos da temporada, a Mina realiza sua sexta extração (`mina.cristal_produzido`), elevando o estoque para 1 cristal bruto;
- **e** aos 13 segundos transcorrem os 3 segundos da construção, o servidor encerra o temporizador da obra, emite `construcao.concluida` para todos, entrega a `lapidaria-1` de Nível 1 na situação `disponível` e libera automaticamente o trabalhador (`0/2`);
- **em seguida** (ainda aos 13 segundos), o servidor detecta 1 cristal bruto no estoque geral e a vaga livre da recém-concluída `lapidaria-1`, debitando esse cristal bruto (saldo bruto vai a zero) e emitindo `lapidaria.processamento_iniciado` para todos, iniciando o primeiro ciclo de 10 segundos de lapidação (com término aos 23 segundos);
- **e** entre os 14 e 22 segundos da temporada, a Mina realiza mais cinco extrações periódicas (a cada 2 segundos), acumulando 5 cristais brutos no estoque geral;
- **quando** a temporada alcança os 23 segundos, o primeiro ciclo de 10 segundos encerra e o servidor emite `lapidaria.cristal_lapidado` para todos, creditando 1 cristal lapidado no estoque comunitário;
- **e** imediatamente depois (ainda aos 23 segundos), como existem cristais brutos disponíveis (5 unidades acumuladas) e a temporada continua aberta, a mesma vaga inicia automaticamente um segundo processamento, debitando 1 cristal bruto do estoque e emitindo `lapidaria.processamento_iniciado` para todos,
- **então** o estado da vila após os acontecimentos dos 23 segundos consolida:
  - Estoque de cristais lapidados: 1 unidade;
  - Estoque de cristais brutos: 4 unidades;
  - Uma lapidação em andamento na `lapidaria-1`;
  - A Mina continua produzindo normalmente a cada 2 segundos.

---

### Cenário 3 — Disputa concorrente por recursos entre dois jogadores
- **Dado que** a temporada da vila encontra-se na fase `aberta`,
- **e** o estoque comunitário possui exatamente 5 cristais brutos,
- **e** existem trabalhadores livres (`0/2`) e lotes vagos no cenário,
- **quando** os jogadores A e B emitem o pedido `construcao.solicitada` (modalidade: cristais brutos) quase simultaneamente,
- **então** o servidor enfileira e avalia as requisições em ordem sequencial estrita:
  1. A requisição do jogador A é avaliada primeiro: o servidor confirma saldo de 5 cristais brutos, debita integralmente o montante (reduzindo o saldo a zero), aloca o lote vago, ocupa 1 trabalhador (`1/2`) e emite `construcao.iniciada` para todos os participantes;
  2. A requisição do jogador B é avaliada na sequência: o servidor constata que o saldo de cristais brutos encontra-se zerado e emite `construcao.recusada` exclusivamente para o jogador B por insuficiência de recursos;
- **e** o saldo final encerra exatamente em zero, sem cobrança duplicada, sem saldo negativo e sem inconsistência de estado.
*(Regra idêntica aplica-se a disputas concorrentes na modalidade de cristais lapidados).*

---

### Cenário 4 — Limite global de trabalhadores e concorrência de construções
- **Dado que** a temporada da vila encontra-se na fase `aberta`,
- **e** existem dois trabalhadores livres na vila (`0/2`),
- **e** o estoque comunitário dispõe de recursos abundantes (mínimo de 15 cristais brutos) e há múltiplos lotes vagos,
- **quando** a seguinte sequência de eventos é processada:
  1. O jogador A emite `construcao.solicitada` (modalidade: cristais brutos). O servidor valida e aceita sequencialmente o pedido: debita 5 cristais brutos, aloca o `lote1`, ocupa 1 trabalhador (`1/2`) e emite `construcao.iniciada` para todos. A obra entra em contagem regressiva de 3 segundos;
  2. O jogador B emite `construcao.solicitada` (modalidade: cristais brutos) antes da conclusão da obra de A. O servidor valida e aceita sequencialmente o pedido: debita 5 cristais brutos, aloca o `lote2`, ocupa o segundo trabalhador (`2/2`) e emite `construcao.iniciada` para todos. A segunda obra entra em contagem regressiva de 3 segundos;
  3. O jogador C emite `construcao.solicitada` (modalidade: cristais brutos) enquanto ambas as obras permanecem em andamento. O servidor avalia sequencialmente o pedido, constata que o limite de trabalhadores está saturado (`2/2`) e emite `construcao.recusada` exclusivamente para o jogador C com o motivo literal:
     `Sem trabalhador livre`.  
     Nenhum cristal bruto é debitado do jogador C e nenhum lote adicional é ocupado;
  4. Transcorrem os 3 segundos da obra do jogador A. O temporizador encerra, o servidor emite `construcao.concluida` para todos, entrega a lapidária no nível 1 e **libera automaticamente 1 trabalhador**. O contador de ocupação retorna para `1/2`;
  5. O jogador C emite novamente o pedido `construcao.solicitada` (modalidade: cristais brutos). O servidor processa o pedido, valida que há 1 trabalhador disponível (`1/2`), recursos suficientes e lote vago, aceita a construção e emite `construcao.iniciada`, ocupando o trabalhador liberado e elevando o contador novamente para `2/2`,
- **então** fica plenamente verificado que o limite global de 2 trabalhadores é rigidamente mantido pelo servidor em todas as transições, sem permitir extrapolação de obras simultâneas.
