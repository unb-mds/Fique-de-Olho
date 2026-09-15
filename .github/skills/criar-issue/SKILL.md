---
name: criar-issue
description: "Transforma descricoes de tarefas, problemas ou melhorias em GitHub Issues estruturadas. Use quando o usuario quiser criar, rascunhar, organizar ou publicar uma issue no repositorio atual. Analisa lacunas, faz perguntas, apresenta uma versao final para aprovacao e somente depois usa o GitHub CLI para criar a issue."
argument-hint: "Descreva a tarefa, problema ou melhoria para transformar em issue"
user-invocable: true
disable-model-invocation: false
---

# Criar Issue

## Objetivo

Converter uma descricao fornecida pelo usuario em uma GitHub Issue clara, rastreavel e pronta para revisao, sem inventar requisitos, arquivos, tecnologias ou comportamentos.

## Quando usar

- Criar uma nova GitHub Issue a partir de uma tarefa, problema, bug ou melhoria.
- Organizar uma solicitacao ainda incompleta antes de publica-la.
- Gerar um rascunho de issue para o repositorio atual.

## Procedimento

1. Leia a solicitacao inteira e identifique o tipo da issue: funcionalidade, melhoria, bug ou tarefa.
2. Extraia somente as informacoes fornecidas pelo usuario e, quando aplicavel, fatos descobertos no projeto atual.
3. Verifique se existem informacoes essenciais ausentes, como o objetivo, o comportamento esperado, o problema observado ou as condicoes de conclusao.
4. Se houver lacunas que impeçam uma issue objetiva, faca perguntas curtas e especificas ao usuario. Aguarde as respostas antes de montar a versao final.
5. Se a solicitacao depender do estado do repositorio, examine apenas os arquivos e referencias necessarios para confirmar os fatos. Nao presuma detalhes que nao estejam no pedido ou no projeto.
6. Monte a issue com um titulo curto e objetivo. O titulo deve indicar claramente se e uma funcionalidade, melhoria, bug ou tarefa.
7. Escreva a descricao exatamente com as secoes abaixo:

   ```markdown
   ## Contexto
   Explique brevemente o motivo da tarefa.

   ## Problema ou objetivo
   Explique o que precisa ser resolvido ou desenvolvido.

   ## Solucao proposta
   Descreva a solucao esperada sem acrescentar informacoes nao fornecidas ou descobertas.

   ## Criterios de aceite
   - [ ] Condicao objetiva para considerar a issue concluida.

   ## Tarefas
   - [ ] Etapa necessaria para implementar a solucao.
   ```

8. Nos criterios de aceite, use somente condicoes verificaveis derivadas da solicitacao. Se nao houver criterios suficientes, pergunte antes de prosseguir.
9. Nas tarefas, liste as etapas conhecidas usando checkboxes. Nao transforme suposicoes em tarefas.
10. Mostre ao usuario o titulo e a descricao completos para revisao. Pergunte explicitamente se ele aprova a criacao da issue.
11. Nao crie, edite nem publique a issue antes de receber uma aprovacao clara do usuario. Uma solicitacao inicial para "criar uma issue" nao substitui essa aprovacao da versao final.
12. Depois da aprovacao, confirme que esta no repositorio atual e verifique se o GitHub CLI esta disponivel e autenticado, por exemplo com `gh auth status`.
13. Se o GitHub CLI estiver configurado, crie a issue usando o titulo e a descricao aprovados, por exemplo:

   ```powershell
   gh issue create --title "TITULO_APROVADO" --body-file "CAMINHO_DO_ARQUIVO_TEMPORARIO"
   ```

   Preserve acentos e toda a formatacao aprovada ao passar a descricao. Prefira `--body-file` para evitar problemas de escaping no shell.
14. Se o GitHub CLI nao estiver instalado, autenticado ou associado ao repositorio, informe exatamente o que falta configurar. Nao diga que a issue foi criada e nao tente simular o resultado.
15. Apos uma criacao bem-sucedida, informe o numero e o link retornados pelo GitHub CLI.

## Regras de qualidade

- Nao invente requisitos, arquivos, tecnologias, labels, milestones, responsaveis ou comportamentos.
- Nao adicione labels, milestones ou assignees sem solicitacao explicita.
- Mantenha o titulo especifico e conciso.
- Mantenha contexto, problema, solucao, criterios e tarefas coerentes entre si.
- Diferencie claramente fatos confirmados, informacoes fornecidas e pontos ainda pendentes.
- Se a issue continuar ambigua depois das perguntas, nao publique; apresente o que ainda falta decidir.
- A aprovacao deve ocorrer depois que a versao final estiver visivel ao usuario e antes do comando de criacao.

## Resultado esperado

- Antes da aprovacao: um rascunho completo da issue, pronto para revisao.
- Apos a aprovacao e criacao: o numero e o link da GitHub Issue.
- Se a criacao nao for possivel: uma explicacao honesta do bloqueio e dos passos de configuracao necessarios.
