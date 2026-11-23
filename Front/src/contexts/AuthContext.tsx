import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';

import {
  getCurrentUser,
  updateEmailPreference,
  type Usuario,
} from '@/services/authService';
import { isAuthError, isTransientError } from '@/services/apiClient';
import { limparCacheFavoritos } from '@/services/favoritosService';
import { limparCacheAlertas } from '@/services/notificacoesService';
import {
  lerUsuarioCacheado,
  limparSessaoStorage,
  obterTokenStorage,
  salvarSessaoStorage,
  tokenLocalExpirado,
} from '@/utils/authStorage';
import { safeStorageSet } from '@/utils/storage';

type AuthContextType = {
  usuario: Usuario | null;
  autenticado: boolean;
  carregando: boolean;
  atualizarUsuario: () => Promise<void>;
  atualizarPreferenciaEmail: (receberEmails: boolean) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

type AuthProviderProps = {
  children: ReactNode;
};

export function AuthProvider({ children }: AuthProviderProps) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [carregando, setCarregando] = useState(true);

  const limparSessaoLocal = useCallback(() => {
    limparSessaoStorage();
    limparCacheFavoritos();
    limparCacheAlertas();
    setUsuario(null);
  }, []);

  const atualizarUsuario = useCallback(async () => {
    try {
      const token = obterTokenStorage();

      if (!token) {
        setUsuario(null);
        return;
      }

      if (tokenLocalExpirado(token)) {
        limparSessaoLocal();
        return;
      }

      try {
        const usuarioAtual = await getCurrentUser();
        setUsuario(usuarioAtual);
        salvarSessaoStorage(token, usuarioAtual);
      } catch (err: unknown) {
        if (isAuthError(err)) {
          limparSessaoLocal();
          return;
        }

        if (isTransientError(err)) {
          if (tokenLocalExpirado(token)) {
            limparSessaoLocal();
            return;
          }
          const usuarioCacheado = lerUsuarioCacheado();
          if (usuarioCacheado) {
            setUsuario(usuarioCacheado);
          }
          return;
        }

        limparSessaoLocal();
      }
    } finally {
      setCarregando(false);
    }
  }, [limparSessaoLocal]);

  async function atualizarPreferenciaEmail(receberEmails: boolean) {
    const usuarioAtual = await updateEmailPreference(receberEmails);
    setUsuario(usuarioAtual);
    safeStorageSet('usuario', JSON.stringify(usuarioAtual));
  }

  function logout() {
    limparSessaoLocal();
  }

  useEffect(() => {
    void atualizarUsuario();
  }, [atualizarUsuario]);

  return (
    <AuthContext.Provider
      value={{
        usuario,
        autenticado: !!usuario,
        carregando,
        atualizarUsuario,
        atualizarPreferenciaEmail,
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
    throw new Error('useAuth deve ser usado dentro de AuthProvider.');
  }

  return context;
}
