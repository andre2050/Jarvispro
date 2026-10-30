# NEXUS ULTRA 2026
### Assistente pessoal de voz — desenvolvido por André Luiz Lima Menezes · Versão 4.0.0

Mapa de todas as pastas e arquivos do projeto, como estão hoje na pasta.
Base: MARK LV — JARVIS (© FatihMakes, CC BY-NC 4.0) — veja `LICENSE` e `NOTICE.md`.

```
Nexus-Ultra-2026/
├── .gitignore                           # Mantém chave de API, memórias e dados pessoais fora do repositório
├── Abrir NEXUS (mostra erros).bat       # Abre o NEXUS e não fecha sozinho, para ler os erros
├── CHANGELOG.md                         # Histórico das mudanças por versão
├── claude_voice.py                      # Assistente por voz com Claude: microfone → Whisper → Claude → voz
├── configurar_email.py                  # Configura o e-mail que o NEXUS lê em voz alta
├── configurar_github.py                 # Liga a atualização automática ao seu repositório do GitHub
├── ESTRUTURA.md                         # Este mapa do projeto
├── gerar_exe.bat                        # Dois cliques e o Nexus.exe aparece na pasta
├── Ideias_Nexus.txt                     # Lista de ideias para as próximas versões
├── Instalar o NEXUS (primeira vez).bat  # Instala tudo na primeira vez
├── instalar_pacotes.py                  # Instalador tolerante das bibliotecas
├── LICENSE                              # Licença CC BY-NC 4.0 (base MARK LV — JARVIS, © FatihMakes) — uso não comercial
├── main.py                              # Ponto de partida: ajustes do Windows, abre a janela e liga o assistente
├── nexus.spec                           # Receita do PyInstaller para gerar o Nexus.exe
├── nexus_exe.py                         # Ponto de partida do Nexus.exe
├── NOTICE.md                            # Créditos: André Luiz Lima Menezes + FatihMakes (obrigatório manter)
├── preparar_publicacao.py               # Prepara uma versão para publicar no GitHub, sem segredos
├── pyproject.toml                       # Configuração do pytest e do ruff
├── readme.md                            # Apresentação, funções e como usar
├── requirements.txt                     # Bibliotecas Python necessárias
├── setup.py                             # Instalação inicial (confere o Python e as bibliotecas)
├── VERSION                              # Número da versão (4.0.0)
├── actions/                             # Habilidades que controlam o computador — uma por arquivo, descobertas sozinhas ao iniciar
│   ├── agent_task.py                    # Tarefas autônomas (modo agente): planeja, executa, confere e avisa no fim
│   ├── agenda_google.py                 # Agenda: Google Calendar / .ics por voz (só leitura)
│   ├── anomalia_pc.py                   # Vigia de anomalias do PC (autoencoder)
│   ├── background_monitor.py            # Vigia de assuntos que você pediu (checagem diária)
│   ├── briefing.py                      # Resumo do dia por voz
│   ├── browser_control.py               # Controle do navegador
│   ├── casa_inteligente.py              # Casa inteligente: Home Assistant e webhooks
│   ├── cerebro_local.py                 # Cérebro local no Ollama (dados, Modelfile, LoRA)
│   ├── code_helper.py                   # Escreve e roda scripts em qualquer linguagem
│   ├── compras.py                       # Lista de compras com listas nomeadas
│   ├── computer_control.py              # Atalhos de teclado, mouse e janelas
│   ├── computer_settings.py             # Volume, brilho, Wi-Fi e energia
│   ├── computer_vision.py               # Visão com OpenCV: QR, rostos, análise da tela e vigia de movimento
│   ├── contatos.py                      # Contatos e aniversários
│   ├── conversation_threads.py          # Fios de conversa: lembra o que ficou em aberto
│   ├── daily_planner.py                 # Plano do dia a partir de notas, memória e hábitos
│   ├── desktop.py                       # Área de trabalho e barra de tarefas
│   ├── dev_agent.py                     # Agente de código: planeja, escreve, instala, roda, confere e corrige
│   ├── diagnostico.py                   # Diagnóstico da saúde do próprio NEXUS
│   ├── diario.py                        # Diário com humor (só no seu PC)
│   ├── email_checker.py                 # "Nexus, verifica meu e-mail"
│   ├── email_reader.py                  # Lê e-mails novos em voz alta
│   ├── everyday_tools.py                # Pequenas ferramentas do dia a dia
│   ├── file_controller.py               # Operações com arquivos e pastas
│   ├── file_processor.py                # Leitura e resumo de documentos
│   ├── financas_ia.py                   # Finanças com IA: categoria automática e previsão do mês
│   ├── flight_finder.py                 # Busca de voos
│   ├── focus_mode.py                    # Modo foco (Pomodoro por voz)
│   ├── forge_app.py                     # Nexus Forge por voz: plano aprovado → constrói → testa → revisa; alterar, desfazer, zip, exe, GitHub (CONFIRMAR)
│   ├── game_updater.py                  # Atualiza ou instala jogos pelo launcher
│   ├── isa_core.py                      # I.S.A. por voz: "relatório da I.S.A."
│   ├── loja_plugins.py                  # Loja de plugins por voz: listar, instalar (com CONFIRMAR), remover, confiar no autor
│   ├── llm_brain.py                     # Modelo de linguagem para trabalhos pesados de texto
│   ├── local_vision.py                  # Visão local por voz e modo privado (sem internet)
│   ├── manutencao_pc.py                 # Manutenção do PC: disco, limpeza, backup, rede e bateria
│   ├── mapas.py                         # Mapas e rotas
│   ├── memoria_semantica.py             # Memória semântica: acha o que você disse pelo sentido
│   ├── memory_bank.py                   # Memória de longo prazo: "lembra que…"
│   ├── music_control.py                 # Controle de música e mídia
│   ├── neural_core.py                   # Rede neural treinada do zero
│   ├── notepad.py                       # Bloco de Notas por voz e ditado
│   ├── notion_nexus.py                  # Notion: criar notas e buscar
│   ├── noticias.py                      # Notícias sob demanda
│   ├── open_app.py                      # Abre programas (mapa de nomes por sistema)
│   ├── orquestrador.py                  # Equipe de agentes especialistas trabalhando juntos
│   ├── previsao_habitos.py              # Previsão de hábitos por horário
│   ├── price_alert.py                   # Alertas de preço
│   ├── proactive.py                     # Conversa proativa ciente de horário, contexto e projetos
│   ├── projetos.py                      # Meus projetos: registra projeto e próximo passo
│   ├── quick_notes.py                   # Notas rápidas por voz
│   ├── rastreador_habitos.py            # Hábitos e metas diárias com sequências
│   ├── reminder.py                      # Lembretes agendados no sistema
│   ├── screen_processor.py              # Captura de tela e câmera para a visão
│   ├── send_message.py                  # Envio de mensagens
│   ├── shortcut_manager.py              # Catálogo de atalhos nomeados
│   ├── simple_finance.py                # Finanças: gastos, categorias e orçamento com aviso
│   ├── smart_routines.py                # Rotinas: uma frase, várias ações
│   ├── system_monitor.py                # Monitor de CPU, RAM, GPU e temperatura com alerta
│   ├── system_update.py                 # O NEXUS se mantém atualizado
│   ├── telegram_nexus.py                # Telegram: manda e lê mensagens do seu chat com o seu bot
│   ├── tema_auto.py                     # Tema automático por voz: horário, humor ou os dois
│   ├── tarefas.py                       # Lista de tarefas com prazo e prioridade
│   ├── texto_dev.py                     # Ferramentas de texto e de programador, offline
│   ├── timer_action.py                  # Timers e alarmes por voz
│   ├── unit_converter.py                # Conversão de unidades e moedas
│   ├── video_player.py                  # Toca vídeo no HUD
│   ├── visao_ia.py                      # Objetos (YOLOX) e rostos (YuNet+SFace), sem enviar imagem a ninguém
│   ├── voz_treino.py                    # Cadastro da sua voz e da palavra "Nexus"
│   ├── weather_report.py                # Clima e previsão, falados
│   ├── web_search.py                    # Busca na web (Gemini + DDG): notícias, preço, comparação
│   └── youtube_video.py                 # Busca, resumo e transcrição de vídeos
├── assistant/                           # O cérebro: conversa por voz, ferramentas e tarefas em segundo plano
│   ├── __init__.py                      # Motor do NEXUS
│   ├── audio.py                         # Microfone, alto-falante, interrupção e imagens
│   ├── background.py                    # O que roda sozinho: monitores, proativo, e-mail, foco, atualização, celular
│   ├── common.py                        # Constantes e auxiliares usados por todos
│   ├── core.py                          # A classe do assistente (NexusLive)
│   ├── dictation.py                     # Modo ditado
│   ├── motor_proprio.py                 # Motor próprio: Whisper + o modelo escolhido + a voz escolhida
│   ├── session.py                       # Sessão com o Gemini Live: conexão, reconexão, saudação, resumo
│   ├── tool_declarations.py             # Ferramentas declaradas direto no código
│   ├── tools.py                         # Executa as ferramentas que o modelo pede
│   ├── typed.py                         # Comandos digitados: rotinas e rede neural local
│   └── wake.py                          # Palavra de ativação, dormir/acordar, segurar para falar
├── config/                              # Chaves e configurações (api_keys.json nunca vai para o GitHub)
│   ├── __init__.py                      # Caminhos e leitura da configuração
│   ├── api_keys.example.json            # Modelo do api_keys.json (chave, nome, voz, cor) — criado na 1ª abertura
│   ├── nexus.ico                        # Ícone do programa
│   └── update.json                      # Repositório do GitHub usado pelo botão ATUALIZAR (vazio = desligado)
├── core/                                # Peças internas: voz, rede neural, I.S.A., licença, segurança
│   ├── __init__.py                      # Pacote core
│   ├── action_loader.py                 # Descobre e executa as actions
│   ├── anomalia.py                      # Detector de anomalias do PC
│   ├── armazem.py                       # Guarda listas pessoais em JSON sem corromper
│   ├── audio_devices.py                 # Lista e escolhe microfone e alto-falante
│   ├── audio_feat.py                    # Características de áudio em NumPy puro
│   ├── audit.py                         # Registro de cada ação em memory/audit.log
│   ├── aviso_voz.py                     # Avisos falados que não dependem do Gemini
│   ├── bloco_de_notas.py                # Bloco de Notas do Windows + modo ditado
│   ├── cerebro_local.py                 # Cérebro local (Ollama)
│   ├── claude_voice.py                  # Laço de voz com Claude
│   ├── comandos_usuario.py              # Comandos criados por você
│   ├── confirm.py                       # Confirmação de ação irreversível que o modelo não consegue falsificar
│   ├── dev_projeto.py                   # Conferências do agente de código, sem IA e sem rede
│   ├── echo.py                          # Separa a sua voz do eco do próprio NEXUS
│   ├── embeddings.py                    # Texto em vetores para comparar sentido
│   ├── financas_ia.py                   # Categoria automática e previsão de gastos
│   ├── focus_guard.py                   # Modo reunião, tela cheia e limites de alerta
│   ├── forge_engine.py                  # Motor do Forge: arquiteto, construtor, revisor, checkpoints em git e limite de tokens
│   ├── gemini.py                        # Todas as chamadas avulsas ao Gemini: escada de modelos, tempos e pausas
│   ├── habits.py                        # Aprende como você usa o NEXUS
│   ├── hotkey.py                        # Segurar uma tecla para falar
│   ├── indice_semantico.py              # Índice da memória semântica
│   ├── installer.py                     # Instalador automático de dependências
│   ├── intent_net.py                    # Rede neural local que entende comandos sem internet
│   ├── isa.py                           # I.S.A.: o núcleo de decisões ao vivo
│   ├── integracoes.py                   # Telegram, agenda (.ics) e Notion
│   ├── plugin_loja.py                   # Loja de plugins: pacotes assinados, permissões conferidas, hashes
│   ├── isa_hud.py                       # Desenho da I.S.A. no HUD: cérebro + engrenagens
│   ├── janelas.py                       # Fechar app pelo nome, trazer para a frente, limites da plataforma
│   ├── keras_engine.py                  # Motor de rede neural em Keras/TensorFlow (opcional)
│   ├── keras_intent.py                  # Rede de intenções em Keras/TensorFlow (opcional)
│   ├── licenca.py                       # Chave de licença assinada, offline
│   ├── llm_client.py                    # Cliente de modelo local
│   ├── llm_providers.py                 # Provedores do motor próprio: Claude, Gemini, OpenAI, Ollama e outros
│   ├── neural_backend.py                # Escolhe entre Keras/TensorFlow e NumPy
│   ├── neural_engine.py                 # Motor de rede neural em NumPy puro
│   ├── organizador.py                   # Organiza a área de trabalho por tipo (e desfaz)
│   ├── plugin_loader.py                 # Descobre, valida e executa os plugins
│   ├── preferences.py                   # Preferências do painel de controle
│   ├── previsao_habitos.py              # Rede que prevê hábitos
│   ├── prompt.txt                       # Todo o texto do prompt do assistente
│   ├── protecao.py                      # Contém erros que fechavam o programa e grava falhas.log
│   ├── pt_time.py                       # Datas e horas em português
│   ├── reconexoes.py                    # Diário das quedas e renovações da conexão
│   ├── roteador.py                      # Segunda opinião para a rede de intenções
│   ├── rag_documentos.py                # Memória de documentos (RAG): pastas opt-in, trechos com fonte citada
│   ├── roteador_modelos.py              # Cérebro de decisão: modelo rápido, forte ou equipe de agentes
│   ├── settings_tools.py                # Lógica das Configurações (sem Qt)
│   ├── stt.py                           # Motores de fala para texto
│   ├── tema_auto.py                     # Tema automático: cor pela hora do dia e pelo humor do diário
│   ├── tts.py                           # Motores de texto para fala
│   ├── undo.py                          # Pilha única de desfazer
│   ├── verificacao.py                   # Status done/unverified/failed e conteúdo não confiável
│   ├── visao_ia.py                      # Visão local de objetos e rostos
│   ├── visao_local.py                   # Visão sem internet: OCR e descrição de imagens
│   ├── volume_dispositivo.py            # Volume por dispositivo de áudio
│   ├── voz_id.py                        # Reconhece a voz do dono
│   ├── voz_propria.py                   # Ouvido (Whisper) e vozes do motor próprio
│   ├── vozes.py                         # Escolha da voz do sistema (masculina por padrão)
│   ├── wake_custom.py                   # Palavra "Nexus" treinada na sua voz
│   ├── wake_nexus.py                    # Palavra de ativação "Nexus", offline
│   └── wake_word.py                     # Palavra de ativação local ("Nexus" ou "Hey Jarvis")
├── dashboard/                           # Painel de controle pelo celular (QR code)
│   ├── __init__.py                      # Pacote do painel
│   ├── server.py                        # Servidor FastAPI do painel do celular (login com limite de tentativas)
│   └── static/                          # A página do celular e a tela de login
│       ├── app.html                     # Página de controle do celular
│       ├── crypto-js.min.js             # Biblioteca de criptografia da página
│       └── login.html                   # Tela de login do celular
├── memory/                              # Seus dados (memória, rotinas, notas) e o número da versão
│   ├── __init__.py                      # Pacote de memória
│   ├── config_manager.py                # Acesso ao api_keys.json: chave, nome, voz, cor, opções
│   ├── memory_manager.py                # Carrega e grava a memória de longo prazo
│   └── version.json                     # Versão e histórico de mudanças (o que o ATUALIZAR mostra)
├── plugins/                             # OPCIONAL — habilidades extras: solte um .py aqui
│   ├── __init__.py                      # Pacote de plugins
│   └── _template.py                     # Modelo para criar uma habilidade nova — copie e solte aqui
├── tests/                               # Testes automáticos (python -m pytest)
│   ├── conftest.py                      # Configuração dos testes: sem tela, sem placa de som, sem internet
│   ├── test_aviso_voz.py                # Chave do Gemini inválida: reconhecer os erros e avisar por voz sem repetir
│   ├── test_camera.py                   # Visão da câmera (2.4.2): sem câmera de verdade — um VideoCapture falso
│   ├── test_casa_inteligente.py         # Testes da casa inteligente contra um Home Assistant FALSO de verdade (servidor HTTP local)
│   ├── test_code_helper_linguagens.py   # code_helper escreve em qualquer linguagem: extensão certa, mesmo fora do mapa
│   ├── test_dashboard.py                # Testes do painel pelo celular (dashboard/server.py): login, sessões, limites e uploads
│   ├── test_dev_agent.py                # Testes de actions/dev_agent.py com uma "IA" de mentira: o fluxo inteiro roda de verdade
│   ├── test_dev_agent_navegador.py      # Teste do navegador invisível de verdade (Playwright + Chromium). Pulado se não houver
│   ├── test_dev_agent_proprio_nexus.py  # Agente de código e o próprio NEXUS: resposta na hora, sem círculo
│   ├── test_dev_projeto.py              # Testes de core/dev_projeto.py — as conferências do agente de programação
│   ├── test_diagnostico.py              # Testes do diagnóstico: lê o registro de ações e não vaza nada que não deve
│   ├── test_forge.py                    # Testes do Forge (motor + ação) com um Claude de mentira
│   ├── test_funcoes_22.py               # Testes das funções novas da 2.2: compras, hábitos, contatos, manutenção do PC, texto/dev e diário
│   ├── test_hud_ultra.py                # Os 20 visuais: registro, desenho em todos os estados, migração e volta ao orbe se falhar
│   ├── test_ia_23.py                    # Testes da 2.3: reconexão, embeddings/memória semântica, roteador, voz do dono
│   ├── test_ia_23_memoria.py            # Embeddings, memória semântica e verificador do roteador
│   ├── test_keras_engine.py             # Motor Keras/TensorFlow (core/keras_engine.py, core/keras_intent.py) e o seletor de motor
│   ├── test_monitor_visual.py           # Monitor de sistema e paleta do visual novo: partes que não dependem de tela
│   ├── test_neural_core.py              # Rede neural: motor (core/neural_engine.py) + ferramenta (actions/neural_core.py)
│   ├── test_open_app.py                 # Abrir programas (2.4.1): cmd, câmera, Python 3.12 e Backup do Windows
│   ├── test_orquestrador.py             # 2.5 — roteador de modelos (core/roteador_modelos.py), orquestrador de agentes
│   ├── test_painel_visao.py             # Painel 🤖 VISÃO COMPUTACIONAL (2.4.4)
│   ├── test_simple_finance.py           # Testes das finanças simples: valores em português, períodos, orçamento e arquivo à prova de queda
│   ├── test_streaming.py                # Streaming (2.4.6): core/llm_providers.py (conversar_stream) + core/voz_propria.py (FalaEmFluxo)
│   └── test_voz_23.py                   # Cadastro de voz, palavra treinada e proteção contra fechamento sozinho
└── ui/                                  # A janela (PyQt6): HUD, conversa em balões, painéis e temas
    ├── __init__.py                      # Pacote da interface
    ├── _base.py                         # Tema (paleta Ultra 2026), fontes, caminhos e coletor de métricas
    ├── _qt.py                           # Importações do Qt usadas por todos
    ├── app.py                           # Ponte entre o cérebro e a janela (NexusUI)
    ├── comandos_pt.py                   # Descrição e exemplo de cada função, em português (lista F1)
    ├── hub_geom.py                      # Geometria do visual Hub
    ├── hud.py                           # O HUD central: orbe de reserva e o despacho para os 20 visuais Novos 3.6
    ├── hud_novos.py                     # Os 20 visuais do hub (Prisma, Saturno, Galáxia, Cidade, Tempestade…)
    ├── hud_util.py                      # Ajudas de desenho dos visuais (cores, brilho, núcleo)
    ├── main_window.py                   # A janela principal: layout, botões, atalhos, bandeja, vídeo
    ├── modern.py                        # Conversa em balões, medidores, cartões e barra rápida
    ├── quickbar.py                      # Catálogo da barra rápida e dos atalhos
    ├── widgets.py                       # Peças reutilizáveis: log, área de arquivos, câmera, roda de cores
    └── overlays/                        # Painéis flutuantes: configurações, notas, I.S.A., atualização…
        ├── __init__.py                  # Pacote dos painéis
        ├── activity_log.py              # Log de atividades com filtro
        ├── agenda.py                    # Central de Notas e Lembretes
        ├── base.py                      # Base dos painéis flutuantes
        ├── customize.py                 # Nome, voz, cor, temas prontos, idioma, horário de silêncio
        ├── isa.py                       # Painel do núcleo I.S.A. (Ctrl+I)
        ├── licenca.py                   # Tela de ativação da licença
        ├── panels.py                    # Plugins, confirmação, dispositivos de áudio, memória
        ├── produtividade.py             # Painel PRODUTIVIDADE (Ctrl+P)
        ├── quickbar_editor.py           # Editores da barra rápida e dos atalhos
        ├── remote.py                    # Plugins e pareamento com o celular
        ├── settings.py                  # O menu CONFIGURAÇÕES
        ├── setup.py                     # Tela inicial (chave do Gemini)
        ├── tools.py                     # Visão, sistema, área de transferência, comandos, notas
        ├── update.py                    # Janela ATUALIZAR O NEXUS
        └── user_settings.py             # Configuração do usuário
```

**Criados na primeira abertura (não vêm no pacote, não vão para o GitHub):** `config/api_keys.json` (sua chave), `config/certs/` (certificado do celular), `config/licenca.json`, `memory/long_term.json` e os demais dados em `memory/`.

---

## Detalhes por área

Onde fica cada coisa. Antes eram dois arquivos gigantes (`ui.py` com 7.800 linhas
e `main.py` com 2.900); agora cada área tem o seu arquivo.

## Começo de tudo
| Arquivo | O que faz |
|---|---|
| `main.py` | Ponto de partida (59 linhas): ajustes do Windows, abre a janela e liga o assistente |

## `assistant/` — o cérebro (conversa por voz com o Gemini)
| Arquivo | O que faz |
|---|---|
| `core.py` | A classe do assistente (`NexusLive` / `NexusLive`) e a inicialização |
| `session.py` | Sessão com o Gemini Live: configuração, conexão, reconexão, saudação da manhã, resumo da conversa |
| `audio.py` | Microfone, alto-falante, interrupção, imagens da tela/câmera |
| `tools.py` | Executa as ferramentas que o Gemini pede |
| `tool_declarations.py` | Ferramentas declaradas direto no código (as outras vêm de `actions/` e `plugins/`) |
| `typed.py` | Comandos digitados: rotinas e rede neural local |
| `wake.py` | "Hey Jarvis", dormir/acordar, segurar para falar |
| `background.py` | O que roda sozinho: monitores, conversa proativa, e-mail, foco, atualização, celular |
| `common.py` | Constantes e funções auxiliares usadas por todos |
| `dictation.py` | (1.4) Liga o modo ditado ao Gemini e à janela (avisos, botão, fala adiada) |

## `ui/` — a janela
| Arquivo | O que faz |
|---|---|
| `main_window.py` | A janela principal (layout, botões, atalhos, bandeja, vídeo) |
| `hud.py` | O desenho central e as barras de métricas. Nove visuais clássicos (`HUD_STYLE_INFO`): orbe, mínimo, aurora, líquido, holograma, globo neural, Hub, Matrix e Ondas |
| `hud_novos.py` | Os 20 visuais do hub; cada um é uma função de desenho registrada em `NOVOS_STYLES` |
| `widgets.py` | Peças reutilizáveis: log da conversa, área de arquivo, câmera, roda de cores |
| `app.py` | A ponte entre o cérebro e a janela (`NexusUI`) |
| `_base.py` | Cores do tema ("Aurora", com `accent2()` para os degradês), fontes, caminhos, coletor de métricas (CPU, RAM, rede, GPU, temperatura, processos, histórico) |
| `_qt.py` | Importações do Qt usadas por todos |
| `overlays/settings.py` | O menu CONFIGURAÇÕES (15 seções) |
| `overlays/user_settings.py` | A janela Configuração do usuário |
| `overlays/customize.py` | Nome, voz, cor, tratamento, idioma, horário de silêncio |
| `overlays/panels.py` | Plugins, confirmação, dispositivos de áudio, memória |
| `overlays/tools.py` | Visão, sistema, área de transferência, comandos, notas |
| `overlays/remote.py` | Configuração de plugins e pareamento com o celular |
| `overlays/setup.py` | Tela inicial (chave do Gemini) |
| `overlays/activity_log.py` | Log de atividades |
| `modern.py` | (1.2) Conversa em balões, cartão de ESTADO, barra rápida. (2.2) Monitor novo: `RingGauge` (arco com degradê), `SparkMetric` (gráfico ao vivo), `UptimeCard` (dias/horas/min), `ProcessList` (processos por CPU/RAM), `HeaderBar` e `GradientLabel` do topo |
| `quickbar.py` | (1.2) Catálogo dos botões da barra rápida e da lista de atalhos de teclado |
| `comandos_pt.py` | (1.2) Nome, descrição e exemplo de cada função, em português (lista F1) |
| `overlays/agenda.py` | (1.2) Central de Notas e Lembretes |
| `overlays/quickbar_editor.py` | (1.2) Editores da barra rápida e dos atalhos |
| `overlays/isa.py` | (1.3) Painel do núcleo I.S.A. (Ctrl+I) |
| `overlays/update.py` | (1.4.1) Janela ATUALIZAR O NEXUS: confere o GitHub, instala, reinicia, desfaz |

## Núcleo I.S.A. (1.3)
| Arquivo | O que faz |
|---|---|
| `core/isa.py` | O registro central: cada entrada, decisão, ação, resultado e erro, o estado dos módulos e os números. Só na memória, nada sai do PC |
| `core/isa_hud.py` | O desenho do HUD: cérebro (cognição) + engrenagens (automação) |
| `actions/isa_core.py` | A I.S.A. por voz: “Nexus, relatório da I.S.A.” |

Quem avisa a I.S.A.: `assistant/tools.py` (toda função que o Gemini chama), `assistant/typed.py` (rede neural local, rotinas e o que vai para o Gemini), `assistant/audio.py` (o que você falou e o que ele respondeu), `assistant/session.py` (conexão) e a caixa de comando.

## Bloco de Notas e visão local (1.4)
| Arquivo | O que faz |
|---|---|
| `core/bloco_de_notas.py` | Controla a janela do Bloco de Notas pelas mensagens do Windows (escreve, apaga, lê — sem simular teclado) e o modo ditado (pontuação falada, "apaga a última frase", "parar ditado") |
| `actions/notepad.py` | O Bloco de Notas por voz: abrir, escrever, acrescentar, ler, salvar, ditado |
| `core/visao_local.py` | Visão sem internet: captura (tela, janela, câmera, arquivo), OCR (Windows ou RapidOCR) e descrição com o Ollama |
| `actions/local_vision.py` | A visão local por voz e o modo privado de visão |
| `actions/computer_vision.py` | (1.4.2) OpenCV: QR, rostos, análise da tela/câmera e a vigia de movimento (aviso, som e foto) |
| `core/organizador.py` | (1.4.2) "Organiza a área de trabalho": arquivos soltos em pastas por tipo, e desfazer |

Enquanto o ditado está ligado: `assistant/audio.py` manda a sua fala para o Bloco de Notas e cala a voz do NEXUS, `assistant/tools.py` não executa nenhuma ferramenta e `assistant/typed.py` manda o que você digita para o ditado.

## Conexão e velocidade (1.4.3)
| Onde | O que faz |
|---|---|
| `assistant/session.py` › `_watch_connection` | Renova a conexão com o Gemini antes dos ~10 min (ou quando chega o GoAway), num momento calmo, mantendo a conversa; destrava pedido digitado sem resposta (15 s) |
| `assistant/audio.py` | Lê o GoAway, marca quando a resposta chegou, conta as ferramentas rodando |
| `core/gemini.py` | Escada FAST começa pelos modelos "lite" mais rápidos; cota diária descansa 1 h; clientes reaproveitados |
| `actions/orquestrador.py` | Equipe de agentes especialistas (`orchestrate`): divide, roda em paralelo, junta |
| `core/roteador_modelos.py` | Rede de decisão: pedido simples / difícil / delegar; escolhe o modelo e aprende com o uso |
| `core/intent_net.py` | `exemplo_valido`: só aprende comando que ela mesma poderia executar |

## Motor próprio e novidades da 1.5
| Arquivo | O que faz |
|---|---|
| `assistant/motor_proprio.py` | O MOTOR PRÓPRIO: microfone → Whisper → o modelo escolhido (com as ferramentas do NEXUS) → a voz escolhida; tudo na mesma janela |
| `core/llm_providers.py` | Os provedores (Claude nativo + todos os compatíveis com OpenAI), `limpar_pensamento` (<think>) e `orcamento_ferramentas` |
| `core/voz_propria.py` | Ouvido Whisper (com o idioma), vozes Piper / ElevenLabs / Edge / Windows, tocador com medidor e interrupção |
| `actions/agent_task.py` | Tarefas autônomas (modo agente) |
| `core/verificacao.py` | Status done / unverified / failed de toda função e o embrulho do conteúdo não confiável |
| `core/janelas.py` | Fechar app pelo nome, trazer para a frente, limites da plataforma (administrador, tela bloqueada, Wayland) |
| `core/volume_dispositivo.py` | Volume do alto-falante escolhido (janela de áudio) |

## Novidades da 2.0
| Arquivo | O que faz |
|---|---|
| `core/licenca.py` | A chave de licença: confere a assinatura (Ed25519, offline), validade e ID do computador; guarda em `config/licenca.json` |
| `ui/overlays/licenca.py` | A tela de ativação (ID do computador + campo da chave). `main_window.py` não deixa o NEXUS ligar sem licença válida |
| `core/wake_nexus.py` | Palavra de ativação "Nexus" / "Hey Nexus": corte de fala + Whisper tiny, só em trechos curtos |
| `core/wake_word.py` | (ampliado) escolhe o motor: "Nexus" (Whisper) ou "Hey Jarvis" (openWakeWord), com reserva |
| `actions/projetos.py` | "Meus projetos": registra projeto e próximo passo; o `proactive.py` pergunta do projeto parado |
| `ui/main_window.py` › `_show_content` | O painel de conteúdo mostra Markdown (títulos, listas, tabelas, links) no tema do NEXUS |

## Novidades da 2.1
| Arquivo | O que faz |
|---|---|
| `actions/dev_agent.py` | O agente de código: planeja, escreve, instala (num `.venv` do projeto), roda, confere e corrige. Ações: criar, alterar, listar, abrir, desfazer |
| `core/dev_projeto.py` | As conferências do agente, sem IA e sem rede: caminhos seguros, dependências, comando permitido, verificação de HTML/CSS/JS/JSON/Python, cópias de segurança |
| `actions/casa_inteligente.py` | Casa inteligente (Home Assistant e webhooks). Configuração em `config/casa.json` (não vai para o GitHub) |
| `actions/simple_finance.py` | Finanças: lançamentos, resumo, por categoria, orçamento com aviso |
| `actions/diagnostico.py` | Diagnóstico: lê `memory/audit.log` e confere a saúde do NEXUS |
| `core/audit.py` | O registro de ações agora guarda o tempo de cada uma e gira em 2 MB |
| `dashboard/server.py` | (reforçado) limite de tentativas no login, acesso que vence, cabeçalhos de segurança |
| `tests/` | Testes automáticos (`python -m pytest`) |
| `pyproject.toml` | Configuração do pytest e do ruff |

## Outras pastas
| Pasta | O que tem |
|---|---|
| `actions/` | Uma habilidade por arquivo (abrir app, e-mail, rotinas, foco…). Descobertas sozinhas ao iniciar |
| `plugins/` | Habilidades extras: solte um `.py` aqui |
| `core/` | Peças internas: HUDs, voz, palavra de ativação, rede neural (`intent_net.py` entende comandos; `neural_engine.py` é o motor NumPy da ferramenta `neural_core`; `keras_engine.py` / `keras_intent.py` são os motores Keras/TensorFlow opcionais; `neural_backend.py` escolhe entre eles), preferências |
| `memory/` | Seus dados (memória, rotinas, notas) e o número da versão |
| `config/` | Chaves e configurações (nunca publicar o `api_keys.json`) |
| `dashboard/` | Painel de controle pelo celular |

## Nexus.exe
| Arquivo | O que faz |
|---|---|
| `nexus_exe.py` | Ponto de partida do .exe: roda o `main.py` ao lado dele (e faz papel de python para scripts) |
| `nexus.spec` | Receita do PyInstaller: lê os imports do projeto e leva as bibliotecas certas |
| `gerar_exe.bat` | Dois cliques e o Nexus.exe aparece na pasta |

Lembretes ficam anotados em `memory/reminders.json` (para a central listar e cancelar);
o aviso em si é agendado no Agendador de Tarefas do Windows, como antes.

## Para criar uma habilidade nova
Crie `actions/minha_funcao.py` com um dicionário `TOOL` (nome, descrição,
parâmetros e a função). Ele aparece sozinho na próxima vez que o NEXUS abrir.
Veja `actions/focus_mode.py` como exemplo curto.

## Funções da 2.2
| Arquivo | O que faz |
|---|---|
| `core/armazem.py` | Guardar listas pessoais em JSON sem corromper (arquivo temporário + troca; estragado vira `.quebrado`) e achar item por número ou nome |
| `actions/compras.py` | Lista de compras com listas nomeadas — `memory/compras.json` |
| `actions/rastreador_habitos.py` | Hábitos diários, metas e sequências — `memory/habitos_diarios.json` |
| `actions/contatos.py` | Contatos e aniversários — `memory/contatos.json` |
| `actions/manutencao_pc.py` | Disco, limpeza de temporários (com CONFIRMAR), backup, rede, ping, bateria |
| `actions/texto_dev.py` | Ferramentas de texto e de programador, offline |
| `actions/diario.py` | Diário com humor — `memory/diario.json` |
| `tests/test_funcoes_22.py` | Testes de todas as anteriores |

## Funções da 2.3
| Arquivo | O que faz |
|---|---|
| `core/protecao.py` | Contém erros que fechavam o programa; grava `memory/falhas.log`, `queda_nativa.log`, marca de fechamento normal |
| `core/reconexoes.py` | Diário das quedas/renovações da conexão e as decisões puras de renovar/manter acordado |
| `core/embeddings.py`, `core/indice_semantico.py`, `actions/memoria_semantica.py` | Embeddings (hash embutido ou MiniLM ONNX) e busca por sentido |
| `core/roteador.py` | Segunda opinião (vizinhos) para a rede de intenções |
| `core/audio_feat.py`, `core/voz_id.py`, `core/wake_custom.py`, `actions/voz_treino.py` | Voz do dono e palavra "Nexus" treinada; captura guiada no callback do microfone |
| `core/cerebro_local.py`, `actions/cerebro_local.py` | Dados/Modelfile/LoRA para um modelo local no Ollama |
| `core/previsao_habitos.py`, `actions/previsao_habitos.py` | Rede que prevê hábitos por horário |
| `core/anomalia.py`, `actions/anomalia_pc.py` | Autoencoder do PC; vigia em `assistant/background.py` |
| `core/financas_ia.py`, `actions/financas_ia.py` | Categoria automática e previsão do mês |
| `core/visao_ia.py`, `actions/visao_ia.py` | Objetos (YOLOX) e rostos (YuNet+SFace) |
| `ui/hub_geom.py` | Geometria do visual Hub (sem Qt) |
| `tests/test_voz_23.py`, `tests/test_ia_23.py`, `tests/test_ia_23_memoria.py` | Testes da 2.3 |

## Como a IA funciona (Ultra 2026)
| Arquivo | O que faz |
|---|---|
| `core/ia_status.py` | O que é cada área e tipo de IA + o estado real dos módulos (só leitura) |
| `ui/overlays/ia_painel.py` | O painel: abas ÁREAS DA IA e TIPOS DE IA (botão dentro do Núcleo I.S.A.) |
| `actions/explicar_ia.py` | A voz: "o que é machine learning?", "que tipo de IA você é?", "como você aprende?" |

## Mais capaz dentro da ANI (3.2)
| Arquivo | O que faz |
|---|---|
| `core/autoavaliacao.py` | Mede cada pedido (rota, tempo, erro) e ajusta o roteador de modelos |
| `core/memoria_semanal.py` | Resumo semanal da sua rotina e antecipação de hábitos (só sugere) |
| `actions/memoria_semanal.py` | A voz: "o que você aprendeu sobre mim esta semana?" |
| `core/latencia.py` | Mede cada etapa do pedido (escutar, preparar, rota, modelo, ferramenta) |
| `core/cache_respostas.py` | Cache curto de clima e notícias |
| `core/conexao.py` | Modo offline: detecta queda e volta da internet |
| `core/rotinas_conversa.py` | Rotinas criadas por conversa, com prévia e confirmação |
| `core/perfis.py` | Perfis de uso: Trabalho, Estudo, Jogo e Normal |
| `core/busca_historico.py` | Busca em relatórios, anotações e diário, com período |
| `core/revisao_diaria.py` | Revisão do dia para ser falada |
| `core/privacidade.py` | O que fica no PC, o que sai e apagar com confirmação |
| `actions/perfil.py` | A voz dos perfis: "modo estudo" |
| `actions/buscar_historico.py` | A voz da busca: "o que anotei sobre o carro semana passada?" |
| `actions/revisao_diaria.py` | A voz: "como foi meu dia?" |
| `actions/privacidade.py` | A voz: "o que você guarda sobre mim?" |
| `ui/overlays/latencia_painel.py` | Painel ⏱ Latência |
| `ui/overlays/privacidade_painel.py` | Painel 🔒 Privacidade |
| `core/whatsapp_ligacao.py` | 3.4 — ligações de voz e vídeo pelo WhatsApp Desktop, conferidas na tela |
| `actions/ligar_whatsapp.py` | A voz: "liga pro Marcos no WhatsApp" (com CONFIRMAR) |
| `actions/bom_dia.py` | Rotina Bom dia: e-mail, clima e notícias num comando |
| `core/pesquisa_profunda.py` | Várias buscas em paralelo e um resumo com fontes |
| `actions/pesquisa_profunda.py` | A voz: "pesquisa a fundo sobre…" |
| `core/vigias.py` | Vigias de notícias e preços com alerta de mudança |
| `actions/vigiar.py` | A voz: "me avisa quando o preço do… cair" |
| `core/inicio_projeto.py` | Pasta, editor, documentação e tempo de um projeto |
| `actions/iniciar_projeto.py` | A voz: "inicia o projeto…" |
| `core/analise_trabalho.py` | Formatação, sugestões de conteúdo e tradução de trechos |
| `actions/analisar_trabalho.py` | A voz: "analisar trabalho" |
| `core/oraculo_bemestar.py` | Plano do dia e prevenção a partir dos seus dados (só no PC) |
| `actions/oraculo_bemestar.py` | A voz: "monta meu plano do dia" |
| `core/isa_preditiva.py` | I.S.A. preditiva: tendências, previsões e modo de desempenho automático |
| `core/autoregeneracao.py` | Auto-regeneração: cópias boas, disjuntor, limpeza e placar de remédios |
| `core/rede_colaborativa.py` | Troca do placar de reparos com outros NEXUS da rede (opcional, assinada) |
| `actions/orquestrador.py` | Equipe de agentes com revisor e uma rodada de "refaz isso" |
| `actions/agent_task.py` | Modo agente com conferência do resultado antes de terminar |


## 3.8.0 — arquivos novos
| Arquivo | O que faz |
|---|---|
| `core/missoes.py`, `actions/missao.py` | Missões de longa duração: plano, simulação, decisões, execução em segundo plano e retomada |
| `core/simulacao.py` | Simulação "e se": o efeito de cada passo antes de agir |
| `core/auditoria.py`, `actions/auditoria.py` | Registro com cadeia de hashes: por que o NEXUS fez cada coisa |
| `core/computer_use.py`, `actions/uso_computador.py` | Operar a tela em passos visíveis, com freios |
| `core/grafo.py`, `actions/grafo_conhecimento.py` | Memória em grafo com a fonte de cada ligação |
| `core/hibrido.py`, `actions/modelo_hibrido.py` | Roteador de modelo local/nuvem |
| `core/fabrica_plugins.py`, `actions/fabrica_plugins.py` | Plugins por conversa: revisão, caixa de areia, CONFIRMAR |
| `core/voz_emocao.py`, `actions/voz_natural.py` | Emoção/correção/interrupção na voz (opt-in) |
| `core/contexto_vivo.py`, `actions/contexto_vivo.py` | Avisos de contexto: reunião, anexo, erro (opt-in) |
| `core/rede_nexus.py`, `actions/rede_nexus.py` | Rede de NEXUS pareados, cifrada |


## 3.9.0 — arquivos novos
| Arquivo | O que faz |
|---|---|
| `core/aprovacoes.py`, `actions/aprovacoes.py` | Aprovações aprendidas (sugere, você aceita) |
| `core/missoes_recorrentes.py`, `actions/missao_recorrente.py` | Missões que se repetem |
| `core/copiloto.py` | Diagnóstico de erro na tela e oferta de correção |
| `core/viagem.py`, `actions/modo_viagem.py` | Pacote offline para viagem |
| `core/isa_modulos.py`, `core/isa_codigo.py`, `core/isa_arquitetura.py`, `core/isa_autonomia.py`, `actions/isa_nucleo.py` | Núcleo I.S.A.: módulos, código recente, arquitetura, autonomia |
| `core/conectores.py`, `actions/conectores.py` | Todoist, Trello, ntfy, Discord, IFTTT, Home Assistant |
| `core/aprendizado.py`, `actions/aprendizado.py` | Aprendizado da rotina (opt-in, local) |
| `core/estatisticas_pc.py`, `actions/estatisticas_pc.py` | Estatísticas do PC e sugestões |
| `core/organizador_inteligente.py`, `actions/organizador_inteligente.py` | Organizar qualquer pasta com regras suas |
| `core/reuniao.py`, `actions/reuniao.py` | Preparação para a próxima reunião |
| `core/revisao_texto.py`, `actions/revisao_texto.py` | Revisão de texto em português |
| `core/abrir_tudo.py`, `actions/abrir_tudo.py` | Abrir pasta, arquivo ou programa pelo nome |
| `core/modo_avancado.py`, `actions/modo_avancado.py` | Scripts seus em isolamento |


## 4.0.0 — arquivos novos
| Arquivo | O que faz |
|---|---|
| `core/imunidade.py`, `actions/imunidade.py` | Vacinas contra falhas conhecidas e relatório de bugs |
| `core/competicao.py` | Variantes competem; a melhor vence |
| `core/isa_modularizacao.py` | Plano para dividir módulos grandes |
| `core/desempenho_proativo.py`, `actions/desempenho_agora.py` | Avisos de programa pesado |
| `core/contexto_projeto.py`, `actions/contexto_projeto.py` | Andamento e contexto dos projetos |
| `core/historico_longo.py`, `actions/historico_longo.py` | Memória permanente e pesquisável |
| `core/equipe_agentes.py` | Quadro compartilhado e equipe paralela |
| `core/adaptacao.py`, `actions/adaptacao.py` | Adaptação contínua (opt-in) |
| `core/missoes_checkpoint.py` | 4.1 — checkpoints e rewind das missões (ações `checkpoints` / `rewind` em `actions/missao.py`) |
| `core/guardrails.py`, `actions/guardrails.py` | 4.1 — regras de entrada/saída das ferramentas (padrão + suas em `config/guardrails.json`) |
| `core/trace_local.py`, `actions/trace.py` | 4.1 — linha do tempo local (`memory/trace.jsonl`, `GET /api/trace`) |
