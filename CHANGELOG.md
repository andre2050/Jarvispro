# Mudanças

## 3.2.0 — 25/10/2026

### 🤝 Equipe de agentes mais forte (`actions/orquestrador.py`)
* Novo especialista **revisor**; até **8** subtarefas e **4** em paralelo.
* Depois dos especialistas, um revisor independente confere cada resultado contra o objetivo. O que estiver
  errado, incompleto ou sem fonte volta **uma vez** ao mesmo especialista, com o motivo. Sem tempo (45 s) ou sem
  resposta do modelo, a revisão é pulada e nunca trava a equipe. O relatório ganhou a seção "Revisão".

### 📊 Auto-avaliação (`core/autoavaliacao.py`)
* Cada pedido do motor próprio é medido (rota, tempo, erro, ferramentas que falharam) em `memory/autoavaliacao.json`.
* Ajusta o roteador sozinho, só com regras conservadoras: falhou no modelo rápido → passa a ir para o forte;
  pedido simples (até 6 palavras, sem ferramenta) e lento no forte **duas vezes** → passa a ir para o rápido.
* Por voz: "Nexus, como você está se saindo?" (tempo típico, erros por modelo, ajustes feitos).

### 🧠 Memória semanal (`core/memoria_semanal.py`, `actions/memoria_semanal.py`)
* Toda semana resume, só com contagem, as ações que você mais repetiu, o horário típico, o dia mais ativo e os
  pedidos repetidos (`memory/resumo_semanal.json`, até 12 semanas).
* Antecipa: no check-in proativo, se um hábito se repete no mesmo dia da semana e hora em 3+ dias, o NEXUS
  **oferece** a ação; fazer continua dependendo do seu "sim".
* Por voz: "o que você aprendeu sobre mim esta semana?" / "o que eu costumo fazer agora?".

### 🔁 Raciocínio em etapas (`actions/agent_task.py`)
* O modo agente confere o resultado contra o objetivo antes de dar a tarefa por terminada e, se faltou algo
  (ou o relatório diz mais do que os passos mostram), tenta de novo **uma vez**.

### 🧹 Configurações enxutas
* A grade de abas ficou com 6: **Áudio, Status, APIs, Atuador, Backup e I.S.A.** As outras telas continuam no
  código e podem voltar incluindo a aba em `_TABS`.

## 3.1.0 — 25/10/2026

### 🧬 Como a IA funciona (`core/ia_status.py`, `ui/overlays/ia_painel.py`, `actions/explicar_ia.py`)
* Novo painel (botão **🧬 Como a IA funciona** dentro do Núcleo I.S.A., Ctrl+I) com duas abas:
  **Áreas da IA** (machine learning, aprendizado profundo, linguagem natural, visão computacional) e
  **Tipos de IA** (ANI, AGI, ASI; máquinas reativas, memória limitada, teoria da mente).
* Cada área mostra o que é e o que o NEXUS tem **de verdade** no PC agora (hábitos, anomalias, roteador,
  motor Keras/NumPy, rede de intenções, busca pelo sentido, OCR, Ollama). Só lê o estado: não treina nem baixa nada.
* Cada tipo diz se existe hoje e onde o NEXUS se encaixa (ANI, de memória limitada, com partes reativas).
* Por voz: "o que é machine learning?", "que tipo de IA você é?", "como você aprende?", "abre o painel da IA".
* Testes em `tests/test_ia_status.py`.

### 🧹 Menu SETUP enxuto
* O SETUP mostra só **NÚCLEO I.S.A.** e **ATUALIZAR**. As outras telas continuam no código, só saíram do menu.

O histórico completo das versões anteriores fica em `memory/version.json` (é o que o botão ⬆ ATUALIZAR mostra).

## 3.0.0 — 25/10/2026 · NEXUS Ultra 2026

Projeto novo, criado por **André Luiz Lima Menezes** sobre a base da versão 2.5.1.

### 🎨 Interface 2026
* Nova paleta **Ultra 2026** como padrão: grafite profundo, bordas de vidro fosco e degradê violeta → ciano → magenta.
* Tema pronto **Ultra 2026** em Personalizar › Temas prontos (os antigos continuam).
* Quem já tinha escolhido uma cor própria continua com ela.

### 🌌 Dez visuais novos para o hub (`ui/hud_ultra.py`)
* **Nebulosa** (nuvens de luz e estrelas) · **Giroscópio** (três anéis 3D) · **Hélice** (dupla hélice) ·
  **Sonar** (ondas que saem do núcleo) · **Espectro** (equalizador espelhado com picos) · **Colmeia** (favo de
  hexágonos) · **Átomo** (elétrons com rastro) · **Plasma** (esfera com raios) · **Constelação** (estrelas ligadas
  por linhas) · **Túnel** (viagem em dobra).
* O botão **VISUAL DO HUB** passou de 9 para **19** visuais; os novos ficam numa seção própria da lista.
* Todos seguem a voz (microfone e fala do NEXUS), quase não se mexem no modo mudo e usam só QPainter.
  Se um visual falhar ao desenhar, o HUD volta ao orbe sozinho em vez de fechar a janela.
* Para criar o seu: uma função em `ui/hud_ultra.py` + a chave em `HUD_STYLES` (`memory/config_manager.py`).
* Testes novos em `tests/test_hud_ultra.py`.

## 2.5.1 — 24/10/2026

### 💻 Scripts em qualquer linguagem (`actions/code_helper.py`)
* Ao pedir "cria um script em ...", o NEXUS agora **escreve o código em qualquer linguagem** (antes só reconhecia
  umas 15 e o resto virava `.py`). Mapa com mais de 60 linguagens; se a linguagem não estiver na lista
  (ex.: Zig, Nim, Crystal), o modelo rápido descobre a extensão certa e o NEXUS lembra para os próximos pedidos.
* O prompt de escrita pede arquivo completo e executável, com comentários na sintaxe da própria linguagem.
* Cercas de código como ```` ```c++ ```` e ```` ```c# ```` agora são removidas corretamente.
* Executar/construir: ganhou Perl, Lua, R, Julia, Go, Batch, VBScript, AutoHotkey, Dart, Swift, Kotlin, Elixir,
  Haskell e Java. Linguagem sem executor conhecido: o código fica salvo e o NEXUS avisa, sem dar erro.
* Testes novos em `tests/test_code_helper_linguagens.py`.

## 2.5.0 — 24/10/2026

### 🤝 Equipe de agentes (`actions/orquestrador.py`, função `orchestrate`)
* Para objetivos grandes, o modelo forte **divide em até 6 subtarefas** e entrega cada uma a um especialista:
  pesquisador · programador · arquivista · analista · escritor. As que não dependem uma da outra rodam **ao mesmo
  tempo** (até 3); as que dependem esperam o resultado das anteriores. No fim, o modelo forte junta tudo numa
  resposta falada e o relatório completo vai para Documentos\NEXUS Agente.
* Cada especialista só enxerga **as ferramentas do seu ofício**, e vale tudo o que já valia no modo agente: não
  apaga, move nem renomeia arquivos, não manda mensagens, não mexe no mouse e no teclado, não instala nada, não
  chama outros agentes. O plano é validado (agentes que existem, dependências reais, sem ciclo); plano ruim cai
  para um agente só. Limite de 5 min por orquestração.
* Onde usar: `agent_task` continua para sequências simples; `orchestrate` para objetivos que se dividem.

### 🧠 Cérebro de decisão (`core/roteador_modelos.py`)
* Uma rede neural local (NumPy, ~0,6 s para treinar, milissegundos para decidir) lê cada pedido e escolhe:
  **rápido** (modelo barato), **forte** (precisa raciocinar) ou **delegar** (equipe de agentes). Na dúvida entre
  rápido e forte, usa o forte; delegar exige confiança ≥ 55 % e frase com corpo.
* **Aprende com o seu uso** (`memory/roteador_exemplos.json`): se o modelo rápido falha num pedido, ele passa a
  contar como "forte"; se o modelo chamou a equipe de agentes, passa a contar como "delegar".
* No motor próprio escolhe o modelo por pedido: `llm_model_rapido` / `llm_model_forte` (mesmo provedor). Com o
  **Claude** já vem pronto: Haiku 5.5 nos simples, Sonnet 5.5 nos difíceis. Sem configurar e com outro provedor,
  nada muda. Desligar: `llm_roteamento: false`.
* Nos pedidos "delegar", o modelo recebe a dica de preferir a equipe de agentes (ele ainda decide).
* Os agentes usam a mesma rede para escolher o modelo de cada passo e **sobem de nível sozinhos** quando o rápido
  não responde ou falha.

### 🔌 Rede local de comandos
* Novas intenções resolvidas sem internet: **aumentar / diminuir o brilho** da tela.
* O I.S.A. não mudou.

## 2.4.6 — 24/10/2026

### Começa a falar antes de o modelo terminar (motor próprio)
* **Streaming**: a resposta do modelo chega em pedaços e a voz começa na primeira frase completa, enquanto o resto
  ainda é escrito. Antes o NEXUS esperava a resposta inteira (`core/llm_providers.py` › `conversar_stream`, nos dois
  protocolos: o compatível com OpenAI — Gemini, OpenAI, Groq, DeepSeek, Mistral, xAI, OpenRouter, Ollama, LM Studio,
  llama.cpp, vLLM — e o nativo do Claude).
* **Fala em fluxo** (`core/voz_propria.py` › `FalaEmFluxo`): cada frase é sintetizada enquanto a anterior toca; frases
  curtas se juntam para a entonação ficar natural; o botão de interromper corta o resto.
* **Antes de uma ferramenta**: a frase que o modelo diz ("vou pesquisar…") já sai enquanto a ferramenta roda, e a
  fala da rodada seguinte espera a anterior terminar (não se misturam).
* **Reserva automática**: se o servidor não aceitar streaming, a chamada é refeita no modo de antes; se a conexão
  cair no meio de uma fala, o que já foi dito não é repetido.
* O raciocínio interno de modelos como qwen3/deepseek-r1 (`<think>…</think>`) nunca é falado.
* Para desligar: `llm_streaming: false` na configuração do motor (padrão: ligado).
* Testes novos: `tests/test_streaming.py` (servidor HTTP/SSE de verdade, ferramentas, queda de conexão, interrupção).

## 2.4.5 — 24/10/2026

### Mais rápido para responder (motor próprio)
* **A voz não faz pausas entre frases**: a síntese da próxima frase roda enquanto a anterior toca
  (antes era uma depois da outra). Medido com uma voz simulada: 1,5 s contra 2,4 s para 4 frases (`assistant/motor_proprio.py`).
* **Fecha o pedido mais cedo**: a pausa que encerra a sua fala caiu de 0,7 s para 0,5 s — ganho em todo pedido por voz.
  Se ele cortar você no meio de frases com pausas longas, suba `_SILENCIO_FIM` para 0,6.
* **Prompt e ferramentas uma vez por pedido**: eram refeitos (leitura de arquivos e memória) a cada passo de um pedido
  com várias ferramentas.
* **Whisper com mais núcleos**: usa até 8 threads de CPU (o padrão eram 4), `core/voz_propria.py`.
* Não mexi no motor Gemini Live: a demora ali é de rede e de modelo, não do código local.


### Rede neural em Keras/TensorFlow
* Toda a camada neural ganhou um motor **Keras/TensorFlow** (`core/keras_engine.py`, `core/keras_intent.py`), usado
  automaticamente quando o TensorFlow está instalado. Sem ele, o motor NumPy de sempre segue valendo.
* Cobre `neural_core` (treino, busca, ensemble, fine-tune, distilação, poda), `intent_net`, anomalias, previsão de
  hábitos, voz-ID e palavra de ativação personalizada.
* Os modelos já treinados abrem nos dois motores (mesmo JSON / `.npz`): nada é retreinado.
* Escolha manual: variável `NEXUS_NEURAL_BACKEND` = `auto` | `keras` | `numpy`. O TensorFlow só é importado no primeiro
  uso (em segundo plano para o `intent_net`), nunca na abertura.
* Nova ação `export` em `neural_core`: grava a rede em `.keras`.
* O TensorFlow **não** entra no `.exe` por padrão (`NEXUS_EXE_COM_TF=1` para incluir).
* Tradeoff: em tabelas pequenas o treino em Keras é bem mais lento que o NumPy (qualidade igual).

## 2.4.4 — 23/10/2026

### Novo que você pediu
* **Painel 🤖 VISÃO COMPUTACIONAL** no lugar do painel 👁 VISÃO (`ui/overlays/tools.py`, `VisionOverlay`):
  * **Redes neurais** (`core/visao_ia.py`): 🎯 OBJETOS NA CÂMERA e 🎯 OBJETOS NA TELA (YOLOX, 80 classes) e 🧑 QUEM É?
    (YuNet + SFace, rostos cadastrados por voz), com caixa e nome desenhados na imagem do painel (sem acento, que o
    `putText` do OpenCV não desenha). Linha de situação dos modelos e botão ⬇ INSTALAR quando faltam.
  * 📊 ANALISAR A CÂMERA (antes só a tela).
  * Continuam: QR na tela e na câmera, contar rostos, analisar a tela, vigia de movimento, ler o texto e descrever.
* Barra rápida: o botão "Visão" virou **🤖 Visão computacional** (`ui/quickbar.py`); na lista de comandos,
  `computer_vision` aparece como "Visão computacional" (`ui/comandos_pt.py`).

### Outras correções
* Testes novos em `tests/test_painel_visao.py`.

## 2.4.3 — 23/10/2026

### Correções que você pediu
* **Câmera ocupada**: no Windows só um programa usa a webcam por vez. Quando o WhatsApp (ou Teams, Zoom, Camera HD…)
  estava com ela, o NEXUS dizia só "não achei nenhuma câmera". Agora diz quem está com a câmera — pelo registro de
  privacidade do Windows (`CapabilityAccessManager\ConsentStore\webcam`: início marcado e fim zerado = em uso) ou,
  quando o app não aparece lá (o Camera HD não aparece), pelos apps de câmera abertos — e pede para fechar a câmera
  ou a chamada nele (`actions/computer_vision.py`). Testado com o Camera HD segurando a câmera.
* **"O projeto Nexus Ultra 2026 não está sendo encontrado"**: o agente de código (`dev_agent`) só altera projetos que ele
  criou em `Desktop\NexusProjects`; "Meus projetos" (`projetos`) é outra função, uma lista de tarefas. O "não achei"
  chegava minutos depois e o Gemini mandava registrar em "Meus projetos" e tentar de novo, em círculo. Agora o
  agente confere antes de ir para o segundo plano: pedido para mudar o próprio NEXUS é explicado na hora (as
  correções do NEXUS vêm por atualização) e projeto inexistente responde com a lista dos que existem. As descrições
  das duas ferramentas dizem que uma não tem relação com a outra (`actions/dev_agent.py`, `actions/projetos.py`).

### Outras correções
* O agente de código não pega mais um projeto de nome parecido quando o pedido é sobre o próprio NEXUS.
* Testes novos: `tests/test_dev_agent_proprio_nexus.py` e casos de câmera ocupada em `tests/test_camera.py`.

## 2.4.2 — 23/10/2026

### Correções que você pediu
* **Visão da câmera**: a foto que vai para o Gemini (`_capture_camera`) abria um driver só (DSHOW), lia 10 quadros
  fixos e saía em 640×480 — imagem pequena e escura, ou "não achei a câmera" quando o DSHOW falhava. Agora usa a
  mesma abertura robusta da visão local (`computer_vision.abrir_camera` / `capturar_camera`): câmera escolhida
  primeiro, depois as outras, DSHOW e MSMF, 1280×720 e aquecimento até a imagem clarear. Testado no PC: 1280×720,
  brilho 49 (antes 640×480, brilho 40); com o DSHOW quebrado, cai no MSMF.
* Com a **vigia de movimento** ligada, a foto usa o quadro da vigia em vez de falhar por câmera ocupada.
* A detecção automática gravava `camera_index: 0` para sempre quando falhava uma vez (câmera ocupada, quarto escuro).
  Agora só grava quando acha uma câmera, e grava o `config/api_keys.json` num temporário trocado de uma vez — sem
  regravar por cima um arquivo que não pôde ser lido (`actions/screen_processor.py`).
* A visão local (`core/visao_local.py`) e a prévia da câmera na janela (`ui/main_window.py`) usam a mesma abertura.

### Outras correções
* Testes novos da câmera com um VideoCapture falso (`tests/test_camera.py`).

## 2.4.1 — 23/10/2026

### Correções que você pediu
* **Não abria o cmd nem o Python**: os programas achados no PATH eram iniciados com a saída jogada fora
  (`stdout/stderr=DEVNULL`) e sem janela própria — o cmd e o python abriam em branco ou dentro do console escondido do
  NEXUS. Agora programas de console ganham a própria janela (`CREATE_NEW_CONSOLE`) e começam na pasta do usuário. A
  confirmação "abriu" passou a olhar o PID: antes, com outro `cmd.exe`/`python.exe` já rodando (o próprio NEXUS é
  python), nunca confirmava (`actions/open_app.py`).
* **Não abria a câmera**: a busca no menu Iniciar/Store diferenciava acento — "câmera" não achava "Camera HD". Agora
  ignora acentos; se não houver nenhum app de câmera, a resposta explica como instalar a Câmera do Windows.
* **Não abria o Backup do Windows** quando pedido como "Windows Backup" ou "backup windows" (só o nome exato
  funcionava). Agora vale qualquer ordem das palavras. "prompt de comando" e "linha de comando" também abrem o cmd.
* **Finanças, categoria automática**: com o modelo de sentido (MiniLM) instalado, "corrida de uber" ficava mais perto
  de "boleto" que de "uber". Agora o hash (palavra exata) e o MiniLM votam juntos — 57/57 gastos de teste certos,
  contra 36 só com o MiniLM. As finanças também sobrescreviam o IDF da busca semântica; agora têm um hash próprio
  (`core/financas_ia.py`).

### Outras correções
* Erros que sumiam sem rastro agora ficam em `memory/falhas.log`: arquivo pessoal estragado (`core/armazem.py`),
  gravação de hábitos/auditoria em segundo plano (`assistant/tools.py`), registro de reconexões
  (`assistant/session.py`) e lembrete que não apareceu (`actions/reminder.py`). Nova `protecao.anotar()`.
* Testes não escrevem mais no `memory/falhas.log` real; testes novos para abrir programas.

## 2.4.0 — 22/10/2026

### Correções que você pediu
* **Fechava sozinho**:
  * Com barulho/TV o microfone virava frases soltas ("Abuelo.", "botão, cara.") e o Gemini chamava `shutdown_jarvis`,
    que fechava na hora. Agora só desliga se as falas/textos dos últimos 20 s pedem isso (desligar, encerrar, fechar o
    NEXUS, tchau, boa noite, shut down…); senão o pedido é ignorado e anotado no log (`assistant/tools.py`).
  * Abrir o NEXUS com ele já aberto rodava **duas cópias** (microfone, CPU e porta do celular em disputa; uma
    derrubava a outra). Agora há uma trava de cópia única: a segunda traz a janela aberta para a frente e sai
    (`core/protecao.py`, `main.py`). No reinício de atualização a cópia nova espera a antiga sair.
  * Desligar por voz e reiniciar usavam `os._exit` sem gravar o "fechou direito" — a abertura seguinte dizia
    "fechou de forma inesperada" sem ter fechado. Corrigido.
* **Carregava lento**: o `main.py` importava o motor inteiro (Gemini, numpy, áudio, OpenCV — ~4 s) antes de criar a
  janela. Agora a janela abre primeiro (~0,7 s) e o motor carrega na thread do runner, com a janela já na tela.
* **Demorava para falar**: o Ollama era chamado com `keep_alive: -1` — depois de usado uma vez, o modelo ficava na RAM
  para sempre (num PC de 8 GB isso deixa a memória a 90% e a CPU a 100%). Agora libera depois de 5 min sem uso
  (`core/llm_client.py`).

### Novo
* Botão **＋ Adicionar comando** em Configurações › COMANDO e no painel TODOS OS COMANDOS: uma frase sua
  ("modo cinema") e o que o NEXUS faz. Digitado vale na hora; por voz, na próxima conexão (`core/comandos_usuario.py`).

### Outras correções
* Arquivo enviado pelo celular com `:` no nome perdia o começo do nome no Windows (`dashboard/server.py`).

## 2.3.0 — 22/10/2026

### Correções que você pediu
* **Fechava sozinho**: no PyQt6 um erro Python solto num botão, timer ou thread derruba o programa sem aviso. Agora
  `core/protecao.py` captura esses erros (e quedas nativas), grava em `memory/falhas.log` / `queda_nativa.log` e segue
  aberto; o motor do assistente recomeça sozinho se cair; se a vez anterior terminou de forma inesperada, o log avisa.
  Por voz: "diagnóstico, ele fechou sozinho?" (`diagnostico` ação `crashes`).
* **Desconectava e conectava sozinho (voltando do zero)**: (1) um erro em qualquer monitor/lembrete cancelava a conexão
  inteira — agora tarefas auxiliares são isoladas (`_isolada`); (2) a conexão agora é renovada antes do limite mesmo no
  meio de uma conversa; (3) no modo palavra de ativação, reconectar não faz mais o NEXUS dormir; (4) se a conversa não
  puder ser retomada, as últimas 12 falas são devolvidas; (5) cada queda/renovação é anotada em `memory/reconexoes.log`
  (`diagnostico` ação `reconnections`).
* **Mais rápido**: abrir programa confirma em até 0,7 s (era 1,5 s); "ajuste de turno" ligado por padrão (silêncio de
  450 ms para considerar o fim da sua fala; pode desligar em `config/api_keys.json` → `turn_tuning.enabled=false`).
* **Erro 404 do Gemini** ("gemini-2.5-flash is no longer available"): o padrão agora é `gemini-3.5-flash` e, se o modelo
  escolhido sumir, o NEXUS testa os atuais e passa a usar o primeiro que responde.

### Redes neurais novas
* **Memória semântica** (`memoria_semantica`): acha notas, diário, tarefas, contatos… pelo SENTIDO ("viagem" acha
  "passagem para Recife"). Motor leve embutido; opcional MiniLM multilíngue (ONNX) baixado uma vez.
* **Roteador de comandos**: rejeita "não sei" e dá segunda opinião (vizinhos mais próximos) antes de executar localmente.
* **Voz do dono** (`voz_treino`): cadastro por voz e trava opcional para ações sensíveis. Não é biometria profissional.
* **Palavra "Nexus" treinada na sua voz**: opção em Configurações › Palavra de ativação; só vale se o auto-teste for bom.
* **Cérebro local** (`cerebro_local`): gera dados de treino, Modelfile do Ollama e script LoRA; o treino roda no seu PC.
* **Previsão de hábitos** (`previsao_habitos`) e **anomalias do PC** (`anomalia_pc`, autoencoder; avisa se o PC destoar).
* **Finanças inteligentes** (`financas_ia`): categoria automática ao lançar gasto sem categoria e previsão do mês.
* **Visão local** (`visao_ia`): objetos (YOLOX), contar pessoas e reconhecer rostos cadastrados (YuNet+SFace). Só os
  números do rosto ficam guardados; o cadastro pede CONFIRMAR.

### Interface
* Três visuais novos do hub — **Hub** (módulos em órbita que acendem quando o NEXUS usa aquela área), **Matrix** e
  **Ondas**. Os seis anteriores continuam.

## 2.2.0 — 22/10/2026

### Novo
* **Lista de compras** (`compras`): várias listas com nome (mercado, farmácia…), vários itens de uma vez, quantidade
  ("2 ovos"), item repetido soma, marcar como comprado, limpar os comprados.
* **Hábitos e metas** (`rastreador_habitos`): meta por dia, registro por voz ("bebi 2 copos"), desfazer, sequência atual
  e melhor sequência. Hoje ainda aberto não quebra a sequência de ontem.
* **Contatos e aniversários** (`contatos`): telefone, e-mail, aniversário (aceita "12 de março", "12/03", "12/03/1990"),
  próximos aniversários com a idade que a pessoa vai fazer; 29/02 vale 28/02 em ano comum.
* **Manutenção do PC** (`manutencao_pc`): espaço por disco, pastas que mais ocupam, limpeza de temporários, backup,
  rede (IP local/público, tráfego), ping e bateria. A limpeza pede CONFIRMAR na tela e nunca sai da pasta temporária.
* **Texto e ferramentas de programador** (`texto_dev`): contar, caixa (upper/snake/camel…), slug, hash, base64, URL, JSON,
  UUID, timestamp, tirar acentos, ordenar e tirar linhas repetidas. Só texto, sem arquivos e sem eval.
* **Diário e humor** (`diario`): escrever, ler por dia, procurar, média e tendência do humor (1 a 5), apagar a última.
* O **briefing da manhã** passou a avisar aniversários de hoje e hábitos que ainda faltam.
* `core/armazem.py`: gravação em arquivo temporário + troca (sem arquivo pela metade); arquivo estragado vira `.quebrado`.

### Segurança e correções
* **Chave do Gemini inválida**: o NEXUS agora fala "A chave da API do Gemini é inválida" pela voz do sistema (offline, no máximo 1x por minuto) além de escrever no log e abrir a tela da chave. Reconhece também chave vencida, vazada ou bloqueada (`core/aviso_voz.py`).
* `computer_settings`: o brilho no Linux (sem `brightnessctl`) montava um comando de shell; agora usa `xrandr` direto.
* `assistant/core.py`: importação de `Path` repetida.
* Dados novos (compras, hábitos, contatos, diário) ficam fora do GitHub (`.gitignore` e `preparar_publicacao.py`).
* Mais de 60 testes novos (`tests/test_funcoes_22.py`).

## 2.1.0 — 22/10/2026

### Novo
* **Rede neural turbinada** (`neural_core` + `core/neural_engine.py`): quantas camadas e neurônios você quiser
  (`hidden`: "64,32,16" ou small/medium/large/deep); 7 ativações; 6 otimizadores (SGD, momentum, Nesterov, RMSprop,
  Adam, AdamW); taxa de aprendizado com agendas (cosseno, degrau, exponencial, plateau…); tamanho de lote; L2, dropout e
  ruído nas entradas contra overfitting; parada antecipada que devolve o melhor ponto; pesos de classe e dados sintéticos
  (SMOTE) para dados desbalanceados; ensemble de até 10 redes; busca grid/random; AutoML (`auto`); importância das
  entradas e explicação de cada previsão; ajuste fino com camadas congeladas, destilação, poda/compressão; relatório HTML
  com curvas, diário de experimentos, monitor de drift e colunas de texto/células vazias tratadas. Modelos antigos
  continuam funcionando. Ações novas: `explain`, `finetune`, `distill`, `compress`, `augment`, `report`, `monitor`, `history`.
* **Programar sozinho** (`dev_agent`, reescrito): "cria um site / app / jogo / script" → planeja, escreve, instala as
  dependências num `.venv` só do projeto, roda, confere no navegador (erros de JavaScript) e corrige em até 5 tentativas.
  Também **altera** um projeto existente (com cópia de segurança) e **desfaz** a última alteração. Roda em segundo plano
  e avisa por voz quando termina. Interruptor próprio em ⚙ › ATUADOR.
* **Casa inteligente** (`casa_inteligente`): Home Assistant (API oficial) e webhooks; "apaga todas as luzes", "luz da sala
  em 40%", "põe o ar em 22". Confere se o aparelho realmente mudou. Fechadura, portão e scripts pedem confirmação na tela.
* **Finanças** (`simple_finance`, ampliado): data do gasto, resumo por período com comparação, por categoria, limite mensal
  com aviso (80% / estourou), apagar o último. Os lançamentos da 2.0 continuam valendo.
* **Diagnóstico** (`diagnostico`): o que falhou, o que está lento, saúde do NEXUS, teste de internet.
* **Testes automáticos**: mais de 300, em `tests/`.

### Segurança
* Abrir programa pelo nome não passa mais por um shell (um nome como `calc & outro` executava o segundo comando).
* Código gerado pela IA para a área de trabalho é validado antes de rodar (sem imports, sem `eval/exec/open`, `ctypes` só
  do Windows que precisa) e roda com limite de 60 s.
* O agente de código trata o que a IA devolve como não confiável: caminhos dentro da pasta do projeto, só pacotes de nomes
  válidos, só comandos `python`/`node`/`npm` simples, variáveis com chave/senha removidas do ambiente.
* Painel do celular: limite de tentativas de login (429), acesso que vence por inatividade, cabeçalhos de segurança, limite
  de tamanho dos comandos, sem `shell=True` no firewall.
* Notícias: RSS com `DOCTYPE`/entidades é recusado; só abre links http/https.
* `.gitignore` e `preparar_publicacao.py` agora deixam fora finanças, tarefas, casa, pastas vigiadas e o registro de ações.

### Pequenas correções
* `main.py`: importação repetida; `assistant/core.py`: linha sem efeito.
* `assistant/common.py`: compatível com Python anterior ao 3.11 (grupos de erros).
