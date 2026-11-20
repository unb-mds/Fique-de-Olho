import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AlertButton from "../AlertButton";

const navigateMock = vi.fn();

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigateMock,
}));

const useAuthMock = vi.fn();

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => useAuthMock(),
}));

const listarAlertasEditaisMock = vi.fn();
const ativarAlertaEditalMock = vi.fn();
const desativarAlertaEditalMock = vi.fn();

vi.mock("../../services/notificacoesService", () => ({
  listarAlertasEditais: () => listarAlertasEditaisMock(),
  ativarAlertaEdital: (id: string | number) => ativarAlertaEditalMock(id),
  desativarAlertaEdital: (id: string | number) => desativarAlertaEditalMock(id),
}));

describe("AlertButton Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    useAuthMock.mockReturnValue({
      autenticado: false,
    });

    listarAlertasEditaisMock.mockResolvedValue([]);
    ativarAlertaEditalMock.mockResolvedValue({ notificar_email: true });
    desativarAlertaEditalMock.mockResolvedValue({ notificar_email: false });
  });

  it("deve renderizar o botão de sino desativado inicialmente", () => {
    render(<AlertButton editalId={1} />);

    const button = screen.getByRole("button", {
      name: /ativar notificações por e-mail deste edital/i,
    });

    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-pressed", "false");
  });

  it("deve redirecionar para login quando usuário não autenticado clica no sino", () => {
    render(<AlertButton editalId={42} />);

    const button = screen.getByRole("button", {
      name: /ativar notificações por e-mail deste edital/i,
    });

    fireEvent.click(button);

    expect(navigateMock).toHaveBeenCalledWith("/login", {
      state: {
        fromAlert: true,
        returnTo: "/",
        pendingAlertEditalId: "42",
      },
    });
    expect(ativarAlertaEditalMock).not.toHaveBeenCalled();
  });

  it("deve ativar e desativar alertas por e-mail quando autenticado", async () => {
    useAuthMock.mockReturnValue({ autenticado: true });

    render(<AlertButton editalId={7} />);

    const button = await screen.findByRole("button", {
      name: /ativar notificações por e-mail deste edital/i,
    });

    fireEvent.click(button);

    await waitFor(() => {
      expect(ativarAlertaEditalMock).toHaveBeenCalledWith(7);
      expect(button).toHaveAttribute("aria-pressed", "true");
    });

    fireEvent.click(button);

    await waitFor(() => {
      expect(desativarAlertaEditalMock).toHaveBeenCalledWith(7);
      expect(button).toHaveAttribute("aria-pressed", "false");
    });
  });
});
