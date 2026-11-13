"""Zona horaria y helpers de fecha. Todo el proyecto trabaja en hora de Buenos Aires."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# Una función a las 00:30 publicada en la grilla del viernes es, en el calendario, la madrugada del sábado.
HORA_CORTE_TRASNOCHE = time(6, 0)


def ahora() -> datetime:
    return datetime.now(TZ)


def hoy() -> date:
    return ahora().date()


def combinar(dia: date, hora: time) -> datetime:
    """Fecha de la grilla + hora publicada -> datetime real (corre la trasnoche al día siguiente)."""
    if hora < HORA_CORTE_TRASNOCHE:
        dia = dia + timedelta(days=1)
    return datetime.combine(dia, hora, tzinfo=TZ)


def iso(dt: datetime) -> str:
    """Formato canónico guardado en la DB: 2026-11-13T21:30:00-03:00 (ordenable como texto)."""
    return dt.astimezone(TZ).isoformat(timespec="seconds")
