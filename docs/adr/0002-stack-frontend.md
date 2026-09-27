# 0002. Escolha da Stack do Frontend (React, TypeScript e Vite)

---
status: accepted
date: 2026-09-24
---

## Contexto e Decisão

Para viabilizar a interface web da plataforma **Fique de Olho** (busca por palavra-chave e semântica, filtragem multifacetada, visualização de detalhes e salvamento de favoritos de editais da UnB), decidimos adotar a seguinte stack tecnológica no frontend:

1. **React**: biblioteca declarativa para construção de interfaces reativas baseadas em componentes reutilizáveis.
2. **TypeScript**: linguagem com tipagem estática para garantia de segurança nos contratos de dados consumidos da API FastAPI.
3. **Vite**: ferramenta de empacotamento (*bundler*) e servidor de desenvolvimento leve e de alta performance.
4. **HTML5 Semântico e CSS3 Responsivo**: foco em acessibilidade (conformidade WCAG 2.1 AA) e baixo consumo de dados móveis em dispositivos celulares.

Essa combinação permite lidar com a reatividade exigida pelos filtros dinâmicos de editais mantendo um contrato de tipos seguro com os modelos Pydantic do backend.

## Opções Consideradas

* **Biblioteca / Framework de Interface:**
  * *React (Escolhida)*: Ecossistema consolidado, ampla familiaridade na comunidade de software e suporte maduro a componentes reativos para gerenciar buscas, listagens paginadas e favoritos.
  * *Vanilla TS (HTML + DOM nativo)*: Descartado para a interface completa por exigir manipulação manual de nós do DOM para sincronizar múltiplos filtros combinados (campus, decanato, status, período), tornando a manutenção propensa a bugs de estado.
  * *Vue.js*: Boa reatividade e curva de aprendizado suave, porém menor alinhamento com a base de conhecimento prévia da equipe em comparação ao React.
  * *Next.js (SSR / Fullstack)*: Descartado no momento por introduzir dependência de um servidor Node.js intermediário para SSR, quando o projeto já possui um backend dedicado em FastAPI.

* **Linguagem de Programação:**
  * *TypeScript (Escolhida)*: Elimina erros de execução ao mapear os schemas do FastAPI (OpenAPI), garantindo autocompletion e validação estática de props e estados.
  * *JavaScript Puro*: Descartado pela fragilidade ao manipular estruturas aninhadas de editais (datas de retificações, anexos opcionais, metadados nulos) sem checagem em tempo de compilação.

* **Ferramenta de Build / Empacotamento:**
  * *Vite (Escolhida)*: Inicialização quase instantânea, Hot Module Replacement (HMR) eficiente e compilação otimizada para React + TypeScript.
  * *Create React App (CRA)*: Descartado por estar obsoleto e sem manutenção ativa.
  * *Webpack*: Descartado pela complexidade de configuração e lentidão em relação ao Vite.

## Consequências

* **Positivas (Vantagens):**
  * **Gerenciamento Declarativo de Estados e Filtros**: A busca de editais combina múltiplos critérios simultâneos (texto, decanatos como DEG/DAC, campus e status aberto/encerrado). O React sincroniza o estado e a re-renderização da interface de maneira previsível.
  * **Componentização Reutilizável com Tipagem Estrita**: Componentes críticos como `CardEdital`, `FiltroLateral`, `ModalDetalhes` e `BotaoFavorito` possuem propriedades delimitadas por interfaces TypeScript (`interface CardEditalProps`), facilitando testes isolados e desenvolvimento paralelo no time de MDS.
  * **Tipagem Sincronizada com o Backend**: Utilização de ferramentas como `openapi-typescript` para derivar tipos diretamente do schema OpenAPI gerado pelo FastAPI, fazendo com que qualquer quebra de contrato na API seja detectada imediatamente no build do frontend.
  * **Tratamento de Dados Nulos/Opcionais**: Como editais variam na presença de retificações, anexos ou links externos, o TypeScript força os desenvolvedores a tratarem condicionais antes da renderização em tela.

* **Trade-offs / Riscos identificados (Cuidados):**
  * **Controle de Bundle Size para Redes Móveis**: O React adiciona um peso inicial de runtime JavaScript. Para cumprir os requisitos de carregamento rápido e leveza em dados móveis (especificados nas Personas do projeto), deve-se evitar bibliotecas externas pesadas e utilizar divisão de código (*code splitting* com `React.lazy`).
  * **Curva de Aprendizado com Hooks e Ciclo de Vida**: Membros da equipe precisam dominar não apenas TypeScript, mas também convenções de hooks (`useState`, `useEffect`, `useMemo`) para evitar renderizações excessivas ou vazamento de estado.
  * **Disciplina Contra o Tipo `any`**: O uso inadvertido de `any` em props ou chamadas de API desativa a proteção do compilador, exigindo configuração estrita no `tsconfig.json` e linter (ESLint).
  * **SEO e Renderização Client-Side (SPA)**: Por renderizar no navegador do usuário, o conteúdo dos editais não está presente no HTML bruto inicial; caso seja necessário indexação profunda por motores de busca no futuro, estratégias de pré-renderização estática deverão ser avaliadas.
