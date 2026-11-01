

| ![Logo da instituição][image1] | Linguagem de Programação e Paradigmas *Prof. Esp. Ademar Perfoll Junior* Sistemas de Informação |
| :---- | :---- |

**Trabalho 01 – Programação Orientada a Eventos**

*Vila em Tempo Real*

**Semestre:** 2026/2

**Entrega:** 04/11/2026

**Modalidade:** individual ou em dupla

**Valor:** 10,0 pontos

# **1\. Objetivo**

Desenvolver uma aplicação web em tempo real, no estilo de um **jogo de vila cooperativo**. Vários jogadores acessam a mesma vila. Quando um deles faz uma ação, o servidor decide o que acontece e **todos veem o resultado na hora**, sem recarregar a página.

O foco é o paradigma: **o fluxo do programa é controlado por eventos** (emitir, escutar e reagir), e não por chamadas diretas ou laços que ficam verificando se algo mudou. O visual é secundário.

# **2\. O que construir**

## **Deve ter**

* **Dois papéis:** o **Mestre** inicia e encerra a temporada; o **Jogador** constrói.

* **Tempo real com estado no servidor:** use Socket.IO, WebSocket ou outra tecnologia de tempo real, na linguagem que você escolher (veja “Linguagem livre”). O servidor decide; o cliente só pede e mostra.

* **Uma tela** com o estoque de recursos, os trabalhadores ocupados (por exemplo 14/15), o botão de construir e a **vila desenhada** (no kit ela vem pronta, em Phaser; em outra tecnologia, um visual simples com emojis ou CSS basta), com mensagens de sucesso, recusa e fim de obra. Você liga cada evento a uma reação na vila.

* **Painel de eventos** na tela: lista, em tempo real, cada evento que o cliente **emitiu** (⬆ emit) e **escutou** (⬇ on), com nome, horário, dados, a **causa** (o pedido ou o temporizador que gerou o fato) e a **reação** do cliente. É a parte da interface que mostra o paradigma funcionando.

* **Passagem do tempo:** o servidor produz recursos automaticamente a cada intervalo e avisa todos. A obra de uma construção termina sozinha depois de alguns segundos.

* **Limites:** se faltar recurso ou trabalhador, só quem pediu recebe a recusa. Se dois jogadores pedirem o último recurso ao mesmo tempo, só um consegue.

* **Nome dos desenvolvedores no rodapé** da aplicação.

## **Linguagem livre**

Você pode escolher **qualquer linguagem de programação**, e as bibliotecas que preferir, **desde que os fundamentos da programação orientada a eventos estejam aplicados** e visíveis no código:

* eventos com nome, **emitidos** (emit) e **escutados** por handlers (on);

* o **servidor como fonte da verdade**, tratando **um evento por vez**;

* **pedidos** do cliente separados dos **fatos** do servidor, com a **recusa** também como evento;

* **temporizadores** do servidor como fonte de eventos (produção e obra);

* a **causa** de cada evento visível no Painel de eventos;

* comunicação em **tempo real** entre vários clientes (Socket.IO, WebSocket ou equivalente).

O Guia de Implementação e o Kit Inicial usam Python no servidor e JavaScript (Vue e Phaser) na tela. Quem escolher outra linguagem pode usá-los como referência, mas precisa adaptar o que for necessário e **informar no README** a linguagem e as bibliotecas usadas.

## **Não precisa**

Login e senha, banco de dados (a memória do servidor basta), criar gráficos do zero (a vila desenhada já vem pronta no kit) e publicação na internet. Para trocar o visual, use emojis, CSS ou imagens de uso livre, com crédito no README e sem copiar arte de jogos comerciais.

Extras (como missões com prazo, níveis da vila ou um mapa personalizado no Tiled) são bem-vindos, mas só depois de tudo funcionando e listados no README.

# **3\. Eventos mínimos**

Sua aplicação deve ter, no mínimo, estes sete eventos. Você pode renomeá-los e adaptá-los ao seu tipo de vila, e criar outros.

| Evento | Emite | Recebe | O que acontece |
| :---- | :---- | :---- | :---- |
| vila.iniciada | Servidor | Todos | O Mestre abre a temporada e a produção começa |
| construcao.solicitada | Jogador | Servidor | Pedido para construir |
| construcao.iniciada | Servidor | Todos | Pedido aceito: debita o custo, ocupa um trabalhador e inicia a obra |
| operacao.recusada | Servidor | Só quem pediu | Faltou recurso ou trabalhador, ou a temporada não está aberta |
| recurso.produzido | Servidor | Todos | A cada intervalo, o estoque sobe |
| construcao.concluida | Servidor | Todos | A obra termina e o trabalhador fica livre |
| vila.encerrada | Servidor | Todos | O Mestre encerra e novas ações são recusadas |

**Padrão de nomes:** objeto.acao\_no\_passado para o que o servidor confirma e objeto.acao\_solicitada para o que o cliente pede.

# **4\. Tipo de vila e equipe**

* **Tipo de vila:** definido por **sorteio**, realizado pelo professor. Todas seguem a mesma estrutura; adapte os nomes dos recursos e das construções.

* **Individual ou dupla:** a dupla acrescenta ao painel **contadores por evento**: quantas vezes cada evento já ocorreu.

# **5\. Como trabalhar**

1. **Especifique antes de programar.** Crie o arquivo docs/especificacao.md e faça o commit **antes do código**. Ele deve ter: (a) a tabela de eventos da seção 3, adaptada ao seu tipo de vila; (b) as regras, como custos, tempos e limite de trabalhadores; (c) três cenários de teste escritos com eventos: uma recusa, a passagem do tempo e uma disputa entre dois jogadores. Não cite tecnologia.

| Exemplo de cenário (disputa): dado que há 14 de 15 trabalhadores ocupados, quando os jogadores A e B emitem construcao.solicitada ao mesmo tempo, então o servidor emite construcao.iniciada para um deles e operacao.recusada apenas para o outro. |
| :---- |

2. **Programe em etapas, com um commit por etapa.** Sugestão: conectar e mostrar o estado; o Mestre inicia; pedir e construir; recusa; tempo (produção e obra); encerrar e disputa. Teste cada etapa com duas abas abertas.

3. **Entregue** conforme a seção 6\.

**Material de apoio:** o professor fornece o **Guia de Implementação** (passo a passo) e o **Kit Inicial** (tela com **Vue 3** e **Phaser 3** por CDN, esqueleto do servidor em Python e modelos de especificação e README). Você pode usá-los ou não, conforme a linguagem escolhida. Com o kit, nada precisa ser instalado além de Python e Git.

**Uso de IA:** permitido, mas **não é necessário**. O GitHub Spec Kit pode ser usado para escrever a especificação, mas também é opcional. Se usar qualquer IA, conte no README o que usou e o que você mudou. Em todos os casos, cada membro deve saber **explicar qualquer evento** do projeto: quem emite, quem escuta e o que muda.

# **6\. Entrega pelo GitHub**

A entrega é feita **pelo GitHub**. Crie o repositório seguindo estas regras:

* **Conta e repositório:** na **sua** conta, **vazio** ao criar (sem README, .gitignore ou licença automáticos). Em dupla, **um** repositório só, na conta de um dos dois.

* **Nome:** lpp-trabalho01-seunome (dupla: lpp-trabalho01-nome1-nome2), em minúsculas e sem acentos.

* **Acesso:** público, ou privado com o professor como colaborador (usuário **\[@usuario-do-professor\]**).

* **Histórico:** commits ao longo do trabalho, com a especificação antes do código e um commit por etapa. Em dupla, os dois fazem commits.

* **Prazo:** envie o **link** do repositório em **\[plataforma da disciplina\]** até **\[data e hora\]**. Commits depois do prazo não são considerados.

O repositório deve conter:

* docs/especificacao.md, commitado antes do código;

* o código-fonte, com comentários nos pontos em que um evento é emitido ou escutado, explicando o porquê;

* README.md com o nome e o @ do GitHub de todos os membros, como instalar e executar, como testar com duas abas, o uso de IA (ou “Não utilizei IA”) e as respostas às três perguntas abaixo.

**Perguntas do README:**

* Quais eventos o seu sistema emite e escuta?

* Como o sistema sabe quando deve atualizar os outros jogadores?

* Que parte do código mostra claramente o uso do paradigma orientado a eventos?

# **7\. Avaliação**

| Critério | O que se avalia | Pontos |
| :---- | :---- | ----- |
| Especificação | docs/especificacao.md com a tabela de eventos, as regras e os três cenários, feita antes do código | 2,0 |
| Eventos (emit/on) | Emissão e escuta corretas em servidor e cliente; pedido do cliente e fato do servidor bem separados; nomes no padrão | 2,5 |
| Fluxo em tempo real | Eventos encadeados da abertura ao encerramento; produção e obra por temporizador; recusa e disputa tratadas; tudo sem recarregar a página | 2,0 |
| Painel de eventos e interface | Painel mostrando emit, on, causa e reação de cada evento do catálogo; vila desenhada e avisos atualizando sozinhos, com feedback de sucesso, recusa e fim de obra | 1,5 |
| Código | Organização, nomes coerentes e comentários nos pontos de emissão e escuta | 1,0 |
| README e GitHub | Repositório criado conforme as regras da seção 6; membros com @, instruções de execução, respostas às perguntas, nome no rodapé | 1,0 |
| **Total** |  | **10,0** |

**Penalizações:** −0,10 por funcionalidade incompleta ou fora do escopo. Repositório que o professor não consegue acessar não é corrigido. Especificação commitada depois do código perde os 2,0 pontos do critério “Especificação”. Dupla sem os contadores por evento perde 0,5 ponto em “Painel de eventos e interface”.

# **Apêndice. Exemplo mínimo de emit e on**

Serve apenas para entender o mecanismo. A vila, as regras e os eventos são seus. O exemplo está em Python; em outras linguagens a ideia é a mesma, com a biblioteca de Socket.IO ou de WebSocket dela.

## **Servidor (Python)**

| Instalação: pip install python-socketio uvicorn. Execução: uvicorn server:app. |
| :---- |

import socketio

sio \= socketio.AsyncServer(async\_mode="asgi", cors\_allowed\_origins="\*")

app \= socketio.ASGIApp(sio, static\_files={"/": "client/index.html"})

estado \= {"toras": 100}

@sio.on("construcao.solicitada")       \# escuta o pedido do cliente

async def ao\_construir(sid, dados):

    if estado\["toras"\] \< 50:           \# o servidor decide

        await sio.emit("operacao.recusada", {"motivo": "sem toras"},

                       to=sid)          \# só quem pediu recebe

        return

    estado\["toras"\] \-= 50

    await sio.emit("construcao.iniciada", estado)    \# todos recebem

async def producao():                  \# temporizador do servidor

    while True:

        await sio.sleep(5)

        estado\["toras"\] \+= 10

        await sio.emit("recurso.produzido", estado)

\# inicie quando o Mestre abrir a temporada (vila.iniciada):

\# sio.start\_background\_task(producao)

## **Cliente (HTML e JavaScript)**

\<script src="https\://cdn.socket.io/4.7.5/socket.io.min.js"\>\</script\>

\<script\>

  const socket \= io();

  socket.on("construcao.iniciada", (e) \=\> mostrar(e));

  socket.on("operacao.recusada", (d) \=\> avisar(d.motivo));

  socket.on("recurso.produzido", (e) \=\> mostrar(e));

  function construir() {               // pedido: cliente \-\> servidor

    socket.emit("construcao.solicitada", {});

  }

\</script\>

| Disputa pelo último recurso: o servidor processa um evento por vez. Valide e altere o estado sem await entre os dois passos, e dois pedidos simultâneos serão decididos em sequência: um vence e o outro recebe a recusa. |
| :---- |

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEYAAAA2CAYAAAB6DO9FAAAE6ElEQVR4Xu2ZT2xURRzHHwmGg1wULpiQEFJtGzygBwIN6YGDQFsb9QyacgTlZgRLGkyrRYWDjYm9mFClhmpJW8uBthzEiK2VhEDSaGJ6ISZqSaSANgRsx523b97+9ju/mTfzdrd9wH6SX3b2N7+Zvt+n7832TxA8wuxsel3IwPxjy87mN0IhVTEEKkRGw559S1jz2FG9Sxhebmv/qiqFgZOy/tA7Yv1bR+PYfPm343T+kYeVQoRg0Dojdc0nRV3LqbBYjuMcGavXF/adG1RztIZbUxifYutdwcOUkyDfN7Ye+F29RxHr3jyygDm6niW84IqKOSlqmz7S6l1BIZwUmoubP/wu+7Wc5YQXnEKMyu3qEttwTY413Pq0YjBH4aTQeY516uwxyAspVQyOa/ee0NZhrQ82Ma+0HTudJKbz50mhgua52iJsYrBxFzH0Pb6qsQ82MfQx4hqlUlS8N3XZKjImvGBGzEtB8CQ2mkUxasw1qGR0/HDpTyqnX/z3qZzPPVLhoYzrQsILZsTEc2RsEoOh5upf/ewa1sqxKw179i8mHbzy1fqdB/CxMq7DZvCVjjkxuZdNKodz3Hs5dgWlUDmMqLVkbIXKMR7ApqbonBqbPq5pw7h2V8fcCdzLFe4OQUFpOCMedONhrOHTqI8YbuwrhqMcYiRSTNeVKfseuR/AflHnzMNAOcS0f3dxMfGueRgpVYykKsaAXczQLWGNHLu7RQ0uM/F0EOzAc6gcZ0slwI/uYlAERo4X9w9N4zIT2w9ODqCUrIqRlCTGB3mIo5SqmED/+AcxW4qKffnim8L19H3Njz3JhpgU+xll0ByXdyQbYobnvfdLvDO4nAdmMfJiUUalxATBM0XFLsjGTw/cx3S5MIuRoAxGDGnOCgqJ1m3COmdcHpWkeQusmHg/lEFjQlyVJS5iUAjcLelIEpM0n0B6MdFd8/xrvbN0LQcKKYsYefhyjRdyNey8IyWLkdiapP8JwAgLxsUMLMkEFReDMjQxZB8rd8UxTFWSsonh5KAITYrEVUwJj0UaShMzeFOTU9/a83dd88eaCAy1Loti2F8itcMcZWBEYONJES46JzbEXycJVzGudRY0KZL8vk8UEigCIwIbt0XR3q5o3zEDLjUJWMQQUATGuPhElaIAUxTt7YO8uAvfn8d0jF3eakxwsI+RRNsXRXAR0fKBYP8YxUoZE3tTidEuMELNGebZZhlCMdM/6rXaviiBCwKKYKVI8mv/Lcq5oJr/9uKolksQ0y/EU5indF6Z4u+WLwcX+H1RBBeEZ3e/v2SVIoE1HqzSRFAhBjnGR4RgrJH7fd6v5zUJXPiQZg3lH7GVlaLA9xHGxgP7nGk/NzGujfrWp8HQSL+4f1YJ4ALrYwz75UEJprAxJhqd6kqFu4siPpy5PodCIimrsDbEslceFGALjgnRmVhTLu6I5+zNFB4d650iSdjHT4yKCfFrMHyby5/B7cuObOi26MK0F4l3iwIbTBvLgXNTFuT6obHwD3J2sMG0sVzIxuh/E3zwFotN+sZy4t0cQa6b/asX02awUZ9YCdLISbMmBBt2jZVgXmz2atSnlgWbToqVRDWbb3gjTocMjP4U18yLdpz2A5s3RRagcmxxduQPXJoOlICRJUbGb2giaJh++k3NhOjJtBCkt+9ekZA74m0sMfE/HcGUTNy8188AAAAASUVORK5CYII=> "Logo"