---
title: Fique de Olho - UnB Editais
description: Documentação do projeto G4 — plataforma que centraliza, filtra e notifica editais da Universidade de Brasília.
hide:
  - toc
---

<div class="radar-hero" markdown>
<div class="radar-hero__content" markdown>

<span class="radar-hero__eyebrow">🌐 G4 · MDS · UnB 2026/2</span>

# Fique de Olho — Editais UnB

<p class="radar-hero__subtitle">
Centralizamos, estruturamos, filtramos e notificamos os editais da UnB —
para que nenhuma oportunidade ou prazo passe despercebido.
</p>

<div class="radar-hero__actions" markdown>
[🚀 Acessar Aplicação](https://fique-de-olho.vercel.app){ .radar-btn .radar-btn--primary }
[⚙️ Começar pelo Backend](backend/index.md){ .radar-btn .radar-btn--primary }
[🔌 Swagger da API](https://fique-de-olho-api.onrender.com/docs){ .radar-btn .radar-btn--ghost }
[🎨 Protótipo no Figma](https://www.figma.com/make/yqHT0b3mk0T3EkHD2aUgns/UnB-Editais-Aggregator-Site?fullscreen=1){ .radar-btn .radar-btn--ghost }
[💻 GitHub](https://github.com/unb-mds/G4-2026-2){ .radar-btn .radar-btn--ghost }
</div>
</div>
</div>

## 🎯 Sobre o projeto

O **Fique de Olho** é a plataforma web desenvolvida pelo grupo **G4** de Métodos de Desenvolvimento de Software (UnB 2026/2) para centralizar editais e oportunidades acadêmicas espalhados pelos portais institucionais da Universidade de Brasília.

Hoje o sistema monitora **33 portais da UnB**, extrai prazos, vagas, bolsas e resumos dos PDFs oficiais (combinando heurística local e fallback opcional com **Google Gemini**), oferece filtros por situação, categoria, campus e busca textual, além de **favoritos** e **alertas por e-mail** para atualizações e prazos próximos do encerramento.

---

## 🚀 Acesso rápido e ambientes

| Serviço | Plataforma | Link | Descrição |
| :--- | :---: | :--- | :--- |
| **Aplicação Web (Frontend)** | Vercel | [fique-de-olho.vercel.app](https://fique-de-olho.vercel.app) | SPA React 18 + TypeScript + Vite |
| **API REST & Swagger** | Render | [fique-de-olho-api.onrender.com/docs](https://fique-de-olho-api.onrender.com/docs) | FastAPI em Docker com documentação OpenAPI |
| **Healthcheck da API** | Render | [fique-de-olho-api.onrender.com/health](https://fique-de-olho-api.onrender.com/health) | Status da API, PostgreSQL e SendGrid |
| **Banco de Dados** | Neon | AWS São Paulo (`sa-east-1`) | PostgreSQL 16 Serverless (14 tabelas via Alembic) |

---

## ⚙️ Documentação Técnica — Backend, API & Banco

<div class="radar-grid" markdown>

<div class="radar-card" markdown>
<span class="radar-card__icon">🧭</span>
### Visão Geral & Quickstart
Arquitetura modular em FastAPI, como subir com Docker Compose ou Python local e mapa completo de variáveis de ambiente.

[Abrir Visão Geral →](backend/index.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🔌</span>
### Referência da API REST
Os 19 endpoints (editais, autenticação JWT/Google, favoritos, alertas, notificações e feedback), filtros, cache SWR e exemplos `curl`/JSON.

[Ver Referência da API →](backend/api.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🗄️</span>
### Banco de Dados & Migrations
Diagrama ER das 14 tabelas, enums nativos, constraints, pool do Neon e fluxo de migrações com Alembic.

[Explorar Banco de Dados →](backend/banco-de-dados.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🤖</span>
### Coleta, PDF & IA
Os 33 portais registrados, extração com `pdfplumber`, enriquecimento híbrido (Camada 1 + Gemini) e script de backfill.

[Ver Pipeline de Coleta →](backend/coleta-e-ia.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🚀</span>
### Operação, Alertas & Deploy
Alertas via SendGrid (UTC-3), deploy no Render + Neon, suíte `pytest` e troubleshooting local/produção.

[Abrir Guia Operacional →](backend/operacao-e-deploy.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">📐</span>
### Arquitetura & ADRs
Visão C4 do sistema, fontes de dados e as decisões arquiteturais (ADR 0001 a ADR 0006).

[Ver Arquitetura →](Arquitetura.md)
</div>

</div>

---

## 🗺️ Produto, Requisitos e Estudos

<div class="radar-grid" markdown>

<div class="radar-card" markdown>
<span class="radar-card__icon">📋</span>
### Requisitos & Produto
Visão de produto, personas, critérios de aceitação, story map, wireframe e backlog priorizado.

[Ver requisitos →](Requisitos/Requisitos.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">📚</span>
### Estudos Técnicos
Estudos de arquitetura, Docker, Git/GitHub, segurança, agentes de IA, hospedagem e keep-alive.

[Ver estudos →](Estudos/sprint00/arquitetura.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">🎨</span>
### Design & Frontend
Documentação da interface React/TypeScript, board de planejamento e protótipo de alta fidelidade.

[Ver Frontend →](front.md)
</div>

<div class="radar-card" markdown>
<span class="radar-card__icon">📦</span>
### Backlog do Produto
Épicos, histórias de usuário e priorização MoSCoW do projeto.

[Ver backlog →](Requisitos/produto/backlog.md)
</div>

</div>

<div class="radar-unb-strip" markdown>
<span class="dot"></span> Azul UnB · <span class="dot dot--green"></span> Verde UnB — projeto acadêmico do grupo **G4**, disciplina de Métodos de Desenvolvimento de Software, UnB 2026/2.
</div>
