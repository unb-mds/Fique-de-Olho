# Cibersegurança — Proteção do Projeto

## 1. Objetivo

Cibersegurança reúne práticas para proteger sistemas, dados e usuários contra acessos não autorizados, alterações indevidas, vazamentos e indisponibilidade.

## 2. Práticas essenciais

- **Controle de acesso:** conceder a cada pessoa e serviço somente as permissões necessárias.
- **Autenticação:** utilizar senhas fortes e autenticação multifator quando disponível.
- **Segredos:** manter tokens, senhas e chaves fora do código e do repositório, usando variáveis de ambiente ou um gerenciador de segredos.
- **Validação de entradas:** validar dados recebidos para reduzir riscos de injeção e manipulação.
- **Dependências:** manter bibliotecas atualizadas e verificar vulnerabilidades conhecidas.
- **Comunicação:** utilizar HTTPS e proteger dados sensíveis durante a transmissão.
- **Backups:** manter cópias de segurança e testar a restauração.
- **Logs:** registrar eventos relevantes sem expor senhas, tokens ou dados pessoais.

## 3. Segurança em cada etapa

1. **Planejamento:** identificar dados sensíveis, usuários, ativos e possíveis ameaças.
2. **Desenvolvimento:** seguir práticas seguras e não incluir credenciais no código.
3. **Revisão e testes:** revisar alterações, testar permissões e verificar vulnerabilidades.
4. **Publicação:** revisar configurações, dependências e acessos do ambiente.
5. **Manutenção:** acompanhar alertas, corrigir falhas e atualizar componentes.
6. **Incidentes:** definir como comunicar, investigar, conter e recuperar o sistema.

## 4. Segurança no Git e GitHub

- Não versionar arquivos `.env`, credenciais ou chaves privadas.
- Utilizar um arquivo `.env.example` com valores fictícios para documentar as variáveis necessárias.
- Proteger a branch principal e exigir revisão de Pull Requests.
- Executar verificações de dependências e análise de código.
- Se um segredo for enviado ao repositório, revogá-lo ou rotacioná-lo imediatamente; apagar o arquivo do histórico, por si só, não invalida a credencial.

## 5. Checklist mínimo

- [ ] Credenciais fora do repositório.
- [ ] Permissões seguindo o princípio do menor privilégio.
- [ ] Entradas e dados validados.
- [ ] Dependências verificadas e atualizadas.
- [ ] Revisão de código antes do merge.
- [ ] Backups e restauração testados.
- [ ] Processo básico de resposta a incidentes definido.

## Referências

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
