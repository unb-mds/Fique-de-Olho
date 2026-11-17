import type { Edital } from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let favoritosCache: Edital[] | null = null;
let cachedToken: string | null = null;
let inFlightPromise: Promise<Edital[]> | null = null;
let cacheVersion = 0;

function getToken() {
  return localStorage.getItem("token");
}

function invalidarCacheFavoritos(): void {
  cacheVersion += 1;
  favoritosCache = null;
  inFlightPromise = null;
}

export async function listarFavoritos(): Promise<Edital[]> {
  const token = getToken();

  if (token !== cachedToken) {
    invalidarCacheFavoritos();
    cachedToken = token;
  }

  if (favoritosCache !== null) {
    return favoritosCache;
  }

  if (inFlightPromise !== null) {
    return inFlightPromise;
  }

  const requestVersion = cacheVersion;
  const currentPromise = (async () => {
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

    const data: Edital[] = await response.json();
    if (cacheVersion === requestVersion) {
      favoritosCache = data;
    }
    return data;
  })().finally(() => {
    if (inFlightPromise === currentPromise) {
      inFlightPromise = null;
    }
  });

  inFlightPromise = currentPromise;
  return currentPromise;
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

  invalidarCacheFavoritos();
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

  invalidarCacheFavoritos();
}