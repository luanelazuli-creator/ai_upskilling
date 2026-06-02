#!/usr/bin/env python3
"""
Script para converter documentos (DOCX, XLSX) para Markdown e indexar no RAG
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def convert_docx_to_md(docx_path: str) -> str:
    """
    Converte arquivo .docx para Markdown.
    
    Args:
        docx_path: Caminho para arquivo .docx
    
    Returns:
        Conteúdo em Markdown
    """
    if not HAS_DOCX:
        raise ImportError("python-docx não está instalado. Execute: pip install python-docx")
    
    doc = Document(docx_path)
    md_content = []
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        
        # Detectar nível de heading
        if para.style.name.startswith('Heading'):
            try:
                level = int(para.style.name.split()[-1])
                md_content.append(f"{'#' * level} {text}")
            except (ValueError, IndexError):
                md_content.append(f"## {text}")
        else:
            md_content.append(text)
    
    # Adicionar tabelas
    for table in doc.tables:
        md_content.append("\n")
        for i, row in enumerate(table.rows):
            cells = [cell.text.strip() for cell in row.cells]
            md_content.append("| " + " | ".join(cells) + " |")
            
            # Separador após header
            if i == 0:
                md_content.append("|" + "|".join([" --- " for _ in cells]) + "|")
        md_content.append("\n")
    
    return "\n\n".join(md_content)


def convert_xlsx_to_md(xlsx_path: str) -> str:
    """
    Converte arquivo .xlsx para Markdown.
    
    Args:
        xlsx_path: Caminho para arquivo .xlsx
    
    Returns:
        Conteúdo em Markdown com tabelas
    """
    if not HAS_PANDAS:
        raise ImportError("pandas não está instalado. Execute: pip install pandas openpyxl")
    
    df = pd.read_excel(xlsx_path)
    return df.to_markdown(index=False)


def convert_data_directory(
    source_dir: str,
    target_dir: str,
    recursive: bool = True
) -> Dict[str, List[str]]:
    """
    Converte todos os documentos em um diretório.
    
    Args:
        source_dir: Diretório com documentos originais
        target_dir: Diretório de saída para Markdown
        recursive: Se True, processa subdiretórios
    
    Returns:
        Dicionário com estatísticas de conversão
    """
    source_path = Path(source_dir)
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "converted": [],
        "failed": [],
        "skipped": []
    }
    
    # Padrão de busca
    pattern = "**/*" if recursive else "*"
    
    print(f"🔄 Convertendo documentos de {source_dir}...")
    
    for file_path in source_path.glob(pattern):
        if not file_path.is_file():
            continue
        
        # Pular arquivos ocultos
        if file_path.name.startswith("."):
            continue
        
        # Processar por tipo
        try:
            if file_path.suffix.lower() == ".docx":
                print(f"  📄 Convertendo {file_path.name}...", end=" ")
                md_content = convert_docx_to_md(str(file_path))
                
                # Manter estrutura de diretório
                rel_path = file_path.relative_to(source_path)
                target_file = target_path / rel_path.parent / (file_path.stem + ".md")
                target_file.parent.mkdir(parents=True, exist_ok=True)
                
                target_file.write_text(md_content, encoding='utf-8')
                stats["converted"].append(str(rel_path))
                print("✓")
                
            elif file_path.suffix.lower() == ".xlsx":
                print(f"  📊 Convertendo {file_path.name}...", end=" ")
                md_content = convert_xlsx_to_md(str(file_path))
                
                rel_path = file_path.relative_to(source_path)
                target_file = target_path / rel_path.parent / (file_path.stem + ".md")
                target_file.parent.mkdir(parents=True, exist_ok=True)
                
                target_file.write_text(md_content, encoding='utf-8')
                stats["converted"].append(str(rel_path))
                print("✓")
                
        except Exception as e:
            stats["failed"].append(f"{file_path.name}: {str(e)}")
            print(f"✗ Erro: {e}")
    
    # Resumo
    print(f"\n📊 Resumo:")
    print(f"  ✓ Convertidos: {len(stats['converted'])}")
    print(f"  ✗ Falhados: {len(stats['failed'])}")
    
    if stats["failed"]:
        print("\n  Erros:")
        for error in stats["failed"]:
            print(f"    - {error}")
    
    return stats


def main():
    """Ponto de entrada do script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Converter documentos DOCX/XLSX para Markdown"
    )
    parser.add_argument("source_dir", help="Diretório com documentos originais")
    parser.add_argument("--output", "-o", default="./data/converted_docs",
                       help="Diretório de saída (padrão: ./data/converted_docs)")
    parser.add_argument("--no-recursive", action="store_true",
                       help="Não processar subdiretórios")
    
    args = parser.parse_args()
    
    stats = convert_data_directory(
        args.source_dir,
        args.output,
        recursive=not args.no_recursive
    )
    
    return 0 if not stats["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
