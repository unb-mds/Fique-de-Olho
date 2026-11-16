
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getEditalById } from "@/services/editaisService";
import type { Edital } from "@/services/types";
import { categoryBadgeStyle, formatDate } from "@/utils/editalDisplay";

function formatarDataSegura(data?: string): string {
  if (!data) return "Não informado";

  const partes = /^(\d{4})-(\d{2})-(\d{2})/.exec(data);

  if (!partes) return "Não informado";

  const ano = Number(partes[1]);
  const mes = Number(partes[2]);
  const dia = Number(partes[3]);
  const dataValida = new Date(Date.UTC(ano, mes - 1, dia));

  if (
    dataValida.getUTCFullYear() !== ano ||
    dataValida.getUTCMonth() !== mes - 1 ||
    dataValida.getUTCDate() !== dia
  ) {
    return "Não informado";
  }

  return formatDate(data);
}

function linkSeguro(url?: string): string | null {
  if (!url) return null;

  const endereco = url.trim();

  if (/^https?:\/\//i.test(endereco)) return endereco;
  if (/^\/(?!\/)/.test(endereco)) return endereco;

  return null;
}

export default function EditalDetailPage() {
  const { id } = useParams<{ id: string }>();

  const [edital, setEdital] = useState<Edital | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setLoading(false);
      setError("Identificador do edital não informado.");
      return;
    }

    let ativo = true;

    setLoading(true);
    setError(null);
    setEdital(null);

    getEditalById(id)
      .then((resultado) => {
        if (ativo) setEdital(resultado);
      })
      .catch((err: Error) => {
        if (ativo) setError(err.message);
      })
      .finally(() => {
        if (ativo) setLoading(false);
      });

    return () => {
      ativo = false;
    };
  }, [id]);

  if (loading) {
    return (
      <p className="status-message">
        Carregando edital...
      </p>
    );
  }

  if (error) {
    return (
      <p className="status-message">
        Erro ao carregar edital: {error}
      </p>
    );
  }

  if (!edital) {
    return (
      <p className="status-message">
        Edital não encontrado.
      </p>
    );
  }

  const documentos = edital.documentos ?? [];

  const documentosValidos = documentos.filter(
    (documento) => linkSeguro(documento.url_pdf) !== null
  );

  const documentoPrincipal = linkSeguro(edital.urlDocumento);

  return (
    <main className="detail-page">
      <a className="detail-back-link" href="/">
        Voltar para editais
      </a>

      <article className="detail-card">

        {/* Identificação do edital */}
        <div className="badge-group">
          {edital.categoria && (
            <span
              className="badge"
              style={categoryBadgeStyle(edital.categoria)}
            >
              {edital.categoria}
            </span>
          )}

          {edital.unidade && (
            <span className="badge badge-campus">
              {edital.unidade}
            </span>
          )}

          {edital.orgaoEmissor && (
            <span className="badge">
              {edital.orgaoEmissor}
            </span>
          )}
        </div>

        <h1>{edital.titulo}</h1>

        <p className="detail-description">
          {edital.descricao}
        </p>

        {/* Metadados e informações do edital */}
        <h2>Informações do edital</h2>

        <dl className="detail-metadata">
          <div>
            <dt>Publicação</dt>
            <dd>
              {formatarDataSegura(edital.dataPublicacao)}
            </dd>
          </div>

          <div>
            <dt>Início das inscrições</dt>
            <dd>
              {formatarDataSegura(edital.inicioInscricao)}
            </dd>
          </div>

          <div>
            <dt>Prazo final</dt>
            <dd>
              {formatarDataSegura(edital.prazoFinal)}
            </dd>
          </div>

          <div>
            <dt>Status</dt>
            <dd>
              {edital.status === "aberto"
                ? "Inscrições abertas"
                : "Encerrado"}
            </dd>
          </div>

          {edital.orgaoEmissor && (
            <div>
              <dt>Órgão emissor</dt>
              <dd>{edital.orgaoEmissor}</dd>
            </div>
          )}

          {edital.assunto && (
            <div>
              <dt>Assunto</dt>
              <dd>{edital.assunto}</dd>
            </div>
          )}

          {edital.vagas !== undefined &&
            edital.vagas !== null && (
              <div>
                <dt>Número de vagas</dt>
                <dd>{edital.vagas}</dd>
              </div>
            )}

          {edital.valor && (
            <div>
              <dt>Valor da bolsa / auxílio</dt>
              <dd>{edital.valor}</dd>
            </div>
          )}
        </dl>

        {/* Documentos, anexos e retificações */}
        <section
          aria-labelledby="titulo-documentos"
          style={{ marginTop: "2rem" }}
        >
          <h2 id="titulo-documentos">
            Documentos e anexos
          </h2>

          {documentosValidos.length > 0 ? (
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                display: "grid",
                gap: "0.75rem",
              }}
            >
              {documentosValidos.map((documento) => (
                <li
                  key={documento.id}
                  style={{
                    border: "1px solid #d1d5db",
                    borderRadius: "8px",
                    padding: "1rem",
                  }}
                >
                  <strong>
                    {documento.titulo ||
                      documento.tipo_documento ||
                      "Documento do edital"}
                  </strong>

                  {documento.titulo &&
                    documento.tipo_documento && (
                      <p>
                        Tipo: {documento.tipo_documento}
                      </p>
                    )}

                  <div style={{ marginTop: "0.75rem" }}>
                    <a
                      className="detail-document-link"
                      href={linkSeguro(documento.url_pdf) ?? "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Abrir / baixar documento
                    </a>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p>
              Nenhum documento secundário disponível.
            </p>
          )}

          {documentoPrincipal && (
            <div style={{ marginTop: "1.5rem" }}>
              <a
                className="detail-document-link"
                href={documentoPrincipal}
                target="_blank"
                rel="noopener noreferrer"
              >
                Ver documento oficial
              </a>
            </div>
          )}
        </section>
      </article>
    </main>
  );
}
