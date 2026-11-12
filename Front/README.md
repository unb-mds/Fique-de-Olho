# Editais UnB — Frontend

Frontend do sistema que busca e exibe os editais publicados pela UnB.

## Stack

- React 18 + TypeScript
- Vite (build tool)
- React Router (rotas)
- Vitest + Testing Library (testes unitários e de componentes)
- ESLint + Prettier (lint e formatação)

## Estrutura de pastas

```
src/
├── components/   # Componentes reutilizáveis (ex: EditalCard, FavoriteButton)
├── pages/        # Páginas/telas da aplicação (ex: HomePage, EditalDetailPage)
├── routes/       # Definição das rotas da aplicação
├── services/     # Comunicação com a API do backend e tipos compartilhados
├── test/         # Configurações globais de testes (setup.ts)
├── App.tsx
├── main.tsx
└── index.css
```

## Pré-requisitos

- Node.js 18 ou superior
- npm (ou yarn/pnpm, ajustando os comandos abaixo)

## Setup local

Clone o repositório e rode:

```bash
npm install
npm run dev
```

O projeto sobe em `http://localhost:5173`.

Copie o arquivo de variáveis de ambiente antes de rodar, caso o backend esteja em outra URL:

```bash
cp .env.example .env
```

## Scripts disponíveis

| Comando              | Descrição                                         |
| -------------------- | ------------------------------------------------- |
| `npm run dev`        | Roda o projeto em modo desenvolvimento             |
| `npm run build`      | Gera o build de produção                           |
| `npm run preview`    | Serve o build de produção localmente               |
| `npm run test`       | Executa os testes unitários com Vitest             |
| `npm run test:watch` | Executa os testes em modo interativo (*watch*)     |
| `npm run lint`       | Roda o ESLint                                      |
| `npm run format`     | Formata o código com o Prettier                    |

## Padrões do time

- Todo componente novo vai em `src/components` com seus testes em `src/components/__tests__`.
- Toda página/rota nova vai em `src/pages`, e é registrada em `src/routes/AppRoutes.tsx`.
- Toda chamada à API do backend fica centralizada em `src/services`.
- Rodar `npm run lint` e `npm run test` antes de abrir PR.

---

## ☁️ Hospedagem e Deploy (Vercel)

O frontend é implantado e distribuído globalmente pela **Vercel**:
- **Plataforma:** [Vercel](https://vercel.com) com detecção automática do framework **Vite**.
- **Root Directory:** `Front`
- **Variáveis de Ambiente:** `VITE_API_BASE_URL` configurada apontando para a URL pública da API no Render.
- **Roteamento SPA:** O arquivo `Front/vercel.json` gerencia reescritas automáticas para `/index.html`, evitando erros 404 em recarregamento (*F5*) de rotas internas.
- Decisão e motivações detalhadas na [ADR 0004 — Plataformas de Hospedagem e Deploy](../docs/adr/0004-plataformas-de-deploy.md).

