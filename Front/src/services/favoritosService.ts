import type { Edital } from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function getToken() {
  return localStorage.getItem("token");
}

export async function listarFavoritos(): Promise<Edital[]> {
  const token = getToken();

  const response = await fetch(
    `${API_BASE_URL}/api/v1/editais/favoritos`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error("Erro ao listar favoritos.");
  }

  return response.json();
}

export async function favoritarEdital(
  editalId: string | number
): Promise<void> {
  const token = getToken();

  const response = await fetch(
    `${API_BASE_URL}/api/v1/editais/${editalId}/favoritar`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error("Erro ao favoritar edital.");
  }
}

export async function desfavoritarEdital(
  editalId: string | number
): Promise<void> {
  const token = getToken();

  const response = await fetch(
    `${API_BASE_URL}/api/v1/editais/${editalId}/favoritar`,
    {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error("Erro ao desfavoritar edital.");
  }
}