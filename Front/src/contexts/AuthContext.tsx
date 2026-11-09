import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  getCurrentUser,
  type Usuario,
} from "@/services/authService";

type AuthContextType = {
  usuario: Usuario | null;
  autenticado: boolean;
  carregando: boolean;
  atualizarUsuario: () => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

type AuthProviderProps = {
  children: ReactNode;
};

export function AuthProvider({ children }: AuthProviderProps) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [carregando, setCarregando] = useState(true);

  async function atualizarUsuario() {
    const token = localStorage.getItem("token");

    if (!token) {
      setUsuario(null);
      setCarregando(false);
      return;
    }

    try {
      const usuarioAtual = await getCurrentUser();

      setUsuario(usuarioAtual);
      localStorage.setItem("usuario", JSON.stringify(usuarioAtual));
    } catch {
      localStorage.removeItem("token");
      localStorage.removeItem("usuario");
      setUsuario(null);
    } finally {
      setCarregando(false);
    }
  }

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("usuario");
    setUsuario(null);
  }

  useEffect(() => {
    atualizarUsuario();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        usuario,
        autenticado: !!usuario,
        carregando,
        atualizarUsuario,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth deve ser usado dentro de AuthProvider.");
  }

  return context;
}