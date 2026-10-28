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

Vinte visuais (o botão "Trocar visual" escolhe numa lista), todos em hud_novos.py: prisma, origami, gotas,
Saturno, vaga-lumes, cometas, arcos, fogos, rosa, synthwave, galáxia, cidade, engrenagens, cordas, árvore,
caleidoscópio, buraco negro, escudo, lótus e tempestade. O orbe ("orb") continua por dentro, só como reserva:
se um visual falhar ao desenhar, o HUD volta a ele sem derrubar a janela.
"""
from __future__ import annotations

import collections
import math
import time

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, FONT_MONO, accent2, mix, qcol  # noqa: F401
from .hud_novos import NOVOS_INFO, NOVOS_STYLES

# Estados que o cérebro manda (em inglês, por dentro) e como aparecem na tela
_ESTADOS_PT = {
    "INITIALISING": "INICIANDO", "INITIALIZING": "INICIANDO", "SLEEPING": "DORMINDO",
    "LISTENING": "OUVINDO", "SPEAKING": "FALANDO", "THINKING": "PENSANDO",
    "PROCESSING": "PROCESSANDO", "MUTED": "MUDO", "CONNECTING": "CONECTANDO",
    "RECONNECTING": "RECONECTANDO", "OFFLINE": "OFFLINE", "ERROR": "ERRO",
}

# Nome de cada visual na lista de escolha: (ícone, nome, descrição curta)
HUD_STYLE_INFO = {
    "orb": ("◉", "Orbe", "O orbe clássico (visual de reserva)"),
}
HUD_STYLE_INFO.update(NOVOS_INFO)

_BARRAS = 36                 # por lado (espelhado = 72 no anel)


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
            self.hud_style = _e if _e in HUD_STYLES else "galaxy"
        except Exception:
            self.hud_style = "galaxy"
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
        """Compatibilidade: o antigo visual Hub acendia módulos; os visuais atuais não usam."""

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
        if estilo in NOVOS_STYLES:
            try:
                NOVOS_STYLES[estilo][3](self, p, W, H, cx, cy, R, main, acc, amp)
            except Exception:           # um visual com defeito nunca derruba a janela: volta ao orbe
                self.hud_style = "orb"
                self._orbe(p, cx, cy, R, main, acc, amp)
        else:
            self._orbe(p, cx, cy, R, main, acc, amp)

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
