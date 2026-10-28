"""Cadastro da sua voz e da palavra "Nexus" — NEXUS Ultra 2026 2.3.

Por voz:  "cadastra a minha voz"                      → owner_enroll (você fala ~8 frases)
          "testa se reconhece minha voz"              → owner_test
          "liga a trava de voz" / "desliga" / "rigor alto"
          "treina a palavra Nexus na minha voz"       → wake_train (diz "Nexus" 8x e depois fala à vontade)
          "como está o treino da minha voz?"          → owner_status / wake_status

Tudo é calculado no seu PC; o áudio do cadastro NÃO vai para o Gemini nem fica salvo (só os números
do modelo, em memory/voz_dono.npz e memory/wake_nexus.npz). A trava de voz é um reforço de
segurança, NÃO é biometria profissional: uma gravação da sua voz pode enganá-la.
"""
from __future__ import annotations

import time

from core import voz_id, wake_custom

FRASES_DONO = 8
CHAMADAS = 10
TEMPO_FRASE_S = 14
EXIGE_ACERTO_CHAMADA = 0.70
EXIGE_SEM_FALSO_ALARME = 0.95


def _log(player, msg: str) -> None:
    try:
        if player:
            player.write_log(f"SYS: {msg}")
    except Exception:
        pass


def _coletar(n: int, player, rotulo: str, min_s=1.0, max_s=8.0, silencio_s=0.6, tempo=TEMPO_FRASE_S):
    voz_id.captura.iniciar(min_s, max_s, silencio_s)
    trechos = []
    falhas = 0
    try:
        while len(trechos) < n and falhas < 3:
            t = voz_id.captura.esperar_trecho(tempo)
            if t is None:
                falhas += 1
                _log(player, f"🎙 Não ouvi nada ({rotulo}). Fale mais perto do microfone.")
                continue
            trechos.append(t)
            _log(player, f"🎙 {rotulo}: {len(trechos)}/{n}")
    finally:
        voz_id.captura.parar()
    return trechos


def _status_dono() -> str:
    if not voz_id.cadastrada():
        return "A sua voz ainda não foi cadastrada. Diga 'cadastra a minha voz'."
    r, c = voz_id.relatorio(), voz_id.config()
    return (f"Voz cadastrada em {r.get('treinado_em', '?')} com {r.get('amostras', '?')} frases. "
            f"Trava de voz: {'LIGADA' if c['trava'] else 'desligada'}, rigor {c['rigor']}. "
            f"No teste interno, reconhece você em {r.get('dono_aceito', 0):.0%} e recusa vozes diferentes "
            f"em {r.get('outras_recusadas', 0):.0%} (vozes sintéticas, não pessoas reais).")


def _status_wake() -> str:
    if not wake_custom.treinada():
        return "A palavra 'Nexus' ainda não foi treinada na sua voz. Diga 'treina a palavra Nexus'."
    r = wake_custom.relatorio()
    return (f"Treinada em {r.get('treinado_em', '?')} com {r.get('chamadas', '?')} chamadas. "
            f"No teste: acorda em {r.get('acerta_chamada', 0):.0%} das chamadas e evita "
            f"{r.get('evita_falso_alarme', 0):.0%} dos falsos alarmes. "
            "Para usar, escolha 'Nexus treinada na minha voz' em Configurações › Palavra de ativação.")


def voz_treino(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "owner_status").strip().lower()

    if acao in ("owner_status", "status"):
        return "[done] " + _status_dono() + " | " + _status_wake()

    if acao == "owner_enroll":
        _log(player, f"🎙 Cadastro da voz: diga {FRASES_DONO} frases normais, uma de cada vez (1 a 8 s).")
        trechos = _coletar(FRASES_DONO, player, "frase")
        if len(trechos) < voz_id.MIN_AMOSTRAS:
            return (f"[failed] Só ouvi {len(trechos)} frase(s) clara(s); preciso de pelo menos "
                    f"{voz_id.MIN_AMOSTRAS}. Tente num lugar mais silencioso, falando mais perto do microfone.")
        try:
            rel = voz_id.treinar(trechos, log=lambda *a: None)
        except ValueError as e:
            return f"[failed] {e}"
        return ("[done] Voz cadastrada. No teste interno: reconhece você em "
                f"{rel.get('dono_aceito', 0):.0%} e recusa vozes diferentes em {rel.get('outras_recusadas', 0):.0%}. "
                "A trava de voz continua DESLIGADA; diga 'liga a trava de voz' se quiser usá-la.")

    if acao == "owner_test":
        if not voz_id.cadastrada():
            return "[failed] Cadastre a sua voz primeiro ('cadastra a minha voz')."
        t = _coletar(1, player, "teste", tempo=12)
        if not t:
            return "[failed] Não ouvi você falar. Tente de novo."
        pr = voz_id.probabilidade(t[0])
        if pr is None:
            return "[failed] A fala foi curta demais para conferir. Fale uma frase inteira."
        precisa = voz_id.RIGOR[voz_id.config()["rigor"]]
        return (f"[done] Chance de ser a voz do dono: {pr:.0%} (a trava exige {precisa:.0%}). "
                + ("Passaria." if pr >= precisa else "Não passaria."))

    if acao == "gate":
        estado = str(p.get("state") or "").strip().lower()
        rigor = str(p.get("strictness") or "").strip().lower()
        kw = {}
        if estado in ("on", "ligar", "true", "1"):
            if not voz_id.cadastrada():
                return "[failed] Cadastre a sua voz antes de ligar a trava ('cadastra a minha voz')."
            kw["trava"] = True
        elif estado in ("off", "desligar", "false", "0"):
            kw["trava"] = False
        if rigor in voz_id.RIGOR:
            kw["rigor"] = rigor
        if not kw:
            return "[failed] Diga on/off e/ou o rigor: baixo, normal ou alto."
        c = voz_id.definir_config(**kw)
        return (f"[done] Trava de voz {'LIGADA' if c['trava'] else 'desligada'}, rigor {c['rigor']}. "
                "Ela só protege ações sensíveis (apagar, enviar, comprar, desligar…).")

    if acao == "owner_remove":
        return "[done] Cadastro da voz apagado." if voz_id.remover() else "Não havia cadastro de voz."

    if acao == "wake_status":
        return "[done] " + _status_wake()

    if acao == "wake_train":
        _log(player, f"🎙 Diga só \"Nexus\" {CHAMADAS} vezes, com uma pequena pausa entre elas.")
        pos = _coletar(CHAMADAS, player, "chamada", min_s=0.25, max_s=2.5, silencio_s=0.4, tempo=10)
        if len(pos) < wake_custom.MIN_POSITIVOS:
            return (f"[failed] Só ouvi {len(pos)} chamada(s) boas; preciso de {wake_custom.MIN_POSITIVOS}. "
                    "Diga 'Nexus' curto e claro, com pausa entre uma e outra.")
        _log(player, "🎙 Agora fale à vontade por ~25 segundos (qualquer assunto, SEM dizer Nexus).")
        neg = []
        fim = time.monotonic() + 25
        voz_id.captura.iniciar(0.4, 4.0, 0.5)
        try:
            while time.monotonic() < fim:
                t = voz_id.captura.esperar_trecho(max(0.5, fim - time.monotonic()))
                if t is not None and (not neg or t is not neg[-1]):
                    neg.append(t)
        finally:
            voz_id.captura.parar()
        try:
            rel = wake_custom.treinar(pos, neg, log=lambda *a: None)
        except ValueError as e:
            return f"[failed] {e}"
        ok = (rel["acerta_chamada"] >= EXIGE_ACERTO_CHAMADA
              and rel["evita_falso_alarme"] >= EXIGE_SEM_FALSO_ALARME)
        if not ok:
            wake_custom.remover()
            return (f"[failed] O treino ficou fraco (acorda em {rel['acerta_chamada']:.0%} das chamadas, evita "
                    f"{rel['evita_falso_alarme']:.0%} dos falsos alarmes) e NÃO foi guardado. Tente de novo num "
                    "lugar silencioso, dizendo 'Nexus' sempre do mesmo jeito. Enquanto isso, a palavra "
                    "'Nexus' normal continua funcionando.")
        return (f"[done] Palavra 'Nexus' treinada: acorda em {rel['acerta_chamada']:.0%} das chamadas e evita "
                f"{rel['evita_falso_alarme']:.0%} dos falsos alarmes. Para usar, escolha 'Nexus treinada na "
                "minha voz' em Configurações › Palavra de ativação e reabra o app.")

    if acao == "wake_remove":
        return "[done] Treino da palavra apagado." if wake_custom.remover() else "Não havia treino da palavra."

    return "Ação desconhecida. Use owner_enroll, owner_test, owner_status, gate, owner_remove, wake_train, wake_status ou wake_remove."


TOOL = {
    "name": "voz_treino",
    "description": (
        "Voice enrolment, entirely local. BEFORE calling owner_enroll, owner_test or wake_train, tell the "
        "user what to do (e.g. 'diga oito frases normais, uma de cada vez') because the call blocks while "
        "listening (up to ~2 minutes) and the mic is NOT sent to you meanwhile. action=owner_enroll "
        "('cadastra minha voz'); owner_test; owner_status; gate with state=on|off and/or strictness="
        "baixo|normal|alto (voice lock for sensitive actions; weaker than professional biometrics); "
        "owner_remove; wake_train ('treina a palavra Nexus'); wake_status; wake_remove."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "owner_enroll | owner_test | owner_status | gate | owner_remove | wake_train | wake_status | wake_remove"},
            "state": {"type": "STRING", "description": "For gate: on | off"},
            "strictness": {"type": "STRING", "description": "For gate: baixo | normal | alto"},
        },
        "required": ["action"],
    },
    "handler": voz_treino,
}
