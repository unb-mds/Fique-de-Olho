# Skills do repositório

Este documento consolida a funcionalidade de cada skill presente em [.github/skills](../../../.github/skills), com base nos arquivos de instrução `SKILL.md` e nas convenções de workflow do repositório. A ideia é funcionar como um guia rápido para saber quando usar cada skill, qual problema ela resolve e como as habilidades se conectam em um fluxo de trabalho real.

O material foi organizado para refletir a visão das skills do projeto Matt Pocock, que enfatiza clareza de comunicação, domínio compartilhado, divisão em tarefas pequenas e validação contínua do trabalho.

## Visão geral

As skills deste repositório ajudam a reduzir os principais problemas de trabalho com agentes de IA:

- falta de alinhamento sobre o que será construído;
- ambiguidades no vocabulário do projeto;
- dificuldade de transformar ideias em requisitos e tarefas;
- implementação sem validação adequada;
- excesso de contexto ou decisões mal documentadas;
- triagem caótica de bugs, pedidos e pendências.

Em conjunto, elas formam um ciclo de trabalho que vai de:

1. começar com a ideia certa;
2. definir o problema e o domínio;
3. transformar a conversa em spec e tickets;
4. implementar em pedaços pequenos;
5. revisar e validar a entrega;
6. manter documentação e rastreio organizado.

---

## Skills disponíveis

### 1. ask-matt

- Descrição detalhada: é o roteador do conjunto de skills. Ele funciona como um guia que ajuda a escolher o caminho mais adequado para a tarefa atual, em vez de tentar aplicar a skill certa por tentativa e erro.
- Funcionalidade: analisa o tipo de necessidade do usuário e orienta para a próxima etapa correta, como uma sessão de refinamento, triagem, especificação, implementação ou pesquisa.
- Exemplo simples: se você não sabe se deve criar uma especificação ou começar a codificar, o `ask-matt` ajuda a decidir: "se a ideia ainda está vaga, use `grill-with-docs`; se já está clara, vá para `to-spec` ou `implement`".

### 2. code-review

- Descrição detalhada: é uma revisão de código em duas dimensões: conformidade com padrões do repositório e fidelidade à especificação ou problema original. Isso ajuda a evitar que uma mudança passe apenas porque "funciona", mas não siga as regras do projeto ou não entrega o que foi pedido.
- Funcionalidade: compara a mudança com um ponto fixo e verifica se ela atende aos padrões internos e aos requisitos da issue, spec ou ticket.
- Exemplo simples: após implementar uma correção em um fluxo de autenticação, o `code-review` verifica se a lógica está consistente com os padrões do projeto e se ela realmente resolve a necessidade descrita na issue.

### 3. criar-issue

- Descrição detalhada: serve para padronizar a escrita de issues e tarefas em um formato objetivo, com contexto, objetivos, requisitos e critérios de aceite. Essa padronização reduz mal-entendidos e facilita a execução posterior.
- Funcionalidade: organiza a issue em blocos como descrição da tarefa, objetivos, requisitos, prioridade, checklist, resultado esperado e link do estudo ou artefato final.
- Exemplo simples: para registrar um estudo sobre agentes de IA, a skill gera uma issue com: contexto do estudo, objetivos, requisitos técnicos, prioridade, checklist de execução e link do documento final quando estiver pronto.

### 4. domain-modeling

- Descrição detalhada: ajuda a construir e refinar o modelo de domínio do projeto. Em vez de usar termos vagos e inconsistentes, a skill força a definição clara de conceitos importantes e documenta decisões relevantes.
- Funcionalidade: identifica termos ambíguos, confronta definições, discute cenários e atualiza o glossário do projeto e ADRs quando necessário.
- Exemplo simples: se o projeto usa o termo "conta" em vários sentidos, a skill diferencia "usuário", "cliente" e "perfil" para deixar o vocabulário consistente e evitar confusão entre time e agente.

### 5. grill-with-docs

- Descrição detalhada: é uma sessão de entrevista rigorosa para refinar ideias, planos ou decisões. A diferença principal é que ela também produz documentação útil durante o processo, como glossário e ADRs.
- Funcionalidade: conduz uma conversa estruturada para esclarecer requisitos, descobrir casos de borda, registrar decisões e reduzir ruído na comunicação entre humano e agente.
- Exemplo simples: antes de construir uma função de upload de arquivos, a skill pergunta sobre regras de tipo de arquivo, limite de tamanho, permissões e cenário de erro, e registra essas decisões em documentação para não perder contexto depois.

### 6. implement

- Descrição detalhada: é a skill de execução prática. Ela transforma uma especificação, ticket ou conjunto de requisitos em código funcional, seguindo boas práticas de desenvolvimento e validação incremental.
- Funcionalidade: trabalha com red-green-refactor, testes focados e revisão final para garantir que a implementação atenda ao objetivo sem quebrar o restante do projeto.
- Exemplo simples: quando uma feature já foi especificada e quebrada em tarefas, o `implement` cria a solução em iterações, valida com testes e faz a revisão final antes de concluir.

### 7. research

- Descrição detalhada: é a skill para investigação confiável. Ela busca fontes primárias e oficiais e registra os resultados em um arquivo Markdown com referências, em vez de confiar em memórias vagas ou materiais secundários.
- Funcionalidade: investiga um tema técnico, coleta dados de documentação oficial, APIs, especificações e fontes reconhecidas, e organiza as conclusões em um documento final.
- Exemplo simples: para entender como agentes de IA funcionam, a skill consulta documentação oficial de providers e organiza em um estudo com explicações, citações e contexto técnico.

### 8. setup-matt-pocock-skills

- Descrição detalhada: configura o repositório para o uso das skills de engenharia. Ela prepara a base de trabalho para que as outras skills operem corretamente.
- Funcionalidade: define onde ficam os issues, quais labels serão usadas para triagem e como a documentação de domínio será organizada, como `CONTEXT.md` e ADRs.
- Exemplo simples: ao iniciar um projeto, essa skill pergunta qual tracker será usado (GitHub, GitLab ou arquivos locais) e configura o formato de documentação esperado pelas próximas skills.

### 9. to-spec

- Descrição detalhada: transforma uma conversa, rascunho ou discussão em uma especificação formal. Ela ajuda a capturar o problema, a solução proposta, histórias de usuário, decisões de implementação e testes sem deixar a ideia dispersa.
- Funcionalidade: estrutura o trabalho em blocos como problema, solução, user stories, decisões de implementação, testes e escopo fora do alcance.
- Exemplo simples: se o time discutiu uma nova funcionalidade de dashboard, a skill organiza tudo em uma spec clara antes de começar a divisão em tarefas ou implementação.

### 10. to-tickets

- Descrição detalhada: divide uma spec ou plano em tickets executáveis. Ela transforma uma ideia grande em blocos menores e organizados, com dependências entre eles.
- Funcionalidade: cria tarefas de forma vertical, define bloqueios e ajuda a evitar que o trabalho fique gigantesco ou mal sequenciado.
- Exemplo simples: em um projeto de autenticação, ela pode quebrar em tickets como: "criar fluxo de login", "validar sessão", "tratar erros de permissão" e "escrever testes de integração".

### 11. triage

- Descrição detalhada: é a skill para organizar e classificar demandas de trabalho. Ela ajuda a decidir se uma issue é bug, melhoria, precisa de mais informação ou já está pronta para execução.
- Funcionalidade: move issues e PRs através de estados de triagem e prepara o material para que um agente ou humano possa atuar na próxima etapa.
- Exemplo simples: se uma issue chega dizendo "o botão não salva dados", a skill classifica como bug, verifica contexto, pede informações extras se necessário e marca como pronto para agente ou pronto para humano.

### 12. doc-to-markdown

- Descrição detalhada: converte automaticamente documentos (PDFs, editais, relatórios), fotos, imagens e arquivos Office em Markdown (.md) estruturado.
- Funcionalidade: executa script Python utilizando a biblioteca MarkItDown, extraindo o conteúdo de imagens e PDFs e gerando arquivos `.md` limpos no repositório.
- Exemplo simples: ao receber um PDF de edital do DEG ou a foto de um quadro/anotação, o agente executa a skill e gera o arquivo `.md` correspondente na pasta de documentação.

---

## Como essas skills se conectam no fluxo de trabalho

O fluxo mais comum do repositório é o seguinte:

1. `ask-matt` ou `setup-matt-pocock-skills` para orientar o início e preparar o ambiente;
2. `grill-with-docs` e `domain-modeling` para definir a ideia e o vocabulário;
3. `to-spec` para transformar a conversa em uma especificação formal;
4. `to-tickets` para quebrar em entregas menores e organizadas;
5. `implement` para desenvolver a solução;
6. `code-review` para verificar a qualidade da entrega;
7. `research` para investigar fontes confiáveis;
8. `triage` para organizar issues e pendências.

Esse ciclo reduz ruído, melhora a comunicação com o agente e aumenta a chance de que a implementação fique alinhada com a necessidade real do projeto.

---

## Exemplo de uso prático em sequência

Uma forma comum de utilizar as skills é:

- o usuário tem uma ideia de funcionalidade;
- usa `grill-with-docs` para entender melhor a demanda e registrar termos do domínio;
- transforma a conversa em `to-spec`;
- divide em tarefas com `to-tickets`;
- começa a implementação com `implement`;
- valida com `code-review`;
- usa `research` quando a dúvida precisa de fonte primária;
- usa `triage` quando surge uma issue nova ou backlog externo.

Esse encadeamento torna o processo mais previsível e mais fácil de seguir em projetos reais.

---

## Referências internas

As informações deste README foram extraídas dos arquivos de skill localizados em [.github/skills](../../../.github/skills), da documentação de agentes em [docs/agents](../) e da lógica de workflow descrita no README de referência do projeto Matt Pocock. A combinação dessas fontes mantém a documentação alinhada com a estrutura real do repositório e com a intenção original das skills.
