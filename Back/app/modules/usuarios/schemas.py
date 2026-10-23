"""Schemas Pydantic para validação e serialização do módulo de usuários e autenticação."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UsuarioCadastro(BaseModel):
    """Dados necessários para cadastrar um novo usuário no sistema."""
    nome: str = Field(min_length=1, max_length=255, description="Nome completo do usuário")
    email: EmailStr = Field(description="E-mail único do usuário")
    senha: str = Field(min_length=8, max_length=128, description="Senha com no mínimo 8 caracteres")


class UsuarioLogin(BaseModel):
    """Dados para autenticação de usuário via e-mail e senha."""
    email: EmailStr = Field(description="E-mail cadastrado")
    senha: str = Field(min_length=1, max_length=128, description="Senha do usuário")


class UsuarioResposta(BaseModel):
    """Representação pública de um usuário (sem dados sensíveis)."""
    id: int
    nome: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class TokenResposta(BaseModel):
    """Resposta com token Bearer/JWT após login bem-sucedido."""
    access_token: str = Field(description="Token JWT de acesso")
    token_type: str = Field(default="bearer", description="Tipo de autenticação (Bearer)")
    usuario: UsuarioResposta = Field(description="Dados públicos do usuário autenticado")


class TokenPayload(BaseModel):
    """Estrutura das claims principais decodificadas do JWT."""
    sub: Optional[str] = None
    email: Optional[EmailStr] = None
