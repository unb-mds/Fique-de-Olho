import { useEffect, useId, useRef, useState } from 'react';
import { enviarFeedback, type TipoFeedback } from '@/services/feedbackService';

type ModalTab = 'ajuda' | 'feedback';

const FAQ_ITEMS = [
  {
    pergunta: 'Como buscar e filtrar editais?',
    resposta:
      'Use a barra de busca para procurar por palavras-chave, órgão ou tema, e combine os filtros de Situação (Abertos/Encerrados), Campus, Ano e Categoria. Clique em "Limpar filtros" para voltar à listagem completa.',
  },
  {
    pergunta: 'Qual é a diferença entre Favoritar (★) e Ativar Alerta (🔔)?',
    resposta:
      'Favoritar salva o edital na sua lista pessoal ("Meus editais") para consulta rápida. Ativar o alerta envia e-mails automáticos sempre que houver atualização no edital e lembretes 3 dias, 1 dia e no dia do encerramento das inscrições.',
  },
  {
    pergunta: 'Como o sistema define se um edital está Aberto ou Encerrado?',
    resposta:
      'Editais com prazo final futuro aparecem como Abertos. Quando o prazo vence, sai um Resultado Final/Definitivo ou um edital sem prazo foi publicado há mais de 90 dias, ele passa automaticamente para Encerrados.',
  },
  {
    pergunta: 'Onde abro o documento oficial da UnB?',
    resposta:
      'Clique em "Ver edital" em qualquer card para abrir a página de detalhes com o resumo, cronograma e os links diretos para o PDF oficial, anexos e retificações publicados pela UnB.',
  },
];

export default function HelpAndFeedbackButton() {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const titleId = useId();
  const tipoId = useId();
  const emailId = useId();
  const mensagemId = useId();

  const [activeTab, setActiveTab] = useState<ModalTab>('ajuda');
  const [tipo, setTipo] = useState<TipoFeedback>('sugestao');
  const [email, setEmail] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [sending, setSending] = useState(false);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleClose = () => {
      dialog.returnValue = '';
    };
    dialog.addEventListener('close', handleClose);

    // Fallback para navegadores sem suporte nativo a <dialog closedby="any"> (ex.: Safari)
    const supportsClosedBy =
      typeof HTMLDialogElement !== 'undefined' && 'closedBy' in HTMLDialogElement.prototype;
    if (supportsClosedBy) {
      return () => {
        dialog.removeEventListener('close', handleClose);
      };
    }

    const isOutside = (event: PointerEvent) => {
      const rect = dialog.getBoundingClientRect();
      return (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
      );
    };

    let pressedOutside = false;
    const onPointerDown = (event: PointerEvent) => {
      pressedOutside = isOutside(event);
    };
    const onPointerUp = (event: PointerEvent) => {
      if (pressedOutside && isOutside(event)) {
        dialog.close();
      }
      pressedOutside = false;
    };

    dialog.addEventListener('pointerdown', onPointerDown);
    dialog.addEventListener('pointerup', onPointerUp);
    return () => {
      dialog.removeEventListener('close', handleClose);
      dialog.removeEventListener('pointerdown', onPointerDown);
      dialog.removeEventListener('pointerup', onPointerUp);
    };
  }, []);

  function openDialog(tab: ModalTab = 'ajuda') {
    setActiveTab(tab);
    setFeedbackError(null);
    setFeedbackSuccess(null);
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function closeDialog() {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (typeof dialog.close === 'function') {
      dialog.close();
    } else {
      dialog.removeAttribute('open');
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedbackError(null);
    setFeedbackSuccess(null);

    if (mensagem.trim().length < 5) {
      setFeedbackError('Escreva pelo menos 5 caracteres para enviar seu feedback.');
      return;
    }

    setSending(true);
    try {
      const resp = await enviarFeedback({
        tipo,
        mensagem,
        email: email.trim() || undefined,
      });
      setFeedbackSuccess(resp.message);
      setMensagem('');
      setEmail('');
    } catch (err) {
      setFeedbackError(
        err instanceof Error
          ? err.message
          : 'Não foi possível enviar seu feedback. Tente novamente.',
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="help-fab"
        onClick={() => openDialog('ajuda')}
        aria-label="Abrir central de ajuda e feedback"
        title="Central de Ajuda e Feedback"
      >
        ?
      </button>

      <dialog
        ref={dialogRef}
        className="help-dialog"
        aria-labelledby={titleId}
        {...({ closedby: 'any' } as Record<string, string>)}
      >
        <div className="help-dialog-header">
          <h2 id={titleId}>Central de Ajuda e Feedback</h2>
          <button
            type="button"
            className="help-dialog-close"
            onClick={closeDialog}
            aria-label="Fechar central de ajuda"
          >
            ×
          </button>
        </div>

        <div className="help-dialog-tabs" role="tablist" aria-label="Seções de ajuda">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'ajuda'}
            className={`help-dialog-tab ${activeTab === 'ajuda' ? 'active' : ''}`}
            onClick={() => setActiveTab('ajuda')}
          >
            Ajuda (FAQ)
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'feedback'}
            className={`help-dialog-tab ${activeTab === 'feedback' ? 'active' : ''}`}
            onClick={() => setActiveTab('feedback')}
          >
            Enviar feedback
          </button>
        </div>

        <div className="help-dialog-body">
          {activeTab === 'ajuda' ? (
            <div className="help-faq-list">
              {FAQ_ITEMS.map((item) => (
                <details className="help-faq-item" key={item.pergunta}>
                  <summary>{item.pergunta}</summary>
                  <p>{item.resposta}</p>
                </details>
              ))}
              <div className="help-faq-cta">
                <span>Encontrou algum problema ou tem uma sugestão?</span>
                <button
                  type="button"
                  className="help-dialog-link-btn"
                  onClick={() => setActiveTab('feedback')}
                >
                  Enviar feedback →
                </button>
              </div>
            </div>
          ) : (
            <form className="feedback-form" onSubmit={handleSubmit} noValidate>
              <p className="feedback-intro">
                Envie sugestões, críticas ou relate problemas encontrados nos editais. Sua mensagem é
                encaminhada diretamente para a equipe do Fique de Olho.
              </p>

              <div className="feedback-field">
                <label htmlFor={tipoId}>Tipo de mensagem</label>
                <select
                  id={tipoId}
                  value={tipo}
                  onChange={(event) => setTipo(event.target.value as TipoFeedback)}
                >
                  <option value="sugestao">Sugestão de melhoria</option>
                  <option value="problema">Relatar problema / dado incorreto</option>
                  <option value="elogio">Elogio</option>
                </select>
              </div>

              <div className="feedback-field">
                <label htmlFor={emailId}>Seu e-mail (opcional)</label>
                <input
                  id={emailId}
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="voce@aluno.unb.br"
                  autoComplete="email"
                />
              </div>

              <div className="feedback-field">
                <label htmlFor={mensagemId}>Mensagem</label>
                <textarea
                  id={mensagemId}
                  rows={4}
                  required
                  minLength={5}
                  maxLength={2000}
                  value={mensagem}
                  onChange={(event) => setMensagem(event.target.value)}
                  placeholder="Conte o que podemos melhorar ou descreva o problema encontrado..."
                />
              </div>

              {feedbackError && (
                <p className="feedback-alert feedback-alert-error" role="alert">
                  {feedbackError}
                </p>
              )}

              {feedbackSuccess && (
                <p className="feedback-alert feedback-alert-success" role="status">
                  {feedbackSuccess}
                </p>
              )}

              <div className="feedback-actions">
                <button
                  type="button"
                  className="clear-filters-button"
                  onClick={closeDialog}
                >
                  Fechar
                </button>
                <button
                  type="submit"
                  className="feedback-submit-btn"
                  disabled={sending}
                >
                  {sending ? 'Enviando...' : 'Enviar feedback'}
                </button>
              </div>
            </form>
          )}
        </div>
      </dialog>
    </>
  );
}
