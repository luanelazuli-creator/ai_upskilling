"""Gera dados fictícios para testar o pipeline de ingestão (SPEC-004).

Espelha a estrutura real descrita na SPEC-002 e injeta PII proposital
(emails, telefones, CPF) para validar a política de sanitização:
    - diário/cursos/manuais  -> sanitização agressiva (PII vira [REDACTED_*])
    - referências/stakeholders -> mascarar só email/telefone (mantém nome/cargo)

Uso: python -m scripts.make_fake_data
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402
from openpyxl import Workbook  # noqa: E402

DATA = Path("data")


def _docx(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading(title, level=1)
    for heading, body in sections:
        doc.add_heading(heading, level=2)
        for para in body.strip().split("\n"):
            doc.add_paragraph(para.strip())
    doc.save(str(path))
    print(f"  docx  {path}")


def _xlsx(path: Path, headers: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(str(path))
    print(f"  xlsx  {path}")


def _text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"  text  {path}")


def build() -> None:
    print("Gerando dados fictícios em ./data ...\n")

    # --- DIÁRIO (PII agressivo) ---
    _docx(
        DATA / "diario/2026/06/Dia 11 - Keep Studying.docx",
        "Dia 11 - Keep Studying",
        [
            (
                "Atividades",
                "Estudei embeddings e bancos vetoriais com ChromaDB.\n"
                "Revisei a arquitetura de memória do Second Brain.",
            ),
            (
                "Impedimentos",
                "Fiquei travada na configuração do Ollama por causa da porta 11434.\n"
                "Liguei para o suporte no (11) 98765-4321 para resolver.",
            ),
            (
                "Pendências",
                "Terminar a SPEC-004 e validar o pipeline de ingestão.",
            ),
        ],
    )
    _docx(
        DATA / "diario/2026/06/Dia 12 - Studying MCP.docx",
        "Dia 12 - Studying MCP",
        [
            (
                "Atividades",
                "Aprofundei no Model Context Protocol (MCP).\n"
                "Testei integração de ferramentas com agentes Pydantic AI.",
            ),
            (
                "Decisões",
                "Decidi usar busca híbrida na memória episódica.",
            ),
        ],
    )

    # --- CURSOS ---
    _xlsx(
        DATA / "cursos/Cursos Feitos.xlsx",
        ["Curso", "Status", "Plataforma", "Concluido_em"],
        [
            ["Data Engineer Certificate", "em_andamento", "DataCamp", ""],
            ["Machine Learning Specialization", "concluido", "Coursera", "2025-12-10"],
            ["Pydantic AI Deep Dive", "planejado", "YouTube", ""],
        ],
    )
    _docx(
        DATA / "cursos/Data Engineer Certificate.docx",
        "Data Engineer Certificate",
        [
            (
                "Onde Parei",
                "Módulo 4: modelagem dimensional e data warehouses.\n"
                "Próximo: pipelines com Airflow.",
            ),
            (
                "Insights",
                "Particionamento melhora performance de consultas analíticas.",
            ),
        ],
    )
    _text(
        DATA / "cursos/Golden Prompts/prompt_pesquisa_academica.md",
        """
# Prompt: Pesquisa Acadêmica

Você é um pesquisador rigoroso. Dado um tema, retorne:
1. Definição formal
2. Principais autores e papers seminais
3. Lacunas de pesquisa atuais
4. Sugestão de metodologia

Sempre cite fontes e evite afirmações sem evidência.
""",
    )

    # --- REFERÊNCIAS ---
    _xlsx(
        DATA / "referencias/Glossário.xlsx",
        ["Termo", "Definicao", "Categoria"],
        [
            ["RAG", "Retrieval-Augmented Generation", "AI"],
            ["MCP", "Model Context Protocol para conectar ferramentas a agentes", "AI"],
            ["OTel", "OpenTelemetry, padrão de observabilidade", "Infra"],
            ["PII", "Personally Identifiable Information", "Privacidade"],
        ],
    )
    # Stakeholders: PII deve ser MASCARADO só nos contatos (nome/cargo permanecem).
    _xlsx(
        DATA / "referencias/Pessoas Importantes.xlsx",
        ["Nome", "Cargo", "Email", "Telefone"],
        [
            ["Ana Souza", "Product Manager - Plataforma", "ana.souza@empresa.com", "(11) 91234-5678"],
            ["Bruno Lima", "Tech Lead - Dados", "bruno.lima@empresa.com", "(21) 99876-5432"],
            ["Carla Dias", "Engineering Manager", "carla.dias@empresa.com", "(31) 98765-1234"],
        ],
    )
    _docx(
        DATA / "referencias/Acessos sistemas.docx",
        "Acessos a Sistemas",
        [
            (
                "Ponto Eletrônico",
                "Acesse o portal de RH e registre entrada/saída diariamente.",
            ),
            (
                "VPN",
                "Solicite credenciais ao time de infraestrutura antes do primeiro acesso.",
            ),
        ],
    )

    print("\nDados fictícios gerados com sucesso.")


if __name__ == "__main__":
    build()
