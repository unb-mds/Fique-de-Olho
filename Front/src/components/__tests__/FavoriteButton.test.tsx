import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import FavoriteButton from "../FavoriteButton";

const navigateMock = vi.fn();

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigateMock,
}));

const useAuthMock = vi.fn();

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => useAuthMock(),
}));

const listarFavoritosMock = vi.fn();
const favoritarEditalMock = vi.fn();
const desfavoritarEditalMock = vi.fn();

vi.mock("../../services/favoritosService", () => ({
  listarFavoritos: () => listarFavoritosMock(),
  favoritarEdital: (id: string | number) => favoritarEditalMock(id),
  desfavoritarEdital: (id: string | number) => desfavoritarEditalMock(id),
}));

describe("FavoriteButton Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    useAuthMock.mockReturnValue({
      autenticado: false,
    });

    listarFavoritosMock.mockResolvedValue([]);
    favoritarEditalMock.mockResolvedValue(undefined);
    desfavoritarEditalMock.mockResolvedValue(undefined);
  });

  it("deve renderizar o botão com estado inicial não favoritado", () => {
    render(<FavoriteButton editalId={1} />);

    const button = screen.getByRole("button", {
      name: /favoritar edital/i,
    });

    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent("☆");
  });

  it("deve redirecionar para login quando usuário não autenticado tenta favoritar", () => {
    render(<FavoriteButton editalId={1} />);

    const button = screen.getByRole("button", {
      name: /favoritar edital/i,
    });

    fireEvent.click(button);

    expect(navigateMock).toHaveBeenCalledWith("/login");
  });

  it("não deve chamar a API de favoritos quando usuário não está autenticado", () => {
    render(<FavoriteButton editalId={1} />);

    const button = screen.getByRole("button", {
      name: /favoritar edital/i,
    });

    fireEvent.click(button);

    expect(favoritarEditalMock).not.toHaveBeenCalled();
    expect(desfavoritarEditalMock).not.toHaveBeenCalled();
  });
});

