INSERT INTO tipos_editais (nome)
VALUES
    ('Extensões'),
    ('Bolsas / Auxílios')
ON CONFLICT (nome) DO NOTHING;

INSERT INTO campi (nome)
VALUES
    ('Darcy Ribeiro'),
    ('FGA'),
    ('FCE'),
    ('FUP'),
    ('Geral')
ON CONFLICT (nome) DO NOTHING;