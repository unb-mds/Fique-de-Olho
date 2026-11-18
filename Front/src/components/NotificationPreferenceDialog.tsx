interface NotificationPreferenceDialogProps {
  open: boolean;
  saving: boolean;
  error?: string;
  onChoose: (receberEmails: boolean) => void;
}

export default function NotificationPreferenceDialog({
  open,
  saving,
  error,
  onChoose,
}: NotificationPreferenceDialogProps) {
  if (!open) return null;

  return (
    <div className="preference-dialog-backdrop">
      <section
        className="preference-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preference-dialog-title"
        aria-describedby="preference-dialog-description"
      >
        <span className="preference-dialog-tag">Edital salvo</span>
        <h2 id="preference-dialog-title">Quer receber avisos sobre seus editais?</h2>
        <p id="preference-dialog-description">
          Enviaremos mensagens por e-mail quando o prazo estiver perto ou
          quando houver atualizações nas oportunidades que você acompanha.
        </p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="preference-dialog-actions">
          <button
            className="button button-accent"
            type="button"
            disabled={saving}
            onClick={() => onChoose(true)}
            autoFocus
          >
            {saving ? 'Salvando...' : 'Sim, quero receber'}
          </button>
          <button
            className="button preference-decline"
            type="button"
            disabled={saving}
            onClick={() => onChoose(false)}
          >
            Agora não
          </button>
        </div>
      </section>
    </div>
  );
}
