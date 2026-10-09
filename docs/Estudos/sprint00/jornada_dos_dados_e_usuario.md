# Jornada dos Dados e Jornada do Usuário

Este documento apresenta os principais fluxos de dados e de interação do usuário no projeto Fique de Olho.

## Jornada dos Dados

A Jornada dos Dados representa o caminho percorrido pelas informações dos editais, desde a origem dos dados até a apresentação ao usuário na plataforma.

### 1. Origem dos dados

Os dados utilizados pelo sistema são provenientes do portal de editais do DEG (Decanato de Ensino de Graduação) da Universidade de Brasília.

### 2. Coleta dos dados

A coleta é realizada por meio de um scraper, responsável por acessar o portal e obter as informações disponíveis sobre os editais.

O processo é organizado em dois níveis:

- Nível 1: coleta informações gerais dos editais, como título, link e data de publicação.
- Nível 2: acessa a página individual de cada edital para identificar informações e documentos disponíveis.

### 3. Processamento dos dados

Após a coleta, os dados são organizados e preparados para serem utilizados pelo sistema. Essa etapa permite transformar as informações obtidas pelo scraper em dados que possam ser disponibilizados pelo backend.

### 4. Armazenamento

O backend utiliza PostgreSQL como banco de dados e SQLAlchemy como ORM. A estrutura do banco é gerenciada por migrações utilizando Alembic.

A persistência dos dados faz parte da evolução do backend, permitindo armazenar e consultar as informações coletadas dos editais.

### 5. Backend e API

O backend foi desenvolvido utilizando Python e FastAPI.

A API disponibiliza endpoints responsáveis pela consulta dos editais, incluindo:

- `GET /health` - verifica a disponibilidade da API.
- `GET /api/v1/editais/` - lista os editais disponíveis.
- `GET /api/v1/editais/{id}` - consulta um edital pelo seu identificador.

### 6. Apresentação no frontend

O frontend recebe as informações disponibilizadas pelo backend e apresenta os editais ao usuário por meio da interface da plataforma.

### Fluxo visual da Jornada dos Dados

```text
Portal de Editais do DEG
          ↓
        Scraper
          ↓
Coleta das informações
          ↓
Processamento dos dados
          ↓
   Banco de Dados
      PostgreSQL
          ↓
     Backend / API
        FastAPI
          ↓
       Frontend
          ↓
        Usuário
```

**Fluxo resumido:**

Fonte dos dados → Coleta → Processamento → Banco de dados → Backend/API → Frontend → Usuário

---

## Jornada do Usuário

A Jornada do Usuário representa as principais etapas de interação de uma pessoa com a plataforma Fique de Olho.

### 1. Acesso à plataforma

O usuário acessa a página inicial da plataforma, onde pode visualizar e consultar os editais disponíveis.

### 2. Busca e consulta de editais

O usuário pode consultar os editais apresentados pela plataforma e procurar oportunidades de seu interesse.

### 3. Utilização de filtros

Os mecanismos de busca e filtros auxiliam o usuário a encontrar editais de acordo com as informações disponíveis na plataforma.

### 4. Seleção do edital

Após localizar um edital de interesse, o usuário pode selecioná-lo para acessar suas informações.

### 5. Visualização das informações

A página do edital apresenta as informações disponíveis para que o usuário possa analisar os dados e documentos relacionados à oportunidade.

### Fluxo visual da Jornada do Usuário

```text
Acesso à plataforma
        ↓
  Busca / Consulta
        ↓
      Filtros
        ↓
 Seleção do edital
        ↓
Visualização das informações
```

**Fluxo resumido:**

Acesso à plataforma → Busca/consulta → Filtros → Seleção do edital → Visualização das informações

---

## Considerações finais

A documentação das duas jornadas facilita a compreensão do funcionamento do projeto. A Jornada dos Dados demonstra como as informações percorrem o sistema, enquanto a Jornada do Usuário apresenta como ocorre a interação com a plataforma.