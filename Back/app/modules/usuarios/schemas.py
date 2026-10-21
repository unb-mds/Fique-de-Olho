
from pydantic import BaseModel, EmailStr, Field


class UsuarioCadastro(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)


class UsuarioLogin(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class UsuarioResposta(BaseModel):
    id: int
    nome: str
    email: EmailStr

    class Config:
        from_attributes = True