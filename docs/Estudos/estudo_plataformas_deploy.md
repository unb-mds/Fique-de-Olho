# Estudo: Plataformas de Hospedagem e Deploy para o Projeto Fique de Olho

Este documento consolida a investigação técnica realizada com base na skill de **research**, fundamentando-se exclusivamente em **fontes primárias** (documentações oficiais e especificações dos provedores). O objetivo é avaliar a viabilidade, funcionamento, vantagens e desvantagens de ferramentas de hospedagem gratuitas ou acessíveis para o ecossistema do projeto (Frontend React/Vite, Backend FastAPI em Docker e Banco de Dados PostgreSQL).

---

## 1. Frontend e Hospedagem Estática

### 1.1. Vercel
*Fonte primária: [Vercel Documentation](https://vercel.com/docs)*

#### Como Funciona
A Vercel é uma plataforma de nuvem focada na experiência do desenvolvedor frontend e na entrega otimizada de conteúdo estático e serverless. Ela se integra nativamente ao repositório GitHub através de webhooks. A cada `git push` na branch monitorada (ex: `main`), a Vercel inicializa um container de build, detecta o framework (Vite/React), executa `npm run build` e distribui os arquivos resultantes (`dist/`) por sua rede global de borda (*Edge Network CDN*).

#### Vantagens
- **Otimização nativa para Single Page Applications (SPAs):** Tratamento simplificado de rotas клиент-side (React Router) via configuração de reescritas (*rewrites*).
- **Deploy Previews automáticos:** Cria um ambiente isolado com URL única para cada Pull Request aberto no GitHub.
- **Integração contínua zero-config:** Reconhece automaticamente o Vite e define os comandos de build e output directory.
- **Rede global de borda (CDN):** Latência mínima para usuários no Brasil.

#### Desvantagens
- **Restrição de uso no plano gratuito (Hobby):** O plano gratuito é estritamente não-comercial.
- **Limitações de execução contínua:** Não foi projetada para executar processos de longa duração ou containers Docker tradicionais (foco em Serverless/Edge).

---

### 1.2. Netlify
*Fonte primária: [Netlify Documentation](https://docs.netlify.com/)*

#### Como Funciona
O Netlify funciona como uma plataforma completa de automação de frontend e computação serverless. Ao conectar o repositório GitHub, a cada commit o Netlify clona o repositório, instala dependências e executa o empacotamento estático. Os artefatos finais são propagados para nós de CDN globais (*Netlify Edge*). O roteamento de SPAs com React Router é tratado por meio de um arquivo `_redirects` ou `netlify.toml`.

#### Vantagens
- **Deploy Previews e Branches de Staging:** Permite visualizar alterações de PRs e branches secundárias (como a branch `Dev`).
- **Gerenciamento simples de variáveis de ambiente:** Interface intuitiva para configurar `VITE_API_BASE_URL`.
- **Generoso plano gratuito:** Inclui 100 GB de largura de banda mensal e 300 minutos de build.

#### Desvantagens
- **Consumo de minutos de build:** Builds lentos ou complexos podem consumir a cota mensal de minutos gratuitos.
- **Não executa backend persistente:** Assim como a Vercel, não serve para rodar a API FastAPI como processo contínuo nem o banco PostgreSQL.

---

### 1.3. GitHub Pages
*Fonte primária: [GitHub Pages Documentation](https://docs.github.com/en/pages)*

#### Como Funciona
O GitHub Pages é o serviço nativo de hospedagem estática do GitHub. Ele serve arquivos diretamente de uma branch específica (geralmente `gh-pages` ou pasta `/docs` da branch principal). Atualmente, o projeto já utiliza o GitHub Pages via workflow [`.github/workflows/deploy-docs.yml`](../../.github/workflows/deploy-docs.yml) para publicar a documentação em MkDocs Material.

#### Vantagens
- **Hospedagem nativa no próprio repositório:** Não requer cadastro em serviços externos ou compartilhamento de tokens de terceiros.
- **Totalmente gratuito e estável:** Sem risco de suspensão por inatividade de conta.
- **Excelente para documentação:** Integração perfeita com ferramentas geradoras de sites estáticos (MkDocs, Jekyll).

#### Desvantagens
- **Incompatível com servidores dinâmicos:** Não suporta execução de código Python, APIs ou bancos de dados.
- **Roteamento de SPAs complexo:** Exige contornos técnicos (hacks com `404.html`) para que rotas diretas do React Router (ex: `/editais/1`) não retornem erro 404 ao recarregar a página.
- **Compartilhamento de domínio:** O repositório já utiliza a cota do Pages para a documentação técnica oficial.

---

## 2. Backend e Containers (FastAPI)

### 2.1. Render (Web Services)
*Fonte primária: [Render Documentation](https://render.com/docs/web-services)*

#### Como Funciona
O Render é uma plataforma de nuvem como serviço (PaaS). Ele permite conectar diretamente um repositório Git e criar um **Web Service** a partir do arquivo [`Back/Dockerfile`](../../Back/Dockerfile). A cada push na branch configurada, o Render constrói a imagem Docker, expõe a porta configurada (ex: `8000`) e atribui um subdomínio HTTPS automático (ex: `fique-de-olho-api.onrender.com`).

#### Vantagens
- **Suporte nativo a Docker:** Lê diretamente o `Dockerfile` existente no projeto sem exigir alterações na estrutura de pastas.
- **HTTPS automático e certificados gerenciados:** Configuração imediata de TLS sem custo.
- **Variáveis de ambiente seguras:** Permite injetar `DATABASE_URL` e segredos diretamente pelo painel.

#### Desvantagens
- **Comportamento de "Spin Down" no plano gratuito:** Instâncias gratuitas hibernam após 15 minutos sem receber tráfego. Quando uma nova requisição chega, a API pode levar de 50 a 60 segundos para iniciar (*cold start*), gerando demora no primeiro acesso do usuário.
- **Cota mensal de 750 horas gratuitas:** Suficiente para manter apenas um serviço ativo continuamente durante o mês.

---

### 2.2. Koyeb
*Fonte primária: [Koyeb Documentation](https://www.koyeb.com/docs)*

#### Como Funciona
O Koyeb é uma plataforma serverless orientada a microVMs baseadas na tecnologia Firecracker. Ele permite implantar containers Docker globais conectados ao GitHub. Ao receber um commit, a plataforma compila o container e o instancia em data centers com roteamento anycast e terminação SSL na borda.

#### Vantagens
- **Cold start mais rápido:** MicroVMs baseadas em Firecracker inicializam com menor latência que containers tradicionais.
- **Rede global de borda:** Roteamento com baixa latência e terminação TLS automática.
- **Suporte completo a Docker e Python nativo:** Excelente compatibilidade com FastAPI e Uvicorn.

#### Desvantagens
- **Plano gratuito restrito:** O plano "Eco / Hobby" permite apenas 1 serviço ativo no plano gratuito.
- **Exigência de validação de conta:** Pode solicitar validação com cartão de crédito mesmo para planos com cota gratuita ativa.

---

## 3. Banco de Dados Gerenciado (PostgreSQL)

### 3.1. Supabase
*Fonte primária: [Supabase Documentation](https://supabase.com/docs/guides/database)*

#### Como Funciona
O Supabase oferece instâncias completas e dedicadas do PostgreSQL 15/16 hospedadas na AWS. Ele fornece uma string de conexão padrão do PostgreSQL compatível com SQLAlchemy e `psycopg2` (utilizados no backend), além de painel de controle com editor de SQL, visualizador de tabelas e logs em tempo real.

#### Vantagens
- **PostgreSQL 100% padrão:** Total compatibilidade com as migrações SQL do projeto ([`db/migrations/`](../../db/migrations/)) e modelos SQLAlchemy.
- **Interface web robusta:** Facilita a inspeção e manipulação de tabelas sem necessidade de clientes locais como DBeaver ou pgAdmin.
- **Recursos adicionais integrados:** Autenticação, armazenamento de arquivos (Storage para eventuais PDFs) e APIs REST automáticas.

#### Desvantagens
- **Pausa automática por inatividade no plano gratuito:** Se o projeto passar 7 dias consecutivos sem receber consultas, a instância do banco de dados é pausada e precisa ser reativada manualmente pelo painel.
- **Limite de 2 projetos gratuitos por conta.**

---

### 3.2. Neon
*Fonte primária: [Neon Documentation](https://neon.tech/docs/introduction)*

#### Como Funciona
O Neon é um PostgreSQL serverless baseado em uma arquitetura que desacopla completamente o processamento computacional (*Compute*) do armazenamento de dados (*Storage*). O armazenamento é replicado e distribuído em nuvem, permitindo que a camada computacional escale até zero quando não há requisições e reinicie sob demanda em centenas de milissegundos.

#### Vantagens
- **Arquitetura Serverless real:** Capacidade de escalar a computação a zero sem perder dados e acordar rapidamente em novas consultas.
- **Database Branching (Ramificação de Banco):** Permite criar cópias instantâneas do banco de dados para testes e Pull Requests, como se fossem branches do Git.
- **Excelente cota gratuita:** 0.5 GB de armazenamento persistente gratuito e suporte integral a conexões PostgreSQL padrão via pool de conexões (*connection pooling*).

#### Desvantagens
- **Particularidades de Pooler de Conexão:** Conexões diretas a funções serverless requerem uso de endpoints com PgBouncer (`-pooler`), exigindo atenção na string de conexão do SQLAlchemy.
- **Sem painel gráfico avançado de backend:** Focado primordialmente no banco de dados, sem serviços satélites integrados como storage ou autenticação embutida (como no Supabase).

---

### 3.3. Render PostgreSQL
*Fonte primária: [Render PostgreSQL Documentation](https://render.com/docs/databases)*

#### Como Funciona
O Render permite criar uma instância gerenciada de PostgreSQL diretamente em sua infraestrutura, permitindo conexão interna de rede de alta velocidade com os Web Services do próprio Render (onde a API FastAPI estiver rodando).

#### Vantagens
- **Comunicação em rede privada:** A API hospedada no Render pode se comunicar com o banco de dados via rede interna sem custos de tráfego externo e com latência mínima.
- **Configuração em 1 clique:** Criação instantânea no mesmo painel da API.

#### Desvantagens
- **Expiração agressiva no plano gratuito:** As instâncias gratuitas de PostgreSQL no Render **expiram e são excluídas após 30 dias** de criação, exigindo recriação do banco ou upgrade para plano pago. **Não é recomendado para persistência de longo prazo em projetos acadêmicos**.

---

## 4. Matriz Comparativa e Síntese de Decisão

| Componente | Opção Recomendada | Justificativa Técnica | Alternativa Viável |
| :--- | :--- | :--- | :--- |
| **Frontend** | **Vercel** | Reconhecimento nativo do Vite, facilidade com React Router, deploy previews para cada PR e CDN global. | **Netlify** |
| **Backend** | **Render** | Executa diretamente o [`Back/Dockerfile`](../../Back/Dockerfile) sem adaptações de código; suporta variáveis de ambiente e HTTPS. | **Koyeb** |
| **Banco de Dados** | **Neon** ou **Supabase** | Neon oferece persistência contínua serverless e ramificação de banco; Supabase oferece PostgreSQL com excelente console de administração. | **Supabase** |

---

## 5. Referências (Fontes Primárias)

1. Vercel Inc. *Vercel Documentation & Build Steps*. Disponível em: <https://vercel.com/docs>. Acesso em out. 2026.
2. Netlify Inc. *Netlify Core Documentation & Continuous Deployment*. Disponível em: <https://docs.netlify.com/>. Acesso em out. 2026.
3. GitHub Inc. *About GitHub Pages and Static Hosting*. Disponível em: <https://docs.github.com/en/pages>. Acesso em out. 2026.
4. Render Services Inc. *Render Web Services and Deploying Docker*. Disponível em: <https://render.com/docs/web-services>. Acesso em out. 2026.
5. Koyeb Inc. *Koyeb Serverless Engine Documentation*. Disponível em: <https://www.koyeb.com/docs>. Acesso em out. 2026.
6. Supabase Pte Ltd. *Supabase Database Documentation (PostgreSQL)*. Disponível em: <https://supabase.com/docs/guides/database>. Acesso em out. 2026.
7. Neon Inc. *Neon Architecture and PostgreSQL Serverless*. Disponível em: <https://neon.tech/docs/introduction>. Acesso em out. 2026.

