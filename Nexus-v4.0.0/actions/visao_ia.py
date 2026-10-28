"""Visão com IA no PC — NEXUS Ultra 2026 2.3. Objetos (YOLOX) e rostos (YuNet+SFace), sem enviar imagem a ninguém.

Por voz: "instala a visão de rostos"   "o que tem na minha frente?" (câmera)   "quantas pessoas tem na sala?"
         "quem está na câmera?"   "cadastra o rosto da Ana"   "esquece o rosto da Ana"   "quais rostos você conhece?"
Veja core/visao_ia.py. Reconhecimento facial erra e nunca autoriza nenhuma ação.
"""
from __future__ import annotations

import time

from core import visao_ia as V


def _imagem(p: dict):
    from core import visao_local as VL
    origem = str(p.get("source") or "camera")
    img, nome = VL.capturar(origem, str(p.get("path") or ""))
    return V.para_bgr(img), nome


def _frases_rostos(rs: list[dict]) -> str:
    if not rs:
        return "não vi nenhum rosto"
    partes = []
    for r in rs:
        partes.append(r["nome"] if r["nome"] else "alguém que eu não conheço")
    return ", ".join(partes)


def visao_ia(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "objects").strip().lower()
    try:
        if acao in ("install", "instalar"):
            quais = ["yunet", "sface"] if str(p.get("what") or "").lower() in ("faces", "rostos") else \
                    ["yolox"] if str(p.get("what") or "").lower() in ("objects", "objetos") else ["yunet", "sface", "yolox"]
            msgs = []
            for m in quais:
                ok, msg = V.baixar(m, log=lambda t: player and player.write_log(f"SYS: {t}"))
                msgs.append(f"{m}: {msg}")
                if not ok:
                    return "[failed] " + "; ".join(msgs)
            return "[done] Visão instalada (" + "; ".join(msgs) + ")."
        if acao == "status":
            s = V.situacao()
            return ("[done] Rostos: " + ("pronto" if s["yunet"] and s["sface"] else "não instalado") +
                    ". Objetos: " + ("pronto" if s["yolox"] else "não instalado") +
                    f". Rostos cadastrados: {', '.join(V.cadastrados()) or 'nenhum'}.")
        if acao in ("list", "listar"):
            c = V.cadastrados()
            return "[done] Rostos que conheço: " + (", ".join(f"{n} ({q} foto-números)" for n, q in c.items()) or "nenhum") + "."
        if acao in ("forget", "esquecer"):
            nome = str(p.get("name") or "").strip()
            if not nome:
                return "Diga de quem é o rosto a esquecer."
            return f"[done] Esqueci o rosto de {nome}." if V.esquecer(nome) else f"Não conheço ninguém chamado {nome}."
        if acao in ("enroll", "cadastrar"):
            nome = str(p.get("name") or "").strip()
            if not nome:
                return "[failed] Diga o nome da pessoa."
            if not (V.instalado("yunet") and V.instalado("sface")):
                return "[failed] Instale a visão de rostos primeiro (action=install, what=faces)."
            from core import confirm
            if confirm.pending_title():
                return "[failed] Já existe uma confirmação na tela. Peça ao usuário para responder a ela primeiro."

            def _fazer() -> str:
                imgs = []
                for _ in range(4):
                    try:
                        imgs.append(_imagem(p)[0])
                    except Exception:
                        pass
                    time.sleep(0.7)
                n = V.cadastrar(nome, imgs)
                if not n:
                    return f"Não vi o rosto de {nome} com clareza. Peça para olhar para a câmera, com boa luz."
                return f"Cadastrei o rosto de {nome} ({n} capturas). A foto não foi guardada, só números."
            return confirm.request(
                f"face-{nome.lower()}", f"Cadastrar o rosto de {nome}",
                "O NEXUS vai olhar pela câmera e guardar neste PC apenas os números (não a foto) do rosto, para "
                "reconhecer essa pessoa. Faça isso só com quem concordou.", _fazer)
        if acao in ("recognize", "reconhecer", "who"):
            bgr, onde = _imagem(p)
            rs = V.reconhecer(bgr)
            return f"[done] Na {onde}: {_frases_rostos(rs)}." + \
                ("" if V.cadastrados() else " (Ainda não conheço nenhum rosto cadastrado.)")
        if acao in ("people", "count", "pessoas"):
            bgr, onde = _imagem(p)
            rostos = len(V.detectar_rostos(bgr))
            if V.instalado("yolox"):
                pessoas = sum(1 for o in V.detectar_objetos(bgr) if o["classe"] == "pessoa")
                return f"[done] Na {onde}: {pessoas} pessoa(s) e {rostos} rosto(s) visível(is)."
            return f"[done] Na {onde}: {rostos} rosto(s) visível(is)."
        if acao in ("objects", "objetos", "see"):
            bgr, onde = _imagem(p)
            return f"[done] Na {onde}: {V.resumo_objetos(V.detectar_objetos(bgr))}."
    except V.VisaoIndisponivel as e:
        return f"[failed] {e}"
    except Exception as e:
        try:
            from core import visao_local as VL
            if isinstance(e, VL.VisaoIndisponivel):
                return f"[failed] {e}"
        except Exception:
            pass
        return f"[failed] A visão falhou: {e}"
    return "Ação desconhecida. Use install, status, objects, people, recognize, enroll, forget ou list."


TOOL = {
    "name": "visao_ia",
    "description": (
        "On-device vision with neural nets; no image leaves the PC. source=camera (default) | tela | arquivo "
        "(+ path). action=objects ('o que tem na minha frente?'), people (count people and faces), recognize "
        "('quem está na câmera?'), enroll with name (asks the user to CONFIRM on screen; only people who "
        "agreed; stores numbers, not photos), forget with name, list, status, install (+ what=faces|objects, "
        "downloads the models once). Face recognition can be wrong and never authorizes anything."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "objects | people | recognize | enroll | forget | list | status | install"},
        "source": {"type": "STRING", "description": "camera | tela | arquivo"},
        "path": {"type": "STRING", "description": "For source=arquivo: image path"},
        "name": {"type": "STRING", "description": "For enroll/forget: the person's name"},
        "what": {"type": "STRING", "description": "For install: faces | objects (default both)"}},
        "required": ["action"]},
    "handler": visao_ia,
}
