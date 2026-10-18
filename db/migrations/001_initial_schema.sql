CREATE TABLE tipos_editais (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE campi (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cursos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome VARCHAR(200) NOT NULL UNIQUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE editais (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identificador_origem VARCHAR(200),
    titulo VARCHAR(500) NOT NULL,
    resumo TEXT,
    url_pdf TEXT NOT NULL UNIQUE,
    texto_extraido TEXT,
    data_publicacao DATE,
    inicio_inscricao DATE,
    fim_inscricao DATE,
    status_processamento VARCHAR(30) NOT NULL DEFAULT 'pendente',
    hash_conteudo CHAR(64),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT editais_status_processamento_ck
        CHECK (status_processamento IN ('pendente', 'processado', 'parcialmente_processado', 'erro')),
    CONSTRAINT editais_periodo_inscricao_ck
        CHECK (inicio_inscricao IS NULL OR fim_inscricao IS NULL OR inicio_inscricao <= fim_inscricao)
);

CREATE UNIQUE INDEX editais_identificador_origem_uidx
    ON editais (identificador_origem)
    WHERE identificador_origem IS NOT NULL;

CREATE TABLE edital_tipos (
    edital_id BIGINT NOT NULL REFERENCES editais (id) ON DELETE CASCADE,
    tipo_edital_id BIGINT NOT NULL REFERENCES tipos_editais (id) ON DELETE RESTRICT,
    PRIMARY KEY (edital_id, tipo_edital_id)
);

CREATE TABLE edital_campi (
    edital_id BIGINT NOT NULL REFERENCES editais (id) ON DELETE CASCADE,
    campus_id BIGINT NOT NULL REFERENCES campi (id) ON DELETE RESTRICT,
    PRIMARY KEY (edital_id, campus_id)
);

CREATE TABLE edital_cursos (
    edital_id BIGINT NOT NULL REFERENCES editais (id) ON DELETE CASCADE,
    curso_id BIGINT NOT NULL REFERENCES cursos (id) ON DELETE RESTRICT,
    PRIMARY KEY (edital_id, curso_id)
);

CREATE TABLE usuarios (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    senha_hash TEXT NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX usuarios_email_uidx ON usuarios (LOWER(email));

CREATE TABLE favoritos (
    usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    edital_id BIGINT NOT NULL REFERENCES editais (id) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (usuario_id, edital_id)
);

CREATE TABLE notificacoes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    edital_id BIGINT NOT NULL REFERENCES editais (id) ON DELETE CASCADE,
    tipo VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pendente',
    enviada_em TIMESTAMPTZ,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT notificacoes_tipo_ck
        CHECK (tipo IN ('novo_edital', 'prazo_encerrando', 'edital_atualizado')),
    CONSTRAINT notificacoes_status_ck
        CHECK (status IN ('pendente', 'enviada', 'falhou'))
);

CREATE TABLE coletas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fonte VARCHAR(100) NOT NULL DEFAULT 'DEG',
    iniciada_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalizada_em TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'executando',
    editais_encontrados INTEGER NOT NULL DEFAULT 0,
    mensagem_erro TEXT,
    CONSTRAINT coletas_status_ck
        CHECK (status IN ('executando', 'concluida', 'falhou'))
);

ALTER TABLE editais
    ADD COLUMN busca_documento TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('portuguese', COALESCE(titulo, '') || ' ' || COALESCE(resumo, '') || ' ' || COALESCE(texto_extraido, ''))
    ) STORED;

CREATE INDEX editais_busca_documento_gin_idx ON editais USING GIN (busca_documento);
CREATE INDEX editais_fim_inscricao_idx ON editais (fim_inscricao);
CREATE INDEX notificacoes_status_idx ON notificacoes (status);