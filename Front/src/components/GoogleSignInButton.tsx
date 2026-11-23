import React, { useEffect, useRef } from 'react';
import { loginWithGoogle } from '@/services/authService';
import { salvarSessaoStorage } from '@/utils/authStorage';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
            auto_select?: boolean;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              theme?: 'outline' | 'filled_blue' | 'filled_black';
              size?: 'large' | 'medium' | 'small';
              text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin';
              shape?: 'rectangular' | 'pill' | 'circle' | 'square';
              width?: string | number;
              locale?: string;
            },
          ) => void;
          prompt?: () => void;
        };
      };
    };
  }
}

interface GoogleSignInButtonProps {
  onSuccess?: () => void;
  onError?: (mensagem: string) => void;
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin';
}

const GSI_SCRIPT_SRC = 'https://accounts.google.com/gsi/client';

export const GoogleSignInButton: React.FC<GoogleSignInButtonProps> = ({
  onSuccess,
  onError,
  text = 'signin_with',
}) => {
  const buttonRef = useRef<HTMLDivElement>(null);
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onErrorRef.current = onError;
  });

  useEffect(() => {
    if (!clientId) {
      return;
    }

    let ativo = true;

    function initGoogle() {
      if (!ativo || !window.google?.accounts?.id || !buttonRef.current) {
        return;
      }

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (response) => {
          try {
            const data = await loginWithGoogle(response.credential);
            salvarSessaoStorage(data.access_token, data.usuario);

            if (!ativo) return;

            if (onSuccessRef.current) {
              onSuccessRef.current();
            } else {
              window.location.href = '/';
            }
          } catch (err: unknown) {
            if (!ativo) return;
            const msg =
              err instanceof Error
                ? err.message
                : 'Erro ao autenticar com o Google.';
            onErrorRef.current?.(msg);
          }
        },
      });

      const containerWidth = buttonRef.current.clientWidth;
      const buttonWidth =
        containerWidth > 0
          ? Math.min(400, Math.max(200, Math.floor(containerWidth)))
          : 400;

      buttonRef.current.innerHTML = '';

      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
        text,
        shape: 'rectangular',
        width: buttonWidth,
        locale: 'pt-BR',
      });
    }

    if (window.google?.accounts?.id) {
      initGoogle();
      return () => {
        ativo = false;
      };
    }

    const existingScript = document.querySelector<HTMLScriptElement>(
      `script[src="${GSI_SCRIPT_SRC}"]`,
    );
    const script = existingScript ?? document.createElement('script');

    const handleScriptError = () => {
      if (ativo) {
        onErrorRef.current?.('Não foi possível carregar o login com o Google.');
      }
    };

    script.addEventListener('load', initGoogle);
    script.addEventListener('error', handleScriptError);

    if (!existingScript) {
      script.src = GSI_SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }

    return () => {
      ativo = false;
      script.removeEventListener('load', initGoogle);
      script.removeEventListener('error', handleScriptError);
    };
  }, [clientId, text]);

  if (!clientId) {
    return (
      <div
        style={{
          padding: '8px 12px',
          background: '#fef3c7',
          color: '#92400e',
          borderRadius: '6px',
          fontSize: '13px',
          margin: '12px 0',
        }}
      >
        ⚠️ Configure <code>VITE_GOOGLE_CLIENT_ID</code> no <code>.env</code> do
        frontend para habilitar o login com o Google.
      </div>
    );
  }

  return (
    <div
      ref={buttonRef}
      style={{
        display: 'flex',
        justifyContent: 'center',
        width: '100%',
        margin: '12px 0',
      }}
    />
  );
};
