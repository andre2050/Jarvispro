# ✦ NEXUS Ultra 2026
### Assistente pessoal de voz para o seu computador — desenvolvido por André Luiz Lima Menezes

Versão 4.1.1 — interface 2026

NEXUS ouve, vê, fala e controla o computador em tempo real. Ele conversa por voz
(Gemini Live), lembra de você entre uma conversa e outra, abre seus programas,
lê seus e-mails, cuida do seu foco e aprende com o seu jeito de usar.

> Desenvolvido por **André Luiz Lima Menezes**. Baseado em MARK LV — JARVIS (© FatihMakes, CC BY-NC 4.0): veja `LICENSE` e `NOTICE.md` — uso não comercial.

---

## O que ele faz

| Área | Funções |
|---|---|
| Documentos | (3.5) "Indexa a pasta Contratos", "o que o contrato diz sobre multa?": lê PDF, Word, PowerPoint, texto e código só das pastas que você escolher e responde **citando a fonte** (arquivo e página) |
| Loja de plugins | (3.5) Pacotes `.nexusplugin` assinados, com permissões conferidas no código; instalar pede CONFIRMAR |
| Integrações | (3.5) Telegram (só o seu chat), Google Calendar por link iCal (só leitura) e Notion (criar e buscar) |
| App no celular | (3.5) O painel do celular instala na tela inicial (PWA), tem tela offline e avisos |
| OCR | (3.7) Fotos de recibos e PDFs escaneados na memória de documentos (Tesseract local) |
| Resumo do dia | (3.7) Agenda, e-mails importantes e tarefas num pedido só |
| Presença e ambientes | (3.7) Acorda quando você chega; Casa/Trabalho/Estudo/Jogo trocam cor, hub e avisos |
| Missões | (3.8) Metas de horas em segundo plano, com simulação, aprovação no celular e desfazer |
| Especialistas e auditoria | (3.8) Agentes por área com permissões próprias; registro verificável de cada decisão |
| Computer-use | (3.8) Vê a tela e opera mouse/teclado em passos visíveis, com CONFIRMAR e freios |
| Grafo, modelo híbrido, fábrica de plugins | (3.8) Memória ligada com fontes; roteador local/nuvem; plugins por conversa testados em caixa de areia |
| Missões 4.1 | (4.1) Checkpoints e rewind, guardrails de entrada/saída editáveis, trace local |
| Núcleo I.S.A. 4.0 | (4.0) Imunidade a falhas, módulos competitivos, desempenho proativo, histórico longo, quadro de agentes, adaptação contínua |
| Missões 3.9 | (3.9) Ensaio, orçamento, aprovações aprendidas, recorrentes, painel de auditoria |
| Núcleo I.S.A. 3.9 | (3.9) Módulos com saúde, análise de código, arquitetura, autonomia |
| Conectores e utilitários | (3.9) Todoist/Trello/Home Assistant…, estatísticas do PC, organizador de pastas, reunião, revisão de texto, abrir tudo, modo avançado |
| Voz natural, contexto vivo, rede de NEXUS | (3.8) Opt-in: emoção na voz, avisos de contexto; aparelhos pareados e cifrados |
| Backup | (3.7) Backup criptografado automático para a pasta da sua nuvem; rotinas na loja |
| MCP | (3.6) Ferramentas da comunidade via servidores MCP, com CONFIRMAR no que altera algo |
| Fora de casa | (3.6) Avisos no celular com o app fechado e túnel https sob pedido |
| E-mails | (3.6) E-mails na memória de documentos (opt-in, só no PC), com fonte |
| Hub | (3.6) 20 visuais novos e menu organizado |
| Tema automático | (3.5) A cor da interface acompanha a hora do dia e o seu humor do diário |
| Visual do hub | (Ultra 2026) 19 visuais para escolher no botão VISUAL DO HUB — orbe, aurora, holograma, globo, Matrix e os dez novos: Nebulosa, Giroscópio, Hélice, Sonar, Espectro, Colmeia, Átomo, Plasma, Constelação e Túnel |
| Conversa | Voz em tempo real, em português; histórico longo; responde por texto também |
| Memória | Lembra fatos sobre você, das últimas conversas e do que ficou em aberto ("fios de conversa") |
| Rotinas | "modo trabalho" abre vários apps de uma vez; você cria as suas por voz |
| E-mail | Lê em voz alta os e-mails novos (Gmail com senha de app) |
| Foco | "me dá 25 minutos de foco" — silencia os avisos e sugere a pausa no fim |
| Computador | Abre apps, volume, brilho, janelas, arquivos, navegador. "Organiza a área de trabalho" guarda os arquivos soltos em pastas por tipo (e "desfaz a organização" volta tudo) |
| Visão | Olha a tela e a câmera quando você pede. No painel 👁 Visão, sem internet: QR na tela e na câmera, contar rostos, analisar a tela e vigia de movimento (com aviso, som e foto) |
| Rede neural local | Comandos simples digitados rodam na hora, sem internet, e ela aprende com você |
| Celular | Painel de controle remoto pelo celular (QR code) |
| Plugins | Solte um arquivo `.py` na pasta `plugins/` e ele ganha uma função nova |
| Atualização | Botão ⬆ ATUALIZAR: confere o GitHub, mostra o que mudou e instala com um clique (1.4.1) |
| Notas e lembretes | Central própria (Ctrl+N): criar, procurar, editar, copiar e cancelar |
| Barra rápida | Os botões que você mais usa, na ordem que quiser, e comandos rápidos (Alt+1…9) |
| Atalhos | Todas as teclas de atalho personalizáveis (Configurações › ATALHOS) |
| Núcleo I.S.A. | O centro de decisões ao vivo (Ctrl+I): cognição, automação e cada passo — o que chegou, quem decidiu, o que foi feito e quanto tempo levou. Visual de cérebro + engrenagens no HUD |
| Bloco de Notas e ditado | (1.4) "Abre o bloco de notas e escreve o que eu falar": ele escreve sozinho tudo o que você fala (🎙 Ditado ou Ctrl+D). Também escreve, acrescenta, lê e salva textos |
| Visão local | (1.4) Lê o texto da tela, da janela ou da câmera e descreve imagens **sem internet** — nada sai do PC |
| Motor de voz | (1.5) Gemini Live **ou** o seu próprio: Whisper (ouve no PC) + Claude, Gemini, OpenAI, Groq, DeepSeek, Mistral, xAI, OpenRouter, Ollama, LM Studio, llama.cpp ou vLLM + voz Piper (offline), ElevenLabs, Edge ou Windows. A voz segue o seu idioma. Tudo offline com Ollama + Piper |
| Tarefas autônomas | (1.5) Modo agente: objetivos de vários passos — ele planeja, executa, confere e avisa no fim |
| Licença | Chave de licença assinada, offline, com validade e travamento por computador opcionais |
| Projetos | "Registra o projeto…": os check-ins espontâneos perguntam do projeto parado e do próximo passo |
| Voz masculina | (2.0) Gemini (Charon), Edge (Antonio), Kokoro e Piper em voz masculina por padrão; trocável em ⚙ |
| Produtividade | (2.0) Painel Ctrl+P: tarefas com prazo e prioridade, lembretes, plano do dia, foco — "adiciona a tarefa…", "o que tenho pra hoje?" |
| Assistente completo | (2.0) Clima falado (Open-Meteo), notícias, mapas e rotas, cotações (ações e cripto), e-mail com **enviar e responder** só depois de você apertar CONFIRMAR |
| Visual | (2.0) Interface nova (vidro, brilho, animação suave), HUD único que reduz o uso de CPU quando parado |
| Programar sozinho | (2.1) "Cria um site de portfólio", "faz um jogo da cobrinha", "altera o botão para azul": o agente planeja, escreve os arquivos, instala o que precisa num ambiente separado (`.venv` do projeto), roda, confere no navegador e corrige. Tudo em `Área de Trabalho\NexusProjects`; "desfaz" volta a última alteração. Tem interruptor em ⚙ › ATUADOR |
| Casa inteligente | (2.1) Luz, tomada, cortina, ar-condicionado, cenas e fechadura pelo seu **Home Assistant** (ou webhooks). Destrancar, abrir portão e rodar scripts pedem CONFIRMAR na tela. Veja `actions/casa_inteligente.py` |
| Finanças | (2.1) Gastos e receitas com data, resumo por período, por categoria, limite mensal com aviso aos 80% e ao estourar, comparação com o mês passado. Só no seu PC |
| Diagnóstico | (2.1) "O que deu errado hoje?", "o que está lento?", "o NEXUS está saudável?": lê o registro de ações e confere chaves, permissões, disco e pacotes — sem mostrar chaves |
| Compras | (2.2) "Põe leite, pão e 2 ovos na lista de compras", "o que falta comprar?", "comprei o pão": listas com nome (mercado, farmácia…), quantidade e itens repetidos somados |
| Hábitos | (2.2) "Cria o hábito beber água, meta 8 copos", "bebi 2 copos": progresso do dia e sequência de dias seguidos; o briefing da manhã lembra dos que faltam |
| Contatos | (2.2) Telefone, e-mail e aniversário de quem importa; "quem faz aniversário essa semana?" (com a idade). O briefing avisa os aniversários de hoje |
| Manutenção do PC | (2.2) Espaço em disco, o que está ocupando espaço, limpeza de temporários (só depois do seu CONFIRMAR), backup de pasta em .zip conferido, IP, teste de conexão e bateria |
| Texto e dev | (2.2) Conta palavras, maiúsculas/snake/camel, hash, base64, URL, JSON, UUID, timestamp e slug — offline |
| Diário | (2.2) "Escreve no diário…", "humor 4", "o que escrevi ontem?", média e tendência do humor. Só no seu PC |
| Memória semântica | (2.3) "O que anotei sobre viagem?": busca por sentido em notas, diário, tarefas e contatos |
| Voz e palavra Nexus | (2.3) "Cadastra a minha voz", "treina a palavra Nexus": trava de voz opcional e chamada treinada na sua voz |
| Cérebro local | (2.3) Prepara um modelo pequeno no Ollama que entende comandos simples sem internet |
| Previsão e anomalias | (2.3) "O que eu costumo fazer agora?", "meu PC está estranho?" — redes neurais locais |
| Finanças inteligentes | (2.3) Categoria automática do gasto e "quanto vou fechar o mês gastando?" |
| Visão com IA | (2.3) "O que tem na minha frente?", "quantas pessoas?", "quem está na câmera?" (rostos só os que você cadastrar) |
| Honestidade | (1.5) Cada função diz se fez e conferiu, se não deu para conferir ou se falhou; conteúdo de fora (web, arquivos, tela) nunca dá ordens |

## Instalação

1. Python 3.11 ou mais novo.
2. Na pasta do NEXUS: `python setup.py` (instala as dependências).
3. `python main.py` — na primeira vez ele pede a chave do Gemini
   (gratuita em https://aistudio.google.com/apikey).

### Nexus.exe (Windows)

Depois de instalar, dê dois cliques em `gerar_exe.bat`. Em alguns minutos ele cria o
`Nexus.exe` (e a pasta `_internal`) dentro da pasta do NEXUS. A partir daí é só abrir o
Nexus.exe — nem precisa do terminal. O código continua nos arquivos `.py`, então plugins
e atualizações funcionam sem gerar o .exe de novo; gere de novo só se instalar uma
biblioteca nova.

Opcional:
- `python configurar_email.py` — leitura automática de e-mails.
- `python configurar_github.py` — auto-update pelo seu repositório.

## Novidades da 1.4

### Modo ditado no Bloco de Notas
Diga **"Nexus, abre o bloco de notas e escreve o que eu falar"** (ou clique em 🎙 Ditado,
ou Ctrl+D). Ele abre um Bloco de Notas novo e escreve tudo o que você fala, sem mexer
no teclado — dá para usar outro programa enquanto isso. Durante o ditado:

| Você fala | Entra no texto |
|---|---|
| "vírgula", "ponto final", "dois pontos", "ponto de interrogação" | , . : ? |
| "nova linha" / "novo parágrafo" | quebra de linha / linha em branco |
| "abre aspas" … "fecha aspas", "travessão" | “ ” — |
| "apaga a última frase" | desfaz o último trecho |
| **"parar ditado"** | termina e salva |

Enquanto dita, o NEXUS fica em silêncio e não executa comandos (se você falar "abre o
Chrome", isso vira texto). Uma cópia fica em `Documentos\NEXUS Notas\Ditados`.
Também por voz: "escreve no bloco de notas uma lista de compras", "lê o que está no bloco
de notas", "salva o bloco de notas como receita".

### Visão local (offline)
"Copia o texto dessa janela", "lê o texto da minha tela", "passa o texto da tela pro bloco
de notas", "descreve minha tela sem mandar pra nuvem". Também no painel 👁 Visão.
- **Ler texto**: usa o OCR que já vem no Windows (entende acentos). Em outros sistemas,
  o RapidOCR (já está no `requirements.txt`).
- **Descrever imagens**: precisa do [Ollama](https://ollama.com) instalado e de um modelo
  de visão: `ollama pull gemma3:4b` (ou `moondream`, mais leve). O NEXUS acha sozinho.
- **Modo privado** (Configurações › VISÃO LOCAL): quando você pede "o que tem na minha
  tela?", a imagem não vai para a nuvem — o Gemini recebe só o que foi visto no PC.

### Respostas mais rápidas
Pedidos com várias coisas ("abre o Spotify e o Chrome") rodam juntos; programas da
Microsoft Store (WhatsApp, Spotify…) abrem direto; o tempo de resposta aparece no painel
I.S.A. (Ctrl+I). Em Configurações › VELOCIDADE DA RESPOSTA há o modo **Rápido**.

### Organizar a área de trabalho (1.4.2)
"Nexus, **organiza a área de trabalho**" — os arquivos soltos vão para pastas ali mesmo:
Imagens, Documentos, Planilhas, Apresentações, Vídeos, Músicas, Compactados, Instaladores,
Código e Outros. Atalhos, pastas, arquivos ocultos e o que está sendo baixado ou está aberto
ficam onde estão; nome repetido vira "foto (2).jpg"; nada é apagado. "Organiza por data"
separa por mês. "**Desfaz a organização**" põe tudo de volta (até depois de reiniciar).
Também pelo botão 🗂 Organizar (adicione em ＋ Personalizar, na barra rápida).

### Visão corrigida (1.4.2)
No painel 👁 Visão: **QR na tela** (lê todos os monitores; o NEXUS sai da frente por um
instante), **QR na câmera**, **contar rostos**, **analisar a tela** (brilho, nitidez e cores),
**vigiar movimento** com sensibilidade de 1 a 10 — avisa na conversa, com notificação, som e
uma foto em `Imagens\NEXUS Vigia` — e **parar de vigiar**. O painel mostra a imagem que foi
analisada, com as marcações, e o texto para copiar ou abrir o link.

### Atualizar pelo GitHub (1.4.1)
Clique em **⬆ ATUALIZAR** (menu ⚙ SETUP ou Configurações › Atualizar sistema), ou diga
"atualiza o Nexus". Ele confere o repositório do `config/update.json`
(preencha `github_repo` quando publicar o projeto), mostra a versão nova e o que mudou e, com um clique, baixa e
instala. Chaves, memória, notas e configurações ficam como estão; cada arquivo trocado
vai antes para `backups/` ("Desfazer a última" volta tudo). No fim: **REINICIAR AGORA**.
Se a versão nova pede bibliotecas novas, ele avisa (e instala, quando roda pelo Python).

**Para publicar uma versão nova:** mude o número em `memory/version.json` (o
`python preparar_publicacao.py` faz isso e confere que não vai nenhuma senha) e envie para
o GitHub (git push ou GitHub Desktop). Quem clicar em ATUALIZAR recebe. Se você criar uma
*Release* com o .zip, ela tem prioridade sobre a branch.

## Palavra de ativação

O NEXUS acorda com **"Nexus"**, **"Hey Nexus"** ou **"Ei Nexus"**, offline:
um corte de fala por energia separa os trechos curtos e só eles vão para o Whisper
*tiny* (≈75 MB, baixado uma vez; o pacote `faster-whisper` já está no `requirements.txt`).
Conversa longa, TV e música nunca chegam ao Whisper. Ligue em ⚙ → PALAVRA DE ATIVAÇÃO.

Em Configurações › Áudio › *Palavra de ativação* dá para escolher entre Automática
(Nexus se estiver instalado, senão Hey Jarvis), só "Nexus" ou só "Hey Jarvis"
(modelo pronto do openWakeWord). O botão de falar e **Ctrl+Espaço** (segurar para
falar) continuam funcionando. Em sala barulhenta, ajuste a sensibilidade.

## Chave de licença

Na primeira abertura o NEXUS pede a chave (`NEXUS-XXXXX-…`). A tela mostra o **ID deste
computador**, para licenças presas a um PC. A conferência é offline, por assinatura digital
(Ed25519): o NEXUS só carrega a chave *pública*, que confere mas não cria licenças.

Quem gera as chaves é o desenvolvedor, com `gerar_chave.py` e a `chave_privada_nexus.pem`
da pasta **Ferramentas do desenvolvedor** — que fica FORA da pasta do NEXUS e nunca vai para
o GitHub. Exemplos: `python gerar_chave.py --nome "Maria" --dias 30 --maquina 3FA9-12BC-77D0`.
Cada chave emitida é anotada em `chaves_emitidas.csv`.

Se o NEXUS não abrir: dê dois cliques em **Abrir NEXUS (mostra erros).bat** — a janela de texto
fica aberta e mostra o motivo. Qualquer erro ao abrir também é gravado em `erro_ao_abrir.txt`.
A licença é conferida mesmo sem o pacote `cryptography` (verificador em Python puro) e a chave
pode ser colada com texto em volta (ex.: o conteúdo inteiro do `minha_chave.txt`).

Limite honesto: como o NEXUS é Python, quem sabe programar consegue remover a verificação.
A licença impede o uso casual e o compartilhamento de chaves; para mais proteção, distribua só
o `Nexus.exe`. E lembre: leia o arquivo LICENSE antes de cobrar pelo NEXUS.

## Organização do código

Veja `ESTRUTURA.md`: o cérebro fica em `assistant/`, a janela em `ui/` e cada
habilidade é um arquivo em `actions/`.

## Seus dados

Chaves, senhas, memórias, notas, rotinas e as frases que a rede neural aprendeu
ficam só no seu computador (`config/api_keys.json` e a pasta `memory/`).
Para publicar o projeto sem esses dados, use `python preparar_publicacao.py`.


## Para quem desenvolve (2.1)

* `python -m pytest` roda mais de 300 testes automáticos (pasta `tests/`), sem tela, sem microfone e sem internet.
  Os testes do agente de código usam uma IA de mentira; os da casa inteligente, um Home Assistant de mentira.
* `ruff check .` procura erros de verdade (configurado em `pyproject.toml`).
* Antes de publicar no GitHub, rode `python preparar_publicacao.py`: ele faz uma cópia sem chaves, finanças,
  tarefas, casa e memórias, e procura sinais de segredo na cópia.
