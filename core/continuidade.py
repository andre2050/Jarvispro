"""Continuidade quando o motor reinicia sozinho (4.6.0).

Se o motor do assistente cai por um erro inesperado, o main.py cria um NexusLive novo. Antes, o novo começava
vazio: a conversa do Gemini Live (o "handle" de retomada) e o registro do que foi dito (para o resumo do
dia seguinte) ficavam no objeto velho e se perdiam. Agora o novo herda os dois.

O handle continua só na memória (nunca em disco) e só dentro do mesmo programa aberto: abrir o NEXUS de novo
começa uma conversa nova, como sempre. Um handle vencido é descartado pelo próprio motor na primeira conexão
(assistant/session.py) e a conversa recomeça limpa.
"""
from __future__ import annotations


def herdar(velho, novo) -> dict:
    """Passa a conversa do motor que caiu para o novo. Devolve o que foi herdado (para log e teste)."""
    herdado = {"handle": False, "falas": 0}
    handle = getattr(velho, "_resume_handle", None)
    if handle:
        novo._resume_handle = handle
        herdado["handle"] = True
    log = getattr(velho, "_session_log", None)
    if isinstance(log, list) and log:
        novo._session_log = list(log)
        herdado["falas"] = len(log)
    return herdado
