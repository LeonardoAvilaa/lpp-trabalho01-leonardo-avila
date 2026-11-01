

| ![Logo da instituição][image1] | Linguagem de Programação e Paradigmas *Prof. Esp. Ademar Perfoll Junior* Sistemas de Informação |
| :---- | :---- |

**Guia de Implementação – Vila em Tempo Real**

*Trabalho 01 · Programação Orientada a Eventos · 2026/2*

# **1\. Como usar este guia**

Este guia leva você, **uma etapa por vez**, do zero até a vila funcionando em tempo real. Junto com ele você recebe o **Kit Inicial**, que contém a tela pronta (com a vila desenhada em Phaser e o **Painel de eventos**), o esqueleto do servidor e os modelos de especificação e de README.

* As **etapas 0 a 6** constroem uma **vila de exemplo** com um único recurso (toras). Ao final delas você tem o fluxo mínimo do trabalho funcionando.

* A **etapa 7** é obrigatória só para duplas. A **etapa 8** pede que você adapte tudo ao **seu tipo de vila** (sorteado) e à **sua especificação**.

* Em cada etapa: escreva o código, **teste com duas abas abertas** e faça **um commit**.

| Antes da etapa 0: preencha o docs/especificacao.md do kit (regras, tabela de eventos e três cenários de teste) e faça o commit. A especificação vem antes do código. |
| :---- |

# **2\. Ferramentas**

| Peça | Ferramenta | Papel no projeto |
| :---- | :---- | :---- |
| Servidor | Python 3, python-socketio e uvicorn | Guarda o estado, decide o que acontece e emite os eventos |
| Comunicação | Socket.IO | Leva os eventos entre o navegador e o servidor, nos dois sentidos |
| **Front-end (tela)** | **Vue 3**, carregado por CDN (sem instalar nada) | Mostra o painel e os botões a partir do estado e os atualiza sozinho |
| **Jogo (visual)** | **Phaser 3**, carregado por CDN (sem instalar nada) | Desenha a vila (terreno, obras e casas) e anima o que acontece |
| **Mapa (opcional)** | **Tiled**, editor de mapas gratuito (mapeditor.org) | Edita o cenário em client/assets/vila.json sem programar |

## **Por que Vue?**

* **A tela é um reflexo do estado.** O servidor emite um fato, o cliente atualiza o estado e o Vue redesenha a tela. Você não mexe no HTML na mão, e isso deixa o foco nos eventos.

* **Sem instalação nem build:** basta um arquivo HTML com duas tags \<script\>.

* É uma biblioteca muito usada no mercado, então o que você aprende aqui serve depois.

## **Por que Phaser?**

* É a biblioteca de **jogos 2D** mais usada na web, gratuita (licença MIT) e com muito material de estudo. Ela desenha a vila em um canvas e anima os objetos.

* **Você não programa gráficos.** A cena da vila já vem pronta no kit, com **um método para cada evento** do servidor. Seu trabalho é fazer cada ouvir(...) chamar o método certo.

* Isso mostra o paradigma de forma visível: o servidor **emite** um fato, o cliente **escuta** e a vila **reage**.

* Vue e Phaser dividem o trabalho: o Vue cuida do painel, dos botões e dos avisos; o Phaser cuida do desenho.

## **Como o Phaser se encaixa nos eventos**

| Evento do servidor | Você chama | O que aparece na vila |
| :---- | :---- | :---- |
| estado.sincronizado | jogo.mostrarEstado(d.estado) | A vila como está agora (casas e obras) |
| vila.iniciada | jogo.vilaIniciada() | Faixa “☀️ Temporada aberta” |
| construcao.iniciada | jogo.obraIniciada(d.estado) | Canteiro 🚧 com barra de progresso e “-50 🪵” |
| operacao.recusada | jogo.recusado(d.motivo) | A tela treme e mostra ✋ com o motivo (só para quem pediu) |
| recurso.produzido | jogo.recursoProduzido(d.estado) | “+10 🪵” sobe do acampamento |
| construcao.concluida | jogo.obraConcluida(d.estado) | O canteiro vira uma casa 🏠 |
| vila.encerrada | jogo.vilaEncerrada() | Faixa “🌙 Temporada encerrada” e a vila escurece |

## **O Painel de eventos: onde você vê o paradigma**

A vila desenhada mostra **o resultado** dos eventos. O **Painel de eventos** mostra **os próprios eventos**: o que o cliente **emitiu** (emit), o que ele **escutou** (on), o que causou cada fato e como o cliente reagiu. Ele é obrigatório para todos e faz parte da avaliação.

| No painel | O que representa |
| :---- | :---- |
| **⬆ emit** (azul) | Este cliente **pediu** algo ao servidor, como construcao.solicitada. É um **pedido**. |
| **⬇ on** (verde) | Este cliente **escutou** um evento do servidor e reagiu. É um **fato**, como construcao.iniciada. |
| **⬇ on** (vermelho) | O servidor **recusou** o pedido: operacao.recusada. |
| causa | O que **gerou** o fato: um pedido (por exemplo construcao.solicitada) ou o temporizador. É o **encadeamento de eventos** aparecendo na tela. |
| dados | O que veio junto com o evento (quem pediu, estoque, motivo da recusa). |
| reação | O que o cliente fez ao ouvir. É uma frase **sua**, escrita no ouvir(...). |

Exemplo do que o painel de um Jogador mostra, do mais antigo para o mais novo:

⬆ emit  construcao.solicitada

⬇ on    construcao.iniciada   causa: construcao.solicitada

        reação: mostra o canteiro de obras

⬇ on    recurso.produzido     causa: temporizador

⬇ on    construcao.concluida  causa: construcao.iniciada (temporizador)

        reação: transforma o canteiro em casa

Repare que o recurso.produzido aparece **sozinho**, sem ninguém clicar: é o servidor emitindo por causa de um temporizador. Para isso você usa duas funções que o kit fornece: pedir(...) no lugar de socket.emit(...) e ouvir(...) no lugar de socket.on(...). Elas fazem o mesmo trabalho e **escrevem no painel**.

## **O mínimo de Vue que você precisa**

| Recurso | O que faz |
| :---- | :---- |
| ref(...) e reactive(...) | Criam dados que o Vue observa. Quando mudam, a tela muda. |
| {{ estado.toras }} | Mostra um valor na tela. |
| @click="construir" | Chama a função construir quando o botão é clicado (é um evento do navegador). |
| v-if e v-else | Mostram ou escondem um pedaço da tela. |
| v-for | Repete um elemento para cada item de uma lista. |

| Regra de ouro: o cliente nunca altera o estado por conta própria. Ele só muda quando chega um evento do servidor. Isso mantém todos os jogadores vendo a mesma coisa. |
| :---- |

# **3\. Repositório e ambiente**

## **Repositório no GitHub (regras de entrega)**

A entrega do trabalho é feita **pelo GitHub**. Crie o repositório seguindo estas regras:

1. Crie o repositório na **sua conta** do GitHub, **vazio** (sem README, .gitignore ou licença automáticos). Em dupla, é **um** repositório só, na conta de um dos dois.

2. **Nome:** lpp-trabalho01-seunome (dupla: lpp-trabalho01-nome1-nome2), em minúsculas e sem acentos.

3. **Visibilidade:** público. Se preferir privado, adicione o professor como colaborador (usuário **\[@usuario-do-professor\]**).

4. **Conteúdo:** a estrutura do kit (client/, docs/, server.py, requirements.txt, README.md, .gitignore). Não envie a pasta .venv.

5. **Histórico:** a especificação em docs/ **antes** do código e **um commit por etapa**. Em dupla, os dois fazem commits e aparecem no README.md com nome e @.

6. **Entrega:** envie o **link** do repositório em **\[plataforma da disciplina\]** até **\[data e hora\]**. Commits depois do prazo não são considerados.

**Primeiros passos** (troque SEU-USUARIO e o nome do repositório):

git clone https\://github.com/SEU-USUARIO/lpp-trabalho01-seunome.git

cd lpp-trabalho01-seunome

\# copie TODO o conteúdo do kit para dentro desta pasta (inclusive o .gitignore)

\# preencha docs/especificacao.md e depois:

git add .

git commit \-m "docs: especificação da vila"

git push

O aviso “You appear to have cloned an empty repository” é normal. Para o git push pedir login, use o acesso pelo VS Code ou pelo GitHub Desktop, ou um token pessoal.

## **Ambiente**

Dentro da pasta do repositório, abra um terminal e rode:

python \-m venv .venv

.venv\\Scripts\\activate            \# Windows

source .venv/bin/activate         \# Linux ou macOS

pip install \-r requirements.txt

uvicorn server:app \--reload

Abra **http\://localhost:8000** no navegador (e não o arquivo direto, com file://). Para testar, abra **duas abas** lado a lado.

Estrutura do kit:

vila/

├── client/index.html      \# tela (Vue) \- você escreve as ESCUTAS e os PEDIDOS

├── client/assets/         \# mapa (vila.json), peças e sprites da vila

├── server.py              \# servidor \- você escreve a partir da Etapa 1

├── docs/especificacao.md  \# preencha ANTES do código

├── requirements.txt

└── README.md              \# preencha ao final

| O estado da vila fica na memória do servidor. Sempre que o uvicorn \--reload reinicia (ao salvar o arquivo), a vila volta ao começo. Depois de salvar, recarregue as abas e entre de novo. |
| :---- |

# **4\. Passo a passo**

## **Etapa 0 – Servidor no ar e tela aberta**

**Objetivo:** o servidor sobe e a tela abre. **Eventos:** nenhum ainda.

**Servidor** (server.py, já vem no kit):

import socketio

sio \= socketio.AsyncServer(async\_mode="asgi", cors\_allowed\_origins="\*")

app \= socketio.ASGIApp(sio, static\_files={

    "/": "client/index.html",

    "/assets": "client/assets",      \# mapa, tileset e sprites da vila

})

**Cliente** (client/index.html, já vem no kit). Leia o arquivo com calma. Ele já tem a tela e o estado do Vue, e três regiões que você vai preencher:

* **ESCUTAS:** ouvir("evento", "reação", função) significa “quando o servidor **emitir** esse evento, registre no painel e rode a função”. Por dentro ele usa socket.on. A **reação** é uma frase sua, curta, sobre o que o cliente faz.

* **PEDIDOS:** pedir("evento") significa “**peça** isso ao servidor”: registra no painel e usa socket.emit. Há uma função para cada botão.

* atualizar(d) copia o estado enviado pelo servidor para a tela. avisar(texto, tipo) mostra uma mensagem.

* O **primeiro** bloco \<script\> é a vila desenhada (Phaser): já vem pronta, **não altere**. O **segundo** é a aplicação (Vue e Socket.IO), onde você trabalha. Os métodos jogo.algumaCoisa(...) são os da tabela da seção 2\.

**Teste:** rode o servidor, abra a página, digite um nome e entre como Jogador. Aparece a tela da vila com o painel zerado (Toras: 0), o **Painel de eventos** vazio (“Nenhum evento ainda”) e a vila desenhada vazia (grama, caminho e o acampamento de lenha 🪓🪵), com a faixa “Aguardando o Mestre”. Você conectou, mas o servidor ainda não mandou nada.

**Commit:** feat: kit inicial e esqueleto do servidor e depois git push.

## **Etapa 1 – Conectar e sincronizar o estado**

**Evento:** estado.sincronizado (servidor → **um** cliente).

**Servidor** – acrescente ao final do server.py:

CUSTO \= 50          \# toras por construção

TEMPO\_OBRA \= 8      \# segundos até a obra terminar

INTERVALO \= 5       \# segundos entre as produções

estado \= {

    "fase": "aguardando",     \# aguardando \-\> aberta \-\> encerrada

    "toras": 150,

    "trabalhadores": 0,       \# ocupados agora

    "limite": 2,              \# máximo de trabalhadores

    "producao": 10,           \# toras produzidas a cada INTERVALO

    "intervalo": INTERVALO,

    "tempo\_obra": TEMPO\_OBRA,

    "custo": CUSTO,

    "concluidas": 0,

    "em\_obra": 0,

}

jogadores \= {}                \# sid \-\> {"nome": ..., "papel": ...}

def fato(causa, \*\*extras):

    """Monta o payload de um FATO: o estado atual, a CAUSA (o evento ou o

    temporizador que gerou o fato) e dados extras."""

    return {"estado": dict(estado), "causa": causa, \*\*extras}

@sio.event

async def connect(sid, environ, auth):

    auth \= auth or {}

    jogadores\[sid\] \= {

        "nome": auth.get("nome", "Anônimo"),

        "papel": auth.get("papel", "jogador"),

    }

    \# servidor \-\> UM cliente: entrega o estado atual

    await sio.emit("estado.sincronizado", fato("conexao"), to=sid)

@sio.event

async def disconnect(sid):

    jogadores.pop(sid, None)

**Cliente** – dentro de entrar(), na região ESCUTAS:

ouvir("estado.sincronizado", "guarda o estado e desenha a vila", (d) \=\> {

  atualizar(d);

  jogo.mostrarEstado(d.estado);

});

**Teste:** abra duas abas e entre nas duas. As duas mostram Toras: 150 e Temporada: aguardando, e a vila desenhada exibe a faixa “Aguardando o Mestre”. No **Painel de eventos** aparece ⬇ on estado.sincronizado, com causa: conexao e a sua reação.

| O que é \`fato(...)\`: todo fato que o servidor emite é montado por fato(causa, ...): o estado atual, mais a causa, que é o evento ou o temporizador que gerou o fato. É isso que o painel mostra e que deixa o encadeamento visível. |
| :---- |

| Para pensar: por que o estado é enviado com to=sid (só para quem conectou) e não para todos? Porque quem já estava conectado já tem o estado. Só o recém-chegado precisa dele. |
| :---- |

**Commit:** feat: conexão e estado.sincronizado e depois git push.

## **Etapa 2 – O Mestre abre a temporada**

**Eventos:** vila.abertura\_solicitada (Mestre → servidor, é um **pedido**) e vila.iniciada (servidor → **todos**, é um **fato**).

**Servidor** – acrescente ao final do server.py:

async def recusar(sid, motivo, causa):

    """Responde só a quem pediu."""

    await sio.emit("operacao.recusada", {"motivo": motivo, "causa": causa}, to=sid)

@sio.on("vila.abertura\_solicitada")

async def abrir\_vila(sid, dados=None):

    pedido \= "vila.abertura\_solicitada"

    if jogadores\[sid\]\["papel"\] \!= "mestre":

        await recusar(sid, "Só o Mestre pode abrir a temporada", pedido)

        return

    if estado\["fase"\] \!= "aguardando":

        await recusar(sid, "A temporada já foi aberta", pedido)

        return

    estado\["fase"\] \= "aberta"

    await sio.emit("vila.iniciada", fato(pedido))   \# para todos

**Cliente** – na região ESCUTAS:

ouvir("vila.iniciada", "muda a faixa para temporada aberta", (d) \=\> {

  atualizar(d);

  avisar("A temporada começou\!", "ok");

  jogo.vilaIniciada();

});

**Cliente** – dentro da função abrirVila(), na região PEDIDOS:

pedir("vila.abertura\_solicitada");

**Teste:** em uma aba entre como **Mestre** e em outra como **Jogador**. Clique em “Abrir temporada” no Mestre: na aba do Jogador a fase muda para aberta, aparece o aviso e a faixa da vila vira “☀️ Temporada aberta”, **sem recarregar**. No painel do Mestre aparece ⬆ emit vila.abertura\_solicitada e depois ⬇ on vila.iniciada (causa: vila.abertura\_solicitada). No painel do Jogador aparece só o ⬇ on, porque quem pediu foi o Mestre.

O servidor também já emite operacao.recusada (por exemplo, quando um Jogador tenta abrir). A tela só vai mostrar isso na Etapa 4\.

**Commit:** feat: Mestre abre a temporada (vila.iniciada) e depois git push.

## **Etapa 3 – Pedido e fato: construir**

**Eventos:** construcao.solicitada (Jogador → servidor) e construcao.iniciada (servidor → **todos**).

**Servidor** – acrescente ao final do server.py:

@sio.on("construcao.solicitada")

async def construir(sid, dados=None):

    pedido \= "construcao.solicitada"

    estado\["toras"\] \-= CUSTO

    estado\["trabalhadores"\] \+= 1

    estado\["em\_obra"\] \+= 1

    nome \= jogadores\[sid\]\["nome"\]

    await sio.emit("construcao.iniciada", fato(pedido, por=nome))

**Cliente** – na região ESCUTAS:

ouvir("construcao.iniciada", "mostra o canteiro de obras", (d) \=\> {

  atualizar(d);

  avisar(d.por \+ " iniciou uma obra");

  jogo.obraIniciada(d.estado);

});

**Cliente** – dentro da função construir(), na região PEDIDOS:

pedir("construcao.solicitada");

**Teste:** reinicie o servidor, abra o Mestre e um Jogador e abra a temporada. O Jogador clica em “Construir”: as toras caem de 150 para 100 e os trabalhadores vão para 1/2, **nas duas abas**, junto com o aviso “… iniciou uma obra”. Na vila desenhada aparece um **canteiro 🚧 com barra de progresso** e um “-50 🪵” sobe do acampamento. No painel do Jogador aparecem ⬆ emit construcao.solicitada e, em seguida, ⬇ on construcao.iniciada com causa: construcao.solicitada. O Mestre vê **só** o ⬇ on, porque não fez o pedido.

| Bug proposital: clique em “Construir” quatro vezes. As toras ficam em \-50 e os trabalhadores em 4/2. Nada está validando o pedido. A próxima etapa corrige isso. |
| :---- |

**Commit:** feat: construção (construcao.solicitada e construcao.iniciada) e depois git push.

## **Etapa 4 – Recusa: só quem pediu é avisado**

**Evento:** operacao.recusada (servidor → **um** cliente).

**Servidor** – **substitua** a função construir inteira por esta:

@sio.on("construcao.solicitada")

async def construir(sid, dados=None):

    pedido \= "construcao.solicitada"

    \# Valide TUDO antes de alterar o estado e sem await no meio:

    \# assim, dois pedidos simultâneos são decididos um de cada vez.

    if estado\["fase"\] \!= "aberta":

        motivo \= "A temporada não está aberta"

    elif estado\["toras"\] \< CUSTO:

        motivo \= "Toras insuficientes"

    elif estado\["trabalhadores"\] \>= estado\["limite"\]:

        motivo \= "Sem trabalhador livre"

    else:

        motivo \= None

    if motivo:

        await recusar(sid, motivo, pedido)    \# só quem pediu recebe

        return

    estado\["toras"\] \-= CUSTO

    estado\["trabalhadores"\] \+= 1

    estado\["em\_obra"\] \+= 1

    nome \= jogadores\[sid\]\["nome"\]

    await sio.emit("construcao.iniciada", fato(pedido, por=nome))

**Cliente** – na região ESCUTAS:

ouvir("operacao.recusada", "avisa o motivo e a tela treme", (d) \=\> {

  avisar(d.motivo, "erro");

  jogo.recusado(d.motivo);

});

**Teste** (reinicie o servidor antes):

1. O Jogador clica em “Construir” **antes** de o Mestre abrir: aparece o aviso vermelho “A temporada não está aberta” e a vila **treme** mostrando ✋, **só nessa aba**. No painel, o ⬇ on operacao.recusada aparece em **vermelho**, com causa e motivo, apenas para quem pediu.

2. O Mestre abre a temporada. O Jogador constrói duas vezes: toras em 50 e trabalhadores em 2/2.

3. Terceiro clique: “Sem trabalhador livre”. As toras **nunca** ficam negativas.

Para ver a recusa “Toras insuficientes”, aumente temporariamente limite para 5 no estado e construa várias vezes.

| Por que validar no servidor e não só desabilitar o botão? Porque o servidor é a fonte da verdade. Vários jogadores pedem ao mesmo tempo e o botão de uma aba pode estar desatualizado. |
| :---- |
| **Sem** await **entre validar e alterar:** o servidor processa um evento por vez. Se você validar e alterar o estado **sem** await no meio, dois pedidos simultâneos são decididos em sequência: um vence e o outro é recusado. Um await entre os dois passos abriria espaço para os dois passarem na validação. |

**Commit:** feat: validações e operacao.recusada e depois git push.

## **Etapa 5 – A passagem do tempo**

**Eventos:** recurso.produzido e construcao.concluida (servidor → **todos**), disparados por **temporizadores do servidor**, e não por cliques.

**Servidor** – acrescente ao final do server.py:

async def producao():

    while estado\["fase"\] \== "aberta":

        await sio.sleep(INTERVALO)

        if estado\["fase"\] \!= "aberta":

            break

        estado\["toras"\] \+= estado\["producao"\]

        await sio.emit("recurso.produzido", fato("temporizador"))

async def obra(nome):

    await sio.sleep(TEMPO\_OBRA)

    if estado\["fase"\] \!= "aberta":

        return

    estado\["trabalhadores"\] \-= 1

    estado\["em\_obra"\] \-= 1

    estado\["concluidas"\] \+= 1

    estado\["producao"\] \+= 5       \# cada obra concluída aumenta a produção

    causa \= "construcao.iniciada (temporizador)"

    await sio.emit("construcao.concluida", fato(causa, por=nome))

**Servidor** – inicie os temporizadores. Na função abrir\_vila, acrescente a linha marcada:

    estado\["fase"\] \= "aberta"

    sio.start\_background\_task(producao)                \# nova linha

    await sio.emit("vila.iniciada", fato(pedido))   \# para todos

**Servidor** – na função construir, acrescente a linha marcada ao final:

    await sio.emit("construcao.iniciada", fato(pedido, por=nome))

    sio.start\_background\_task(obra, nome)                  \# nova linha

**Cliente** – na região ESCUTAS:

ouvir("recurso.produzido", "atualiza as toras e mostra o \+N", (d) \=\> {

  atualizar(d);

  jogo.recursoProduzido(d.estado);

});

ouvir("construcao.concluida", "transforma o canteiro em casa", (d) \=\> {

  atualizar(d);

  avisar("Obra de " \+ d.por \+ " concluída\! A produção aumentou.", "ok");

  jogo.obraConcluida(d.estado);

});

**Teste:** reinicie, abra a temporada e construa uma vez. Nas duas abas, as toras sobem de 10 em 10 a cada 5 segundos, sozinhas, e o painel mostra \+120/min. Após 8 segundos a obra termina: trabalhadores voltam a 0/2, “concluídas” vira 1 e a produção sobe para \+180/min. Na vila, um “+10 🪵” sobe do acampamento a cada produção e, quando a obra termina, o canteiro 🚧 vira uma casa 🏠. No painel, recurso.produzido aparece **sozinho**, com causa: temporizador, e construcao.concluida aparece com causa: construcao.iniciada (temporizador). Marque “ocultar recurso.produzido” se ele atrapalhar a leitura.

| Temporizador é fonte de evento. A função producao() roda em segundo plano e emite o resultado. O cliente só escuta; ele nunca pergunta “já produziu?”. Use await sio.sleep(...). Com time.sleep(...) o servidor inteiro trava. |
| :---- |

**Commit:** feat: produção automática e obra com tempo e depois git push.

## **Etapa 6 – Encerramento e disputa**

**Eventos:** vila.encerramento\_solicitado (Mestre → servidor) e vila.encerrada (servidor → **todos**).

**Servidor** – acrescente ao final do server.py:

@sio.on("vila.encerramento\_solicitado")

async def encerrar\_vila(sid, dados=None):

    pedido \= "vila.encerramento\_solicitado"

    if jogadores\[sid\]\["papel"\] \!= "mestre":

        await recusar(sid, "Só o Mestre pode encerrar a temporada", pedido)

        return

    if estado\["fase"\] \!= "aberta":

        await recusar(sid, "A temporada não está aberta", pedido)

        return

    estado\["fase"\] \= "encerrada"

    await sio.emit("vila.encerrada", fato(pedido))

**Cliente** – na região ESCUTAS:

ouvir("vila.encerrada", "escurece a vila e bloqueia novas ações", (d) \=\> {

  atualizar(d);

  avisar("Temporada encerrada.");

  jogo.vilaEncerrada();

});

**Cliente** – dentro da função encerrarVila(), na região PEDIDOS:

pedir("vila.encerramento\_solicitado");

**Teste do encerramento:**

* O Mestre clica em “Encerrar temporada”: todos passam a ver encerrada e a vila escurece com a faixa “🌙 Temporada encerrada”. No painel aparece ⬇ on vila.encerrada com causa: vila.encerramento\_solicitado.

* As toras param de subir e qualquer “Construir” é recusado com “A temporada não está aberta”.

**Teste da disputa** (use três abas: Mestre, Jogador A e Jogador B, lado a lado):

1. O Mestre abre a temporada. O Jogador A constrói uma vez (trabalhadores 1/2).

2. Clique em “Construir” no Jogador A e no Jogador B **quase ao mesmo tempo**, antes de a obra terminar.

3. Só um consegue (2/2). O outro vê “Sem trabalhador livre”. Os trabalhadores **nunca passam do limite**.

**Commit:** feat: encerramento da temporada e depois git push.

## **Etapa 7 – Contadores por evento (obrigatória para duplas)**

O painel de eventos já existe para todos. A dupla acrescenta **contadores**: quantas vezes cada evento já ocorreu. O kit já conta os eventos por trás (contadores); falta mostrá-los. No index.html, dentro do Painel de eventos, troque o comentário ETAPA 7 (dupla) por:

**Cliente** – no \<section class="eventos"\> do index.html:

\<div class="contadores"\>

  \<span v-for="(n, nome) in contadores" class="chip"\>{{ nome }} ×{{ n }}\</span\>

\</div\>

**Teste:** no alto do painel aparecem etiquetas como construcao.iniciada ×2 e vila.iniciada ×1, que crescem a cada evento. Quem faz o trabalho individualmente pode fazer esta etapa como extra.

**Commit:** feat: contadores por evento e depois git push.

## **Etapa 8 – Adapte à sua vila**

Até aqui você construiu a **vila de exemplo**. O seu trabalho é o **seu tipo de vila**. Atualize primeiro o docs/especificacao.md e só depois o código:

1. **Nomes:** troque o recurso, as construções, os textos e os emojis da tela e, se quiser, renomeie os eventos. Os nomes devem ser **iguais** na especificação, no server.py e no index.html.

2. **Reações:** a frase de cada ouvir(...) deve descrever o que o seu cliente faz e combinar com a coluna “O que muda” da sua especificação. O painel de eventos faz parte da entrega: não o remova.

3. **Números:** ajuste CUSTO, TEMPO\_OBRA, INTERVALO, limite, a produção inicial e o ganho por obra conforme a sua especificação.

4. **Recurso refinado:** por exemplo, quando uma obra termina, passa a produzir um segundo recurso (novo campo no estado e nova linha no painel).

5. **Um evento seu:** por exemplo, uma missão com prazo (missao.aceita e missao.expirada). Documente-o na especificação **antes** de programar.

6. **Visual:** a vila já vem com um mapa pronto. Personalize o cenário no Tiled (Anexo A) para ficar com a cara do seu tipo de vila. Se usar arte de terceiros, só de uso livre, e **credite** a fonte no README.md. Não copie arte de jogos comerciais.

| Um trabalho igual ao exemplo, sem adaptação ao seu tipo de vila, não cumpre o escopo. O professor poderá pedir que você explique qualquer evento: quem emite, quem escuta e o que muda no estado. |
| :---- |

# **5\. Problemas comuns**

| Sintoma | O que verificar |
| :---- | :---- |
| A tela abre mas aparece {{ ... }} ou io is not defined | Os scripts do Vue, do Socket.IO ou do Phaser não carregaram (sem internet ou rede bloqueada). Veja a solução abaixo. |
| A área da vila desenhada fica em branco | O Phaser não carregou (veja a solução abaixo) ou há erro no console (tecla F12). A vila só começa a ser desenhada depois que você entra. |
| A vila desenhada fica vazia ou aparece erro de mapa no console | Veja o Anexo A: o nome do tileset no código deve ser igual ao do Tiled, e o servidor precisa servir /assets (confira o static\_files do server.py). |
| Meu evento não aparece no Painel de eventos | Use ouvir(...) e pedir(...) em vez de socket.on(...) e socket.emit(...) diretos: só eles escrevem no painel. |
| Nada atualiza na outra aba | O nome do evento deve ser **idêntico** no on e no emit (letra por letra). Confira também se a outra aba foi recarregada depois de salvar. |
| TypeError: ... missing 1 required positional argument | Todo tratador de evento no servidor precisa do parâmetro dados=None: async def f(sid, dados=None). |
| A vila “voltou ao começo” | O \--reload reinicia o servidor ao salvar e apaga o estado da memória. É normal. Recarregue as abas. |
| Aviso “You are running a development build of Vue” no console | É normal na versão de desenvolvimento do CDN. Ignore. |
| Porta 8000 ocupada | Use uvicorn server:app \--reload \--port 8001 e abra http\://localhost:8001. |
| Erro de CORS ou página em branco | Abra pelo endereço http\://localhost:8000, não pelo arquivo file://. |

## **Se a rede bloquear o CDN**

Abra as três URLs dos scripts do index.html no navegador, salve-as em client/ como vue.global.js, socket.io.min.js e phaser.min.js, troque as tags \<script src=...\> por /vue.global.js, /cliente-socketio.js e /phaser.min.js e sirva os arquivos pelo servidor:

app \= socketio.ASGIApp(sio, static\_files={

    "/": "client/index.html",

    "/vue.global.js": "client/vue.global.js",

    "/cliente-socketio.js": "client/socket.io.min.js",

    "/phaser.min.js": "client/phaser.min.js",

    "/assets": "client/assets",

})

# **6\. Checklist de entrega**

* Repositório criado conforme as regras da seção 3 (nome, acesso do professor) e **link entregue** no prazo.

* docs/especificacao.md preenchido e commitado **antes** do código.

* Um commit por etapa, com mensagens claras.

* Testei cada etapa com duas ou mais abas abertas.

* Adaptei a vila ao meu tipo de vila: nomes, números e pelo menos um recurso refinado ou evento próprio.

* Comentários nos pontos em que um evento é emitido ou escutado, explicando o porquê.

* Nome dos desenvolvedores no rodapé da tela.

* O Painel de eventos mostra, para cada evento, o ⬆ emit ou ⬇ on, a causa, os dados e a minha reação.

* Dupla: contadores por evento funcionando.

* README.md com integrantes e @, como instalar e executar, como testar, respostas às três perguntas e declaração de uso de IA.

# **Anexo A. Como criar o fundo da vila (mapa no Tiled)**

O fundo da vila é um **mapa de peças** (em inglês, “tilemap”). Em vez de uma imagem gigante, o mapa é uma grade de peças pequenas (16 × 16 pixels) que se repetem, como um jogo de montar. É o jeito padrão de fazer cenários 2D no Phaser, e o que dá o visual de vila de jogo.

## **A.1 O que o kit traz**

| Arquivo (client/assets/) | O que é |
| :---- | :---- |
| tileset-vila.png | As **peças** do cenário: grama, caminho, água, árvores, pedras, hortas e cerca. |
| vila.json | O **mapa**: qual peça fica em cada célula, em duas camadas (chao e decoracao), mais os pontos lote1 a lote6 (onde aparecem obras e casas) e acampamento (de onde sobem os “+10”). |
| sprites-vila.png | A **casa** e o **canteiro de obras** (32 × 32 pixels), desenhados por cima do mapa. |
| LEIA-ME.txt | A lista de peças e a regra de numeração do caminho e da água. |

## **A.2 Editar o mapa que já existe**

1. Instale o **Tiled** (gratuito, em mapeditor.org) e abra o arquivo client/assets/vila.json (menu “File \> Open”).

2. Na janela de peças (“Tilesets”), escolha uma peça. Na barra de ferramentas, use o **carimbo** (“Stamp Brush”) e pinte no mapa.

3. Pinte o **terreno** na camada chao (grama, caminho, água) e os **enfeites** na camada decoracao (árvores, pedras, hortas). A borracha apaga.

4. Para mudar onde as obras aparecem, selecione a camada de objetos pontos e mova os pontos lote1 a lote6. O ponto acampamento é de onde sobem os “+10”.

5. Salve com **Ctrl+S** (continua no formato JSON), **recarregue a página** do navegador e veja o resultado.

| Caminho e água em 16 versões: as peças de caminho (8 a 23\) e de água (24 a 39\) têm bordas diferentes. O número é 8 \+ soma (ou 24 \+ soma), onde a soma é Norte \= 1, Leste \= 2, Sul \= 4 e Oeste \= 8, contando os lados em que continua caminho. Exemplos: reto horizontal \= 18, reto vertical \= 13, cruzamento \= 23\. |
| :---- |

## **A.3 Criar um mapa do zero**

1. “File \> New \> New Map”. Orientação **Orthogonal**, formato de camada **CSV** ou **Base64 (sem compressão)**, tamanho das peças **16 × 16** e tamanho do mapa à sua escolha (o kit usa 18 × 9).

2. “New Tileset”, tipo **Based on Tileset Image**, aponte para tileset-vila.png e marque **Embed in map**. Dê o nome tileset-vila (é o nome que o código usa).

3. Crie duas camadas de peças (chao e decoracao) e uma camada de objetos (pontos) com pontos chamados lote1, lote2… e acampamento (“Insert Point”).

4. Salve como **JSON** em client/assets/vila.json (“File \> Save As”, tipo JSON map files).

## **A.4 Como o Phaser carrega o mapa**

Isso já está na cena do kit. Leia para entender cada passo:

// preload(): carrega os arquivos

this.load.image("tiles", "assets/tileset-vila.png");        // imagem das peças

this.load.tilemapTiledJSON("mapa", "assets/vila.json");     // o mapa

// create(): monta o cenário

const mapa \= this.make.tilemap({ key: "mapa" });

const tileset \= mapa.addTilesetImage("tileset-vila", "tiles");

//   1º texto: nome do tileset NO TILED   2º texto: chave da imagem do preload

mapa.createLayer("chao", tileset);                 // nome da camada NO TILED

mapa.createLayer("decoracao", tileset);

const pontos \= mapa.getObjectLayer("pontos").objects;   // pontos do mapa

Cada obra nasce em um ponto lote do mapa. Ou seja, **o desenho do cenário e a lógica dos eventos se encontram nos pontos do mapa**.

## **A.5 Dicas para um cenário bonito**

* **Varie as peças:** misture grama lisa, com tufos e com flores em vez de repetir a mesma.

* **Duas camadas:** chão primeiro, enfeites depois. Árvores e pedras vão sempre na camada decoracao.

* **Bordas naturais:** árvores e arbustos nas bordas do mapa; água com margem; caminhos ligando os lotes.

* **Deixe espaço livre** em volta dos lotes, para a casa e o canteiro aparecerem bem.

* **Menos é mais:** poucos enfeites bem colocados ficam melhores do que o mapa lotado.

* **Nítido:** o kit já usa pixelArt: true e zoom 2x. Não use imagens com tamanhos fora da grade de 16 pixels.

## **A.6 Usar arte de terceiros**

Você pode trocar o tileset-vila.png por outro conjunto de peças **de uso livre**, como os pacotes gratuitos do Kenney (CC0) ou o Tiny Swords. Confira a licença na página do pacote, **credite o autor no \`README.md\`** e lembre que:

* o tamanho da peça deve ser o mesmo no Tiled e no pacote (muitos usam 16 × 16, o Tiny Swords usa peças maiores). Se mudar, ajuste o tamanho do mapa e o setZoom da cena;

* o nome do tileset no Tiled e o primeiro texto de addTilesetImage precisam continuar iguais.

## **A.7 Erros comuns do mapa**

| Sintoma | O que verificar |
| :---- | :---- |
| Erro “Invalid Tilemap Layer” ou mapa vazio | O nome da camada no createLayer deve ser **idêntico** ao do Tiled (chao, decoracao). |
| Mapa preto ou peças erradas | O primeiro texto de addTilesetImage deve ser o nome do tileset **dentro do Tiled** (tileset-vila). Confira também se o tileset foi **embutido** no mapa (“Embed in map”). |
| Erro 404 em assets/... no console | O servidor precisa servir a pasta: confira "/assets": "client/assets" no static\_files do server.py e se os arquivos estão nessa pasta. |
| As obras aparecem no lugar errado | Os pontos devem se chamar lote1, lote2… e ficar na camada de objetos pontos. Eles são usados na ordem do número. |
| A imagem fica borrada | Mantenha pixelArt: true na configuração do jogo e o image-rendering: pixelated do CSS. |
| Alterei o mapa e nada mudou | Recarregue a página com **Ctrl+F5**. O navegador guarda os arquivos antigos. |

[image1]: <data:image/png;base64,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> "Logo"