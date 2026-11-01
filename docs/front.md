# Frontend

O frontend do Fique de Olho é uma aplicação web React que apresenta os editais da UnB, permite filtrar categorias e oferece uma página de detalhes com acesso ao documento oficial.

## Stack

- React 18
- TypeScript
- Vite
- React Router
- ESLint e Prettier
- CSS responsivo
- **Vercel** para hospedagem e deploy contínuo em produção (conforme [ADR 0004](adr/0004-plataformas-de-deploy.md))

## Estrutura principal

```text
Front/src/
├── components/   # Header, filtros, cards e favoritos
├── pages/        # HomePage e EditalDetailPage
├── routes/       # Rotas da aplicação
├── services/     # Comunicação HTTP com a API
├── utils/        # Formatação de datas e categorias
└── App.tsx       # Composição da aplicação
```

## Fluxo principal

1. A `HomePage` solicita os editais à API.
2. O serviço `editaisService` faz as requisições HTTP.
3. Os componentes exibem destaques, filtros e cards.
4. O usuário pode abrir `/editais/{id}` para consultar os detalhes.
5. A página de detalhes apresenta datas, status e o documento oficial.

## Execução local

```powershell
cd Front
npm install
npm run dev
```

A aplicação fica disponível em `http://localhost:5173`. A URL da API pode ser configurada pela variável `VITE_API_BASE_URL` (no `.env`).

## Validação

```powershell
npm run lint
npm run build
```

## Hospedagem e Deploy

O deploy da aplicação web é realizado na **Vercel**:
- **Gatilho:** Conectado à branch `main` do GitHub para deploy automático e deploy previews a cada Pull Request.
- **Variáveis de Ambiente:** `VITE_API_BASE_URL` apontando para o endpoint do backend em produção no Render.
- **Roteamento SPA:** Utiliza `rewrites` no `vercel.json` para direcionar todas as rotas para o `index.html`.

[Abrir o README completo do frontend no GitHub](https://github.com/unb-mds/Fique-de-Olho/blob/main/Front/README.md)
