"""Painel de fora de casa (3.6): túnel seguro e avisos no celular com o app fechado.

Por voz:  "abre o painel para fora de casa"   "fecha o túnel"   "o túnel está aberto?"
          "como estão os avisos no celular?"  "manda um aviso de teste pro celular"
Abrir o túnel pede CONFIRMAR e fecha sozinho em algumas horas. Detalhes: core/tunel.py e core/push_web.py."""
from __future__ import annotations

from core import confirm as _confirm
from core import push_web as _pw
from core import tunel as _tn


def _porta_e_https() -> tuple[int, bool]:
    from dashboard import server as S
    return S.PORT, S.DashboardServer._ssl_enabled()


def tunel_painel(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    t = _tn.tunel()
    try:
        if acao in ("open", "abrir"):
            if t.ativo():
                return f"O túnel já está aberto: {t.url} (fecha em {t.restante_min()} min)."
            if not _tn.achar_cloudflared():
                return ("[failed] Não achei o cloudflared. Instale (Windows: winget install Cloudflare.cloudflared) "
                        "e peça de novo.")
            try:
                horas = float(parameters.get("hours") or _tn.DURACAO_PADRAO_H)
            except (TypeError, ValueError):
                horas = _tn.DURACAO_PADRAO_H
            horas = max(0.5, min(horas, _tn.DURACAO_MAX_H))
            if _confirm.pending_title():
                return "Já há uma confirmação esperando na tela; resolva ela antes."

            def abrir() -> str:
                try:
                    porta, https = _porta_e_https()
                    url = t.iniciar(porta, https, horas)
                except Exception as e:
                    return f"[failed] {e}"
                return (f"[done] Túnel aberto: {url}. Entre pelo celular e use a chave de 6 dígitos do painel. "
                        f"Fecha sozinho em {int(horas)} h.")

            return _confirm.request(
                key="tunel_painel", title="ABRIR O PAINEL PARA A INTERNET",
                detail=(f"O painel do celular ficará acessível de fora de casa por um endereço temporário "
                        f"(https://….trycloudflare.com) por {horas:g} h. Continua exigindo a chave de 6 dígitos. "
                        f"Só confirme se foi você que pediu."), run=abrir)
        if acao in ("close", "fechar", "stop"):
            t.parar()
            return "[done] Túnel fechado. O painel voltou a ficar só na sua rede."
        if acao in ("push_test", "teste"):
            if not _pw.quantas():
                return "Nenhum celular ligou os avisos ainda. No painel do celular, toque no 🔔."
            r = _pw.enviar("NEXUS", "Aviso de teste: está funcionando.", ignorar_intervalo=True)
            return (f"[done] Aviso de teste enviado para {r['enviados']} celular(es)." if r["enviados"]
                    else f"[failed] Não consegui enviar: {r['motivo'] or 'o serviço de push recusou'}.")
        # status
        partes = [f"Túnel aberto: {t.url} (fecha em {t.restante_min()} min)." if t.ativo() else "Túnel fechado."]
        partes.append(f"Avisos com o app fechado: {_pw.quantas()} celular(es) ligado(s)"
                      + ("" if _pw.disponivel() else "; falta o pacote pywebpush (pip install pywebpush)") + ".")
        return " ".join(partes)
    except Exception as e:
        return f"[failed] Painel externo: {e}"


TOOL = {
    "name": "tunel_painel",
    "description": (
        "REMOTE PANEL OUTSIDE THE HOME NETWORK + PHONE PUSH: action=open (secure temporary https tunnel to the phone "
        "dashboard via cloudflared, needs on-screen CONFIRM, optional hours), action=close, action=status (tunnel + how "
        "many phones have push on), action=push_test (send a test notification to the phone). Use for 'abre o painel "
        "para fora de casa', 'fecha o túnel', 'manda um aviso de teste pro celular'."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "open | close | status | push_test"},
            "hours": {"type": "NUMBER", "description": "For open: how long to keep it open (default 4, max 12)"},
        },
        "required": ["action"],
    },
    "handler": tunel_painel,
}
