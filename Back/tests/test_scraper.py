import httpx

from app.modules.scraper import deg


HTML_BY_YEAR = {
    "2026": """
        <h6><a href="/edital-atual">Edital Atual DEG 01/2026</a></h6>
        <p>23 de setembro de 2026</p>
    """,
    "2025": """
        <h6><a href="/edital-anterior">Edital Anterior DEG 01/2025</a></h6>
        <p>31 de janeiro de 2025</p>
    """,
}


def test_fetch_editais_supports_current_and_previous_year(monkeypatch):
    requested_urls = []

    def fake_get(url, **kwargs):
        requested_urls.append(url)
        year = "2026" if "editais/" in url else "2025"
        return httpx.Response(
            200,
            text=HTML_BY_YEAR[year],
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(deg.httpx, "get", fake_get)

    current_editais = deg.fetch_editais()
    previous_editais = deg.fetch_editais(2025)

    assert requested_urls == [
        "https://deg.unb.br/editais/",
        "https://deg.unb.br/editais-2025/",
    ]
    assert current_editais[0] == {
        "titulo": "Edital Atual DEG 01/2026",
        "link": "https://deg.unb.br/edital-atual",
        "data_publicacao": "23 de setembro de 2026",
    }
    assert previous_editais[0]["data_publicacao"] == "31 de janeiro de 2025"


def test_fetch_editais_returns_empty_list_on_network_error(monkeypatch):
    def fake_get(url, **kwargs):
        raise httpx.RequestError(
            "falha de conexão",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(deg.httpx, "get", fake_get)

    assert deg.fetch_editais() == []