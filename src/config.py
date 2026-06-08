"""Configuração centralizada (SPEC-003-2 / SPEC-004)."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "development"

    # --- Identidade do usuário (single-user no MVP; SPEC-003-2 §4) ---
    user_id: str = "luane"
    session_id: str = ""  # vazio => orquestrador gera UUID por sessão

    # --- Ollama ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    ollama_temperature: float = 0.7
    ollama_max_tokens: int = 2048

    # --- Agente 1 (triagem) — SPEC-005 ---
    ollama_triage_model: str = "qwen2.5:3b"
    ollama_triage_temperature: float = 0.1
    ollama_triage_timeout_s: int = 10
    # Limiares da política híbrida de triagem (SPEC-005 §4)
    triage_rules_confidence_threshold: float = 0.7  # >= => resolve só com regras
    triage_clarify_confidence_threshold: float = 0.6  # < => pede clarificação
    triage_max_clarification_rounds: int = 2

    # --- Agente 2 (síntese) — SPEC-006 ---
    ollama_synthesis_model: str = "mistral"
    ollama_synthesis_temperature: float = 0.3  # mais baixa: favorece ancoragem
    ollama_synthesis_max_tokens: int = 1024
    ollama_synthesis_timeout_s: int = 30
    # Limiar mínimo de relevância máxima do bundle (SPEC-006 §5).
    # Abaixo disso, devolve NoEvidence(low_relevance) sem chamar o LLM.
    synthesis_min_relevance_score: float = 0.25

    # --- Agente ---
    agent_name: str = "SecondBrain-Basic"
    agent_version: str = "0.1.0"

    # --- Dados e paths ---
    data_root: str = "./data"
    processed_root: str = "./data/processed"
    vectorstore_path: str = "./data/vectorstore"  # ChromaDB unificado (SPEC-003-2 §5)
    episodic_metadata_db: str = "./data/episodic_metadata.db"

    # --- Embedding (SPEC-004 §5) ---
    # "chroma_default" -> ONNX all-MiniLM-L6-v2 (leve, sem torch)
    # "fake"           -> embedder determinístico por hash (testes de mecânica)
    # "<model_name>"   -> sentence-transformers (ex.: paraphrase-multilingual-MiniLM-L12-v2)
    embedding_model: str = "chroma_default"

    # --- Coleções ChromaDB ---
    collection_diario: str = "diario"
    collection_cursos: str = "cursos"
    collection_referencias: str = "referencias"
    collection_user_facts: str = "user_facts"
    collection_episodic: str = "episodic_conversations"

    # --- Chunking adaptativo (SPEC-004 §4) ---
    chunk_size_default: int = 1000
    chunk_overlap_default: int = 200

    # --- Retenção (SPEC-MEM §7) ---
    episodic_retention_days: int = 90

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
