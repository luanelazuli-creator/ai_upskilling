"""
Memória Semântica - Armazenamento de fatos e conhecimento aprendido
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any


class SemanticMemory:
    """
    Memória semântica - Armazena fatos, conceitos e conhecimento.
    
    Funcionalidades:
    - Armazenar fatos estruturados
    - Recuperação por keywords
    - Grafo de relações entre conceitos
    - Persistência em JSON
    """
    
    def __init__(self, storage_path: str = "./data/semantic_memory.json"):
        """
        Inicializar memória semântica.
        
        Args:
            storage_path: Caminho para arquivo JSON de armazenamento
        """
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Estrutura interna
        self._facts: Dict[str, Dict[str, Any]] = {}
        self._concepts: Dict[str, Set[str]] = {}  # Mapeamento conceito -> keywords
        self._relations: Dict[str, List[str]] = {}  # Relações entre conceitos
        
        # Carregar dados existentes
        self._load()
    
    def add_fact(
        self,
        fact_id: str,
        content: str,
        keywords: Optional[List[str]] = None,
        confidence: float = 0.9,
        source: Optional[str] = None
    ) -> None:
        """
        Adicionar um fato à memória semântica.
        
        Args:
            fact_id: ID único do fato
            content: Conteúdo/descrição do fato
            keywords: Palavras-chave associadas
            confidence: Nível de confiança do fato (0-1)
            source: Fonte do fato (ex: document_name)
        """
        keywords = keywords or []
        
        self._facts[fact_id] = {
            "id": fact_id,
            "content": content,
            "keywords": keywords,
            "confidence": confidence,
            "source": source,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
            "access_count": 0
        }
        
        # Atualizar índice de conceitos
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower not in self._concepts:
                self._concepts[keyword_lower] = set()
            self._concepts[keyword_lower].add(fact_id)
        
        self._save()
    
    def get_fact(self, fact_id: str) -> Optional[Dict[str, Any]]:
        """
        Recuperar um fato específico.
        
        Args:
            fact_id: ID do fato
        
        Returns:
            Dicionário com fato ou None
        """
        if fact_id in self._facts:
            fact = self._facts[fact_id]
            fact["access_count"] += 1
            self._save()
            return fact
        return None
    
    def search_by_keyword(
        self,
        keyword: str,
        exact_match: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Buscar fatos por palavra-chave.
        
        Args:
            keyword: Palavra-chave a buscar
            exact_match: Se True, busca exata; se False, busca parcial
        
        Returns:
            Lista de fatos correspondentes
        """
        keyword_lower = keyword.lower()
        matching_facts = []
        
        if exact_match:
            # Busca exata
            if keyword_lower in self._concepts:
                fact_ids = self._concepts[keyword_lower]
                matching_facts = [
                    self._facts[fid] for fid in fact_ids
                    if fid in self._facts
                ]
        else:
            # Busca parcial em todas as keywords
            for keyword_key, fact_ids in self._concepts.items():
                if keyword_lower in keyword_key:
                    for fact_id in fact_ids:
                        if fact_id in self._facts:
                            fact = self._facts[fact_id]
                            if fact not in matching_facts:
                                matching_facts.append(fact)
        
        return matching_facts
    
    def add_relation(
        self,
        source_fact_id: str,
        target_fact_id: str,
        relation_type: str = "related"
    ) -> None:
        """
        Adicionar relação entre dois fatos.
        
        Args:
            source_fact_id: ID do fato origem
            target_fact_id: ID do fato destino
            relation_type: Tipo de relação (ex: "parent", "child", "related")
        """
        relation_key = f"{source_fact_id}_{relation_type}"
        
        if relation_key not in self._relations:
            self._relations[relation_key] = []
        
        if target_fact_id not in self._relations[relation_key]:
            self._relations[relation_key].append(target_fact_id)
        
        self._save()
    
    def get_related_facts(
        self,
        fact_id: str,
        relation_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recuperar fatos relacionados.
        
        Args:
            fact_id: ID do fato
            relation_type: Tipo de relação (opcional)
        
        Returns:
            Lista de fatos relacionados
        """
        related = []
        
        for rel_key, target_ids in self._relations.items():
            source_id, rel_type = rel_key.rsplit("_", 1)
            
            if source_id == fact_id:
                if relation_type is None or rel_type == relation_type:
                    for target_id in target_ids:
                        if target_id in self._facts:
                            related.append(self._facts[target_id])
        
        return related
    
    def delete_fact(self, fact_id: str) -> bool:
        """
        Deletar um fato.
        
        Args:
            fact_id: ID do fato
        
        Returns:
            True se deletado, False se não encontrado
        """
        if fact_id not in self._facts:
            return False
        
        # Remover do índice de conceitos
        fact = self._facts[fact_id]
        for keyword in fact.get("keywords", []):
            keyword_lower = keyword.lower()
            if keyword_lower in self._concepts:
                self._concepts[keyword_lower].discard(fact_id)
                if not self._concepts[keyword_lower]:
                    del self._concepts[keyword_lower]
        
        # Remover relações
        keys_to_delete = [k for k in self._relations.keys() 
                         if k.startswith(fact_id + "_")]
        for key in keys_to_delete:
            del self._relations[key]
        
        # Remover fato
        del self._facts[fact_id]
        self._save()
        
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Obter estatísticas da memória semântica.
        
        Returns:
            Dicionário com estatísticas
        """
        total_access = sum(f.get("access_count", 0) for f in self._facts.values())
        
        return {
            "total_facts": len(self._facts),
            "total_concepts": len(self._concepts),
            "total_relations": len(self._relations),
            "total_accesses": total_access,
            "avg_confidence": sum(f.get("confidence", 0) for f in self._facts.values()) / len(self._facts) if self._facts else 0
        }
    
    def export_to_json(self, output_file: str) -> None:
        """
        Exportar memória para JSON.
        
        Args:
            output_file: Caminho do arquivo de saída
        """
        export_data = {
            "facts": self._facts,
            "relations": self._relations,
            "exported_at": datetime.utcnow().isoformat(),
            "statistics": self.get_statistics()
        }
        
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
    
    def _save(self) -> None:
        """Salvar memória em arquivo."""
        data = {
            "facts": self._facts,
            "concepts": {k: list(v) for k, v in self._concepts.items()},
            "relations": self._relations,
            "last_updated": datetime.utcnow().isoformat()
        }
        
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def _load(self) -> None:
        """Carregar memória de arquivo."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self._facts = data.get("facts", {})
                self._concepts = {
                    k: set(v) for k, v in data.get("concepts", {}).items()
                }
                self._relations = data.get("relations", {})
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️  Erro ao carregar memória semântica: {e}")
