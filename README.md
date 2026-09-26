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

- Git
- Docker Desktop, com o Docker Compose habilitado

Para executar o backend sem Docker, também são necessários Python 3.12 ou superior e `pip`.

## 🚀 Executando o backend

O backend utiliza FastAPI e PostgreSQL. A forma recomendada de executar os serviços é pelo Docker Compose:

```powershell
cd Back
docker compose up --build
```

Quando os containers estiverem em execução, acesse:

- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Healthcheck: [http://localhost:8000/health](http://localhost:8000/health)

Para executar os serviços em segundo plano, use `docker compose up -d --build`. Para mais detalhes sobre a arquitetura, dependências e testes do backend, consulte o [README do backend](Back/README.md).

### Execução local do backend

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
