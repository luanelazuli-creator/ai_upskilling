"""Resolução de USER_ID/SESSION_ID (SPEC-003-2 §4)."""

from __future__ import annotations

import uuid
from typing import Optional


def resolve_session_id(env_value: Optional[str]) -> str:
    """Devolve o session_id efetivo para esta execução.

    Regra (SPEC-003-2 §4):
        - se `env_value` é uma string não-vazia, usa como-é (testes reprodutíveis);
        - caso contrário, gera um UUID v4 novo.
    """
    if env_value:
        return env_value
    return str(uuid.uuid4())
