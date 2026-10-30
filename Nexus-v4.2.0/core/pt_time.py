"""Datas e horas em português, sem depender do idioma do sistema."""
from datetime import datetime, timedelta, timezone

# Horário de Brasília. O zoneinfo usa o banco de fusos do sistema; se ele não
# existir (Windows sem o pacote tzdata), usa UTC-3 fixo, que é o horário de
# Brasília desde o fim do horário de verão, em 2019.
try:
    from zoneinfo import ZoneInfo
    BRASILIA = ZoneInfo("America/Sao_Paulo")
except Exception:
    BRASILIA = timezone(timedelta(hours=-3))

_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo"]
_DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
_MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago",
                 "set", "out", "nov", "dez"]


def data_extensa(dt: datetime) -> str:
    """Ex.: 'segunda-feira, 12 de outubro de 2026'."""
    return f"{_DIAS[dt.weekday()]}, {dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def data_curta(dt: datetime) -> str:
    """Ex.: 'seg 12 out 2026'."""
    return f"{_DIAS_CURTOS[dt.weekday()]} {dt.day:02d} {_MESES_CURTOS[dt.month - 1]} {dt.year}"


def hora(dt: datetime) -> str:
    """'11:42' ou, se a preferência for 12 horas, '11:42 AM'."""
    try:
        from core import preferences as P
        if str(P.get("hour_format")) == "12":
            h = dt.hour % 12 or 12
            return f"{h:02d}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    except Exception:
        pass
    return f"{dt:%H:%M}"


def data_hora(dt: datetime) -> str:
    """Ex.: 'segunda-feira, 12 de outubro de 2026 — 11:42'."""
    return f"{data_extensa(dt)} — {hora(dt)}"


def agora() -> datetime:
    """Agora em horário de Brasília, sem tzinfo.

    Sem tzinfo porque o resto do código já compara e formata datetimes naive;
    trocar por aware quebraria essas comparações."""
    return datetime.now(BRASILIA).replace(tzinfo=None)


def de_timestamp(ts: float) -> datetime:
    """Converte um timestamp para a hora de Brasília (naive)."""
    return datetime.fromtimestamp(ts, BRASILIA).replace(tzinfo=None)


def dia_hora(dt: datetime) -> str:
    """Ex.: 'segunda-feira 11:42'."""
    return f"{_DIAS[dt.weekday()]} {hora(dt)}"


def hora_extensa(dt: datetime) -> str:
    """Ex.: '12 de outubro às 11:42'."""
    return f"{dt.day} de {_MESES[dt.month - 1]} às {hora(dt)}"

