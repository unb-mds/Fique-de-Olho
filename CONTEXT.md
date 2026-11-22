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
Vínculo estabelecido pelo usuário para salvar um Edital em sua lista pessoal de consulta e acompanhamento.
_Avoid_: Curtida, item salvo, bookmark genérico, edital favorito

**Alerta de Edital**:
Ativação explícita feita pelo usuário para receber notificações por e-mail sobre atualizações relevantes e prazos de inscrição de um Edital específico.
_Avoid_: Favorito com e-mail, sininho, assinatura genérica

**Prazo de inscrição**:
Intervalo formado pela data inicial e pela data final em que uma pessoa pode se inscrever em um Edital.
_Avoid_: Cronograma completo, prazo genérico

**Catálogo controlado**:
Conjunto de valores previamente definidos e mantidos pelo sistema para classificar Editais, como categorias, campi e cursos.
_Avoid_: Texto livre, tag improvisada

**Texto extraído**:
Conteúdo textual obtido pelo backend a partir do PDF oficial durante a coleta automatizada, para permitir busca e consulta na plataforma, mantendo o link do documento original.
_Avoid_: Cópia integral do PDF armazenada localmente, resumo manual

**Atualização relevante**:
Alteração detectada em datas ou prazos, status, documentos, ou no título e órgão de um Edital monitorado por alerta.
_Avoid_: Qualquer alteração técnica, mudança de hash sem alteração observável

**Notificação de atualização**:
Mensagem de e-mail enviada quando uma atualização relevante de um Edital com alerta ativado é descoberta, contendo um resumo e o link original do edital.
_Avoid_: Resumo diário, alerta genérico

**Notificação de encerramento**:
Mensagem de e-mail que lembra o usuário sobre o prazo de inscrição de um Edital com alerta ativado três dias antes, um dia antes e no dia do fechamento.
_Avoid_: Notificação de prazo genérica
