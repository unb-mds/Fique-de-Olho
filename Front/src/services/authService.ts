const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Usuario = {
  id: number;
  nome: string;
  email: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  usuario: Usuario;
};

export async function login(
  email: string,
  senha: string
): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      senha,
    }),
  });

  if (!response.ok) {
    throw new Error("E-mail ou senha inválidos.");
  }

  return response.json();
}
export type RegisterResponse = {
  id: number;
  nome: string;
  email: string;
};

export async function register(
  nome: string,
  email: string,
  senha: string
): Promise<RegisterResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      nome,
      email,
      senha,
    }),
  });

  if (!response.ok) {
    throw new Error("Não foi possível realizar o cadastro.");
  }

  return response.json();
}
export async function getCurrentUser(): Promise<Usuario> {
  const token = localStorage.getItem("token");

  if (!token) {
    throw new Error("Usuário não autenticado.");
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Sessão inválida ou expirada.");
  }

  return response.json();
}