"""Guia do NEXUS (4.5.0): "o que você sabe fazer?" em português simples, por assunto.

Cada grupo traz uma frase do que ele faz e exemplos do que dizer. A lista de ferramentas de cada grupo é
conferida por teste contra as ações que existem de verdade, para o guia não ficar desatualizado.
"""
from __future__ import annotations

import re
import unicodedata

GRUPOS: dict[str, dict] = {
    "computador": {
        "titulo": "Controlar o computador", "ferramentas": ("printer_control", "open_app", "open_anything", "computer_control", "computer_settings", "desktop_control", "file_controller", "organize_folder", "pc_stats", "performance_now", "manutencao_pc"),
        "resumo": "Abre programas, mexe em volume, brilho, janelas e arquivos, e cuida da manutenção do PC.",
        "exemplos": ["imprime este arquivo", "abre o Chrome", "aumenta o volume", "organiza a área de trabalho", "como está o desempenho do PC?"]},
    "internet": {
        "titulo": "Internet e pesquisa", "ferramentas": ("web_search", "browser_control", "pesquisa_profunda", "noticias", "weather_report", "mapas", "flight_finder", "price_alert", "youtube_video"),
        "resumo": "Pesquisa, lê notícias, vê o tempo, acha rotas, voos e preços.",
        "exemplos": ["pesquisa o preço do dólar", "como vai estar o tempo amanhã?", "me avisa quando o produto baixar de preço"]},
    "agenda": {
        "titulo": "Agenda, lembretes e rotina", "ferramentas": ("reminder", "timer_action", "agenda_google", "daily_planner", "morning_briefing", "resumo_diario", "tarefas", "kanban_board", "focus_mode", "routines", "meeting_prep", "revisao_diaria"),
        "resumo": "Lembretes, cronômetros, agenda, plano do dia, foco e rotinas.",
        "exemplos": ["cria o quadro Casa", "me lembra às 15h de ligar para o João", "me dá 25 minutos de foco", "resumo do meu dia"]},
    "mensagens": {
        "titulo": "Mensagens e e-mail", "ferramentas": ("email_reader", "email_checker", "send_message", "ligar_whatsapp", "telegram_nexus", "contatos"),
        "resumo": "Lê e-mails em voz alta, manda mensagens e liga para contatos.",
        "exemplos": ["tem e-mail novo?", "manda mensagem para a Ana", "aniversários desta semana"]},
    "memoria": {
        "titulo": "Memória e anotações", "ferramentas": ("save_memory", "recall_memory", "memory_bank", "quick_notes", "notepad", "diario", "conversation_threads", "buscar_historico", "memoria_semantica", "knowledge_graph", "compras"),
        "resumo": "Lembra de você entre conversas, guarda notas, diário e listas de compras e busca em documentos.",
        "exemplos": ["anota que a reunião mudou", "o que eu falei sobre o contrato?", "põe leite na lista de compras"]},
    "criar": {
        "titulo": "Criar e programar", "ferramentas": ("forge_app", "dev_agent", "code_helper", "agent_task", "iniciar_projeto", "plugin_factory", "advanced_mode"),
        "resumo": "Cria aplicativos, escreve e roda código e executa tarefas de vários passos sozinho.",
        "exemplos": ["vamos criar um aplicativo do zero", "escreve um script que renomeia meus arquivos"]},
    "midia": {
        "titulo": "Música, vídeo e tela", "ferramentas": ("music_control", "video_player", "screen_process", "computer_vision", "local_vision", "visao_ia", "close_camera"),
        "resumo": "Toca música e vídeos, olha a tela e a câmera quando você pede.",
        "exemplos": ["toca uma música calma", "o que está na minha tela?"]},
    "financas": {
        "titulo": "Dinheiro e saúde", "ferramentas": ("simple_finance", "financas_ia", "rastreador_habitos", "oraculo_bemestar", "previsao_habitos", "unit_converter"),
        "resumo": "Controle de gastos simples, hábitos, bem-estar e conversão de unidades.",
        "exemplos": ["gastei 40 no mercado", "converte 5 milhas para km"]},
    "estudo": {
        "titulo": "Estudar", "ferramentas": ("study",),
        "resumo": "Cartões com repetição espaçada, quiz de múltipla escolha e acompanhamento do que você já domina.",
        "exemplos": ["cria um cartão: capital da França :: Paris", "o que devo revisar hoje?", "me faz um quiz de 5 perguntas"]},
    "nexus": {
        "titulo": "Cuidar do próprio NEXUS", "ferramentas": ("diagnostico", "system_status", "tool_load", "manage_actions", "nexus_guide", "system_update", "guardrails", "privacidade", "auditoria", "approvals", "trace", "immunity", "loja_plugins"),
        "resumo": "Diagnóstico, atualização, privacidade, auditoria e o perfil de ferramentas.",
        "exemplos": ["o NEXUS está saudável?", "o que deu errado hoje?", "usa o perfil essencial de ferramentas"]},
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def escolher(tema: str) -> list[str]:
    """Quais grupos casam com o assunto dito (vazio = todos)."""
    palavras = {w for w in _norm(tema).split() if len(w) > 2}
    if not palavras:
        return list(GRUPOS)
    achados = []
    for chave, g in GRUPOS.items():
        alvo = set(_norm(" ".join([chave, g["titulo"], g["resumo"], " ".join(g["exemplos"]), " ".join(g["ferramentas"]).replace("_", " ")])).split())
        if any(w in alvo or any(a.startswith(w[:5]) for a in alvo if len(w) > 4) for w in palavras):
            achados.append(chave)
    return achados


def texto(tema: str = "", disponiveis=None) -> str:
    """O guia falado. `disponiveis` (nomes das ferramentas que existem agora) filtra o que não está carregado."""
    chaves = escolher(tema)
    if not chaves:
        return "Não achei esse assunto. Posso falar de: " + ", ".join(g["titulo"].lower() for g in GRUPOS.values()) + "."
    linhas = []
    for c in chaves:
        g = GRUPOS[c]
        if disponiveis is not None and not any(f in disponiveis for f in g["ferramentas"]):
            continue
        ex = "; ".join(f"“{e}”" for e in g["exemplos"][:3])
        linhas.append(f"{g['titulo']}: {g['resumo']} Por exemplo: {ex}.")
    return "\n".join(linhas) or "Nenhuma dessas funções está ativa agora."
