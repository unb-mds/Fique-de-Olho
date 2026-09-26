# Editais UnB — Frontend

Frontend do sistema que busca e exibe os editais publicados pela UnB.

## Stack

- React 18 + TypeScript
- Vite (build tool)
- React Router (rotas)
- ESLint + Prettier (lint e formatação)

## Estrutura de pastas

```
src/
├── components/   # Componentes reutilizáveis (ex: EditalCard)
├── pages/        # Páginas/telas da aplicação (ex: HomePage, EditalDetailPage)
├── routes/        # Definição das rotas da aplicação
├── services/      # Comunicação com a API do backend e tipos compartilhados
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

| Comando           | Descrição                                  |
| ------------------ | ------------------------------------------- |
| `npm run dev`      | Roda o projeto em modo desenvolvimento      |
| `npm run build`    | Gera o build de produção                    |
| `npm run preview`  | Serve o build de produção localmente        |
| `npm run lint`     | Roda o ESLint                               |
| `npm run format`   | Formata o código com o Prettier             |

## Padrões do time

- Todo componente novo vai em `src/components`.
- Toda página/rota nova vai em `src/pages`, e é registrada em `src/routes/AppRoutes.tsx`.
- Toda chamada à API do backend fica centralizada em `src/services`.
- Rodar `npm run lint` e `npm run format` antes de abrir PR.
