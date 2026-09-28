# Frontend

O frontend do Fique de Olho é uma aplicação web React que apresenta os editais da UnB, permite filtrar categorias e oferece uma página de detalhes com acesso ao documento oficial.

## Stack

- React 18
- TypeScript
- Vite
- React Router
- ESLint e Prettier
- CSS responsivo

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

## Execução

```powershell
cd Front
npm install
npm run dev
```

A aplicação fica disponível em `http://localhost:5173`. A API pode ser configurada pela variável `VITE_API_BASE_URL`.

## Validação

```powershell
npm run lint
npm run build
```

[Abrir o README completo do frontend no GitHub](https://github.com/unb-mds/Fique-de-Olho/blob/main/Front/README.md)
