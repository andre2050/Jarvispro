# Mudanças

## 4.6.0 — 31/10/2026

### ⚡ Perfil "dinâmico" (`core/carga_ferramentas.py`)
* Quarto perfil: o modelo recebe o básico (**44 ferramentas, cerca de 9,9 mil tokens**, contra 31,5 mil do completo) mais duas ferramentas, `tool_search` e `tool_call`, que alcançam **todas as outras** sob demanda. A chamada passa pelo mesmo caminho das demais (confirmações, auditoria e proteções valem igual).
* Ative em Configurações › FERRAMENTAS ou por voz ("usa o perfil dinâmico"). O padrão continua sendo o completo.

### 🔁 Conversa que continua (`core/continuidade.py`)
* Quando o motor de voz reinicia sozinho (queda de rede, erro), a conversa **retoma de onde parou**: o identificador de retomada do Gemini Live e o resumo das últimas falas passam para o motor novo. O identificador fica só na memória (não vai para o disco).

### 🔐 Cofre de chaves (`core/cofre.py`, `actions/cofre_chaves.py`) — opcional, começa desligado
* "Guarda minhas chaves no cofre": chaves de API, tokens e senhas saem do `config/api_keys.json` e vão para o cofre do sistema (Gerenciador de Credenciais do Windows, Keychain do macOS, Secret Service no Linux), via `keyring`. No arquivo fica só `@cofre`.
* Antes de mudar o arquivo, uma cópia é guardada em `config/api_keys.json.antes_do_cofre`. Se um segredo não for confirmado no cofre, ele **continua no arquivo**. "Tira as chaves do cofre" traz tudo de volta e não mexe em nada se faltar algum valor.
* Os leitores de configuração (`load_api_keys`, `get_config` e as ações que liam a chave direto) resolvem o `@cofre` sozinhos; o backup leva os valores reais. Um segredo novo digitado numa tela é levado ao cofre ao abrir o NEXUS e ao salvar.
* **Não foi possível testar o cofre real do Windows neste ambiente** — os testes usam um cofre falso. Teste com "chaves no cofre: status" antes de apagar a cópia `.antes_do_cofre`.

### 🪵 Erros engolidos deixam rastro
* 479 lugares que faziam `except Exception: pass` agora chamam `core.protecao.engolida()`: o programa segue igual, mas uma linha vai para `memory/falhas_menores.log` (arquivo à parte, sem repetir a mesma linha em menos de 60 s). Ficaram de fora a leitura inicial de console em `main.py` e as importações opcionais.

### 🧱 Código mais fácil de mexer
* `ui/main_window.py` (3.808 linhas) foi dividido em **seis arquivos** `ui/janela_*.py` por assunto (câmera e vídeo, atalhos do sistema, conteúdo e quiz, voz e entrada, painéis, licença e atalhos de teclado); `ui/modern.py` em quatro `ui/modern_*.py`. Sem mudança de comportamento; `ui.modern` continua exportando os mesmos nomes.
* Repositório sem as 26 pastas `Nexus-vX.Y.Z/` (cerca de 140 MB). Elas continuam no histórico do git (commit `b88b0b6`, o da 4.5.0).
* `isa_core`, `isa_nucleo` e `neural_core` **não** foram unificados: avaliei e não se sobrepõem (relatório da I.S.A., módulos/autonomia e redes neurais de verdade).

### Bom saber
* 29 testes novos (`tests/test_46_*.py`). Suíte: 1301 passam, 4 ficam de fora por dependerem do sistema; `ruff` limpo.

## 4.5.0 — 31/10/2026

### ⚡ Perfil de ferramentas (`core/carga_ferramentas.py`, `actions/carga_ferramentas.py`)
* **Medido na 4.4.0:** o NEXUS apresentava **129 ferramentas (cerca de 31 mil tokens)** ao Gemini em TODA conversa. Isso pesa na abertura da sessão e aumenta a chance de a IA escolher a ferramenta errada.
* Três perfis, em Configurações › FERRAMENTAS ou por voz ("usa o perfil essencial", "quantas ferramentas você tem?"): **completo** (padrão, igual ao de sempre), **recentes** (essenciais + o que você usou nos últimos 30 dias + as que você fixar) e **essencial** (42 ferramentas, cerca de 9,7 mil tokens: ~70% menos).
* Só muda o que é **mostrado** à IA; nada é apagado. Segurança e configuração ficam sempre à vista. Com o perfil reduzido a IA é avisada, para oferecer voltar ao completo se faltar algo. Vale na próxima conversa.

### 🧹 Ações que falham ou que você não usa (`core/acoes_desativadas.py`, `actions/gerenciar_acoes.py`)
* "O que anda falhando?" lista as ações que erraram em 70% ou mais das vezes (mínimo de 5 chamadas, últimos 14 dias). "Desativa a ação X" / "reativa X". Desativada = não carrega e não gasta tokens; o arquivo continua em `actions/`.
* Ações de segurança, configuração e diagnóstico **não podem** ser desativadas.

### 🧭 Guia (`core/guia_nexus.py`, `actions/guia_nexus.py`)
* "O que você sabe fazer?" / "o que você faz com e-mail?": explica por assunto, com exemplos do que dizer. Um teste confere que o guia só cita ferramentas que existem.

### 🖨️ Impressora (`core/impressora.py`, `actions/printer_control.py`)
* Lista impressoras, vê a fila, imprime arquivo ou texto, cancela a fila. Windows (PowerShell) e Linux/macOS (CUPS).
* Imprimir e cancelar pedem **CONFIRMAR**. Só arquivos da sua pasta de usuário, de tipos comuns; impressora só se estiver na lista do sistema; até 20 cópias.

### 🎓 Estudo (`core/estudo.py`, `actions/estudo.py`)
* Cartões com **repetição espaçada (SM-2)**, importação "pergunta :: resposta", "o que devo revisar hoje?" e **quiz** de múltipla escolha que atualiza os cartões conforme você acerta ou erra.

### 🗂️ Kanban (`core/kanban.py`, `actions/kanban.py`)
* Quadros em Markdown no formato do **plugin Kanban do Obsidian** (colunas `## Título`, cartões `- [ ]`/`- [x]`). Aponte a pasta para o seu cofre e eles aparecem lá; o bloco de ajustes do Obsidian é preservado.

### Já existiam (não repeti): WhatsApp, Telegram, Home Assistant, Lista de Compras, Pomodoro (modo foco), monitor em segundo plano, Forge, controle de apps e navegador, permissões e aprovações.

### Bom saber
* 54 testes novos (`tests/test_45_*.py`). Toda a suíte passa; o `ruff` não acusa erros.
* **Não testado no seu PC:** a impressão real (os testes usam um sistema de impressão de mentira), a conversa por voz com o Gemini e a janela. O perfil de ferramentas só se prova de verdade abrindo uma conversa: se a IA errar mais ou menos, o perfil "completo" volta tudo.
* Google (Gmail/Agenda) continua como estava (e-mail por senha de app e agenda por link .ics, só leitura); acesso completo ao Google Drive/Docs por OAuth não foi incluído.

## 4.4.0 — 30/10/2026

### 🐞 Correções no painel remoto do celular (`dashboard/static/app.html`, `login.html`)
* O painel do celular ainda estava **em inglês** (botões, avisos, erros de conexão, guia do microfone) e a tela de login mostrava a marca **JARVIS** em vez de **NEXUS**. Agora está tudo em português do Brasil (`lang="pt-BR"`) e com a marca NEXUS.
* Em telas estreitas (≈ 400 px) o botão ENVIAR e o ícone 🎯 ficavam cortados; o cabeçalho e o rodapé agora se ajustam.

### ✨ Melhorias de interface (ideias do Mark58)
* **Atalhos rápidos** acima do campo de texto: hora, tempo, captura de tela, desempenho do PC, volume −/+, lembrete e mudo. Tocar envia o comando pelo mesmo caminho do botão ENVIAR (nada novo passa por fora das proteções do NEXUS).
* **Cor de destaque** (botão 🎨 no cabeçalho): um toque troca entre 6 cores; fica guardada só neste navegador (se o navegador bloquear o armazenamento, a cor apenas não persiste).
*  testes novos em `tests/test_dashboard_ptbr.py`.

### Bom saber
* Os textos de erro da API do servidor (`dashboard/server.py`) não foram mexidos; a tela já mostra as mensagens em português.
* Testado em navegador de verdade só com a conexão simulada: o painel funcionando contra o NEXUS real no seu PC e no celular ainda precisa do seu olho.

## 4.3.0 — 30/10/2026

### 📱 Forge para Android (`core/forge_android.py`, `core/forge_engine.py`, `actions/forge_app.py`)
* O Forge agora cria **aplicativos Android nativos** (Kotlin + Jetpack Compose): o arquiteto marca a plataforma `android`, o construtor escreve o projeto Gradle, o próprio Forge **compila o APK de teste** (`gradlew assembleDebug`), roda os testes unitários e o revisor lê o código com atenção a permissões e segredos.
* **Instala no seu celular** (“instala no celular”): acha o aparelho por USB (adb), compila antes se ainda não há APK, instala e abre o app. Também entrega o APK em `NexusForge\_entregas` (“gera o apk”).
* **Confere o PC antes de gastar tokens** (“ambiente android” / ação `android_check`): procura JDK 17+, Android SDK (com licenças), adb e Gradle e diz em português o que falta. Sem isso o plano fica guardado e nada é construído.
* Versões fixas que funcionam juntas (Gradle 8.9, AGP 8.5.2, Kotlin 2.0.20, SDK 34, minSdk 26). O Forge cria `local.properties`, `gradle.properties` e o `gradlew` sozinho; `local.properties` (caminho do seu PC) fica fora do git.
* Segurança: `gradlew` só roda `assembleDebug`, `testDebugUnitTest`, `lintDebug` e `clean`; o `adb` só aceita listar aparelhos, instalar APK **da pasta do projeto**, `logcat -d`, abrir/parar o app e desinstalar o pacote do projeto. A chave da API continua sem ser passada aos processos filhos.
* Só **APK de depuração**: assinar para a Play Store não está incluído.
* Honesto: os 71 testes novos (`tests/test_forge_android.py`) usam um Android Studio de mentira (scripts que fingem JDK, SDK, Gradle e adb). Eles provam a lógica do Forge, **não** que um build Android real passa; isso só se vê no seu PC, e o primeiro build baixa muita coisa e demora. O Gradle executa o script do projeto, que foi escrito por IA e roda com as suas permissões: revise o que você não conhece.

## 4.2.1 — 30/10/2026

### 🐞 Correção — o Forge não achava a chave do Claude
* O Forge procurava a chave só em `anthropic_api_key` (`config/api_keys.json`), mas a tela de Configurações guarda a chave do Claude em outro lugar (`llm_keys.claude`: MOTOR DE VOZ → **Chave do provedor**). Quem colou a chave na tela ouvia o Forge reclamar da chave. Agora ele acha nos dois lugares: a da tela vale mais que a do json, que vale mais que a variável `ANTHROPIC_API_KEY`.
* Os erros agora dizem **o que fazer**: sem chave (e onde colar), chave recusada, conta sem crédito, sem internet, pacote `anthropic` ausente. Antes quase tudo virava “Confira a chave da API.” e a falta de crédito virava um texto cortado de código.
* Nova ação `check` (“testa a chave do Forge”): confere o pacote, a chave e a resposta da Anthropic sem gastar tokens e diz de onde a chave veio (nunca a mostra). O saldo da conta só aparece quando o Forge gasta.
* Bom saber (pelo `core/gemini.py`): ter `anthropic_api_key` no json também faz as chamadas rápidas do próprio NEXUS irem para o Claude e gastarem crédito; a chave só em `llm_keys` não faz isso.
* 18 testes novos em `tests/test_forge.py`, inclusive um que grava a chave pelo mesmo caminho da tela.

## 4.2.0 — 30/10/2026

### 🔨 Nexus Forge (`actions/forge_app.py`, `core/forge_engine.py`)
* Construtor de apps em etapas, para quando você diz **“usa o Forge”**: o Nexus conversa com você, o **arquiteto** monta o plano e você aprova antes de qualquer arquivo ser escrito.
* O **construtor** (Claude) escreve o código e roda o que escreveu num `.venv` do projeto. O próprio Forge roda o comando de teste do plano e manda corrigir (até 3 rodadas); um **revisor** separado procura bugs e falhas de segurança e o que for grave é corrigido.
* Cada etapa vira um **checkpoint em git**: “desfazer a última alteração” volta, guardando antes o que você tinha mexido à mão (recuperável pelo `git reflog`). Projetos em `Desktop\NexusForge\<nome>`; depois dá para pedir mudanças (“no app, adiciona…”), revisar, empacotar em zip, gerar o .exe e publicar no GitHub.
* Publicar no GitHub passa pelo botão **CONFIRMAR** da tela (`core/confirm.py`); o repositório é privado por padrão.
* Limite de tokens por missão (1,5 milhão) e por dia (6 milhões), ajustáveis por variável de ambiente. Os comandos rodam sem shell, com lista de permitidos, e a chave da API não é passada ao programa gerado.
* O `dev_agent` continua sendo o padrão para “cria um site / faz um jogo”; o Forge só entra quando você pede.
* Honesto: o app gerado é código escrito por IA e roda com as permissões do seu usuário — não é uma caixa isolada de verdade; revise o que você não conhece. Usa a chave `anthropic_api_key` (a mesma do `claude_voice`) e cada app gasta créditos.
* 42 testes novos (`tests/test_forge.py`).

## 4.1.1 — 28/10/2026

### 🧹 Hub
* O visual de rosto (“Rosto · Real”) saiu da interface do hub e do menu de visuais. Quem o tinha escolhido volta ao visual padrão (Galáxia) sozinho. Os visuais são os 20 da 3.6.

## 4.1.0 — 28/10/2026

### ⏪ Checkpoints e replay das missões (`core/missoes_checkpoint.py`)
* Cada passo concluído guarda um **checkpoint** (até 30). `missao action=checkpoints` lista; `action=rewind checkpoint=N [step=pX new_args={…json}]` volta ao ponto, deixa a missão **pausada** e refaz dali — opcionalmente por outro caminho.
* Honesto: voltar a missão **não desfaz** o que os passos já fizeram fora dela (arquivo movido, mensagem enviada); o NEXUS lista esses passos.
### 🚧 Guardrails (`core/guardrails.py`, `config/guardrails.json`)
* Entrada: bloqueia chave de API saindo em mensagens, pastas do sistema e comandos destrutivos. Saída: oculta cartão, CPF e chaves nos resultados. Regras suas (bloquear / redigir / avisar) via ferramenta `guardrails`; as padrão não podem ser desligadas; missões e agentes não editam regras.
* Auditoria e trace passaram a mascarar chaves de API mesmo no meio de um texto.
### 🔍 Trace local (`core/trace_local.py`)
* Linha do tempo de cada ferramenta (quem pediu, duração, ok/falha), só em `memory/trace.jsonl` (máx. 5000). Ferramenta `trace` e `GET /api/trace`.

## 4.0.0 — 28/10/2026

### 🛡️ Auto-regeneração com imunidade (`core/imunidade.py`)
* Cada falha ganha uma **digital** (sem números, caminhos e endereços). O NEXUS conta as repetições e o que resolveu; quando uma vacina **já funcionou**, aplica **antes** (espera de rede crescente, espera de arquivo em uso, liberar memória, limpar sobras do NEXUS).
* Falha repetida sem remédio vira **relatório de bug** (arquivo:linha, quantas vezes). Instalar pacote continua pedindo o seu sim; **o NEXUS nunca reescreve o próprio código**.
### 🧬 Arquitetura que evolui
* **Módulos competitivos** (`core/competicao.py`): variantes da mesma capacidade competem (acerto + tempo), com teste mínimo, experimento de 10%, aposentadoria reversível e fixação manual.
* **Planejamento da modularização** (`core/isa_modularizacao.py`): onde dividir, em grupos de funções, em que ordem (menos dependentes primeiro) e com que testes. Só planeja.
### ⚙️ Desempenho e projeto
* **Desempenho proativo** (`core/desempenho_proativo.py`): avisa de programa pesado ou com vazamento; nunca fecha nada; respeita foco e a proatividade aprendida.
* **Contexto de projeto** (`core/contexto_projeto.py`): andamento, próximo passo, horas, arquivos da pasta que mudaram e o que você escreveu sobre ele.
### 🧠 Memória e equipe
* **Histórico longo** (`core/historico_longo.py`): arquivo permanente das conversas, diário e notas (sem cartões/CPF/chaves), com compactação e busca em que **palavras × semântica competem**.
* **Quadro da equipe** (`core/equipe_agentes.py`): os especialistas do orquestrador veem o que os outros descobrem **ao vivo**; conflitos entre eles vão para a síntese.
* **Adaptação contínua** (`core/adaptacao.py`, opt-in): ajusta verbosidade e proatividade, silêncio de avisos e favoritas; 8 sinais, 1 passo por dia, travar e desfazer.
### 🔧 Núcleo I.S.A.
* `isa_nucleo` ganhou: `modularization`, `immunity`, `competition`; novos módulos entram na checagem de saúde.

## 3.9.1 — 28/10/2026

### 🐞 Correção
* Auto-regeneração/Núcleo I.S.A.: erro “too many values to unpack (expected 2)” na checagem de saúde dos módulos. Seis módulos da 3.9 devolviam texto no lugar de `(ok, mensagem)`; corrigidos, e a checagem passou a aceitar qualquer formato.

## 3.9.0 — 28/10/2026

### 🎯 Missões
* **Modo ensaio**: mostra o que faria, passo a passo, sem tocar em nada. **Orçamento** por missão (horas, chamadas, passos sensíveis), com aviso aos 80%.
* **Aprovações aprendidas** (`core/aprovacoes.py`): depois de 5 aprovações iguais de uma ação que só escreve, o NEXUS *sugere* uma regra automática; só vale se você aceitar, e dá para revogar. Nunca vale para enviar, apagar, gastar ou controlar o PC.
* **Missões recorrentes** (`core/missoes_recorrentes.py`): "toda segunda organize minha semana"; até 10, com recuperação de até 6 h de atraso.
* 🧾 **Painel de auditoria no celular**: busca, período, tipo e "verificar integridade" da cadeia de hashes.
### 🕸️ Grafo · 🏭 Plugins · 🌐 Rede · 🎙️ Voz · 👁️ Tela · ✈️ Viagem
* Grafo se atualiza sozinho e responde "o que mudou nos últimos N dias". Plugins gerados têm **versões** (comparar, melhorar, voltar).
* Rede: **fila de tarefas** (24 h) e sincronização automática opcional. Voz: **calibração guiada** (6 amostras). Copiloto de tela: diagnostica o erro e oferece corrigir (com CONFIRMAR).
* **Modo viagem/offline** (`core/viagem.py`): pacote local de agenda/contatos/notas. Não baixa mapas nem clima.
### 🧠 Núcleo I.S.A. (`core/isa_*.py`, ferramenta `isa_nucleo`)
* Módulos com **saúde** e **recarga a quente** (testa antes), custo de importação; **análise de código recente**; **relatório de arquitetura** (ciclos, arquivos grandes, propostas — só sugere); **autonomia** que religa tarefas caídas e missões travadas (nível "avisar" ou "seguros").
### 🔌 Novidades
* **Conectores** (`core/conectores.py`): Todoist, Trello, ntfy, Discord, IFTTT, cena do Home Assistant. O modelo só dá o texto; o endereço vem da receita; só https, sem redirecionar, sem endereços internos; o que mexe no mundo pede CONFIRMAR.
* **Aprendizado da rotina** (`core/aprendizado.py`): desligado por padrão; só contagens por horário, neste PC, com esquecimento gradual; exportar e esquecer.
* **Estatísticas do PC** (`core/estatisticas_pc.py`): CPU por núcleo, memória, discos, processos agregados, bateria, temperatura e sugestões.
* **Organizador de pastas** (`core/organizador_inteligente.py`): qualquer pasta, regras suas, nunca sobrescreve, CONFIRMAR e desfazer.
* **Reunião** (`core/reuniao.py`), **revisão de texto** (`core/revisao_texto.py`), **abrir qualquer coisa** (`core/abrir_tudo.py`; não abre .exe/.bat/.lnk/macros por caminho) e **modo avançado** (`core/modo_avancado.py`; scripts só de cálculo/texto, isolados, aprovação por hash).
### 🐞 Correções
* **Plugins gerados que importavam `urllib`/`requests` não carregavam na caixa de areia da 3.8** (o bloqueio de rede trocava a classe `socket`); corrigido.
* Trava ao iniciar missão pela voz (bloqueio reentrante); detecção de import não usado; cache velho de `.pyc` na recarga a quente.

## 3.8.0 — 28/10/2026

### 🎯 Missões de longa duração (`core/missoes.py`, `actions/missao.py`)
* "Missão: organize meu mês": o NEXUS planeja, **simula o que mudaria**, pede a sua aprovação do plano quando há passo sensível e trabalha em segundo plano por horas.
  Confere o resultado, para nas decisões (enviar, mover, apagar, gastar, controlar o PC) e avisa por voz e push. Sobrevive a reiniciar; até 3 ativas, 25 passos de plano, 8 h.
* Painel do celular: botão 🎯 com lista, **Aprovar / Negar**, pausar, cancelar e desfazer o último passo.
### 🤝 Especialistas (`actions/orquestrador.py`)
* Novos agentes **agenda** e **finanças**; cada agente tem suas ferramentas (`config/agentes.json`), nunca as proibidas.
### 🔮 Simulação "e se" (`core/simulacao.py`) e 🧾 Auditoria (`core/auditoria.py`)
* Mostra o efeito de cada passo (inspeciona o disco: sobrescrever, apagar N itens). Toda ação e decisão entra num registro com **cadeia de hashes** (segredos mascarados): "por que você fez isso?" e "verifica o registro".
### 🖱️ Computer-use (`core/computer_use.py`)
* Vê a tela e opera passo a passo: CONFIRMAR para começar, máx. 25 passos / 5 min, teclas perigosas e janelas de banco/senha bloqueadas, segredos pedem aprovação, `parar` interrompe.
### 🕸️ Grafo de conhecimento (`core/grafo.py`) · 🧠 Modelo híbrido (`core/hibrido.py`) · 🏭 Fábrica de plugins (`core/fabrica_plugins.py`)
* Grafo: pessoas/projetos/compromissos/preferências ligados **com a fonte**. Híbrido: dado sensível fica no PC; modos auto/privado/rápido/econômico/offline.
  Fábrica: escreve, revisa permissões, testa em processo isolado sem rede e instala só com CONFIRMAR (plugin gerado não executa programas).
### 🎙️ Voz natural (`core/voz_emocao.py`) · 👁️ Contexto vivo (`core/contexto_vivo.py`) — ambos opt-in e locais
* Emoção/hesitação/correção e interrupção falando; reunião em 3 min, anexo esquecido, erro na tela (respeita o modo foco).
### 🌐 Rede de NEXUS (`core/rede_nexus.py`)
* Pareamento por código (20 caracteres, 10 min, uma vez), AES-256-GCM com anti-repetição; memória compartilhada (lista fixa, o mais novo vence, com backup) e tarefas de **leitura** entre aparelhos (só se ligar `aceitar_tarefas`).
### 🌌 Hub
* Ficam só os **20 visuais "Novos 3.6"** (mais o orbe de reserva); escolhas antigas migram para a Galáxia.
### 🐞 Correções internas
* Trava (deadlock) ao iniciar missão pela voz, achada nos testes de rota.

## 3.7.0 — 28/10/2026

### 🔎 OCR na memória de documentos (`core/ocr.py`)
* "Liga a leitura de fotos": fotos de recibos e PDFs escaneados viram texto (Tesseract local + pytesseract + pypdfium2) e entram na busca, citando "p. 3 (OCR)".
  Opt-in (OCR é lento); sem o Tesseract instalado o NEXUS diz o que falta. 4 testes com imagem e PDF de verdade.

### 🗞️ Resumo diário por voz (`core/resumo_diario.py`)
* "Resumo do dia": agenda de hoje + e-mails importantes (remetentes VIP ou palavras como urgente/prazo/vence) + tarefas, lidos ao mesmo tempo. Texto de e-mail marcado como de terceiros.

### 🎯 Modo foco com distrações
* `focus_mode` guarda a lista de programas de distração; "foco de 25 min e fecha as distrações" pede CONFIRMAR e fecha com `terminate` (nunca kill; protegidos nunca entram).
  Durante o foco os avisos no celular (push) ficam em silêncio.

### 👋 Presença (`core/presenca.py`)
* Opt-in: celular na rede da casa (só IP privado) e/ou câmera que pergunta "tem rosto?" e descarta o quadro. Ao chegar, acorda e dá um oi (no máx. 1 a cada 30 min).

### 🎛️ Editor do hub (`core/hub_ajustes.py`)
* Cor (matiz) e velocidade por visual, com prévia ao vivo: menu do hub › "Ajustar cor e velocidade deste visual…".

### 🏠 Ambientes (`core/perfis.py`)
* Perfil novo **Casa**; cada ambiente traz cor da interface, visual do hub e silêncio de push. Ao voltar ao Normal, devolve a cor e o visual que eram seus.

### 💾 Backup criptografado (`core/backup_cripto.py`)
* AES-256-GCM, chave derivada da frase por scrypt; a frase não é guardada. Pasta da sua nuvem, a cada 24 h, últimos 7. Restaurar pede CONFIRMAR e só escreve em memory/ e config/.

### 📦 Rotinas na loja (`core/rotinas_loja.py`)
* Pacotes `.nexusrotina` (sem código, só ferramentas seguras, assinatura opcional de autor confiável). Instalar pede CONFIRMAR e nunca substitui rotina sua.

## 3.6.0 — 28/10/2026

### 🔧 Integração MCP (`core/mcp_cliente.py`, `actions/mcp_nexus.py`)
* Cliente MCP (stdio, JSON-RPC, protocolo 2025-06-18): "adiciona o servidor MCP …", lista e chama as ferramentas deles.
* Ferramenta que altera algo (sem `readOnlyHint`) pede **CONFIRMAR**; o resultado volta marcado como `<untrusted_content>`. 13 testes com servidor falso.

### 📲 Avisos com o app fechado + acesso de fora de casa (`core/push_web.py`, `core/tunel.py`, `actions/tunel_painel.py`)
* Push web com VAPID (`pywebpush`): o painel avisa no celular mesmo fechado. Túnel `cloudflared` (Quick Tunnel) dá https confiável fora de casa,
  só ligado a pedido; o IP real vem de `cf-connecting-ip` apenas com o túnel ativo. Lista de destinos permitidos contra SSRF.

### ✉️ E-mails na memória de documentos (`core/rag_emails.py`)
* Opt-in ("coloca meus e-mails na memória"): cache local em `memory/emails_cache/`, indexado junto com as pastas. Cita "E-mail de Fulano · assunto · data",
  marca o texto como não confiável, "esquece meus e-mails" apaga o cache e o índice. 5 testes com IMAP falso.

### ✨ Hub e tema
* 20 visuais novos em `ui/hud_novos.py`; menu do hub em Essenciais, Ultra 2026 e Novos 3.6 (antigos fora do menu; quem já usava um continua com ele).
* Paleta refinada (contraste de texto ≥ 4,5:1 sobre os painéis) e 10 temas prontos, cada um com um visual do hub.

## 3.5.0 — 28/10/2026

### 🧩 Loja de plugins (`core/plugin_loja.py`, `actions/loja_plugins.py`, `ferramentas/assinar_plugin.py`)
* Pacote `.nexusplugin` (zip com `plugin.json` + `plugin.sig` + os `.py`). O autor assina com Ed25519; só vale se a chave dele estiver em
  `config/autores_confiaveis.json` ("confia no autor Maria com a chave …"). A chave do desenvolvedor do NEXUS já vem confiada.
* **Permissões** (rede, arquivos, programas, tela, mídia, pessoais) declaradas no manifesto e **conferidas no código** por análise estática:
  usou algo que não declarou, o pacote é recusado. `eval`, `exec` e `importlib` são recusados sempre.
* Instalar mostra **CONFIRMAR** com autor, assinatura e permissões. Pacote sem assinatura de autor confiável é recusado.
* O hash de cada arquivo é conferido na instalação e a cada abertura: plugin alterado depois de instalado não carrega.
  Plugins soltos em `plugins/` continuam funcionando como antes. `ferramentas/assinar_plugin.py` gera chaves e empacota. 8 testes.

### 🔌 Integrações (`core/integracoes.py`, `actions/telegram_nexus.py`, `agenda_google.py`, `notion_nexus.py`)
* **Telegram:** manda e lê mensagens do SEU chat com o SEU bot; mensagens de outros chats são ignoradas.
* **Agenda:** Google Calendar (ou qualquer `.ics` https) pelo endereço secreto iCal, só leitura: hoje, amanhã, semana, próximo; entende eventos repetidos.
* **Notion:** cria páginas no seu banco de dados e procura nas suas páginas. Chaves ficam em `config/api_keys.json` e nunca aparecem em respostas ou erros. 9 testes.

### 📱 Painel do celular como app — PWA (`dashboard/`)
* Manifesto, ícones, service worker e tela "NEXUS fora do ar". O service worker não guarda `/api`, `/ws` nem `/uploads`.
* Botão 🔔: avisa no celular quando o NEXUS responde com o app em segundo plano (aviso local, sem servidor de push).
* O logo do painel agora diz NEXUS. Precisa de contexto seguro (https confiável ou localhost) para instalar. 2 testes novos.

### 🎨 Tema automático (`core/tema_auto.py`, `actions/tema_auto.py`)
* "Tema automático pelo horário / pelo humor / pelos dois / desliga": a cor da interface acompanha a faixa do dia e a média do humor do diário
  nos últimos 3 dias. Nada é gravado: ao desligar volta a cor que você escolheu. 6 testes.

### 🧾 Preparar publicação
* `preparar_publicacao.py` e `.gitignore` deixam de fora a memória de documentos, os plugins instalados e os autores confiáveis.

### 📚 Memória de documentos com fonte citada (`core/rag_documentos.py`, `actions/memoria_semantica.py`)
* "Indexa a pasta Documentos/Contratos", "o que o contrato diz sobre multa?", "procura nos meus documentos algo sobre garantia".
  Lê PDF, Word, PowerPoint, texto, Markdown, CSV, JSON e código; corta em trechos e responde **com a fonte** (arquivo e página, slide ou linha).
* Opt-in: só entram as pastas que você adicionar. Recusa o disco inteiro, a pasta pessoal inteira e a pasta do próprio NEXUS.
  Ignora pastas ocultas, de dependências e de sistema. Tudo fica no PC (`memory/rag_documentos.npz`, `memory/rag_pastas.json`).
* Atualização incremental: só arquivo novo ou alterado é lido de novo; o que sumiu sai do índice. Busca por sentido + empurrão para as palavras exatas.
* Novas ações: `add_folder`, `remove_folder`, `folders`, `docs_reindex`, `docs_status`, `docs_search`. 9 testes em `tests/test_rag_documentos.py`.

### 🧭 Menu SETUP em ordem lógica (`ui/overlays/settings.py`, `ui/main_window.py`)
* Três grupos: GERAL (Configuração do usuário, Áudio, Chaves e APIs), SISTEMA (Status, Núcleo I.S.A., Atuador, Backup) e PERSONALIZAR (Barra rápida, Atalhos).

### 🔒 Apagar só com o CONFIRMAR da pessoa (`actions/file_controller.py`)
* **Limpar temporários** e **apagar arquivos ocultos** não dependem mais do `confirm=true` que o modelo escreve:
  o pedido abre o aviso **CONFIRMAR / CANCELAR** no HUD (`core/confirm.py`) e só apaga quando a pessoa aperta.
  Sem interface ligada, não apaga nada. Medir e listar continuam imediatos, sem pergunta.

### 🛡 Caixa de areia do controle do desktop (`actions/desktop.py`)
* O código gerado pela IA não pode mais **escrever** (`write_text`, `write_bytes`) nem **desligar, bloquear ou fechar
  janelas** pelo `user32` (`ExitWindowsEx`, `LockWorkStation`, `PostMessage`…), nem por variável nem por índice.
* `shutil.copy2` / `copytree` da caixa de areia **não sobrescrevem** nem misturam com o que já existe.
* Corrigido: o `shutil.copy2` da caixa de areia nunca funcionou (dava `TypeError`); agora copia para destino novo.
* 31 testes novos em `tests/test_seguranca_35.py`.

## 3.4.0 — 25/10/2026

### 📞 Ligar pelo WhatsApp (`core/whatsapp_ligacao.py`, `actions/ligar_whatsapp.py`)
* "Liga pro Marcos no WhatsApp", "chamada de vídeo com a Maria", "liga no zap pro 11 98888-7777".
* O nome vai para os seus contatos e vira número (DDI 55 entra sozinho); o WhatsApp Desktop abre a conversa CERTA
  pelo link `whatsapp://send?phone=` e o botão de voz/vídeo é achado pelo nome, nunca por coordenada.
* Antes de ligar aparece **CONFIRMAR** com quem e qual número. Só diz "liguei" se o botão de encerrar apareceu.
* Entrou no grupo "Enviar mensagens e fazer ligações" das permissões do Atuador.

### 💻 Rotina Programação pergunta o que criar (`actions/smart_routines.py`)
* "Modo programação" abre o VS Code e pergunta **qual aplicativo ou site** criar; a resposta vai direto para o
  agente de código (`dev_agent`). Uma rotina "programação" que você já tinha ganha a mesma pergunta.
* Toda rotina pode ter a sua pergunta (`ask` ao criar).

### ☀ Rotina Bom dia (`actions/bom_dia.py`)
* Um comando: abre a caixa de e-mail no navegador (pelo seu e-mail salvo), o clima de hoje e as manchetes, ao mesmo
  tempo. Chega pronta, uma vez, também para quem já tinha rotinas.

### 🔎 Pesquisa profunda e 🔔 vigias (`core/pesquisa_profunda.py`, `core/vigias.py`)
* "Pesquisa a fundo sobre…": várias buscas em paralelo e um resumo com pontos principais, divergências, o que não
  foi confirmado e fontes; relatório em Documentos/NEXUS Agente.
* "Fica de olho nas notícias sobre…", "me avisa quando o preço do… cair" (também de uma página): a 1ª olhada só
  aprende; depois avisa o que é novo ou a mudança de preço acima do limite.

### 🚀 Iniciar projeto (`core/inicio_projeto.py`)
* Pasta com README, notas e .gitignore, VS Code, documentação oficial, contagem de tempo ("quanto tempo trabalhei
  no projeto?") e a pergunta do próximo passo, já registrado na lista de projetos.

### 📝 Analisar trabalho (`core/analise_trabalho.py`)
* Formatação (com as linhas), sugestões de conteúdo e trechos em outro idioma com tradução oferecida. Corrigir e
  traduzir sempre geram um arquivo NOVO; o original não muda.

### 🌿 Oráculo de bem-estar (`core/oraculo_bemestar.py`)
* Plano do dia com sono, energia, humor, hábitos, tarefas, lembretes, tempo de tela e clima: energia prevista, foco
  no seu pico, pausas, movimento e hora de dormir. Prevenção para padrões que se repetem há dias.
* Avisos ao longo do dia (pausa, água, dormir) com intervalo mínimo. Não é conselho médico; os dados não saem do PC.

### 🔮 Núcleo I.S.A. avançado (`core/isa_preditiva.py`)
* Prevê disco cheio, vazamento de memória do NEXUS, memória do PC no limite, respostas mais lentas e funções que
  falham — antes de virar problema, com sugestão. "Otimiza o sistema" aplica o que é seguro.
* Desempenho automático: economia (jogo, CPU alta, bateria baixa: prioridade do NEXUS mais baixa e laços 3× mais
  calmos), equilibrado ou desempenho. Só o próprio NEXUS é ajustado.

### 🛠 Auto-regeneração e aprendizado colaborativo (`core/autoregeneracao.py`, `core/rede_colaborativa.py`)
* Restaura a cópia boa de um arquivo estragado, pausa por 10 min a função que falha sem parar (disjuntor), libera
  memória e limpa sobras do NEXUS. Instalar um pacote que falta só do requirements.txt e só com o seu CONFIRMAR.
* Aprende qual remédio funciona para cada falha. Opcional: os NEXUS da sua rede trocam esse placar (sem dados
  pessoais), assinado com HMAC do código do grupo; o que chega só reordena remédios que já existem.

## 3.3.0 — 25/10/2026

### ⏱ Latência e resposta mais rápida (`core/latencia.py`, `core/cache_respostas.py`)
* Cada pedido do motor próprio é medido por etapa (escutar, preparar, rota, modelo, ferramenta), do fim da sua fala
  até a 1ª fala (`memory/latencia.json`). No Gemini Live mede-se o total.
* Botão **⏱ Latência** na I.S.A.: tempo típico, 90% dos casos, média de cada etapa, maior gargalo e dica.
* Clima e notícias ficam num cache curto. "Nexus, por que você está lento?" responde com os números.

### 📴 Modo offline (`core/conexao.py`)
* Sem internet, as ferramentas de rede respondem na hora e o resto segue funcionando; aviso ao cair e ao voltar.

### 🗣 Rotinas por conversa (`core/rotinas_conversa.py`)
* "Toda manhã abre meu e-mail e me diz o clima": mostra a prévia e só salva com o seu sim; roda uma vez por dia.

### 🎚 Perfis de uso (`core/perfis.py`)
* Trabalho, Estudo, Jogo e Normal mudam o tom, silenciam a proatividade (e a água no Jogo) e desativam ferramentas
  que distraem. Travas de segurança e confirmações são iguais em todos os perfis.

### 🔎 Busca no que você já fez (`core/busca_historico.py`)
* Procura em relatórios, anotações e diário, entendendo hoje, ontem, semana passada, mês passado, últimos N dias.

### 🌙 Revisão diária por voz (`core/revisao_diaria.py`)
* "Como foi meu dia?": concluído hoje, pendente/atrasado, lembretes que ainda tocam e o que fica para amanhã.

### 🔒 Privacidade (`core/privacidade.py`)
* Painel na I.S.A. e por voz: o que fica no PC, o que sai e **Apagar** por item, sempre com confirmação
  (por voz só vale depois de o NEXUS perguntar). Chaves de API e licença não são apagáveis por ali.

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
