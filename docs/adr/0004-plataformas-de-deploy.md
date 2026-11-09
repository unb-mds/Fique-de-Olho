# 0004. Escolha das Plataformas de Hospedagem e Deploy

---
status: accepted
date: 2026-10-31
---

## Contexto e Decisão

Para viabilizar a disponibilização pública da plataforma **Fique de Olho** (interface web, API REST, banco de dados relacional e documentação técnica) com infraestrutura acessível, confiável e automatizada, foi realizado um estudo técnico sobre as opções gratuitas e de baixo custo disponíveis para o ecossistema do projeto (detalhado em `docs/Estudos/estudo_plataformas_deploy.md`).

A arquitetura do projeto é desacoplada em três camadas principais:
1. **Frontend:** Aplicação SPA em React 18, TypeScript e Vite;
2. **Backend:** API assíncrona em FastAPI executada em container Docker;
3. **Banco de Dados:** PostgreSQL 16 relacional gerenciado via SQLAlchemy e Alembic;
4. **Documentação:** Site estático gerado por MkDocs Material.

Decidimos adotar a seguinte matriz de tecnologias para hospedagem e deploy contínuo (CD):

- **Frontend:** **Vercel**
- **Backend (API):** **Render (Web Services)**
- **Banco de Dados:** **Neon** (com **Supabase** como alternativa homologada)
- **Documentação Técnica:** **GitHub Pages** (mantida via GitHub Actions)

---

## Opções Consideradas e Justificativas

### 1. Hospedagem do Frontend
* **Vercel (Escolhida):**
  - Reconhecimento automático do bundler Vite e do framework React.
  - Rede global de distribuição de conteúdo (*Edge CDN*) com baixa latência para usuários no Brasil.
  - Recurso de *Deploy Previews*: cada Pull Request aberto no GitHub gera automaticamente uma URL isolada para validação visual antes do merge.
  - Configuração simples de redirecionamento de rotas (*rewrites*) para compatibilidade nativa com o React Router.
* *Netlify (Alternativa homologada):* Boa infraestrutura e generosa cota de transferência, porém com consumo de minutos de build que requer monitoramento no plano gratuito.
* *GitHub Pages (Descartada para o frontend):* Já está dedicado à documentação do projeto; além disso, hospeda apenas arquivos estáticos sem suporte facilitado para roteamento profundo de SPAs sem contornos técnicos adicionais.

### 2. Hospedagem do Backend (API REST)
* **Render - Web Services (Escolhida):**
  - Compatibilidade direta com o arquivo `Back/Dockerfile` existente, dispensando adaptações na estrutura de pastas ou na configuração de inicialização.
  - Emissão automática de certificados SSL/TLS (HTTPS) e geração de subdomínio seguro.
  - Suporte à injeção segura de variáveis de ambiente (`DATABASE_URL`, `JWT_SECRET`, etc.).
  - Integração contínua atrelada à branch `main` do GitHub.
* *Koyeb (Alternativa):* Excelente performance com microVMs, mas possui políticas mais restritivas de limite de serviços ativos no plano Hobby.
* *Hospedagem estática (Vercel/Netlify):* Incompatíveis com a API, pois foram desenhadas para funções serverless efêmeras e não suportam o ciclo de vida contínuo do FastAPI com Uvicorn e scrapers em segundo plano.

### 3. Banco de Dados (PostgreSQL)
* **Neon (Escolhida principal):**
  - PostgreSQL verdadeiramente *serverless*, desacoplando computação de armazenamento.
  - Não impõe exclusão automática dos dados após 30 dias (ao contrário do plano gratuito do Render PostgreSQL).
  - Suporte nativo a *Database Branching*, permitindo criar ramificações do banco para testes isolados.
  - Total compatibilidade com o schema SQLAlchemy e migrations Alembic (ADR 0003).
* *Supabase (Alternativa homologada):* Instância dedicada de PostgreSQL na nuvem com excelente dashboard visual para inspeção de dados e tabelas, pausando apenas após 7 dias de inatividade completa.
* *Render PostgreSQL (Descartada):* Exclui o banco de dados e todos os dados armazenados após 30 dias no plano gratuito, tornando-o inviável para persistência em ambiente acadêmico contínuo.

### 4. Documentação Técnica
* **GitHub Pages (Mantida):**
  - Totalmente integrada ao repositório via workflow `.github/workflows/deploy-docs.yml`.
  - Custo zero, alta disponibilidade e atualizações instantâneas a cada push na branch `main`.

---

## Consequências

### Positivas
- **Ambiente de Produção 100% Funcional:** Permite que a comunidade acadêmica da UnB acesse a plataforma pela web sem necessidade de instalar Docker ou configurar ambiente de desenvolvimento local.
- **Isolamento de Responsabilidades:** O backend pode ser atualizado ou reiniciado sem afetar a disponibilidade do frontend ou da documentação.
- **Custo Zero:** Todas as plataformas escolhidas oferecem planos gratuitos adequados ao tráfego e volume de dados do projeto de graduação.
- **Deploy Contínuo (CD):** Commits aprovados e mesclados na branch `main` são implantados automaticamente nas três camadas (Vercel, Render e GitHub Pages).

### Trade-offs e Cuidados (Mitigações)
- **Cold Start do Backend no Render:** No plano gratuito, a API entra em estado de hibernação após 15 minutos sem requisições. O primeiro acesso subsequente pode levar até ~50 segundos para responder.
  - *Mitigação:* O frontend apresentará estados de carregamento claros (*skeletons* e indicadores de progresso) e o endpoint `/health` poderá ser monitorado ou chamado preventivamente.
- **Roteamento SPA no Frontend:** A navegação direta por URLs profundas (ex: `/editais/12`) na Vercel exige configuração de reescrita no arquivo `vercel.json`:
  ```json
  {
    "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
  }
  ```
- **Conexões do Banco Neon com SQLAlchemy:** Como o Neon é serverless, deve-se utilizar a string de conexão com pooler (`-pooler`) ou configurar timeouts adequados no `Back/app/core/database.py` para evitar conexões pendentes.

