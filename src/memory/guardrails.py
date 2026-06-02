"""
Guardrails para detecção e remoção de PII (Personally Identifiable Information)
"""

import re
from typing import Dict, List, Optional, Set


class PIIGuardrails:
    """
    Remove ou mascara Informações Pessoalmente Identificáveis.
    
    Detecta e sanitiza:
    - CPF (formato brasileiro)
    - Telefone (formato brasileiro)
    - Email
    - Cartão de crédito
    - Nomes próprios (opcional)
    """
    
    # Padrões regex para detecção
    PATTERNS = {
        "cpf": r"\d{3}\.\d{3}\.\d{3}-\d{2}",
        "phone": r"\(\d{2}\)\s\d{4,5}-\d{4}",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "credit_card": r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
        "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "ssn": r"\d{3}-\d{2}-\d{4}",  # Social Security Number (USA)
    }
    
    # Padrões adicionais mais sensíveis
    ADDITIONAL_PATTERNS = {
        "date_dob": r"\d{1,2}/\d{1,2}/\d{4}",  # Data em formato DD/MM/YYYY ou MM/DD/YYYY
        "passport": r"[A-Z]{1,2}\d{6,9}",  # Número de passaporte simplificado
        "credit_card_detailed": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b",  # Visa, Mastercard, Amex
    }
    
    # Palavras-chave sensíveis
    SENSITIVE_KEYWORDS = {
        "password", "pwd", "secret", "token", "api_key", "apikey",
        "authorization", "auth_header", "bearer",
        "credit_card", "card_number", "account_number",
        "social_security", "ssn", "tax_id"
    }
    
    def __init__(self, additional_patterns: Optional[Dict[str, str]] = None):
        """
        Inicializar guardrails.
        
        Args:
            additional_patterns: Padrões regex adicionais customizados
        """
        self.patterns = self.PATTERNS.copy()
        if additional_patterns:
            self.patterns.update(additional_patterns)
    
    @staticmethod
    def sanitize(text: str, redaction_marker: str = "[REDACTED]") -> str:
        """
        Remove PII de um texto.
        
        Args:
            text: Texto a ser sanitizado
            redaction_marker: Marcador a usar no lugar do PII
        
        Returns:
            Texto sanitizado
        """
        sanitized = text
        
        for pii_type, pattern in PIIGuardrails.PATTERNS.items():
            sanitized = re.sub(
                pattern,
                f"{redaction_marker}_{pii_type.upper()}",
                sanitized,
                flags=re.IGNORECASE
            )
        
        return sanitized
    
    @staticmethod
    def sanitize_dict(
        data: Dict,
        redaction_marker: str = "[REDACTED]"
    ) -> Dict:
        """
        Sanitizar todas as strings em um dicionário.
        
        Args:
            data: Dicionário com dados
            redaction_marker: Marcador a usar
        
        Returns:
            Dicionário com PII removido
        """
        sanitized = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = PIIGuardrails.sanitize(value, redaction_marker)
            elif isinstance(value, dict):
                sanitized[key] = PIIGuardrails.sanitize_dict(value, redaction_marker)
            elif isinstance(value, list):
                sanitized[key] = [
                    PIIGuardrails.sanitize(item, redaction_marker) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def extract_pii(text: str) -> Dict[str, List[str]]:
        """
        Extrai PII encontrados no texto.
        
        Args:
            text: Texto a analisar
        
        Returns:
            Dicionário com tipos de PII e valores encontrados
        """
        found_pii = {}
        
        for pii_type, pattern in PIIGuardrails.PATTERNS.items():
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            if matches:
                found_pii[pii_type] = list(set(matches))  # Remove duplicatas
        
        return found_pii
    
    @staticmethod
    def has_pii(text: str) -> bool:
        """
        Verificar se texto contém PII.
        
        Args:
            text: Texto a verificar
        
        Returns:
            True se contém PII, False caso contrário
        """
        return len(PIIGuardrails.extract_pii(text)) > 0
    
    @staticmethod
    def get_pii_statistics(text: str) -> Dict[str, int]:
        """
        Obter estatísticas de PII encontrados.
        
        Args:
            text: Texto a analisar
        
        Returns:
            Dicionário com contagem por tipo
        """
        pii_found = PIIGuardrails.extract_pii(text)
        return {
            pii_type: len(values)
            for pii_type, values in pii_found.items()
        }
