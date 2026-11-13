# Relatório Técnico: Decisões Arquiteturais de Infraestrutura e Deploy em Nuvem

Este relatório consolida todas as decisões arquiteturais tomadas pela equipe para a publicação em nuvem da plataforma **Fique de Olho** (Backend FastAPI, Banco de Dados PostgreSQL e Frontend React), detalhando o contexto, as justificativas técnicas, as vantagens, as desvantagens e os trade-offs avaliados até o momento.

---

## 1. Matriz Consolidada de Decisões

| Componente / Decisão | Tecnologia Escolhida | Alternativas Avaliadas | Status |
|---|---|---|---|
| **Hospedagem do Backend** | **Render (Web Services)** | Google Cloud Run, Azure Container Apps, Fly.io, Koyeb | **Implementado e Live** |
| **Banco de Dados Relacional** | **Neon (Serverless PostgreSQL)** | Supabase, Render PostgreSQL | **Provisionado e Migrado** |
| **Estratégia de Migrações** | **Execução no Boot do Container** | Pre-Deploy Command (Render), Jobs externos | **Implementado no Dockerfile** |
| **Resiliência de Conexão** | **Validador de Dialeto Pydantic** | Configuração estrita manual no painel | **Implementado no Config** |
| **Infraestrutura como Código** | **`render.yaml` (Blueprint)** | Criação puramente manual via UI | **Implementado** |
| **Otimização de Build** | **`.dockerignore` Modular** | Cópia irrestrita de contexto | **Implementado** |

---

## 2. Detalhamento das Decisões Técnicas

### Decisão 1: Adoção do Render para a API FastAPI
* **Contexto:** A aplicação necessitava de um ambiente PaaS capaz de executar o [`Back/Dockerfile`](../../Back/Dockerfile) sem custos financeiros e sem exigir cadastro de cartão de crédito da equipe acadêmica.
* **Vantagens:**
  - **Custo R$ 0,00 real:** Não exige cartão de crédito no cadastro, eliminando 100% do risco de cobranças acidentais.
  - **Suporte nativo a Docker:** Lê diretamente o arquivo `Dockerfile`, preservando as dependências de sistema (`libpq-dev`, `build-essential`) necessárias para as bibliotecas de parsing e banco.
  - **HTTPS gerenciado:** Emissão e renovação automática de certificados TLS sem custo.
  - **Integração contínua (CI/CD):** Deploy automático a cada push na branch configurada.
* **Desvantagens e Mitigações:**
  - *Desvantagem (Cold Start):* No plano gratuito, a instância hiberna após 15 minutos sem requisições, levando de 45 a 55 segundos para acordar no primeiro acesso.
    - *Mitigação:* Implementação de estados de carregamento (*skeleton loaders*) no frontend para dar feedback imediato ao usuário.
  - *Desvantagem (Datacenters nos EUA):* Latência de rede transcontinental de ~120ms a 150ms.
    - *Mitigação:* Alinhamento de consultas e cacheamento de respostas.

---

### Decisão 2: Adoção do Neon (PostgreSQL Serverless) para o Banco de Dados
* **Contexto:** O projeto precisava de um banco PostgreSQL 16+ gerenciado que garantisse persistência contínua durante todo o semestre letivo.
* **Por que o Render PostgreSQL foi descartado:** O plano gratuito do Render PostgreSQL **exclui e deleta o banco de dados após 30 dias**, inviabilizando projetos contínuos de software.
* **Vantagens do Neon:**
  - **Persistência vitalícia no Free Tier:** Não deleta dados por tempo de inatividade.
  - **Compatibilidade total com o SQLAlchemy e Alembic:** Suporta perfeitamente todas as migrações, tipos nativos (Enums, Check Constraints) e índices textuais GIN (`tsvector` em português).
  - **Connection Pooling integrado (PgBouncer):** O endpoint `-pooler` gerencia centenas de conexões concorrentes da API sem esgotar a memória do banco.
* **Desvantagens:**
  - *Desvantagem:* A camada de computação entra em modo de suspensão após 5 minutos ociosa.
    - *Mitigação:* O backend já possui `pool_pre_ping=True` configurado no SQLAlchemy ([`database.py`](../../Back/app/core/database.py)), garantindo reconexão transparente sem quebras de sessão.

---

### Decisão 3: Execução de Migrações Automáticas via Startup do Container
* **Contexto:** O Render disponibiliza o recurso *Pre-Deploy Command* exclusivamente para planos pagos (Starter, Standard). No plano gratuito, esse campo é bloqueado com ícone de cadeado.
* **Solução implementada:** Atualização do comando de inicialização no `Back/Dockerfile`:
  ```dockerfile
  CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
  ```
* **Vantagens:**
  - **Automação 100% gratuita:** Toda vez que um deploy ocorre, o Alembic aplica as novas tabelas e colunas no Neon antes do Uvicorn abrir as portas para o tráfego público.
  - **Idempotência:** Se o banco já estiver na versão `head`, o Alembic apenas checa a tabela `alembic_version` em ~50ms e segue a inicialização sem impacto de performance.
  - **Segurança de integridade:** Se uma migração falhar por erro de sintaxe SQL, o container aborta imediatamente, impedindo que uma versão defeituosa da API entre no ar com schema quebrado.
* **Desvantagens:**
  - Um pequeno acréscimo de 1 a 2 segundos no tempo de inicialização do container.

---

### Decisão 4: Normalização Defensiva da `DATABASE_URL` via Pydantic
* **Contexto:** O SQLAlchemy exige o dialeto `postgresql+psycopg2://`. Serviços em nuvem como Neon, Render e Supabase frequentemente fornecem strings iniciando apenas com `postgresql://` ou `postgres://`.
* **Solução implementada:** Adicionado validador antes da inicialização no [`Back/app/core/config.py`](../../Back/app/core/config.py):
  ```python
  @field_validator("DATABASE_URL", mode="before")
  @classmethod
  def assemble_db_connection(cls, v: str) -> str:
      if isinstance(v, str):
          if v.startswith("postgres://"):
              return v.replace("postgres://", "postgresql+psycopg2://", 1)
          elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
              return v.replace("postgresql://", "postgresql+psycopg2://", 1)
      return v
  ```
* **Vantagens:**
  - Blindagem total contra erro humano: o desenvolvedor pode colar a URL do painel sem se preocupar em editar manualmente o prefixo.
  - Evita o erro fatal `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`.
* **Desvantagens:**
  - Nenhuma (custo de processamento desprezível de microssegundos no startup).

---

### Decisão 5: Descarte do Azure for Students e Manutenção da Arquitetura Render
* **Contexto:** Investigou-se a viabilidade de hospedar o container no **Azure Container Apps** na região `Brazil South` (São Paulo) utilizando o benefício de estudante sem cartão de crédito.
* **Motivo do descarte:** A Microsoft aplica a política interna restritiva `RequestDisallowedByAzure` em contas *Azure for Students*, bloqueando a criação de Container Apps na região de São Paulo por restrições de capacidade local.
* **Vantagens do descarte (Trade-off favorável ao Render):**
  - O Render é consideravelmente mais simples de operar e integrar ao fluxo Git que o portal corporativo do Azure.
  - Não há risco de esgotamento acidental de créditos de estudante.
  - A latência de ~140ms nos EUA foi validada como perfeitamente aceitável para o caso de uso de consulta a editais acadêmicos.
* **Desvantagens:**
  - Aceitação da latência internacional em troca de simplicidade e estabilidade.

---

### Decisão 6: Implementação do `render.yaml` (Infrastructure-as-Code)
* **Contexto:** A configuração manual via interface web é suscetível a esquecimentos de parâmetros essenciais (como a porta `8000`, a pasta raiz `Back` e a rota `/health`).
* **Solução implementada:** Criação do arquivo de blueprint declarativo [`render.yaml`](../../render.yaml) na raiz do repositório.
* **Vantagens:**
  - **Reprodutibilidade:** O ambiente pode ser recriado do zero em caso de incidentes com 1 clique.
  - **Segurança automatizada:** O parâmetro `generateValue: true` no `JWT_SECRET_KEY` instrui o Render a gerar uma chave criptográfica forte de 32 bytes de forma automática, garantindo que segredos de desenvolvimento jamais vão para produção.
* **Desvantagens:**
  - Requer manutenção da documentação do arquivo caso novas variáveis de ambiente sejam introduzidas no backend.

---

### Decisão 7: Conformidade Jurídica com a LGPD (Artigo 33)
* **Contexto:** Verificação da legalidade da hospedagem de dados de estudantes da UnB em servidores internacionais (EUA).
* **Fundamentação:** A transferência internacional de dados é plenamente legal e respaldada pelo **Art. 33, incisos II, VIII e IX da Lei nº 13.709/2018 (LGPD)** e pela **Resolução CD/ANPD nº 19/2024**.
* **Vantagens:**
  - Segurança jurídica para a equipe e para a universidade.
  - Utilização de infraestruturas auditadas com certificações internacionais de segurança bancária (**SOC 2 Type II** e **ISO 27001**).
  - O projeto não armazena dados sensíveis (apenas dados públicos de editais e credenciais comuns criptografadas com `Argon2`).
* **Desvantagens:**
  - Exige manter transparência ativa nos Termos de Uso do frontend.

---

## 3. Síntese do Estado Atual da Infraestrutura

| Item | Situação Atual |
|---|---|
| **Banco de Dados (Neon)** | **100% Funcional** — 13 tabelas estruturadas e ativas na nuvem. |
| **Backend (FastAPI no Render)** | **100% Funcional** — Container compilado e executando com healthcheck ativo. |
| **Frontend (Vite / React)** | **Pronto para Deploy** — 5 testes unitários passando, build de produção gerado. |
| **Documentação Técnica** | **Atualizada** — MkDocs com 4 novos estudos de caso sobre infraestrutura, latência e LGPD. |
