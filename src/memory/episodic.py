"""
Memória Episódica - Histórico de conversações persistente
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import json

try:
    from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer
    from sqlalchemy.orm import declarative_base, sessionmaker
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


if HAS_SQLALCHEMY:
    Base = declarative_base()

    class ConversationRecord(Base):
        """Modelo para armazenar registros de conversa."""
        __tablename__ = "conversations"
        
        id = Column(String, primary_key=True)
        user_id = Column(String, index=True)
        timestamp = Column(DateTime, default=datetime.utcnow, index=True)
        user_message = Column(Text)
        agent_response = Column(Text)
        metadata = Column(Text)  # JSON serialized
        tokens_used = Column(Integer, default=0)


class EpisodicMemory:
    """
    Memória episódica - Armazena histórico de conversações.
    
    Funcionalidades:
    - Persistência em SQLite
    - Recuperação de conversas por usuário
    - Limpeza automática de dados antigos
    - Busca por intervalo de tempo
    """
    
    def __init__(self, db_path: str = "./data/episodic_memory.db"):
        """
        Inicializar memória episódica.
        
        Args:
            db_path: Caminho para o banco SQLite
        
        Raises:
            ImportError: Se SQLAlchemy não estiver instalado
        """
        if not HAS_SQLALCHEMY:
            raise ImportError("SQLAlchemy não está instalado. Execute: pip install sqlalchemy")
        
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Engine e session factory
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def add_conversation(
        self,
        user_id: str,
        user_msg: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None,
        tokens_used: int = 0
    ) -> str:
        """
        Registrar uma conversa.
        
        Args:
            user_id: ID do usuário
            user_msg: Mensagem do usuário
            response: Resposta do agente
            metadata: Metadados adicionais
            tokens_used: Tokens utilizados na resposta
        
        Returns:
            ID do registro criado
        """
        session = self.SessionLocal()
        try:
            record_id = f"{user_id}_{datetime.utcnow().timestamp()}"
            
            record = ConversationRecord(
                id=record_id,
                user_id=user_id,
                user_message=user_msg,
                agent_response=response,
                metadata=json.dumps(metadata or {}),
                tokens_used=tokens_used
            )
            
            session.add(record)
            session.commit()
            
            return record_id
        finally:
            session.close()
    
    def get_recent_conversations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Recuperar conversas recentes de um usuário.
        
        Args:
            user_id: ID do usuário
            limit: Número máximo de registros
        
        Returns:
            Lista de conversas ordenadas por data recente
        """
        session = self.SessionLocal()
        try:
            records = session.query(ConversationRecord) \
                .filter(ConversationRecord.user_id == user_id) \
                .order_by(ConversationRecord.timestamp.desc()) \
                .limit(limit) \
                .all()
            
            return [self._record_to_dict(r) for r in records]
        finally:
            session.close()
    
    def get_conversation_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        Recuperar conversa específica por ID.
        
        Args:
            record_id: ID do registro
        
        Returns:
            Dicionário com conversa ou None
        """
        session = self.SessionLocal()
        try:
            record = session.query(ConversationRecord) \
                .filter(ConversationRecord.id == record_id) \
                .first()
            
            return self._record_to_dict(record) if record else None
        finally:
            session.close()
    
    def get_conversations_between(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Recuperar conversas em um intervalo de tempo.
        
        Args:
            user_id: ID do usuário
            start_date: Data inicial
            end_date: Data final
        
        Returns:
            Lista de conversas neste intervalo
        """
        session = self.SessionLocal()
        try:
            records = session.query(ConversationRecord) \
                .filter(ConversationRecord.user_id == user_id) \
                .filter(ConversationRecord.timestamp >= start_date) \
                .filter(ConversationRecord.timestamp <= end_date) \
                .order_by(ConversationRecord.timestamp.asc()) \
                .all()
            
            return [self._record_to_dict(r) for r in records]
        finally:
            session.close()
    
    def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        Obter estatísticas de um usuário.
        
        Args:
            user_id: ID do usuário
        
        Returns:
            Dicionário com estatísticas
        """
        session = self.SessionLocal()
        try:
            records = session.query(ConversationRecord) \
                .filter(ConversationRecord.user_id == user_id) \
                .all()
            
            if not records:
                return {
                    "user_id": user_id,
                    "total_conversations": 0,
                    "total_tokens": 0,
                    "avg_tokens": 0
                }
            
            total_tokens = sum(r.tokens_used for r in records)
            
            return {
                "user_id": user_id,
                "total_conversations": len(records),
                "first_interaction": records[0].timestamp.isoformat(),
                "last_interaction": records[-1].timestamp.isoformat(),
                "total_tokens": total_tokens,
                "avg_tokens": total_tokens // len(records) if records else 0
            }
        finally:
            session.close()
    
    def delete_conversation(self, record_id: str) -> bool:
        """
        Deletar registro de conversa.
        
        Args:
            record_id: ID do registro
        
        Returns:
            True se deletado, False se não encontrado
        """
        session = self.SessionLocal()
        try:
            record = session.query(ConversationRecord) \
                .filter(ConversationRecord.id == record_id) \
                .first()
            
            if record:
                session.delete(record)
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def cleanup_old_conversations(self, days_to_keep: int = 30) -> int:
        """
        Limpar conversas com mais de X dias.
        
        Args:
            days_to_keep: Número de dias a manter
        
        Returns:
            Número de registros deletados
        """
        from datetime import timedelta
        
        session = self.SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            deleted = session.query(ConversationRecord) \
                .filter(ConversationRecord.timestamp < cutoff_date) \
                .delete()
            
            session.commit()
            return deleted
        finally:
            session.close()
    
    def export_conversations(
        self,
        user_id: str,
        output_file: str
    ) -> int:
        """
        Exportar conversas de um usuário para JSON.
        
        Args:
            user_id: ID do usuário
            output_file: Caminho do arquivo de saída
        
        Returns:
            Número de conversas exportadas
        """
        conversations = self.get_recent_conversations(user_id, limit=10000)
        
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(conversations, f, indent=2, ensure_ascii=False, default=str)
        
        return len(conversations)
    
    @staticmethod
    def _record_to_dict(record) -> Dict[str, Any]:
        """Converter registro SQLAlchemy para dicionário."""
        return {
            "id": record.id,
            "user_id": record.user_id,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "user_message": record.user_message,
            "agent_response": record.agent_response,
            "metadata": json.loads(record.metadata) if record.metadata else {},
            "tokens_used": record.tokens_used
        }
