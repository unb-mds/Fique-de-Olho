import { useEffect, useState } from "react";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import {
  listarNotificacoes,
  type Notificacao,
} from "@/services/notificacoesService";

function descricaoTipo(notificacao: Notificacao) {
  return notificacao.tipo === "prazo_encerrando"
    ? "Prazo de inscrição se aproximando"
    : "Edital atualizado";
}

export default function NotificationsPage() {
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    listarNotificacoes()
      .then(setNotificacoes)
      .catch((error: Error) => setErro(error.message));
  }, []);

  return (
    <div>
      <Header />
      <main className="notification-history">
        <h1>Histórico de notificações</h1>
        {erro && <p className="status-message">{erro}</p>}
        {!erro && notificacoes.length === 0 && (
          <p className="empty-state">Nenhuma notificação registrada.</p>
        )}
        <ul>
          {notificacoes.map((notificacao) => (
            <li key={notificacao.id}>
              <strong>{descricaoTipo(notificacao)}</strong>
              <span>{notificacao.edital_titulo}</span>
              <small>Status: {notificacao.status}</small>
            </li>
          ))}
        </ul>
      </main>
      <Footer />
    </div>
  );
}
