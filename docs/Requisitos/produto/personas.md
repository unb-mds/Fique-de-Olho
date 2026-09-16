# Personas do Projeto: NotificaDEG / Radar DEG UnB

Este documento apresenta as personas desenvolvidas para o sistema de busca, análise, filtragem e notificação de editais do Decanato de Ensino de Graduação da Universidade de Brasília (DEG UnB).

As personas foram elaboradas com base no público heterogêneo da UnB, cobrindo diferentes perfis socioeconômicos, demandas acadêmicas e necessidades de acessibilidade.

---

## 1. Persona 1: Estudante Graduando Cotista

![Avatar Lucas](https://api.dicebear.com/7.x/bottts/svg?seed=Lucas "Lucas Alves")

### **Lucas Alves, 21 anos**
* **Ocupação:** Estudante do 4º semestre de Engenharia de Software (Campus Darcy Ribeiro / FGA).
* **Condição:** Aluno cotista (renda / escola pública), beneficiário de auxílios socioeconômicos.
* **Acesso à Tecnologia:** Utiliza prioritariamente smartphone com plano de dados móveis limitado; acesso a computador quase exclusivo nos laboratórios da UnB.
* **Nível de Familiaridade Técnica:** Médio a Avançado.

#### Perfil e Rotina
> *"Concilio disciplinas puxadas com a busca constante por bolsas para me manter em Brasília. Se eu perder um prazo de edital por falta de aviso, coloco meu semestre em risco."*

Lucas mora em uma região administrativa distante do campus e passa cerca de 3 horas diárias no transporte público. Sua permanência na universidade depende diretamente de bolsas (permanência, alimentação, extensão ou monitoria remunerada). Devido à rotina exaustiva, ele não tem tempo de abrir o site do DEG diariamente para checar se saíram novos editais ou retificações de prazos.

#### Objetivos e Metas
* Encontrar rapidamente editais que ofereçam **bolsas remuneradas** e auxílios de permanência.
* Ser avisado em tempo real assim que um novo edital do seu interesse ou uma **retificação de prazo/cronograma** for publicada.
* Entender de forma resumida e direta os pré-requisitos e documentação necessária sem ter que ler PDFs de 40 páginas pelo celular.

#### Dores e Frustrações
* Sites institucionais da UnB fragmentados, difíceis de navegar pelo celular e sem alertas.
* Editais publicados em PDFs digitalizados ou sem formatação acessível que consomem seus dados móveis.
* Prazos de inscrição muito curtos (muitas vezes de apenas 3 a 5 dias úteis) que ele só descobre quando já encerraram.

#### Como o sistema resolve a dor do Lucas:
* **Filtros específicos:** Permite filtrar por tipo "Bolsas / Auxílios" e "Monitoria Remunerada".
* **Notificações instantâneas:** Alertas push/e-mail no smartphone assim que o edital é lançado.
* **Resumo inteligente do edital:** Destaque dos prazos de inscrição, valor da bolsa e documentos exigidos logo no card do edital.
* **Interface leve e responsiva:** Baixo consumo de dados móveis e acessível em qualquer tela.

---

## 2. Persona 2: Estudante Graduanda (Foco em Monitoria e PIBIC)

![Avatar Mariana](https://api.dicebear.com/7.x/bottts/svg?seed=Mariana "Mariana Silveira")

### **Mariana Silveira, 19 anos**
* **Ocupação:** Estudante do 3º semestre de Ciências Biológicas (Campus Darcy Ribeiro).
* **Condição:** Estudante de graduação com bom rendimento acadêmico (IRA alto), em busca de experiência acadêmica e créditos complementares.
* **Acesso à Tecnologia:** Notebook próprio e celular iOS/Android, conexão Wi-Fi frequente.
* **Nível de Familiaridade Técnica:** Intermediário (usuária assídua de plataformas digitais, redes sociais e apps acadêmicos).

#### Perfil e Rotina
> *"Quero enriquecer meu currículo para tentar pós-graduação no futuro. Preciso conseguir uma monitoria no meu departamento ou uma vaga de iniciação científica (PIBIC), mas os editais saem em datas imprevistas."*

Mariana frequenta aulas em tempo integral e participa de ligas acadêmicas. Ela tem grande interesse em atuar como monitora nas disciplinas introdutórias de biologia ou participar de projetos de iniciação científica e extensão. No entanto, os editais do DEG e dos institutos saem de maneira descentralizada, e muitas vagas exigem critérios específicos (como ter cursado a matéria com menção SS/MS ou ter completado certo número de créditos).

#### Objetivos e Metas
* Filtrar editais exatamente pelo seu **curso (Ciências Biológicas)**, **campus (Darcy Ribeiro)** e **tipo de edital (Monitoria / PIBIC / Extensão)**.
* Visualizar claramente a quantidade de vagas (remuneradas vs. voluntárias) e critérios de elegibilidade (IRA mínimo, pré-requisitos).
* Salvar editais em uma lista de "Favoritos" para acompanhar o status (aberto, homologação, resultado final).

#### Dores e Frustrações
* Dificuldade de saber se um edital geral do DEG contempla o seu curso específico ou se é voltado a outras áreas.
* Perder editais de monitoria porque foram divulgados apenas em murais físicos ou em links ocultos na página do DEG.
* Falta de clareza sobre o cronograma das fases (inscrição, recurso, divulgação do resultado).

#### Como o sistema resolve a dor da Mariana:
* **Filtros combinados:** Campus Darcy Ribeiro + Curso Ciências Biológicas + Tipo Monitoria/PIBIC.
* **Acompanhamento de prazos:** Linha do tempo visual indicando abertura, encerramento de inscrições e data do resultado.
* **Notificações por tags de interesse:** Recebe notificações personalizadas apenas quando surgem vagas para sua área.

---

## 3. Persona 3: Estudante que quer Trocar de Curso (Mudança de Curso / Transferência)

![Avatar Rafael](https://api.dicebear.com/7.x/bottts/svg?seed=Rafael "Rafael Mendes")

### **Rafael Mendes, 22 anos**
* **Ocupação:** Estudante do 5º semestre de Administração (Campus Darcy Ribeiro), com intenção de transferência interna para Ciência da Computação.
* **Condição:** Estudante veterano enfrentando desmotivação com o curso atual, planejando transferência facultativa interna ou mudança de curso pelo DEG.
* **Acesso à Tecnologia:** Computador desktop em casa e smartphone.
* **Nível de Familiaridade Técnica:** Alto.

#### Perfil e Rotina
> *"Estou decidido a mudar para a área de tecnologia. O edital de Mudança de Curso do DEG é extremamente concorrido, burocrático e se você errar uma certidão ou perder o dia da inscrição, tem que esperar mais um ano."*

Rafael já cursou disciplinas equivalentes como aluno especial e estuda a matriz curricular de Ciência da Computação. Os editais do DEG de **Mudança de Curso**, **Transferência Facultativa (TF)** e **Portador de Diploma (PD)** têm regras rígidas de aproveitamento de créditos, prazos severos de entrega de documentação e critérios de desempate complexos.

#### Objetivos e Metas
* Localizar com precisão o histórico e as novas publicações dos editais de **Mudança de Curso / Transferência Facultativa do DEG**.
* Filtrar os cursos de destino que ofertam vagas ociosas para o semestre vigente.
* Receber alerta prioritário no exato momento da publicação da minuta do edital e da abertura das inscrições.

#### Dores e Frustrações
* Os editais de transferência contêm tabelas extensas com dezenas de cursos, dificultando achar se há vaga para o curso desejado no seu campus.
* As retificações de editais de transferência do DEG acontecem com frequência e alteram calendários sem aviso ostensivo.
* A linguagem excessivamente burocrática dos editais gera medo de indeferimento de inscrição.

#### Como o sistema resolve a dor do Rafael:
* **Extração e análise dos editais:** O sistema processa o edital e lista o número exato de vagas abertas por curso de destino e campus.
* **Filtro temático:** Categoria dedicada a "Mudança de Curso / Vagas Ociosas / Transferência".
* **Radar de Retificações:** Notificação imediata caso o edital sofra retificação ou alteração de cronograma.

---

## Matriz Comparativa das Personas

| Critério | Lucas Alves (Cotista) | Mariana Silveira (Graduanda) | Rafael Mendes (Troca de Curso) |
| :--- | :--- | :--- | :--- |
| **Principal Necessidade** | Bolsas de permanência / remuneração | Monitoria / Iniciação Científica (PIBIC) | Edital de Mudança de Curso / Transferência |
| **Filtros Mais Usados** | Tipo: Bolsas, Auxílios, Prazos urgentes | Campus: Darcy, Curso: Biologia, Tipo: Monitoria | Tipo: Vagas Ociosas/Mudança, Curso: Computação |
| **Canal de Notificação Preferido** | Push no celular / WhatsApp | Push no app / E-mail | E-mail / Push com alertas de retificação |
| **Dispositivo Principal** | Smartphone (baixo consumo de dados) | Notebook e Smartphone | Desktop e Smartphone |
| **Requisito Crítico** | Resumo simples do edital e acessibilidade | Linha do tempo de datas e requisitos de IRA | Quadro de vagas por curso e alertas de mudanças |

---

## Histórico de Revisões

| Data | Versão | Descrição | Autor |
| :---: | :---: | :--- | :--- |
| 10/09/2026 | 1.0 | Definição das 3 personas oficiais (Cotista, Graduanda Monitoria/PIBIC, Troca de Curso) | Grupo 4 |
