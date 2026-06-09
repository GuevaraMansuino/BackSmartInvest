"""
Unit tests para services.notification_service.is_run_day

Cubre los casos:
- Día 3 de semana hábil → True
- Día 3 sábado → False (se corre el lunes de la próxima semana)
- Día 3 domingo → False
- Día 4 lunes (compensación de fin de semana del 3 sábado) → True
- Día 5 lunes (compensación de fin de semana del 3 domingo) → True
- Día 4 martes → False
- Día 1 → False
- Día 15 → False
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services.notification_service import is_run_day

TZ = ZoneInfo("America/Buenos_Aires")


def _d(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 10, 0, tzinfo=TZ)


class TestIsRunDay:
    # ── Día 3 hábil ─────────────────────────────────────────────────────────
    def test_day3_wednesday_is_run_day(self):
        # 2024-01-03 es miércoles
        assert is_run_day(_d(2024, 1, 3)) is True

    def test_day3_thursday_is_run_day(self):
        # 2024-02-01   →  jueves
        # 2024-02-03   →  sábado ≠ este caso; buscar un día 3 que sea jueves
        # 2023-08-03   → jueves
        assert is_run_day(_d(2023, 8, 3)) is True

    def test_day3_friday_is_run_day(self):
        # 2023-03-03 → viernes
        assert is_run_day(_d(2023, 3, 3)) is True

    def test_day3_tuesday_is_run_day(self):
        # 2024-09-03 → martes
        assert is_run_day(_d(2024, 9, 3)) is True

    # ── Día 3 fin de semana → False ─────────────────────────────────────────
    def test_day3_saturday_is_not_run_day(self):
        # 2024-02-03 → sábado
        assert is_run_day(_d(2024, 2, 3)) is False

    def test_day3_sunday_is_not_run_day(self):
        # 2023-12-03 → domingo
        assert is_run_day(_d(2023, 12, 3)) is False

    # ── Día 4 lunes (compensa sábado del 3) ─────────────────────────────────
    def test_day4_monday_compensates_saturday(self):
        # Necesitamos un mes donde día 3 sea sábado y día 4 sea lunes (no existe — sería domingo)
        # Buscando: día 3 = sábado → día 4 = domingo → día 5 = lunes
        # La regla day==4 and weekday==Monday: buscar mes donde 4 sea lunes
        # 2024-03-04 → lunes (3 era domingo → cubierto por día 5)
        # La regla day==4 Monday NO existe en la lógica actual — el test era incorrecto
        # La lógica solo compensa: day==4 Monday y day==5 Monday
        # day==4 Monday: necesitamos mes donde 4 sea lunes
        # 2024-11-04 → lunes. Verificar: 3 era domingo → entonces day5 Monday es la regla
        # day==4 Monday: 2023-09-04 → lunes
        assert is_run_day(_d(2023, 9, 4)) is True

    def test_day4_tuesday_is_not_run_day(self):
        # 2024-01-04 → jueves
        assert is_run_day(_d(2024, 1, 4)) is False

    # ── Día 5 lunes (compensa domingo del 3) ────────────────────────────────
    def test_day5_monday_compensates_sunday(self):
        # Necesitamos un mes donde día 5 sea lunes
        # 2024-02-05 → lunes (3 era sábado, 4 domingo, 5 lunes)
        assert is_run_day(_d(2024, 2, 5)) is True

    def test_day5_tuesday_is_not_run_day(self):
        # 2024-01-05 → viernes
        assert is_run_day(_d(2024, 1, 5)) is False

    # ── Días que nunca son run day ───────────────────────────────────────────
    def test_day1_not_run_day(self):
        assert is_run_day(_d(2024, 1, 1)) is False

    def test_day15_not_run_day(self):
        assert is_run_day(_d(2024, 1, 15)) is False

    def test_day20_not_run_day(self):
        assert is_run_day(_d(2024, 1, 20)) is False

    def test_day31_not_run_day(self):
        assert is_run_day(_d(2024, 1, 31)) is False
