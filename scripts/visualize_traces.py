#!/usr/bin/env python3
"""
Script para visualizar e analisar traces gerados pelo OpenTelemetry
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def load_trace_file(trace_path: str) -> Dict[str, Any]:
    """
    Carregar arquivo de trace JSON.
    
    Args:
        trace_path: Caminho para arquivo de trace
    
    Returns:
        Dicionário com dados do trace
    """
    with open(trace_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_traces(traces_dir: str) -> Dict[str, Any]:
    """
    Analisar todos os traces em um diretório.
    
    Args:
        traces_dir: Diretório com arquivos de trace
    
    Returns:
        Dicionário com análise consolidada
    """
    traces_path = Path(traces_dir)
    
    if not traces_path.exists():
        print(f"❌ Diretório não encontrado: {traces_dir}")
        return {}
    
    traces = []
    stats = {
        "total_traces": 0,
        "total_spans": 0,
        "successful_spans": 0,
        "failed_spans": 0,
        "total_duration_ms": 0,
        "avg_duration_ms": 0,
        "operations": {},
        "errors": []
    }
    
    # Carregar todos os traces
    print(f"📂 Analisando traces em {traces_dir}...")
    
    for trace_file in sorted(traces_path.glob("trace_*.json")):
        try:
            trace = load_trace_file(str(trace_file))
            traces.append(trace)
            
            # Atualizar estatísticas
            stats["total_spans"] += 1
            
            if trace.get("status") == "Status.OK":
                stats["successful_spans"] += 1
            else:
                stats["failed_spans"] += 1
                if "error" in trace:
                    stats["errors"].append({
                        "operation": trace.get("name"),
                        "error": trace.get("error"),
                        "timestamp": trace.get("timestamp")
                    })
            
            # Duração
            duration = trace.get("duration_ms", 0)
            if duration:
                stats["total_duration_ms"] += duration
            
            # Operações
            op_name = trace.get("name", "unknown")
            if op_name not in stats["operations"]:
                stats["operations"][op_name] = {
                    "count": 0,
                    "total_duration": 0,
                    "errors": 0
                }
            
            stats["operations"][op_name]["count"] += 1
            stats["operations"][op_name]["total_duration"] += duration
            
            if trace.get("status") != "Status.OK":
                stats["operations"][op_name]["errors"] += 1
                
        except json.JSONDecodeError as e:
            print(f"  ⚠️  Erro ao ler {trace_file.name}: {e}")
        except Exception as e:
            print(f"  ⚠️  Erro ao processar {trace_file.name}: {e}")
    
    # Calcular médias
    if stats["total_spans"] > 0:
        stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["total_spans"]
        stats["total_traces"] = len(set(t.get("trace_id") for t in traces))
    
    return stats, traces


def print_statistics(stats: Dict[str, Any]) -> None:
    """
    Imprimir estatísticas de forma legível.
    
    Args:
        stats: Dicionário com estatísticas
    """
    print("\n" + "="*60)
    print("📊 RESUMO DE TRACES")
    print("="*60)
    
    print(f"\n📈 Estatísticas Gerais:")
    print(f"  Total de Traces: {stats['total_traces']}")
    print(f"  Total de Spans: {stats['total_spans']}")
    print(f"  ✓ Bem-sucedidos: {stats['successful_spans']}")
    print(f"  ✗ Falhados: {stats['failed_spans']}")
    
    if stats['total_spans'] > 0:
        success_rate = (stats['successful_spans'] / stats['total_spans']) * 100
        print(f"  Taxa de sucesso: {success_rate:.1f}%")
    
    print(f"\n⏱️  Duração:")
    print(f"  Total: {stats['total_duration_ms']:.2f}ms")
    print(f"  Média: {stats['avg_duration_ms']:.2f}ms")
    
    if stats['operations']:
        print(f"\n📋 Operações:")
        for op_name, op_stats in sorted(
            stats['operations'].items(),
            key=lambda x: x[1]['total_duration'],
            reverse=True
        ):
            avg_duration = (op_stats['total_duration'] / op_stats['count']
                          if op_stats['count'] > 0 else 0)
            print(f"  {op_name}:")
            print(f"    Chamadas: {op_stats['count']}")
            print(f"    Duração total: {op_stats['total_duration']:.2f}ms")
            print(f"    Duração média: {avg_duration:.2f}ms")
            if op_stats['errors'] > 0:
                print(f"    Erros: {op_stats['errors']}")
    
    if stats['errors']:
        print(f"\n❌ Erros ({len(stats['errors'])}):")
        for error in stats['errors'][:5]:  # Mostrar apenas os 5 primeiros
            print(f"  {error['operation']}: {error['error']}")
        if len(stats['errors']) > 5:
            print(f"  ... e mais {len(stats['errors']) - 5} erros")
    
    print("\n" + "="*60 + "\n")


def export_analysis(
    stats: Dict[str, Any],
    traces: List[Dict[str, Any]],
    output_file: str
) -> None:
    """
    Exportar análise para arquivo JSON.
    
    Args:
        stats: Estatísticas consolidadas
        traces: Lista de traces individuais
        output_file: Caminho do arquivo de saída
    """
    export_data = {
        "generated_at": datetime.utcnow().isoformat(),
        "statistics": stats,
        "traces": traces[:100]  # Limitar a 100 traces para não ficar muito grande
    }
    
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"✓ Análise exportada para {output_file}")


def main():
    """Ponto de entrada do script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analisar traces OpenTelemetry"
    )
    parser.add_argument("traces_dir", 
                       help="Diretório com arquivos de trace")
    parser.add_argument("--output", "-o",
                       help="Arquivo de saída para análise (opcional)")
    parser.add_argument("--top-operations", "-t", type=int, default=5,
                       help="Número de top operações a mostrar")
    
    args = parser.parse_args()
    
    stats, traces = analyze_traces(args.traces_dir)
    
    if not stats:
        return 1
    
    print_statistics(stats)
    
    if args.output:
        export_analysis(stats, traces, args.output)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
