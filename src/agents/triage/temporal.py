"""Detecção de janela temporal (SPEC-005 §5).

Camada A: `dateparser` (PT-BR) cobre expressões comuns ("ontem", "dia 11",
"semana passada", "junho").
Camada B: LLM fallback opcional para expressões que o dateparser não resolve
("antes do feriado"). Injetável; ausente => simplesmente retorna None.

`now_fn` é injetável para tornar os testes determinísticos.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

import dateparser
from dateparser.search import search_dates

from .schemas import TemporalRange

_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

_DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "past",
    "DATE_ORDER": "DMY",  # PT-BR: dia/mês/ano
}


def _strip(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class TemporalLLM(Protocol):
    """Contrato do fallback LLM (implementação concreta usa Pydantic AI)."""

    async def extract(self, query: str, now: datetime) -> Optional[TemporalRange]: ...


class TemporalExtractor:
    def __init__(
        self,
        llm: Optional[TemporalLLM] = None,
        now_fn: Callable[[], datetime] = datetime.now,
    ):
        self._llm = llm
        self._now_fn = now_fn

    async def extract(self, query: str) -> Optional[TemporalRange]:
        now = self._now_fn()

        # Camada A0 — datas explícitas por regex.
        # dateparser 1.4 não resolve o prefixo coloquial "dia N" (ex.: "dia 11
        # de junho" → None), então capturamos esses casos de forma determinística.
        explicit = self._parse_explicit(query, now)
        if explicit is not None:
            return explicit

        # Camada A — dateparser
        try:
            found = search_dates(
                query,
                languages=["pt"],
                settings={**_DATEPARSER_SETTINGS, "RELATIVE_BASE": now},
            )
        except Exception:
            found = None

        if found:
            expression, parsed = found[0]  # primeira expressão temporal
            return self._expand_to_range(parsed, expression, now)

        # Camada B — LLM fallback (se configurado)
        if self._llm is not None:
            try:
                return await self._llm.extract(query, now)
            except Exception:
                return None

        return None

    # --------------------------------------------------------------- explicit

    # "dia 11", "dia 11 de junho"
    _RE_DIA = re.compile(r"\bdia\s+(\d{1,2})(?:\s+de\s+([a-z]+))?")
    # "11/06", "11/06/2026"
    _RE_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")

    def _parse_explicit(self, query: str, now: datetime) -> Optional[TemporalRange]:
        norm = _strip(query)

        m = self._RE_DIA.search(norm)
        if m:
            day = int(m.group(1))
            month_token = m.group(2)
            month = _MONTHS.get(month_token) if month_token else None
            parsed = self._day_in_past(now, day, month)
            if parsed is not None:
                start, end = self._day_bounds(parsed)
                return TemporalRange(
                    start=start, end=end, expression=m.group(0), detection_method="explicit"
                )

        m = self._RE_SLASH.search(norm)
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else now.year
            if m.group(3) and year < 100:  # "26" -> 2026
                year += 2000
            try:
                parsed = datetime(year, month, day)
            except ValueError:
                return None
            start, end = self._day_bounds(parsed)
            return TemporalRange(
                start=start, end=end, expression=m.group(0), detection_method="explicit"
            )

        return None

    @staticmethod
    def _day_in_past(now: datetime, day: int, month: Optional[int]) -> Optional[datetime]:
        """Resolve "dia N" preferindo o passado (diário é sobre o que já ocorreu).

        Sem mês: usa o mês atual se N <= hoje, senão o mês anterior.
        Com mês: usa o mês dado (ano atual; recua um ano se cair no futuro).
        """
        if month is None:
            year, mon = now.year, now.month
            if day > now.day:  # ainda não chegou neste mês → mês anterior
                mon -= 1
                if mon == 0:
                    mon, year = 12, year - 1
        else:
            year, mon = now.year, month
        try:
            parsed = datetime(year, mon, day)
        except ValueError:
            return None
        if parsed > now:  # mês explícito que caiu no futuro → ano anterior
            try:
                parsed = parsed.replace(year=year - 1)
            except ValueError:
                return None
        return parsed

    # ------------------------------------------------------------------ expand

    def _expand_to_range(
        self, parsed: datetime, expression: str, now: datetime
    ) -> TemporalRange:
        """Expande um instante detectado para uma janela conforme a granularidade.

        - mês (nome do mês sem dia, ou "mes passado") → mês inteiro
        - semana ("semana passada") → semana ISO (segunda→domingo) que contém a data
        - dia (default) → dia inteiro 00:00:00 → 23:59:59
        """
        norm = _strip(expression)

        # Granularidade de mês: contém nome de mês e NÃO contém número de dia.
        has_month_name = any(m in norm for m in _MONTHS)
        has_day_number = re.search(r"\b\d{1,2}\b", norm) is not None
        if (has_month_name and not has_day_number) or "mes" in norm:
            start, end = self._month_bounds(parsed)
            return TemporalRange(
                start=start, end=end, expression=expression, detection_method="dateparser"
            )

        # Granularidade de semana.
        if "semana" in norm:
            start, end = self._week_bounds(parsed)
            return TemporalRange(
                start=start, end=end, expression=expression, detection_method="dateparser"
            )

        # Default: dia inteiro.
        start, end = self._day_bounds(parsed)
        method = "explicit" if re.search(r"\d{1,2}/\d{1,2}", expression) else "dateparser"
        return TemporalRange(
            start=start, end=end, expression=expression, detection_method=method
        )

    @staticmethod
    def _day_bounds(d: datetime) -> tuple[datetime, datetime]:
        start = d.replace(hour=0, minute=0, second=0, microsecond=0)
        end = d.replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end

    @staticmethod
    def _month_bounds(d: datetime) -> tuple[datetime, datetime]:
        last_day = calendar.monthrange(d.year, d.month)[1]
        start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = d.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
        return start, end

    @staticmethod
    def _week_bounds(d: datetime) -> tuple[datetime, datetime]:
        monday = d - timedelta(days=d.weekday())
        sunday = monday + timedelta(days=6)
        start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = sunday.replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end
