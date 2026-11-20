import type { Edital } from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let cachedToken: string | null = null;
let cachedFavoritos: Edital[] | null = null;
let inflightFavoritosRequest: Promise<Edital[]> | null = null;

function getToken() {
  return localStorage.getItem("token");
}

export function limparCacheFavoritos(): void {
  cachedToken = null;
  cachedFavoritos = null;
  inflightFavoritosRequest = null;
}

export async function listarFavoritos(): Promise<Edital[]> {
  const token = getToken();
  if (!token) {
    limparCacheFavoritos();
    return [];
  }

  if (cachedToken !== token) {
    cachedToken = token;
    cachedFavoritos = null;
    inflightFavoritosRequest = null;
  }

  if (cachedFavoritos !== null) {
    return cachedFavoritos;
  }

  if (inflightFavoritosRequest) {
    return inflightFavoritosRequest;
  }

  inflightFavoritosRequest = (async () => {
    try {
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

      const dados: Edital[] = await response.json();
      if (cachedToken === token) {
        cachedFavoritos = dados;
      }
      return dados;
    } finally {
      inflightFavoritosRequest = null;
    }
  })();

  return inflightFavoritosRequest;
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

  cachedFavoritos = null;
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

  if (cachedFavoritos !== null) {
    cachedFavoritos = cachedFavoritos.filter(
      (edital) => String(edital.id) !== String(editalId)
    );
  }
}
