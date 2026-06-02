"""
Configuração de tracer OpenTelemetry com exportadores locais
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace.export import SpanExportResult

try:
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    HAS_JAEGER = True
except ImportError:
    HAS_JAEGER = False


class LocalJSONExporter(SpanExporter):
    """Exportador customizado que salva traces em JSON local."""
    
    def __init__(self, output_dir: str = "./observability/dashboards"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export(self, spans: List) -> SpanExportResult:
        """Exporta spans para JSON."""
        try:
            for span in spans:
                trace_dict = {
                    "timestamp": datetime.now().isoformat(),
                    "trace_id": str(span.context.trace_id),
                    "span_id": str(span.context.span_id),
                    "parent_span_id": str(span.parent.span_id) if span.parent else None,
                    "name": span.name,
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "duration_ms": (span.end_time - span.start_time) / 1e6 if span.end_time else None,
                    "attributes": dict(span.attributes or {}),
                    "status": str(span.status),
                    "events": [
                        {
                            "name": event.name,
                            "timestamp": event.timestamp,
                            "attributes": dict(event.attributes or {})
                        }
                        for event in span.events
                    ] if hasattr(span, 'events') else []
                }
                
                filename = self.output_dir / f"trace_{span.context.trace_id}_{datetime.now().timestamp()}.json"
                with open(filename, 'w') as f:
                    json.dump(trace_dict, f, indent=2, default=str)
            
            return SpanExportResult.SUCCESS
        except Exception as e:
            print(f"❌ Erro ao exportar spans: {e}")
            return SpanExportResult.FAILURE
    
    def shutdown(self) -> None:
        """Shutdown do exportador."""
        pass
    
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush dos spans pendentes."""
        return True


def init_tracer(
    service_name: str = "secondbrain",
    use_jaeger: bool = False,
    output_dir: str = "./observability/dashboards"
) -> TracerProvider:
    """
    Inicializa tracer com exportadores locais.
    
    Args:
        service_name: Nome do serviço para rastreamento
        use_jaeger: Se True, tenta conectar a um Jaeger local
        output_dir: Diretório para exportar traces em JSON
    
    Returns:
        TracerProvider configurado
    """
    
    resource = Resource.create({SERVICE_NAME: service_name})
    tracer_provider = TracerProvider(resource=resource)
    
    # Exportador JSON local
    json_exporter = LocalJSONExporter(output_dir=output_dir)
    tracer_provider.add_span_processor(SimpleSpanProcessor(json_exporter))
    
    # Exportador Jaeger (opcional, se disponível localmente)
    if use_jaeger and HAS_JAEGER:
        try:
            jaeger_exporter = JaegerExporter(
                agent_host_name="localhost",
                agent_port=6831,
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
            print("✓ Jaeger exporter conectado em localhost:6831")
        except Exception as e:
            print(f"⚠️  Jaeger não disponível: {e}")
    
    trace.set_tracer_provider(tracer_provider)
    return tracer_provider


# Global tracer instance
_tracer: Optional[trace.Tracer] = None
_tracer_initialized = False


def get_tracer(service_name: str = "secondbrain") -> trace.Tracer:
    """
    Get or initialize global tracer.
    
    Args:
        service_name: Nome do serviço
    
    Returns:
        Instância do tracer global
    """
    global _tracer, _tracer_initialized
    
    if _tracer is None:
        if not _tracer_initialized:
            init_tracer(service_name)
            _tracer_initialized = True
        _tracer = trace.get_tracer(__name__)
    
    return _tracer


def reset_tracer() -> None:
    """Reset do tracer global (útil para testes)."""
    global _tracer, _tracer_initialized
    _tracer = None
    _tracer_initialized = False
