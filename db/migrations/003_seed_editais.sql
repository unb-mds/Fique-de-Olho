-- Popula tipos adicionais usados no protótipo e editais de demonstração
INSERT INTO tipos_editais (nome)
VALUES
    ('Monitoria'),
    ('Pesquisa'),
    ('Estágio'),
    ('PIBIC'),
    ('Vestibular')
ON CONFLICT (nome) DO NOTHING;

INSERT INTO editais (identificador_origem, titulo, resumo, url_pdf, data_publicacao, inicio_inscricao, fim_inscricao, status_processamento)
VALUES
    ('deg-monitoria-01-2026', 'Edital Monitoria DEG 01/2026', 'Processo seletivo para monitores bolsistas e voluntários nos departamentos da UnB.', 'https://deg.unb.br/editais/edital-monitoria-deg-01-2026.pdf', '2026-09-01', '2026-09-05', '2026-12-01', 'processado'),
    ('deg-premio-inovacao-58-2026', 'Edital DEG N° 58/2026 – Prêmio Anual de Inovação no Ensino de Graduação da Universidade de Brasília', 'Incentivo a projetos inovadores no ensino de graduação da UnB.', 'https://deg.unb.br/edital-deg-n-58-2026-premio-anual-de-inovacao/', '2026-09-23', '2026-09-23', '2026-11-15', 'processado'),
    ('pibic-2026-2027', 'Edital PIBIC/PIBITI 2026/2027', 'Programa Institucional de Bolsas de Iniciação Científica e Tecnológica da UnB.', 'https://deg.unb.br/editais/edital-pibic-2026-2027.pdf', '2026-08-15', '2026-08-20', '2026-10-30', 'processado')
ON CONFLICT (url_pdf) DO NOTHING;

-- Relacionamentos edital_campi
INSERT INTO edital_campi (edital_id, campus_id)
SELECT e.id, c.id FROM editais e, campi c
WHERE e.identificador_origem = 'deg-monitoria-01-2026' AND c.nome = 'Darcy Ribeiro'
ON CONFLICT DO NOTHING;

INSERT INTO edital_campi (edital_id, campus_id)
SELECT e.id, c.id FROM editais e, campi c
WHERE e.identificador_origem = 'deg-premio-inovacao-58-2026' AND c.nome = 'Darcy Ribeiro'
ON CONFLICT DO NOTHING;

INSERT INTO edital_campi (edital_id, campus_id)
SELECT e.id, c.id FROM editais e, campi c
WHERE e.identificador_origem = 'pibic-2026-2027' AND c.nome = 'Geral'
ON CONFLICT DO NOTHING;

-- Relacionamentos edital_tipos
INSERT INTO edital_tipos (edital_id, tipo_edital_id)
SELECT e.id, t.id FROM editais e, tipos_editais t
WHERE e.identificador_origem = 'deg-monitoria-01-2026' AND t.nome = 'Monitoria'
ON CONFLICT DO NOTHING;

INSERT INTO edital_tipos (edital_id, tipo_edital_id)
SELECT e.id, t.id FROM editais e, tipos_editais t
WHERE e.identificador_origem = 'deg-premio-inovacao-58-2026' AND t.nome = 'Extensões'
ON CONFLICT DO NOTHING;

INSERT INTO edital_tipos (edital_id, tipo_edital_id)
SELECT e.id, t.id FROM editais e, tipos_editais t
WHERE e.identificador_origem = 'pibic-2026-2027' AND t.nome = 'PIBIC'
ON CONFLICT DO NOTHING;
