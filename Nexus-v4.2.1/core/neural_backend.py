"""Escolhe o motor da rede neural do NEXUS: Keras/TensorFlow ou o NumPy original.

    from core.neural_backend import engine as NE
    rede = NE.MLP([4, 16, 3], "relu")          # mesma API nos dois motores

O motor Keras (core/keras_engine.py) é usado quando o TensorFlow está instalado;
sem ele o NEXUS segue com o motor NumPy (core/neural_engine.py), exatamente como
antes. Os dois guardam os modelos no MESMO formato (JSON / .npz), então dá para
trocar de motor a qualquer momento sem perder o que a rede já aprendeu.

O TensorFlow só é importado na primeira vez que alguém usa `engine` (o import
leva alguns segundos), nunca na abertura do programa.

Escolha manual, pela variável de ambiente NEXUS_NEURAL_BACKEND:
    auto   (padrão) Keras se o TensorFlow estiver instalado, senão NumPy
    keras  tenta o Keras; se falhar, cai para o NumPy e avisa
    numpy  força o motor NumPy
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import threading

ENV = "NEXUS_NEURAL_BACKEND"
_lock = threading.RLock()
_estado: dict = {"modulo": None, "nome": None, "motivo": ""}


def preferencia() -> str:
    valor = os.environ.get(ENV, "auto").strip().lower()
    return valor if valor in ("auto", "keras", "numpy") else "auto"


def tf_instalado() -> bool:
    """O TensorFlow e o Keras estão instalados? (não importa nenhum dos dois)"""
    try:
        return (importlib.util.find_spec("tensorflow") is not None
                and importlib.util.find_spec("keras") is not None)
    except Exception:
        return False


def keras_provavel() -> bool:
    """Barato: o Keras VAI ser escolhido? Serve para decidir se vale carregar em segundo plano."""
    return preferencia() != "numpy" and tf_instalado()


def resolver():
    """Importa e devolve o módulo do motor escolhido (só na primeira chamada)."""
    with _lock:
        if _estado["modulo"] is not None:
            return _estado["modulo"]
        pref = preferencia()
        modulo, nome, motivo = None, None, ""
        if pref == "numpy":
            motivo = f"forçado por {ENV}=numpy"
        elif not tf_instalado():
            motivo = "TensorFlow não instalado"
        else:
            try:
                modulo = importlib.import_module("core.keras_engine")
                nome = "keras"
            except Exception as e:      # TF quebrado, DLL faltando no Windows, versão incompatível…
                motivo = f"TensorFlow indisponível ({type(e).__name__}: {e})"
        if modulo is None:
            modulo = importlib.import_module("core.neural_engine")
            nome = "numpy"
            if pref == "keras":
                print(f"[Neural] ⚠️ pediu o Keras, mas: {motivo}. Usando o motor NumPy.")
        _estado.update(modulo=modulo, nome=nome, motivo=motivo)
        return modulo


def nome() -> str:
    """'keras' ou 'numpy' — o motor em uso (resolve, se ainda não resolveu)."""
    resolver()
    return _estado["nome"]


def usar_keras() -> bool:
    return nome() == "keras"


def descricao() -> str:
    resolver()
    if _estado["nome"] == "keras":
        try:
            import keras
            import tensorflow as tf
            return f"Keras {keras.__version__} sobre TensorFlow {tf.__version__}"
        except Exception:
            return "Keras"
    return f"NumPy ({_estado['motivo']})" if _estado["motivo"] else "NumPy"


def aquecer() -> threading.Thread:
    """Importa o motor em segundo plano, para a primeira rede não esperar o import do TensorFlow."""
    def _run():
        try:
            resolver()
        except Exception as e:  # pragma: no cover
            print(f"[Neural] não deu para aquecer o motor: {e}")
    t = threading.Thread(target=_run, daemon=True, name="neural-warmup")
    t.start()
    return t


def forcar(escolha: str | None) -> None:
    """Para testes e para trocar de motor: 'keras' | 'numpy' | 'auto' | None (= auto)."""
    with _lock:
        os.environ[ENV] = (escolha or "auto")
        _estado.update(modulo=None, nome=None, motivo="")


class _Motor:
    """Proxy: `engine.X` vira `<motor escolhido>.X`, resolvendo o motor só no primeiro uso."""

    def __getattr__(self, atributo):
        return getattr(resolver(), atributo)

    def __repr__(self) -> str:
        return f"<motor neural: {_estado['nome'] or 'ainda não resolvido'}>"


engine = _Motor()
