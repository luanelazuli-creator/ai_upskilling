"""
Decoradores para instrumentação automática de funções de agentes
"""

import asyncio
import functools
import time
from typing import Any, Callable, Optional, TypeVar, Union

from .tracer import get_tracer

F = TypeVar('F', bound=Callable[..., Any])


def trace_agent_call(operation_name: Optional[str] = None):
    """
    Decorador para rastrear chamadas de agentes.
    
    Funciona com funções sync e async automaticamente.
    
    Args:
        operation_name: Nome da operação para rastreamento (opcional)
    
    Example:
        @trace_agent_call("process_query")
        def my_agent_method(query: str) -> str:
            return f"Processado: {query}"
    """
    def decorator(func: F) -> F:
        op_name = operation_name or func.__qualname__
        
        # Detectar se é async ou sync
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = get_tracer()
                
                with tracer.start_as_current_span(op_name) as span:
                    start_time = time.time()
                    
                    # Adicionar informações de entrada
                    span.set_attribute("function_name", func.__qualname__)
                    span.set_attribute("args_count", len(args))
                    span.set_attribute("kwargs_keys", list(kwargs.keys()))
                    
                    # Limitar tamanho dos atributos para evitar problemas
                    args_str = str(args)[:200]
                    kwargs_str = str(kwargs)[:200]
                    span.set_attribute("args", args_str)
                    span.set_attribute("kwargs", kwargs_str)
                    
                    try:
                        result = await func(*args, **kwargs)
                        
                        # Sucesso
                        elapsed = time.time() - start_time
                        span.set_attribute("success", True)
                        span.set_attribute("duration_seconds", elapsed)
                        span.set_attribute("result_type", type(result).__name__)
                        
                        return result
                    except Exception as e:
                        # Erro
                        elapsed = time.time() - start_time
                        span.set_attribute("error", str(e))
                        span.set_attribute("error_type", type(e).__name__)
                        span.set_attribute("success", False)
                        span.set_attribute("duration_seconds", elapsed)
                        raise
            
            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = get_tracer()
                
                with tracer.start_as_current_span(op_name) as span:
                    start_time = time.time()
                    
                    # Adicionar informações de entrada
                    span.set_attribute("function_name", func.__qualname__)
                    span.set_attribute("args_count", len(args))
                    span.set_attribute("kwargs_keys", list(kwargs.keys()))
                    
                    # Limitar tamanho dos atributos para evitar problemas
                    args_str = str(args)[:200]
                    kwargs_str = str(kwargs)[:200]
                    span.set_attribute("args", args_str)
                    span.set_attribute("kwargs", kwargs_str)
                    
                    try:
                        result = func(*args, **kwargs)
                        
                        # Sucesso
                        elapsed = time.time() - start_time
                        span.set_attribute("success", True)
                        span.set_attribute("duration_seconds", elapsed)
                        span.set_attribute("result_type", type(result).__name__)
                        
                        return result
                    except Exception as e:
                        # Erro
                        elapsed = time.time() - start_time
                        span.set_attribute("error", str(e))
                        span.set_attribute("error_type", type(e).__name__)
                        span.set_attribute("success", False)
                        span.set_attribute("duration_seconds", elapsed)
                        raise
            
            return sync_wrapper  # type: ignore
    
    return decorator


def trace_performance(metric_name: str):
    """
    Decorador simples para registrar performance.
    
    Args:
        metric_name: Nome da métrica a ser rastreada
    """
    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = get_tracer()
                
                with tracer.start_as_current_span(f"metric:{metric_name}") as span:
                    start_time = time.time()
                    result = await func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    
                    span.set_attribute("duration_ms", elapsed * 1000)
                    return result
            
            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = get_tracer()
                
                with tracer.start_as_current_span(f"metric:{metric_name}") as span:
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    
                    span.set_attribute("duration_ms", elapsed * 1000)
                    return result
            
            return sync_wrapper  # type: ignore
    
    return decorator
