from types import SimpleNamespace

from app.modules.notificacoes.email_service import enviar_email


def test_envia_email_pelo_sendgrid(monkeypatch):
    chamadas = []

    class ClienteSendGrid:
        def __init__(self, api_key):
            chamadas.append(("api_key", api_key))

        def send(self, mensagem):
            chamadas.append(("mensagem", mensagem))
            return SimpleNamespace(status_code=202)

    monkeypatch.setattr(
        "app.modules.notificacoes.email_service.SendGridAPIClient",
        ClienteSendGrid,
    )

    resultado = enviar_email(
        destinatario="arthuramaral2606@gmail.com",
        assunto="Edital atualizado",
        html="<p>O edital foi atualizado.</p>",
        api_key="SG.test-key",
        remetente="fiquedeolho1011@gmail.com",
    )

    assert resultado is True
    assert chamadas[0] == ("api_key", "SG.test-key")
    mensagem = chamadas[1][1]
    assert mensagem.from_email.email == "fiquedeolho1011@gmail.com"
    assert mensagem.personalizations[0].tos[0]["email"] == "arthuramaral2606@gmail.com"
