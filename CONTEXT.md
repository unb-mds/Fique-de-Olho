# Fique de Olho - Domínio de Editais UnB

Plataforma acadêmica destinada a centralizar, estruturar, filtrar e notificar a comunidade universitária sobre editais e oportunidades da Universidade de Brasília (UnB).

## Language

**Edital**:
Documento oficial publicado por unidades ou decanatos da UnB (DEG, DAC, DPG, etc.) que regulamenta processos seletivos, bolsas, auxílios e oportunidades com regras e prazos bem delimitados.
_Avoid_: Publicação avulsa, postagem, notícia, PDF solto

**Retificação**:
Alteração formal publicada que modifica itens pontuais de um Edital prévio (como prorrogação de prazos ou revisão de vagas), devendo permanecer estritamente associada ao Edital de origem.
_Avoid_: Novo edital, errata avulsa, edital secundário

**Ingestão / Coleta**:
Processo automatizado de monitoramento e extração periódica de novos editais e seus respectivos anexos a partir das páginas institucionais da UnB.
_Avoid_: Cadastro manual, sincronização de portal

**Favorito**:
Vínculo estabelecido pelo usuário para acompanhar ativamente as atualizações, prazos e retificações de um edital específico.
_Avoid_: Curtida, item salvo, bookmark genérico

**Busca Semântica**:
Modalidade de pesquisa baseada em similaridade vetorial (significado e contexto da intenção do usuário), indo além da correspondência exata de palavras-chave.
_Avoid_: Busca por texto exato, filtro textual simples

**Prazo de inscrição**:
Intervalo formado pela data inicial e pela data final em que uma pessoa pode se inscrever em um Edital.
_Avoid_: Cronograma completo, prazo genérico

**Catálogo controlado**:
Conjunto de valores previamente definidos e mantidos pelo sistema para classificar Editais, como tipos, campi e cursos. No escopo atual, os tipos são `Extensões` e `Bolsas / Auxílios`.
_Avoid_: Texto livre, tag improvisada

**Texto extraído**:
Conteúdo textual obtido pelo backend a partir do PDF oficial durante a coleta automatizada, para permitir busca e consulta na plataforma, mantendo o link do documento original.
_Avoid_: Cópia integral do PDF armazenada localmente, resumo manual

**Edital favorito**:
Edital que um usuário escolheu acompanhar ativamente para receber informações sobre alterações relevantes e prazos de inscrição.
_Avoid_: Edital curtido, item salvo

**Atualização relevante**:
Alteração detectada em datas ou prazos, status, documentos, ou no título e órgão de um edital favorito.
_Avoid_: Qualquer alteração técnica, mudança de hash sem alteração observável

**Notificação de atualização**:
Mensagem de email enviada quando uma atualização relevante de um edital favorito é descoberta, contendo um resumo e o link original do edital.
_Avoid_: Resumo diário, alerta genérico

**Notificação de encerramento**:
Mensagem de email que lembra o usuário sobre o prazo de inscrição de um edital favorito três dias antes, um dia antes e no dia do fechamento.
_Avoid_: Notificação de prazo genérica
