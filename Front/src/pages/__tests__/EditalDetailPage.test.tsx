
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import EditalDetailPage from "../EditalDetailPage";
import { getEditalById } from "@/services/editaisService";
import type { Edital } from "@/services/types";

vi.mock("@/services/editaisService", () => ({
  getEditalById: vi.fn(),
}));

const mockEdital: Edital = {
  id: "edital-123",
  titulo: "Edital de Monitoria",
  unidade: "Campus Darcy Ribeiro",
  categoria: "Monitoria",
  dataPublicacao: "2026-10-01",
  prazoFinal: "2026-12-31",
  status: "aberto",
  descricao: "Seleção de monitores para a UnB.",
  urlDocumento: "https://unb.br/edital.pdf",
  orgaoEmissor: "DEG",
  assunto: "Seleção de monitores",
  inicioInscricao: "2026-11-01",
  vagas: 5,
  valor: "R$ 700,00",
  documentos: [
    {
      id: 1,
      url_pdf: "https://unb.br/retificacao.pdf",
      tipo_documento: "Retificação",
      titulo: "Retificação 01",
    },
    {
      id: 2,
      url_pdf: "https://unb.br/resultado.pdf",
      tipo_documento: "Resultado",
      titulo: "Resultado preliminar",
    },
  ],
};

function renderizarPagina() {
  return render(
    <MemoryRouter initialEntries={["/editais/edital-123"]}>
      <Routes>
        <Route
          path="/editais/:id"
          element={<EditalDetailPage />}
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("EditalDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getEditalById).mockResolvedValue(mockEdital);
  });

  it("exibe as informações principais do edital", async () => {
    renderizarPagina();

    expect(
      await screen.findByRole("heading", {
        name: "Edital de Monitoria",
      })
    ).toBeInTheDocument();

    expect(
      screen.getByText("Início das inscrições")
    ).toBeInTheDocument();

    expect(
      screen.getByText("Número de vagas")
    ).toBeInTheDocument();

    expect(
      screen.getByText("R$ 700,00")
    ).toBeInTheDocument();
  });

  it("exibe todos os documentos anexados", async () => {
    renderizarPagina();

    expect(
      await screen.findByText("Retificação 01")
    ).toBeInTheDocument();

    expect(
      screen.getByText("Resultado preliminar")
    ).toBeInTheDocument();

    const links = screen.getAllByRole("link", {
      name: "Abrir / baixar documento",
    });

    expect(links).toHaveLength(2);
  });

  it("abre os anexos com segurança", async () => {
    renderizarPagina();

    await screen.findByText("Retificação 01");

    const links = screen.getAllByRole("link", {
      name: "Abrir / baixar documento",
    });

    links.forEach((link) => {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute(
        "rel",
        "noopener noreferrer"
      );
    });
  });

  it("exibe mensagem quando não há anexos", async () => {
    vi.mocked(getEditalById).mockResolvedValue({
      ...mockEdital,
      documentos: [],
    });

    renderizarPagina();

    expect(
      await screen.findByText(
        "Nenhum documento secundário disponível."
      )
    ).toBeInTheDocument();

    expect(
      screen.getByRole("link", {
        name: "Ver documento oficial",
      })
    ).toBeInTheDocument();
  });
});
