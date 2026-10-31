"""Peças visuais da versão 1.2 (visual novo).

- ChatLog ........ a CONVERSA em balões (substitui o antigo log de texto corrido)
- RingGauge ...... medidor em arco com degradê (CPU, memória)
- SparkMetric .... linha com gráfico de área (rede, GPU, temperatura)
- UptimeCard ..... tempo ligado (dias/horas/minutos) e barra de 7 dias
- ProcessList .... processos que mais pesam (por CPU ou por RAM)
- StatusCard ..... cartão de estado (núcleo, segurança, versão)
- QuickBar ....... barra de acesso rápido personalizável

Todas usam as cores da classe C em folhas de estilo, então a troca de cor ao
vivo (retheme_all_widgets) continua pintando tudo na hora.

Parte do pacote ui do NEXUS Ultra 2026.
"""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, _persist_activity, accent2, mix, qcol, agora  # noqa: F401
from .modern_base import _font, _grad_ends, _lerp, _level_colour  # noqa: F401
from .modern_conversa import ChatLog, _Bubble  # noqa: F401
from .modern_medidores import CompactMetric, GradientLabel, HeaderBar, ProcessList, RingGauge, SparkMetric, StatusCard, UptimeCard, format_uptime  # noqa: F401
from .modern_botoes import ControlButton, ICONE_FERRAMENTA, ICONE_SETUP, MenuButton, QuickBar, QuickButton, _ESTADO_ALERTA, _ESTADO_DESLIGADO, _ESTADO_LIGADO, _ICONE_POR_CARACTERE, _icone  # noqa: F401
