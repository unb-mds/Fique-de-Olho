# Roteiro dos slides

Este roteiro segue a estrutura do `RoteiroEntrega.md`, especialmente o **Roteiro de Apresentação - Release 2**, e adapta cada parte ao estado atual do projeto Fique de Olho. A apresentação deve ter aproximadamente 7 minutos.

## Slide 1 - Abertura

**Título:** Fique de Olho - Editais UnB

Fala sugerida:

> Somos o grupo G4, da disciplina de Métodos de Desenvolvimento de Software da UnB. Nesta apresentação vamos mostrar o problema identificado, a solução desenvolvida, a arquitetura escolhida e as evidências da implementação.

Mostrar: nome do projeto e integrantes.

## Slide 2 - Contexto e problema

Fala sugerida:

> Os editais da UnB são publicados em diferentes páginas e documentos extensos. Para o estudante, isso dificulta encontrar oportunidades, entender os prazos e acompanhar alterações. O problema é ainda maior para quem acessa principalmente pelo celular ou tem pouco tempo para consultar várias fontes.

Mostrar: um fluxo simples representando páginas, PDFs e estudante.

## Slide 3 - Público e objetivo

Fala sugerida:

> O produto foi pensado para a comunidade discente da UnB. Nosso objetivo é centralizar editais, organizar as informações principais e permitir que o estudante encontre rapidamente o que é relevante para seu perfil.

Mostrar: uma persona ou os principais perfis atendidos.

## Slide 4 - Solução desenvolvida

Fala sugerida:

> O Fique de Olho reúne os editais em uma interface única. A aplicação apresenta editais em aberto, permite filtrar por categoria, mostra prazos e oferece uma página de detalhes com acesso ao documento oficial.

Mostrar: protótipo ou captura da página inicial.

## Slide 5 - Demonstração do produto

Demonstrar nesta ordem:

1. Página inicial.
2. Quantidade de editais ativos.
3. Filtros por categoria.
4. Card de um edital.
5. Navegação para a página de detalhes.
6. Datas, status e link do documento oficial.

Fala de transição:

> Agora vamos mostrar o fluxo principal que o estudante utiliza para sair da listagem e chegar às informações do edital.

## Slide 6 - Arquitetura e tecnologias

Fala sugerida:

> A solução foi dividida em frontend e backend. O frontend utiliza React, TypeScript e Vite. O backend utiliza FastAPI e expõe uma API documentada pelo Swagger. Também implementamos um scraper com HTTPX e BeautifulSoup para coletar informações das páginas institucionais.

Fluxo:

```text
Portal da UnB -> Scraper -> API FastAPI -> Frontend React
                                      -> PostgreSQL planejado
```

Mostrar: diagrama simples com setas.

## Slide 7 - Qualidade, testes e DevOps

Mostrar:

- Swagger em `/docs`.
- Healthcheck em `/health`.
- Testes do backend.
- Testes do scraper com HTML simulado.
- Resultado de `npm run lint`.
- Resultado de `npm run build`.

Fala sugerida:

> A implementação foi acompanhada por verificações de qualidade. O backend possui testes para o healthcheck, endpoints e scraper. No frontend, utilizamos TypeScript, ESLint e build de produção. Docker Compose também facilita a execução padronizada do backend.

## Slide 8 - Gestão ágil e produção

Fala sugerida:

> O desenvolvimento foi organizado a partir de requisitos, personas, story map, backlog e decisões arquiteturais. Esses artefatos ficam versionados no repositório e ajudam a manter a rastreabilidade entre o problema, as funcionalidades e a implementação.

Mostrar:

- [Backlog do produto](../Requisitos/produto/backlog.md).
- [Personas](../Requisitos/produto/personas.md).
- [Story Map](../Requisitos/StoryMap.md).
- Issues, pull requests ou commits do repositório, caso estejam disponíveis.
- [ADRs](../adr/0001-stack-backend.md) como evidência das decisões técnicas.

Não apresentar métricas de velocity, cobertura ou CI/CD como concluídas se elas ainda não estiverem registradas.

## Slide 9 - Organização do projeto

Mostrar a estrutura:

```text
Back/app/modules/  -> módulos da API e scraper
Front/src/pages/   -> páginas
Front/src/components/ -> componentes reutilizáveis
Front/src/services/ -> comunicação com a API
docs/              -> requisitos, ADRs e documentação
```

Fala sugerida:

> A separação por módulos facilita o desenvolvimento em equipe e torna mais claro onde cada responsabilidade deve ser implementada. Requisitos, decisões e contexto do domínio também ficam versionados no repositório.

## Slide 10 - Lições aprendidas

Fala sugerida:

> Aprendemos que definir o domínio e o escopo antes da implementação ajuda a evitar funcionalidades desconectadas do problema real. Também percebemos a importância de manter o contrato entre frontend e backend bem definido e de testar o scraper com HTML simulado, sem depender da internet.

Aprendizados para destacar:

- decisões técnicas documentadas em ADRs;
- separação do frontend em páginas, componentes e serviços;
- testes do scraper com dados controlados;
- importância de alinhar o que está implementado com o que é apresentado;
- necessidade de evoluir a persistência e a automação em uma próxima entrega.

## Slide 11 - Limitações e próximos passos

Fala sugerida:

> Nesta versão, a API ainda utiliza dados em memória. Como próximos passos, planejamos integrar a persistência no PostgreSQL, automatizar a coleta, implementar autenticação, favoritos persistidos, notificações e pipeline de CI/CD.

Importante: apresentar esses itens como evolução planejada, não como funcionalidades já concluídas.

## Slide 12 - Conclusão e encerramento

Fala sugerida:

> Nesta entrega, validamos o problema, o escopo, a arquitetura, as tecnologias e o primeiro fluxo funcional do produto. O Fique de Olho transforma uma busca dispersa por editais em uma experiência centralizada e mais simples para os estudantes da UnB. Obrigado.

## Checklist antes de apresentar

- [ ] Inserir nomes corretos dos integrantes.
- [ ] Adicionar capturas reais do frontend.
- [ ] Adicionar uma captura do Swagger.
- [ ] Conferir se a API e o frontend iniciam localmente.
- [ ] Salvar a versão final dos slides em PDF.
- [ ] Colocar o PDF em `docs/apresentacao/`.
- [ ] Adicionar o link do PDF ao README principal.
- [ ] Ensaiar a apresentação entre 6:45 e 7:00.
- [ ] Ter capturas ou vídeo como backup da demonstração.
