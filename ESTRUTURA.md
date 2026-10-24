# Mapa do código do NEXUS

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
| `hud.py` | O desenho central e as barras de métricas. Seis visuais (`HUD_STYLE_INFO`): orbe, mínimo e, em 2026, aurora, líquido, holograma e globo neural |
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
