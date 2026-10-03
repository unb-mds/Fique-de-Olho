# Fique de Olho - UnB Editais

Grupo G4 - Métodos de Desenvolvimento de Software 2026/2

## 🎯 Objetivo

O projeto facilita o acesso aos editais da Universidade de Brasília, centralizando,
filtrando e notificando as publicações para que estudantes não percam prazos de
bolsas, monitorias, PIBIC e transferências.

## 📚 Documentação

- [Pages](https://unb-mds.github.io/Fique-de-Olho/)
- [Figma](https://www.figma.com/board/Sw1R44AAXzZrW5eBolJybw/Template-MDS--c%C3%B3pia-limpa---c%C3%B3pia-?node-id=1-291)
- [protótipo de alta fidelidade](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1)

## ⚙️ Pré-requisitos

Para executar o projeto, instale:

- **Git**
- **Docker Desktop**, com o Docker Compose habilitado
- **Node.js 18+** e **npm** (para execução e build do frontend)

Para executar o backend localmente sem Docker, também são necessários **Python 3.12+** e `pip`.

## 🚀 Executando o projeto

### 1. Iniciar Banco de Dados (PostgreSQL) e Backend (FastAPI) via Docker Compose

A forma recomendada de executar os serviços de dados e API é pelo Docker Compose na raiz do repositório:

```powershell
docker compose up -d
```

Quando os containers estiverem em execução, acesse:

- **Documentação Swagger (OpenAPI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Documentação ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Healthcheck:** [http://localhost:8000/health](http://localhost:8000/health)

### 2. Iniciar o Frontend (React + TypeScript + Vite)

Em outro terminal, navegue até a pasta `Front/`, instale as dependências e inicie o servidor de desenvolvimento:

```powershell
cd Front
npm install
npm run dev
```

A interface web estará disponível em:
- **Aplicação Web:** [http://localhost:5173](http://localhost:5173)

---

## 🧪 Como Rodar os Testes Automatizados

### Testes do Backend (Pytest)
Com os containers do Docker ativos:

```powershell
docker exec -it fique-de-olho-api pytest -v
```

### Testes e Validação do Frontend (Lint e Build)
Na pasta `Front/`:

```powershell
npm run lint
npm run build
```

---

### Execução local do backend sem Docker (Opcional)

Na pasta `Back`, crie um ambiente virtual, instale as dependências e inicie o servidor:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

## 👥 Autores

<!-- Cada integrante adiciona seu nome manualmente abaixo -->

- 
-
-
-
