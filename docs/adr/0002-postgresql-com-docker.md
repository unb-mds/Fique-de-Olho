---
status: accepted
date: 2026-09-25
---

# PostgreSQL com Docker

## Contexto e decisão

O projeto precisa de um banco relacional compartilhado pela equipe para armazenar editais do DEG, catálogos controlados, usuários, favoritos e notificações. Também precisa consultar texto extraído dos PDFs e poderá receber busca vetorial em uma entrega futura.

Foi decidido utilizar **PostgreSQL** executado por meio de **Docker Compose** no ambiente de desenvolvimento.

## Motivos

- oferece relacionamentos, restrições e buscas textuais adequadas ao domínio;
- permite que toda a equipe use a mesma versão do banco sem instalar o serviço diretamente no sistema operacional;
- facilita iniciar, parar e recriar o ambiente local;
- mantém aberta a possibilidade de adicionar busca vetorial futuramente;
- integra-se bem ao backend em FastAPI e às ferramentas de migration.

## Consequências

- o projeto precisará manter um arquivo de configuração do Docker Compose;
- credenciais e URLs de conexão devem ser fornecidas por variáveis de ambiente;
- a estrutura do banco deverá ser criada e alterada por migrations versionadas;
- os dados locais do banco devem ficar em um volume do Docker, fora do controle de versão;
- a equipe precisará executar Docker para desenvolver e testar a aplicação.