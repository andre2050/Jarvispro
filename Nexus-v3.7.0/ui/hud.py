"""O HUD central do NEXUS: o "orbe" reativo ao áudio e as barras de métricas.

Um único visual (os cinco estilos antigos foram unificados):
  • núcleo que pulsa com a voz;
  • anel de barras = histórico REAL do nível de áudio (microfone ouvindo, voz do
    NEXUS falando), espelhado, como um osciloscópio circular;
  • anéis com nós orbitando — a velocidade depende do estado (pensando gira mais);
  • cor muda com o estado: ouvindo, falando, pensando, mudo.

Leve de propósito: o passo da animação roda num único QTimer cujo intervalo
se adapta (ativo ~33 ms, ocioso ~66 ms, janela escondida ~400 ms) e o brilho
de fundo é um pixmap em cache — nada de recalcular gradiente a cada quadro.

Trinta e quatro visuais (botão "Trocar visual" escolhe numa lista); os dez do Ultra 2026 estão em
hud_ultra.py e os quinze do NexusCore em hud_core.py:
  orb ...... o orbe de sempre (completo)
  minimal .. só o texto de estado e as barras — quase zero CPU
  aurora ... (2026) fitas de luz que ondulam com a voz
  liquid ... (2026) gota de vidro líquido que se deforma com a voz
  holo ..... (2026) holograma: radar com varredura, anéis e espectro
  globe .... (2026) globo neural em 3D que gira e pulsa com a voz
  hub ...... (2.3) central de comando: núcleo + 6 módulos em órbita que acendem quando o NEXUS usa
             aquela área (sistema, memória, web, visão, finanças, mídia), com pacotes de dados
  matrix ... (2.3) chuva de caracteres que cai mais forte e brilhante com a voz
  waves .... (2.3) ondas senoidais empilhadas que viram um osciloscópio quando há voz
  nebula, gyro, helix, sonar, spectrum, hive, atom, plasma, stars, tunnel
            (Ultra 2026) nebulosa, giroscópio, hélice, sonar, espectro, colmeia, átomo, plasma,
            constelação e túnel — ver ui/hud_ultra.py
  pulsar, orbits, mandala, circuit, crystal, lissajous, vortex, sparks, corona, grid,
  pendulum, meteors, bubbles, network, heartbeat
            (NexusCore) pulsar, órbitas, mandala, circuito, cristal, lissajous, vórtice, faíscas,
            coroa, grade, pêndulos, meteoros, bolhas, rede e batimento — ver ui/hud_core.py
"""
from __future__ import annotations

import collections
import math
import time

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, FONT_MONO, accent2, mix, qcol  # noqa: F401
from .hud_core import CORE_INFO, CORE_STYLES
from .hud_novos import NOVOS_INFO, NOVOS_STYLES
from .hud_ultra import ULTRA_INFO, ULTRA_STYLES

# Estados que o cérebro manda (em inglês, por dentro) e como aparecem na tela
_ESTADOS_PT = {
    "INITIALISING": "INICIANDO", "INITIALIZING": "INICIANDO", "SLEEPING": "DORMINDO",
    "LISTENING": "OUVINDO", "SPEAKING": "FALANDO", "THINKING": "PENSANDO",
    "PROCESSING": "PROCESSANDO", "MUTED": "MUDO", "CONNECTING": "CONECTANDO",
    "RECONNECTING": "RECONECTANDO", "OFFLINE": "OFFLINE", "ERROR": "ERRO",
}

# Nome de cada visual na lista de escolha: (ícone, nome, descrição curta)
HUD_STYLE_INFO = {
    "orb":     ("◉", "Orbe", "O núcleo pulsa e o anel de barras mostra a voz"),
    "minimal": ("〰", "Mínimo", "Só barras e o estado — quase não usa CPU"),
    "aurora":  ("🌌", "Aurora", "Fitas de luz que ondulam com a voz"),
    "liquid":  ("💧", "Líquido", "Gota de vidro que se deforma quando há voz"),
    "holo":    ("🛰", "Holograma", "Radar com varredura, anéis e espectro"),
    "globe":   ("🌐", "Globo neural", "Globo 3D de pontos que gira e pulsa"),
    "hub":     ("⬡", "Hub", "Central de comando: módulos em órbita que acendem quando o NEXUS os usa"),
    "matrix":  ("▦", "Matrix", "Chuva de caracteres que acelera e brilha com a voz"),
    "waves":   ("≋", "Ondas", "Ondas empilhadas que viram osciloscópio com a voz"),
}
# NEXUS Ultra 2026: dez visuais novos (ui/hud_ultra.py), na mesma lista
HUD_STYLE_INFO.update(ULTRA_INFO)
# NexusCore: quinze visuais novos (ui/hud_core.py), depois dos do Ultra
HUD_STYLE_INFO.update(CORE_INFO)
# 3.6: vinte visuais novos (ui/hud_novos.py)
HUD_STYLE_INFO.update(NOVOS_INFO)

_BARRAS = 36                 # por lado (espelhado = 72 no anel)

_GLOBO: tuple | None = None   # (pontos, arestas) do globo, calculado uma vez


def _globo():
    """Esfera de Fibonacci (150 pontos) e as arestas entre vizinhos próximos."""
    global _GLOBO
    if _GLOBO is None:
        n = 150
        ouro = math.pi * (3.0 - math.sqrt(5.0))
        pts = []
        for i in range(n):
            y = 1.0 - 2.0 * (i + 0.5) / n
            r = math.sqrt(max(0.0, 1.0 - y * y))
            a = ouro * i
            pts.append((math.cos(a) * r, y, math.sin(a) * r))
        arestas = set()
        for i, a in enumerate(pts):
            viz = sorted(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2, j)
                         for j, b in enumerate(pts) if j != i)[:3]
            for _, j in viz:
                arestas.add((min(i, j), max(i, j)))
        _GLOBO = (pts, sorted(arestas))
    return _GLOBO
_ANEIS = ((1.00, 0.0, 0.16, 5), (0.86, 62.0, -0.23, 4), (0.72, 118.0, 0.31, 3))


class HudCanvas(QWidget):
    def __init__(self, face_path: str = "", assistant_name: str = "NEXUS", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted = False
        self.speaking = False
        self.state = "INITIALISING"
        self._assistant_name = assistant_name

        try:
            from memory.config_manager import HUD_STYLES, get_hud_style
            _e = get_hud_style()
            self.hud_style = _e if _e in HUD_STYLES else "orb"
        except Exception:
            self.hud_style = "orb"
        self._h: list[float] = [0.0] * _BARRAS      # cópia do histórico, lida pelos desenhos
        self._pulsos: list[float] = []              # instantes das ondas de pulso (globo/holo)
        self._ult_pulso = 0.0

        self._ajustes: dict = {}
        self.recarregar_ajustes()
        self._tick = 0
        self._fase = 0.0            # fase dos anéis (integrada, nunca salta)
        self._t_passo = time.time()
        self._blink = True
        self._blink_tick = 0
        self._bg_cache: QPixmap | None = None
        self._bg_key = None
        self._vivo = 0.0            # pico empurrado pelas threads de áudio (0–1)
        self._amp = 0.0             # nível suavizado que o desenho lê
        self._hist = collections.deque([0.0] * _BARRAS, maxlen=_BARRAS)
        self._hist_t = 0.0
        self._visemes = None        # (níveis, t0, hop) — cronograma da voz tocando
        self._core = 1.0            # raio relativo do núcleo (suavizado)
        self._luz_mod = [0.0] * 6   # brilho (0–1) de cada módulo do visual Hub; decai sozinho
        self._luz_nucleo = 0.0
        self._chuva: list[list[float]] = []        # visual Matrix: [x, y, velocidade, tamanho] de cada fio

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(33)

    # ── API usada pelo resto do programa ─────────────────────────────────────
    def ativar_modulo(self, funcao: str) -> None:
        """Acende no visual Hub o módulo da função que o NEXUS acabou de usar (thread-safe: só grava floats)."""
        try:
            from .hub_geom import modulo_da_funcao
            i = modulo_da_funcao(str(funcao))
            if i is None:
                self._luz_nucleo = 1.0
            elif 0 <= i < len(self._luz_mod):
                self._luz_mod[i] = 1.0
        except Exception:
            pass

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Compatibilidade (o rosto antigo olhava de lado). O orbe não precisa."""

    def set_audio_level(self, level: float) -> None:
        """Seguro entre threads: guarda o maior nível; _step() faz decair."""
        try:
            lv = min(1.0, max(0.0, float(level)))
        except (TypeError, ValueError):
            return
        if lv > self._vivo:
            self._vivo = lv

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Seguro entre threads. Recebe quadros (nível, …) da voz que vai tocar em `at`.

        Só o nível importa para o orbe; os quadros são ENCADEADOS num cronograma
        contínuo (cada lote entra onde o anterior termina, não por cima)."""
        try:
            if not frames:
                return
            hop = max(1e-3, float(hop))
            at = float(at)
            novos = [float(f[0]) if isinstance(f, (tuple, list)) else float(f) for f in frames]
            atual = self._visemes
            if atual is not None and abs(atual[2] - hop) < 1e-6:
                antigos, t0, _ = atual
                i = int(round((at - t0) / hop))
                if 0 <= i <= len(antigos) + 1:
                    junto = antigos[:i] + novos
                    tocado = int((time.time() - t0) / hop) - 2
                    if tocado > 60:               # não deixa crescer sem limite
                        junto = junto[tocado:]
                        t0 += tocado * hop
                    self._visemes = (junto, t0, hop)
                    return
            self._visemes = (novos, at, hop)
        except Exception:
            pass

    # ── animação ─────────────────────────────────────────────────────────────
    def _na_tela(self) -> bool:
        try:
            if not self.isVisible():
                return False
            win = self.window()
            return not (win.isMinimized() or win.isHidden())
        except Exception:
            return True

    def _step(self) -> None:
        self._tick += 1
        agora = time.time()
        dt = min(0.1, max(0.0, agora - self._t_passo))
        self._t_passo = agora

        sched = self._visemes
        if sched is not None:
            niveis, t0, hop = sched
            i = int((agora - t0) / hop)
            if 0 <= i < len(niveis):
                self._vivo = max(self._vivo, niveis[i])
            elif i >= len(niveis):
                self._visemes = None

        self._vivo *= 0.86
        self._amp += (self._vivo - self._amp) * 0.45
        amp = self._amp

        pensando = self.state in ("THINKING", "PROCESSING")
        vel = 1.0 + (1.8 if pensando else 0.0) + (0.9 if self.speaking else 0.0)
        if self.muted:
            vel = 0.25
        self._fase += dt * vel * self._ajustes.get("velocidade", 1.0)

        # histórico do anel: uma amostra a cada ~35 ms
        if agora - self._hist_t >= 0.035:
            self._hist_t = agora
            self._hist.append(0.0 if self.muted else amp)

        if self.hud_style in ("globe", "holo"):
            if amp > 0.22 and agora - self._ult_pulso > 0.5 and not self.muted:
                self._pulsos.append(agora)
                self._ult_pulso = agora
            self._pulsos = [t for t in self._pulsos if agora - t < 1.7]

        alvo = 1.0 + amp * 0.30 + (0.035 * math.sin(self._fase * 1.6) if not self.muted else 0.0)
        self._core += (alvo - self._core) * 0.35
        self._luz_mod = [max(0.0, v - dt * 0.35) for v in self._luz_mod]      # ~3 s para apagar
        self._luz_nucleo = max(0.0, self._luz_nucleo - dt * 0.8)

        self._blink_tick += 1
        piscou = self._blink_tick >= 22
        if piscou:
            self._blink = not self._blink
            self._blink_tick = 0

        # ritmo adaptativo: janela escondida quase para; ocioso é leve
        ativo = self.speaking or amp > 0.02 or pensando
        if not self._na_tela():
            self._tmr.setInterval(400)
            return
        self._tmr.setInterval(33 if ativo else 66)
        self.update()

    # ── desenho ──────────────────────────────────────────────────────────────
    def recarregar_ajustes(self) -> None:
        """Lê do disco a cor/velocidade escolhidas para o visual atual (editor do hub, 3.7)."""
        try:
            from core import hub_ajustes
            self._ajustes = hub_ajustes.obter(self.hud_style)
        except Exception:
            self._ajustes = {}

    def _cores(self):
        """(principal, destaque) conforme o estado."""
        if self.muted:
            return qcol(C.MUTED_C), qcol(C.MUTED_C)
        mt = self._ajustes.get("matiz")
        if mt is not None:
            from core.hub_ajustes import cores_com_matiz
            base = qcol(C.PRI)
            (r1, g1, b1), (r2, g2, b2) = cores_com_matiz(mt, (base.red(), base.green(), base.blue()))
            if self.speaking:
                return QColor(r1, g1, b1), qcol(C.VIOLET)
            if self.state in ("THINKING", "PROCESSING"):
                return QColor(r1, g1, b1), qcol(C.ACC)
            if self.state == "LISTENING":
                return QColor(r1, g1, b1), qcol(C.GREEN)
            return QColor(r1, g1, b1), QColor(r2, g2, b2)
        if self.speaking:
            return qcol(C.PRI), qcol(C.VIOLET)
        if self.state in ("THINKING", "PROCESSING"):
            return qcol(C.PRI), qcol(C.ACC)
        if self.state == "LISTENING":
            return qcol(C.PRI), qcol(C.GREEN)
        return qcol(C.PRI), qcol(accent2())

    def _fundo(self, W: int, H: int) -> QPixmap:
        """Fundo estático (gradiente suave + pontos), refeito só se tamanho/tema mudar."""
        key = (W, H, C.BG, C.PRI_GHO, C.PRI)
        if self._bg_cache is not None and self._bg_key == key:
            return self._bg_cache
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(qcol(C.BG))
        g = QPainter(pm)
        # degradê vertical: um tom mais claro no alto, índigo profundo embaixo
        vg = QLinearGradient(0, 0, 0, H)
        v0 = QColor(qcol(C.PANEL)); v0.setAlpha(255)
        v1 = QColor(qcol(C.BG)); v1.setAlpha(255)
        vg.setColorAt(0.0, v0); vg.setColorAt(1.0, v1)
        g.fillRect(0, 0, W, H, QBrush(vg))
        # brilho do acento atrás do orbe
        rg = QRadialGradient(W / 2, H * 0.46, max(W, H) * 0.62)
        c0 = QColor(qcol(C.PRI)); c0.setAlpha(34)
        c1 = QColor(qcol(C.BG)); c1.setAlpha(0)
        rg.setColorAt(0.0, c0); rg.setColorAt(1.0, c1)
        g.fillRect(0, 0, W, H, QBrush(rg))
        # segundo brilho, violeta, no canto inferior direito
        rg2 = QRadialGradient(W * 0.88, H * 0.95, max(W, H) * 0.55)
        d0 = QColor(qcol(accent2())); d0.setAlpha(30)
        d1 = QColor(qcol(accent2())); d1.setAlpha(0)
        rg2.setColorAt(0.0, d0); rg2.setColorAt(1.0, d1)
        g.fillRect(0, 0, W, H, QBrush(rg2))
        g.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 44):
            for y in range(0, H, 44):
                g.drawPoint(x, y)
        g.end()
        self._bg_cache, self._bg_key = pm, key
        return pm

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.drawPixmap(0, 0, self._fundo(W, H))

        cx = W / 2
        base_y = H * 0.84                       # linha do texto de estado
        faixa = max(80.0, base_y - 14.0)
        R = min(faixa / 2.0, W * 0.46)
        cy = 8.0 + faixa / 2.0
        main, acc = self._cores()
        amp = self._amp

        self._h = list(self._hist)
        estilo = self.hud_style
        if estilo == "orb":
            self._orbe(p, cx, cy, R, main, acc, amp)
        elif estilo == "aurora":
            self._aurora(p, W, H, cx, cy, R, main, acc, amp)
        elif estilo == "liquid":
            self._liquido(p, W, H, cx, cy, R, main, acc, amp)
        elif estilo == "holo":
            self._holo(p, W, H, cx, cy, R, main, acc, amp)
        elif estilo == "globe":
            self._globo_neural(p, W, H, cx, cy, R, main, acc, amp)
        elif estilo == "hub":
            self._hub(p, W, H, cx, cy, R, main, acc, amp)
        elif estilo == "matrix":
            self._matrix(p, W, H, cx, cy, R, main, acc, amp)
        elif estilo == "waves":
            self._ondas(p, W, H, cx, cy, R, main, acc, amp)
        elif estilo in ULTRA_STYLES or estilo in CORE_STYLES or estilo in NOVOS_STYLES:
            try:
                (ULTRA_STYLES.get(estilo) or CORE_STYLES.get(estilo) or NOVOS_STYLES[estilo])[3](self, p, W, H, cx, cy, R, main, acc, amp)
            except Exception:           # um visual com defeito nunca derruba a janela: volta ao orbe
                self.hud_style = "orb"
                self._orbe(p, cx, cy, R, main, acc, amp)
        else:
            self._so_barras(p, W, H, main, amp)

        # texto de estado
        if self.muted:
            txt, col = "⊘  MUDO", qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  FALANDO", acc
        elif self.state == "THINKING":
            txt, col = f"{'◈' if self._blink else '◇'}  PENSANDO", acc
        elif self.state == "PROCESSING":
            txt, col = f"{'▷' if self._blink else '▶'}  PROCESSANDO", acc
        elif self.state == "LISTENING":
            txt, col = f"{'●' if self._blink else '○'}  OUVINDO", acc
        else:
            txt, col = f"{'●' if self._blink else '○'}  {_ESTADOS_PT.get(self.state, self.state)}", main
        f = QFont(FONT_MAIN, 11, QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
        p.setFont(f)
        p.setPen(QPen(col, 1))
        p.drawText(QRectF(0, base_y, W, 28), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()

    def _orbe(self, p: QPainter, cx: float, cy: float, R: float,
              main: QColor, acc: QColor, amp: float) -> None:
        # brilho de fundo: gradiente radial, mais forte com a voz
        halo = QColor(acc); halo.setAlpha(int(46 + 110 * min(1.0, amp * 1.4)))
        none = QColor(acc); none.setAlpha(0)
        rg = QRadialGradient(cx, cy, R * 1.05)
        rg.setColorAt(0.0, halo); rg.setColorAt(0.55, QColor(main.red(), main.green(), main.blue(), 22))
        rg.setColorAt(1.0, none)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(cx, cy), R * 1.05, R * 1.05)

        # anel de barras (histórico de áudio espelhado)
        r_in = R * 0.50
        r_max = R * 0.30
        n = _BARRAS
        hist = list(self._hist)
        for lado in (1, -1):
            for i in range(n):
                v = hist[n - 1 - i] if lado == 1 else hist[n - 1 - i]
                comp = r_in + 3 + v * r_max * (0.75 + 0.25 * math.sin(self._fase * 3 + i * 0.5))
                ang = math.radians(-90 + lado * (i + 0.5) * (180.0 / n))
                ca, sa = math.cos(ang), math.sin(ang)
                cor = QColor(acc if v > 0.12 else main)
                cor.setAlpha(int(70 + 185 * min(1.0, v * 1.6)))
                pen = QPen(cor, max(1.6, R * 0.018), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(cx + ca * r_in, cy + sa * r_in),
                           QPointF(cx + ca * comp, cy + sa * comp))

        # anéis com nós orbitando
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k, (esc, rot0, vel, nos) in enumerate(_ANEIS):
            p.save()
            p.translate(cx, cy)
            p.rotate(rot0 + math.degrees(self._fase) * vel)
            rx, ry = R * esc, R * esc * (0.30 + 0.12 * k)
            cor = QColor(acc if k == 1 else main); cor.setAlpha(78 - k * 14)
            p.setPen(QPen(cor, 1.2))
            p.drawEllipse(QPointF(0, 0), rx, ry)
            p.setPen(Qt.PenStyle.NoPen)
            for j in range(nos):
                a = self._fase * (1.2 + k * 0.5) * (1 if k % 2 == 0 else -1) + j * (2 * math.pi / nos)
                nc = QColor(acc if j == 0 else main); nc.setAlpha(230 if j == 0 else 150)
                p.setBrush(QBrush(nc))
                p.drawEllipse(QPointF(rx * math.cos(a), ry * math.sin(a)), 2.6 + (1.4 if j == 0 else 0), 2.6 + (1.4 if j == 0 else 0))
            p.restore()

        # núcleo
        rc = R * 0.27 * self._core
        cg = QRadialGradient(cx - rc * 0.25, cy - rc * 0.3, rc * 1.3)
        claro = QColor(255, 255, 255, 235)
        cg.setColorAt(0.0, claro)
        cg.setColorAt(0.35, QColor(acc.red(), acc.green(), acc.blue(), 235))
        cg.setColorAt(1.0, QColor(main.red(), main.green(), main.blue(), 200))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(QPointF(cx, cy), rc, rc)
        borda = QColor(main); borda.setAlpha(150)
        p.setPen(QPen(borda, 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), rc * 1.22, rc * 1.22)

    def _so_barras(self, p: QPainter, W: int, H: int, main: QColor, amp: float) -> None:
        """Modo mínimo: só uma linha de barras (quase sem custo)."""
        n = len(self._hist)
        bw = max(4.0, min(10.0, (W * 0.7) / n))
        x0 = (W - n * bw) / 2
        y = H * 0.5
        for i, v in enumerate(self._hist):
            h = 3 + v * 60
            cor = QColor(main); cor.setAlpha(int(90 + 160 * min(1.0, v * 1.6)))
            p.fillRect(QRectF(x0 + i * bw, y - h / 2, bw - 1.5, h), cor)


    # ── visuais 2026 ─────────────────────────────────────────────────────────
    def _hv(self, t: float) -> float:
        """Nível de voz (0–1) interpolado do histórico; t = 0 é o mais antigo, 1 o mais novo."""
        h = self._h
        n = len(h)
        x = max(0.0, min(1.0, t)) * (n - 1)
        i = int(x)
        f = x - i
        j = min(n - 1, i + 1)
        return h[i] * (1.0 - f) + h[j] * f

    @staticmethod
    def _rgba(c: QColor, a: int) -> QColor:
        out = QColor(c)
        out.setAlpha(max(0, min(255, int(a))))
        return out

    def _aurora(self, p: QPainter, W: int, H: int, cx: float, cy: float, R: float,
                main: QColor, acc: QColor, amp: float) -> None:
        """Fitas de luz somadas (modo aditivo) que ondulam; o meio reage ao volume agora."""
        c3 = qcol(accent2())
        x0, x1 = W * 0.04, W * 0.96
        span = x1 - x0
        N = 60
        fase = self._fase
        # brilho largo atrás
        p.save()
        p.translate(cx, cy)
        p.scale(1.0, 0.55)                       # brilho achatado: elipse larga, sem bordas retas
        halo = QRadialGradient(0, 0, W * 0.5)
        halo.setColorAt(0.0, self._rgba(acc, 34 + 70 * amp))
        halo.setColorAt(1.0, self._rgba(acc, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(0, 0), W * 0.5, W * 0.5)
        p.restore()

        fitas = ((0.0, 1.00, 0.9, 1.00), (1.7, 1.35, -0.7, 0.82), (3.1, 0.80, 1.2, 0.66),
                 (4.6, 1.70, -1.1, 0.52), (5.9, 1.10, 0.6, 0.40))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for k, (ph, fq, vel, esc) in enumerate(fitas):
            topo, base, meio = [], [], []
            for i in range(N + 1):
                t = i / N
                x = x0 + span * t
                env = math.sin(math.pi * t) ** 1.3
                v = self._hv(1.0 - abs(2.0 * t - 1.0))
                a = R * esc * (0.10 + 0.70 * v + 0.30 * amp)
                yc = cy + a * env * math.sin(fq * t * 7.5 + ph + fase * vel * 1.5)
                th = (R * 0.045 * esc * (1.0 + 1.6 * v) + 1.0) * env + 0.8
                topo.append(QPointF(x, yc - th))
                base.append(QPointF(x, yc + th))
                meio.append(QPointF(x, yc))
            path = QPainterPath()
            path.moveTo(topo[0])
            for pt in topo[1:]:
                path.lineTo(pt)
            for pt in reversed(base):
                path.lineTo(pt)
            path.closeSubpath()
            g = QLinearGradient(x0, 0, x1, 0)
            g.setColorAt(0.0, self._rgba(main, 0))
            g.setColorAt(0.25, self._rgba(main, 80))
            g.setColorAt(0.55, self._rgba(acc, 90))
            g.setColorAt(0.8, self._rgba(c3, 80))
            g.setColorAt(1.0, self._rgba(c3, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPath(path)
            linha = QPainterPath()
            linha.moveTo(meio[0])
            for pt in meio[1:]:
                linha.lineTo(pt)
            lg = QLinearGradient(x0, 0, x1, 0)
            lg.setColorAt(0.0, self._rgba(main, 0))
            lg.setColorAt(0.5, self._rgba(QColor(255, 255, 255), 110 + 25 * k))
            lg.setColorAt(1.0, self._rgba(c3, 0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QBrush(lg), 1.3))
            p.drawPath(linha)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # partículas flutuando
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(16):
            x = x0 + span * ((j * 0.137 + fase * 0.018 * (1 + j % 3)) % 1.0)
            y = cy + math.sin(j * 2.1 + fase * 0.7) * R * (0.25 + 0.4 * ((j * 7) % 5) / 5.0)
            tam = 1.1 + (j % 3) * 0.7
            p.setBrush(QBrush(self._rgba(QColor(255, 255, 255), 60 + 120 * ((j % 4) / 4.0))))
            p.drawEllipse(QPointF(x, y), tam, tam)

    def _liquido(self, p: QPainter, W: int, H: int, cx: float, cy: float, R: float,
                 main: QColor, acc: QColor, amp: float) -> None:
        """Gota de vidro: a borda ondula (mais com a voz), brilho de vidro e satélites."""
        c3 = qcol(accent2())
        fase = self._fase
        R0 = R * 0.50 * self._core
        n = 64
        harm = ((2, 0.9, 0.0), (3, -1.3, 1.7), (5, 1.9, 3.1), (7, -2.4, 0.6))

        def forma(escala: float, fx: float) -> QPainterPath:
            pts = []
            for i in range(n):
                th = 2.0 * math.pi * i / n
                d = 1.0
                for k, (hh, w, ph) in enumerate(harm):
                    a = (0.040 + 0.19 * amp * (1.0 if k < 2 else 0.55)) / (1.0 + 0.45 * k)
                    d += a * math.sin(hh * th + ph + fase * w * fx)
                r = R0 * escala * d
                pts.append(QPointF(cx + r * math.cos(th), cy + r * math.sin(th)))
            path = QPainterPath()
            mid = lambda a, b: QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)  # noqa: E731
            path.moveTo(mid(pts[-1], pts[0]))
            for i in range(n):
                path.quadTo(pts[i], mid(pts[i], pts[(i + 1) % n]))
            path.closeSubpath()
            return path

        # halos
        p.setPen(Qt.PenStyle.NoPen)
        for esc, a, fx in ((1.52, 14, 0.5), (1.30, 22, 0.7), (1.14, 34, 0.9)):
            p.setBrush(QBrush(self._rgba(acc if esc > 1.25 else main, a + 40 * amp)))
            p.drawPath(forma(esc, fx))

        corpo = forma(1.0, 1.0)
        g = QRadialGradient(cx - R0 * 0.30, cy - R0 * 0.38, R0 * 1.45)
        g.setColorAt(0.0, QColor(255, 255, 255, 235))
        g.setColorAt(0.30, self._rgba(acc, 235))
        g.setColorAt(0.70, self._rgba(main, 232))
        g.setColorAt(1.0, self._rgba(c3, 238))
        p.setBrush(QBrush(g))
        p.drawPath(corpo)

        # brilho de vidro (meia-lua clara no alto) e reflexo embaixo
        p.save()
        p.setClipPath(corpo)
        p.translate(cx - R0 * 0.26, cy - R0 * 0.50)
        p.rotate(-24)
        gl = QLinearGradient(0, -R0 * 0.2, 0, R0 * 0.2)
        gl.setColorAt(0.0, QColor(255, 255, 255, 150))
        gl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gl))
        p.drawEllipse(QPointF(0, 0), R0 * 0.62, R0 * 0.20)
        p.restore()
        p.save()
        p.setClipPath(corpo)
        gb = QRadialGradient(cx, cy + R0 * 1.05, R0 * 0.9)
        gb.setColorAt(0.0, self._rgba(c3, 120))
        gb.setColorAt(1.0, self._rgba(c3, 0))
        p.setBrush(QBrush(gb))
        p.drawEllipse(QPointF(cx, cy + R0 * 1.0), R0 * 0.9, R0 * 0.5)
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.4))
        p.drawPath(corpo)

        # satélites com rastro
        for k, (vel, off, raio, tam) in enumerate(((0.9, 0.0, 0.95, 5.0), (-0.6, 2.1, 1.12, 4.0),
                                                   (0.45, 4.2, 1.28, 3.2))):
            for t in range(6):
                a = fase * vel + off - t * 0.10 * (1 if vel > 0 else -1)
                x = cx + R * raio * math.cos(a)
                y = cy + R * raio * 0.55 * math.sin(a)
                al = 210 - t * 38
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(self._rgba(acc if k != 1 else c3, al)))
                p.drawEllipse(QPointF(x, y), tam - t * 0.5, tam - t * 0.5)

    def _holo(self, p: QPainter, W: int, H: int, cx: float, cy: float, R: float,
              main: QColor, acc: QColor, amp: float) -> None:
        """Holograma: anéis, tiques girando, arcos, espectro radial, varredura e hexágono."""
        c3 = qcol(accent2())
        fase = self._fase
        centro = QPointF(cx, cy)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # anéis finos
        for esc, a in ((1.00, 95), (0.82, 55), (0.60, 70), (0.37, 55)):
            p.setPen(QPen(self._rgba(main, a), 1.0))
            p.drawEllipse(centro, R * esc, R * esc)

        # tiques da borda
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(fase) * 0.12)
        for i in range(120):
            ang = math.radians(i * 3.0)
            longo = i % 10 == 0
            l = R * (0.06 if longo else 0.026)
            ca, sa = math.cos(ang), math.sin(ang)
            p.setPen(QPen(self._rgba(acc if longo else main, 200 if longo else 110), 1.4 if longo else 1.0))
            p.drawLine(QPointF(ca * R, sa * R), QPointF(ca * (R - l), sa * (R - l)))
        p.restore()

        # arcos grossos giratórios
        arcos = ((0.91, 70, 0.55, 4.0, acc), (0.70, 44, -0.85, 3.2, c3), (0.47, 110, 1.35, 3.0, main))
        for k, (esc, vao, vel, larg, cor) in enumerate(arcos):
            r = R * esc
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            ini = math.degrees(fase * vel) + k * 120
            p.setPen(QPen(self._rgba(cor, 220), larg, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, int(ini * 16), int(vao * 16))
            p.setPen(QPen(self._rgba(cor, 110), larg * 0.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, int((ini + 180) * 16), int(vao * 0.6 * 16))

        # espectro radial (72 barras)
        r_in = R * 0.40
        nb = 72
        for i in range(nb):
            ang = math.radians(-90 + i * 360.0 / nb)
            v = self._hv(1.0 - abs(((i / nb) * 2.0) % 2.0 - 1.0))
            comp = R * (0.015 + 0.22 * v * (0.8 + 0.2 * math.sin(fase * 3 + i * 0.4)))
            ca, sa = math.cos(ang), math.sin(ang)
            cor = acc if v > 0.15 else main
            p.setPen(QPen(self._rgba(cor, 90 + 160 * min(1.0, v * 1.8)), 2.0, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(cx + ca * r_in, cy + sa * r_in),
                       QPointF(cx + ca * (r_in + 2 + comp), cy + sa * (r_in + 2 + comp)))

        # varredura (cone de luz que gira)
        ang = (-(fase * 42.0)) % 360.0
        cg = QConicalGradient(cx, cy, ang)
        cg.setColorAt(0.0, self._rgba(c3, 120))
        cg.setColorAt(0.14, self._rgba(c3, 0))
        cg.setColorAt(1.0, self._rgba(c3, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cg))
        p.drawEllipse(centro, R * 0.97, R * 0.97)
        a_r = math.radians(ang)
        p.setPen(QPen(self._rgba(c3, 230), 1.5))
        p.drawLine(centro, QPointF(cx + math.cos(a_r) * R * 0.97, cy - math.sin(a_r) * R * 0.97))

        # ondas de pulso
        agora = time.time()
        p.setBrush(Qt.BrushStyle.NoBrush)
        for t0 in self._pulsos:
            idade = (agora - t0) / 1.6
            if 0.0 <= idade <= 1.0:
                p.setPen(QPen(self._rgba(acc, 170 * (1.0 - idade)), 1.6))
                p.drawEllipse(centro, R * (0.30 + 0.75 * idade), R * (0.30 + 0.75 * idade))

        # hexágono do núcleo
        rh = R * 0.17 * self._core
        for esc, rot, a, larg in ((1.0, fase * 0.5, 235, 2.0), (0.62, -fase * 0.9, 160, 1.4)):
            hx = QPainterPath()
            for i in range(7):
                ang = rot + i * math.pi / 3.0
                pt = QPointF(cx + rh * esc * math.cos(ang), cy + rh * esc * math.sin(ang))
                hx.moveTo(pt) if i == 0 else hx.lineTo(pt)
            if esc == 1.0:
                cgr = QRadialGradient(cx, cy, rh)
                cgr.setColorAt(0.0, self._rgba(QColor(255, 255, 255), 230))
                cgr.setColorAt(0.6, self._rgba(acc, 170))
                cgr.setColorAt(1.0, self._rgba(main, 70))
                p.setBrush(QBrush(cgr))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(self._rgba(acc, a), larg))
            p.drawPath(hx)

        # colchetes dos cantos e rótulos
        m, l = 14.0, 22.0
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self._rgba(main, 150), 1.6))
        for (x, y, dx, dy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + dx * l, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * l))
        p.setFont(QFont(FONT_MONO, 7))
        p.setPen(QPen(self._rgba(main, 170), 1))
        p.drawText(QRectF(m + 8, m + 6, 200, 14), Qt.AlignmentFlag.AlignLeft, f"{self._assistant_name.upper()} // 2026")
        p.drawText(QRectF(W - 208 - m, H - m - 22, 200, 14), Qt.AlignmentFlag.AlignRight,
                   f"VOZ {int(amp * 100):02d}%  ·  {_ESTADOS_PT.get(self.state, self.state)}")

    def _hub(self, p: QPainter, W: int, H: int, cx: float, cy: float, R: float,
             main: QColor, acc: QColor, amp: float) -> None:
        """Hub (2.3): núcleo hexagonal, anéis segmentados, seis módulos em órbita ligados por trilhas de
        dados. O módulo da função que o NEXUS usou acende e apaga em ~3 s; a voz vira espectro no anel."""
        from .hub_geom import MODULOS, pacotes, posicoes
        c3 = qcol(accent2())
        fase = self._fase
        centro = QPointF(cx, cy)
        p.setBrush(Qt.BrushStyle.NoBrush)
        r_orb = R * 0.74                                   # raio da órbita dos módulos
        nos = posicoes(cx, cy, r_orb, fase * 0.06)

        # anéis segmentados (tracejados) girando em sentidos opostos
        for esc, vel, larg, a in ((0.98, 0.10, 1.2, 70), (0.50, -0.22, 2.0, 95)):
            pen = QPen(self._rgba(main, a), larg, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([6.0, 5.0])
            pen.setDashOffset(fase * vel * 60)
            p.setPen(pen)
            p.drawEllipse(centro, R * esc, R * esc)

        # espectro da voz em volta do núcleo
        r_in = R * 0.27
        nb = 60
        for i in range(nb):
            ang = math.radians(-90 + i * 360.0 / nb)
            v = self._hv(1.0 - abs(((i / nb) * 2.0) % 2.0 - 1.0))
            comp = R * (0.012 + 0.16 * v)
            ca, sa = math.cos(ang), math.sin(ang)
            p.setPen(QPen(self._rgba(acc if v > 0.12 else main, 80 + 170 * min(1.0, v * 1.8)), 2.0,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(cx + ca * r_in, cy + sa * r_in), QPointF(cx + ca * (r_in + 2 + comp), cy + sa * (r_in + 2 + comp)))

        # trilhas núcleo → módulo (acendem com a atividade do módulo)
        for i, (nx, ny) in enumerate(nos):
            luz = self._luz_mod[i]
            p.setPen(QPen(self._rgba(acc if luz > 0.05 else main, 40 + 150 * luz), 1.0 + 1.4 * luz))
            p.drawLine(centro, QPointF(nx, ny))
        # pacotes de dados correndo pelas trilhas
        p.setPen(Qt.PenStyle.NoPen)
        for i, t in pacotes(fase, self.state, self.speaking, len(nos)):
            nx, ny = nos[i]
            x, y = cx + (nx - cx) * t, cy + (ny - cy) * t
            luz = self._luz_mod[i]
            p.setBrush(QBrush(self._rgba(c3 if luz < 0.05 else acc, 110 + 120 * max(luz, amp))))
            rr = 2.0 + 1.8 * luz
            p.drawEllipse(QPointF(x, y), rr, rr)

        # módulos (hexágonos pequenos com nome)
        p.setFont(QFont(FONT_MONO, 7))
        rm = max(9.0, R * 0.105)
        for i, (nx, ny) in enumerate(nos):
            luz = self._luz_mod[i]
            hx = QPainterPath()
            for k in range(7):
                a = math.pi / 6 + k * math.pi / 3
                pt = QPointF(nx + rm * math.cos(a), ny + rm * math.sin(a))
                hx.moveTo(pt) if k == 0 else hx.lineTo(pt)
            fill = QColor(acc if luz > 0.05 else main)
            fill.setAlpha(int(24 + 170 * luz))
            p.setBrush(QBrush(fill))
            p.setPen(QPen(self._rgba(acc if luz > 0.05 else main, 120 + 120 * luz), 1.4))
            p.drawPath(hx)
            if luz > 0.05:                                  # halo
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(self._rgba(acc, 120 * luz), 1.2))
                p.drawEllipse(QPointF(nx, ny), rm * (1.3 + 0.5 * (1 - luz)), rm * (1.3 + 0.5 * (1 - luz)))
            p.setPen(QPen(self._rgba(acc if luz > 0.05 else main, 170 + 80 * luz), 1))
            p.drawText(QRectF(nx - 40, ny + rm + 2, 80, 12), Qt.AlignmentFlag.AlignCenter, MODULOS[i][0])

        # núcleo hexagonal
        rh = R * 0.17 * self._core
        for esc, rot, a, larg in ((1.0, fase * 0.4, 235, 2.0), (0.6, -fase * 0.8, 150, 1.3)):
            hx = QPainterPath()
            for k in range(7):
                ang = rot + k * math.pi / 3.0
                pt = QPointF(cx + rh * esc * math.cos(ang), cy + rh * esc * math.sin(ang))
                hx.moveTo(pt) if k == 0 else hx.lineTo(pt)
            if esc == 1.0:
                cgr = QRadialGradient(cx, cy, rh)
                cgr.setColorAt(0.0, self._rgba(QColor(255, 255, 255), 200 + int(55 * self._luz_nucleo)))
                cgr.setColorAt(0.6, self._rgba(acc, 160 + int(80 * self._luz_nucleo)))
                cgr.setColorAt(1.0, self._rgba(main, 60))
                p.setBrush(QBrush(cgr))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(self._rgba(acc, a), larg))
            p.drawPath(hx)

        # colchetes dos cantos e rótulo
        m, l = 14.0, 22.0
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self._rgba(main, 150), 1.6))
        for (x, y, dx, dy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + dx * l, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * l))
        p.setFont(QFont(FONT_MONO, 7))
        p.setPen(QPen(self._rgba(main, 170), 1))
        p.drawText(QRectF(m + 8, m + 6, 220, 14), Qt.AlignmentFlag.AlignLeft, f"{self._assistant_name.upper()} // HUB")

    _GLIFOS = "01ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿ<>/=+*"

    def _matrix(self, p: QPainter, W: int, H: int, cx: float, cy: float, R: float,
                main: QColor, acc: QColor, amp: float) -> None:
        """Matrix (2.3): colunas de caracteres caindo; a voz aumenta a velocidade, o brilho e a densidade."""
        passo = 16
        colunas = max(8, W // passo)
        if len(self._chuva) != colunas:
            import random
            rng = random.Random(7)
            self._chuva = [[i * passo + passo / 2, rng.uniform(0, H), rng.uniform(40, 120), rng.randint(6, 14)]
                           for i in range(colunas)]
        f = QFont(FONT_MONO, 9)
        p.setFont(f)
        vel = 1.0 + amp * 3.0 + (1.2 if self.state in ("THINKING", "PROCESSING") else 0.0)
        if self.muted:
            vel = 0.2
        dt = 0.033
        n_g = len(self._GLIFOS)
        for i, fio in enumerate(self._chuva):
            fio[1] += fio[2] * vel * dt
            if fio[1] - fio[3] * passo > H:
                fio[1] = -passo * (i % 5)
            dist = abs(fio[0] - cx) / max(1.0, W / 2)                  # colunas do centro reagem mais à voz
            extra = amp * (1.0 - dist)
            for k in range(int(fio[3])):
                y = fio[1] - k * passo
                if y < -passo or y > H:
                    continue
                a = (1.0 - k / fio[3])
                cor = acc if k == 0 else main
                p.setPen(QPen(self._rgba(cor, (255 if k == 0 else 150) * a * (0.35 + 0.65 * min(1.0, 0.4 + extra * 1.6))), 1))
                g = self._GLIFOS[(i * 7 + k * 3 + int(self._fase * 6 + y / passo)) % n_g]
                p.drawText(QPointF(fio[0] - 5, y), g)
        # núcleo: halo que pulsa atrás do texto de estado
        rg = QRadialGradient(cx, cy, R * 0.7)
        rg.setColorAt(0.0, self._rgba(acc, 40 + 110 * min(1.0, amp * 1.5)))
        rg.setColorAt(1.0, self._rgba(acc, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(cx, cy), R * 0.7, R * 0.7)

    def _ondas(self, p: QPainter, W: int, H: int, cx: float, cy: float, R: float,
               main: QColor, acc: QColor, amp: float) -> None:
        """Ondas (2.3): 7 senoides empilhadas; com voz, a amplitude segue o histórico real do áudio."""
        p.setBrush(Qt.BrushStyle.NoBrush)
        n_lin = 7
        larg = W * 0.86
        x0 = (W - larg) / 2
        altura = R * 1.5
        topo = cy - altura / 2
        pts = 90
        for j in range(n_lin):
            base = topo + altura * (j + 0.5) / n_lin
            prof = j / (n_lin - 1)
            cor = acc if j == n_lin // 2 else main
            path = QPainterPath()
            for i in range(pts + 1):
                u = i / pts
                env = math.sin(math.pi * u) ** 1.5                      # borda calma, meio vivo
                v = self._hv(u)
                y = base + env * (
                    math.sin(u * 9 + self._fase * (1.0 + prof)) * (3 + 5 * amp)
                    + math.sin(u * 23 - self._fase * 1.7 + j) * 2.0 * amp
                    + (v - 0.15) * (altura / n_lin) * 1.8 * (1 if j % 2 == 0 else -1))
                pt = QPointF(x0 + larg * u, y)
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            p.setPen(QPen(self._rgba(cor, 70 + 150 * (1 - abs(prof - 0.5) * 1.4)), 1.3 + (1.0 if j == n_lin // 2 else 0)))
            p.drawPath(path)

    def _globo_neural(self, p: QPainter, W: int, H: int, cx: float, cy: float, R: float,
                      main: QColor, acc: QColor, amp: float) -> None:
        """Globo de pontos ligados girando em 3D; as faixas incham com a voz."""
        c3 = qcol(accent2())
        pts, arestas = _globo()
        fase = self._fase
        Rg = R * 0.66 * (1.0 + 0.10 * amp)
        ry = fase * 0.30
        rx = 0.38
        cyw, syw = math.cos(ry), math.sin(ry)
        cxw, sxw = math.cos(rx), math.sin(rx)

        # brilho de fundo
        g = QRadialGradient(cx, cy, Rg * 1.6)
        g.setColorAt(0.0, self._rgba(acc, 46 + 90 * amp))
        g.setColorAt(0.6, self._rgba(main, 16))
        g.setColorAt(1.0, self._rgba(main, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), Rg * 1.6, Rg * 1.6)

        proj = []
        for (x, y, z) in pts:
            v = self._hv(1.0 - abs(y))
            k = 1.0 + 0.30 * v
            x1 = (x * cyw + z * syw) * k
            z1 = (-x * syw + z * cyw) * k
            y1 = y * k
            y2 = y1 * cxw - z1 * sxw
            z2 = y1 * sxw + z1 * cxw
            f = 1.0 + z2 * 0.20
            proj.append((cx + x1 * Rg * f, cy + y2 * Rg * f, z2, v))

        # anel do equador e órbitas
        p.setBrush(Qt.BrushStyle.NoBrush)
        for esc, tilt, a in ((1.20, 0.30, 70), (1.42, -0.55, 45)):
            p.save()
            p.translate(cx, cy)
            p.rotate(math.degrees(tilt) + math.degrees(fase) * 0.05)
            p.setPen(QPen(self._rgba(main, a), 1.0))
            p.drawEllipse(QPointF(0, 0), Rg * esc, Rg * esc * 0.28)
            p.restore()

        # arestas
        for i, j in arestas:
            a, b = proj[i], proj[j]
            prof = (a[2] + b[2]) / 2.0
            if prof < -0.35:
                continue
            forca = max(a[3], b[3])
            al = 28 + 85 * (prof + 1) / 2 + 120 * forca
            cor = acc if forca > 0.2 else main
            p.setPen(QPen(self._rgba(cor, al), 1.0))
            p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))

        # pontos: os de trás primeiro
        p.setPen(Qt.PenStyle.NoPen)
        for lado in (0, 1):
            for (x, y, z, v) in proj:
                if (z >= 0.0) != bool(lado):
                    continue
                prof = (z + 1.0) / 2.0
                tam = 1.1 + 2.4 * prof + 2.0 * v
                cor = acc if v > 0.2 else (c3 if z > 0.55 else main)
                p.setBrush(QBrush(self._rgba(cor, 70 + 185 * prof)))
                p.drawEllipse(QPointF(x, y), tam, tam)

        # ondas de pulso e satélites
        agora = time.time()
        p.setBrush(Qt.BrushStyle.NoBrush)
        for t0 in self._pulsos:
            idade = (agora - t0) / 1.6
            if 0.0 <= idade <= 1.0:
                p.setPen(QPen(self._rgba(acc, 160 * (1.0 - idade)), 1.5))
                p.drawEllipse(QPointF(cx, cy), Rg * (1.0 + 0.55 * idade), Rg * (1.0 + 0.55 * idade))
        p.setPen(Qt.PenStyle.NoPen)
        for k, (vel, off, esc, tilt) in enumerate(((0.7, 0.0, 1.20, 0.30), (-0.5, 2.5, 1.42, -0.55))):
            a = fase * vel + off
            x, y = Rg * esc * math.cos(a), Rg * esc * 0.28 * math.sin(a)
            ct, st = math.cos(tilt), math.sin(tilt)
            p.setBrush(QBrush(self._rgba(QColor(255, 255, 255), 235)))
            p.drawEllipse(QPointF(cx + x * ct - y * st, cy + x * st + y * ct), 3.6, 3.6)


class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text = "--"
        self._hist: list[float] = []     # histórico do gráfico (máx. 26 pontos)
        self.setFixedHeight(44)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return          # igual — não repinta
        self._value = v
        self._text = text
        self._hist.append(v)
        if len(self._hist) > 26:
            self._hist.pop(0)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 10, 10)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        p.setFont(QFont(FONT_MAIN, 7, QFont.Weight.DemiBold))
        f_lbl = p.font()
        f_lbl.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        p.setFont(f_lbl)
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(10, 6, 60, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont(FONT_MAIN, 12, QFont.Weight.DemiBold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 3, W - 10, 18),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        gy0, gy1 = 22, H - 6
        gx0, gx1 = 10, W - 10
        gw = max(1.0, gx1 - gx0)
        gh = max(1.0, gy1 - gy0)
        hist = self._hist
        if len(hist) >= 2:
            step = gw / (26 - 1)
            x0 = gx1 - step * (len(hist) - 1)
            pts = [QPointF(x0 + i * step, gy1 - (v / 100.0) * gh) for i, v in enumerate(hist)]
            path = QPainterPath()
            path.moveTo(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            fill = QPainterPath(path)
            fill.lineTo(pts[-1].x(), gy1)
            fill.lineTo(pts[0].x(), gy1)
            fill.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(bar_col.red(), bar_col.green(), bar_col.blue(), 28)))
            p.drawPath(fill)
            p.setPen(QPen(bar_col, 1.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bar_col))
            p.drawEllipse(pts[-1], 2.0, 2.0)

        p.end()
