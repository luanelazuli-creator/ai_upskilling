"""
Módulo de Observabilidade - OpenTelemetry Stack
"""

from .tracer import get_tracer, init_tracer
from .instrumentation import trace_agent_call

__all__ = [
    "get_tracer",
    "init_tracer",
    "trace_agent_call",
]
