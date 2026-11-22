# Critérios de Aceitação — Fique de Olho (UnB Editais)

Este documento define os critérios objetivos de aceitação (**Dado / Quando / Então**) para validar os Requisitos Funcionais e Não Funcionais especificados em [Requisitos](Requisitos.md).

---

## 1. Descoberta, Busca e Filtros

### RF02 — Filtrar por ano e tipo
- **Dado** que o usuário está na página inicial com editais carregados,
- **Quando** seleciona um **Ano** (ex.: `2026`) e/ou uma **Categoria** (ex.: `Graduação`),
- **Então** a listagem exibe apenas editais publicados no ano selecionado e pertencentes à categoria escolhida, e o botão **Limpar filtros** restaura a listagem completa em um clique.

### RF04 — Buscar editais por nome ou palavras-chave
- **Dado** que o usuário digita um termo na barra de busca (título, assunto, resumo ou sigla do órgão, como `DEG` ou `monitoria`),
- **Quando** aguarda o debounce da busca,
- **Então** o sistema retorna apenas os editais correspondentes (de forma insensível a maiúsculas/minúsculas) ou exibe uma mensagem amigável de estado vazio com botão para limpar a busca e os filtros.

### RF05 — Identificar editais abertos e encerrados
- **Dado** um conjunto de editais com e sem prazo de inscrição,
- **Quando** o usuário seleciona a situação **Abertos** ou **Encerrados**,
- **Então**:
  - Editais com `fim_inscricao >= hoje` (e sem `RESULTADO_FINAL`) aparecem em **Abertos**;
  - Editais com `fim_inscricao < hoje`, com documento `RESULTADO_FINAL`/`Resultado Definitivo`, ou sem prazo publicados há mais de 90 dias aparecem em **Encerrados**;
  - Editais com prazo de 0 a 7 dias restantes exibem badge de urgência no card.

### RF06 — Separar por categorias
- **Dado** que o sistema classifica os editais nas 9 categorias controladas (`Pós-graduação`, `Graduação`, `Intercâmbio`, `Evento`, `Bolsa`, `Pesquisa`, `Estágio`, `Extensão`, `Vestibular`),
- **Quando** o usuário seleciona a categoria **Graduação**,
- **Então** nenhum edital de **Pós-graduação** (mestrado, doutorado, stricto/lato sensu, DPG ou PPGs) é exibido nos resultados;
- **E** ao selecionar **Intercâmbio** + **Abertos**, editais antigos/encerrados e editais de estágio da INT não são listados como abertos.

### RF13 — Filtrar por campos de interesse (campus, ano, categoria e situação)
- **Dado** que o usuário deseja combinar múltiplos filtros na página inicial,
- **Quando** seleciona um **Campus** (`Darcy Ribeiro`, `FGA (Gama)`, `FCE (Ceilândia)`, `FUP (Planaltina)`, `Fazenda Água Limpa` ou `Geral`) combinado com **Situação**, **Ano** e/ou **Categoria**,
- **Então** o backend resolve os aliases de sigla/nome do campus (ex.: `FGA` e `Gama`, `FUP` e `Planaltina`, `FCE` e `Ceilândia`) e retorna a interseção exata de todos os filtros aplicados.

---

## 2. Visualização e Resumo de Editais

### RF09 — Visualizar edital e documento oficial (PDF)
- **Dado** que o usuário clica em **Ver edital** em um card,
- **Quando** a página de detalhes (`/editais/:id`) é carregada,
- **Então** o sistema exibe metadados completos (órgão emissor, campus, período de inscrição, vagas, valor de bolsa quando houver) e links validados (`http://`/`https://`) para o PDF oficial, anexos e retificações.

### RF11 — Resumir edital
- **Dado** um edital coletado cujo resumo original do portal seja vazio ou genérico,
- **Quando** o pipeline de ingestão (ou backfill) processa o edital,
- **Então** a Camada 1 extrai o objeto do texto do PDF e, quando `GEMINI_API_KEY` está configurada, a Camada 2 (`gemini-3.5-flash-lite`) gera um resumo objetivo de até 2 frases com fallback transparente para a Camada 1 em caso de falha ou indisponibilidade da API externa.

---

## 3. Engajamento, Favoritos e Notificações

### RF03 — Favoritar edital
- **Dado** que o usuário está autenticado (JWT ou Google OAuth2),
- **Quando** clica no ícone de estrela em um card ou na página de detalhes,
- **Então** o edital é salvo de forma idempotente em `favoritos`, passa a aparecer em **Meus editais** (`/favoritos`) e pode ser removido clicando novamente.

### RF01 — Enviar notificações de atualização
- **Dado** que o usuário ativou o alerta (`POST /api/v1/editais/{id}/alertas`) para um edital e mantém `receber_emails = true`,
- **Quando** uma nova coleta detecta alteração relevante (`hash_conteudo` diferente),
- **Então** o sistema registra uma notificação única (`uq_notificacao_evento`) do tipo `edital_atualizado`, envia o e-mail via SendGrid (quando configurado) e exibe o evento no histórico do usuário (`/api/v1/auth/me/notifications`).

### RF12 — Avisar prazo de inscrição encerrando
- **Dado** que um edital com alerta ativado possui `fim_inscricao` definida,
- **Quando** o agendador horário verifica a data no fuso de Brasília (`UTC-3`) e faltam **3 dias**, **1 dia** ou **0 dias** para o encerramento,
- **Então** o sistema cria no máximo uma notificação por marco (`chave_evento`) e envia o lembrete por e-mail sem duplicação.

---

## 4. Suporte, Ajuda e Feedback

### RF08 — Central de ajuda (`?`)
- **Dado** que o usuário está em qualquer página da aplicação web,
- **Quando** clica no botão flutuante de interrogação (`?`) no canto inferior direito,
- **Então** abre-se um `<dialog>` modal nativo acessível (fechável por botão `×`, tecla `Esc` ou clique fora do modal) contendo as perguntas frequentes (FAQ) sobre busca, filtros, favoritos, alertas e status de editais.

### RF07 — Enviar feedback
- **Dado** que o usuário abre a aba **Enviar feedback** na Central de Ajuda,
- **Quando** escolhe o tipo (`sugestao`, `problema` ou `elogio`), informa uma mensagem com pelo menos 5 caracteres (e opcionalmente um e-mail) e envia o formulário,
- **Então** o backend valida o payload (`POST /api/v1/feedback` → `201 Created`), persiste o registro na tabela `feedbacks`, encaminha o relato por e-mail para `fiquedeolho1011@gmail.com` (via SendGrid, em background) e exibe confirmação clara na interface. Se a mensagem for curta ou houver falha de rede, uma mensagem de erro amigável é exibida.

---

## 5. Requisitos Não Funcionais (Critérios de Verificação)

| RNF | Critério de verificação |
| :--- | :--- |
| **RNF01 / RNF02** | Listagens usam `defer(texto_extraido)`, `lazy="selectin"`, compressão `GZipMiddleware` e cache SWR (`Cache-Control` + cache em memória de 15 min), respondendo abaixo de 5s em condições normais. |
| **RNF03 / RNF06** | Aplicação web responsiva testada em navegadores modernos (Chrome, Edge, Firefox, Safari) com fallback explícito para `<dialog closedby="any">` em navegadores sem suporte nativo. |
| **RNF04** | Barra de busca, filtros de situação, campus, ano e categoria acessíveis diretamente na Home sem necessidade de submenus. |
| **RNF05** | Estados de carregamento, erro de API, estado vazio de busca e validação de formulário exibem alertas acessíveis (`role="alert"` / `role="status"`) com ação sugerida. |
| **RNF07** | Suíte automatizada passando no backend (`pytest Back/tests -m "not live"`) e no frontend (`npm test` / `vitest`). |
| **RNF09** | Uso de elementos nativos semânticos (`<dialog>`, `<details>`, `<select>`, `<label htmlFor>`, `<button type="button">`), atributos `aria-label` e `aria-labelledby`, foco visível (`:focus-visible`) e suporte a `prefers-reduced-motion`. |
