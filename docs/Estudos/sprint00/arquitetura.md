# Arquitetura de Software

## Conceito 
    - A arquitetura de software é basicamente a estrutura de um projeto em que são estabelecidas regras, fluxo de informações e também as base para organizar os componentes de um sistema e suas relações com o objetivo de tornar o ciclo de vida do software mais flexível a alterações e sem conflitos.


## Tópicos fundamentais para o estudo de Arquitetura de Software:
    - Princípios SOLID
    - Acoplamento e Coesão
    - Clean Code
    - Estrutura de dados
#### Essencialmente, é importante ter uma noção de como deixar o código limpo e legível, ter noções de orientação a objetos, ter conhecimentos básicos em como dados são manipulados.

## Atributos de Qualidade (Requisitos Não-Funcionais)
A arquitetura é guiada por atributos de qualidade essenciais para o sistema:
- **Manutenibilidade:** Facilidade de alterar, corrigir e evoluir o código sem introduzir falhas.
- **Escalabilidade:** Capacidade de suportar o aumento de carga (usuários ou dados) de forma estável.
- **Desempenho:** Baixa latência e uso eficiente de recursos (CPU, memória e rede).
- **Segurança:** Proteção de dados e integridade contra acessos não autorizados.
- **Confiabilidade:** Alta disponibilidade do serviço e tolerância a falhas.

## Padrões Arquiteturais

### Arquitetura de Camadas:
    - É dividido em vários camadas (segmentos) o projeto, em que elas normalmente seguem um fluxo unidirecional de requisições de forma hierárquica.

    - Normalmente as camadas mais comuns de um projeto são: Apresentação (frontend) - responsável pela interface do usuário; Negócio - responsável pela operação e fluxo de negócios em relação a alguma requisição; Persistência - responsável pela comunicação de dados entre o banco de dados e o resto do sistema; Banco de Dados - responsável pelo armazenamento de dados.

    ![ilustração do diagrama da arquitetura em camadas](https://res.cloudinary.com/mahenrique94/image/upload/v1640213006/Untitled_Diagram.drawio_2_ohi7x2.png)

### Arquitetura MVC (Model-View-Controller)
    - É divido em três partes bem definidas, sendo o View a interface visual (frontend), o Controller a parte que intermedia as outras duas partes comunicando entre elas ao processar os dados e o Model que é onde acontece as regras de negócios e armazena os dados.

### Monolítico vs. Microsserviços
- **Monólito:** Aplicação unificada em um único repositório/deploy. Possui menor complexidade operacional inicial, mas pode limitar a escalabilidade independente de componentes.
- **Microsserviços:** Divisão em serviços autônomos comunicando-se por rede (APIs/mensageria). Oferece escalabilidade granular, porém eleva a complexidade de infraestrutura.

### Arquitetura Limpa / Hexagonal (Ports & Adapters)
- Isola o domínio e as regras de negócio de agentes externos (bancos, APIs, frameworks). A lógica central permanece independente, facilitando testes e evolução técnica.

## Decisões Arquiteturais e Trade-offs
- **Sem bala de prata:** Toda escolha arquitetural envolve concessões (*trade-offs*), equilibrando simplicidade, custo, performance e manutenibilidade.
- **ADRs (Architectural Decision Records):** Prática ágil para registrar o contexto, a justificativa e as consequências das decisões estruturais do projeto.

## Mais materiais para aprender sobre Arquitetura de Software:
    - https://www.youtube.com/watch?v=mkx0CdWiPRA (SOLID)
    - https://www.youtube.com/watch?v=poJhAnAQd4I (Acoplamento e Coesão)
    - https://www.youtube.com/watch?v=ln6t3uyTveQ (Clean Code)
    - https://www.youtube.com/watch?v=N9w5-TChccQ (Regras de Negócios)
    - https://www.youtube.com/watch?v=jyTNhT67ZyY (arquitetura MVC)
    - https://imasters.com.br/arquitetura-da-informacao/arquitetura-em-camadas (arquitetura em camadas)
    - https://martinfowler.com/architecture/ (Guia de Arquitetura - Martin Fowler)
    - https://adr.github.io/ (Padrão de ADRs)
