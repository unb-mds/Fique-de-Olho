from datetime import date

from app.modules.notificacoes import scheduler


def test_ciclo_de_notificacoes_gera_e_processa_pendentes(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        scheduler,
        "gerar_notificacoes_prazo",
        lambda db: chamadas.append("gerar") or 2,
    )
    monkeypatch.setattr(
        scheduler,
        "processar_notificacoes_se_configuradas",
        lambda db: chamadas.append("processar") or {"enviadas": 1, "falhas": 0},
    )

    class FakeSession:
        def close(self):
            chamadas.append("fechar")

    resultado = scheduler.executar_ciclo_notificacoes(lambda: FakeSession())

    assert resultado == {"geradas": 2, "enviadas": 1, "falhas": 0}
    assert chamadas == ["gerar", "processar", "fechar"]
