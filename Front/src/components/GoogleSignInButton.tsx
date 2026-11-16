import React, { useEffect, useRef } from "react";
import { loginWithGoogle } from "@/services/authService";

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
              theme?: "outline" | "filled_blue" | "filled_black";
              size?: "large" | "medium" | "small";
              text?: "signin_with" | "signup_with" | "continue_with" | "signin";
              shape?: "rectangular" | "pill" | "circle" | "square";
              width?: string | number;
              locale?: string;
            }
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
  text?: "signin_with" | "signup_with" | "continue_with" | "signin";
}

export const GoogleSignInButton: React.FC<GoogleSignInButtonProps> = ({
  onSuccess,
  onError,
  text = "signin_with",
}) => {
  const buttonRef = useRef<HTMLDivElement>(null);
  const clientId =
    import.meta.env.VITE_GOOGLE_CLIENT_ID ||
    ""; // Carrega da variável de ambiente

  useEffect(() => {
    if (!clientId) {
      return;
    }

    function initGoogle() {
      if (!window.google?.accounts?.id || !buttonRef.current) {
        return;
      }

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (response) => {
          try {
            const data = await loginWithGoogle(response.credential);
            localStorage.setItem("token", data.access_token);
            localStorage.setItem("usuario", JSON.stringify(data.usuario));

            if (onSuccess) {
              onSuccess();
            } else {
              window.location.href = "/";
            }
          } catch (err: unknown) {
            const msg =
              err instanceof Error
                ? err.message
                : "Erro ao autenticar com o Google.";
            if (onError) {
              onError(msg);
            }
          }
        },
      });

      // Limpa renderização anterior caso haja re-render
      buttonRef.current.innerHTML = "";

      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
        text,
        shape: "rectangular",
        width: "100%",
        locale: "pt-BR",
      });
    }

    // Se o script do Google já estiver no DOM
    if (window.google?.accounts?.id) {
      initGoogle();
      return;
    }

    // Carrega o script do Google Identity Services dinamicamente
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = initGoogle;
    document.body.appendChild(script);

    return () => {
      // Cleanup se necessário
    };
  }, [clientId, onSuccess, onError, text]);

  if (!clientId) {
    return (
      <div
        style={{
          padding: "8px 12px",
          background: "#fef3c7",
          color: "#92400e",
          borderRadius: "6px",
          fontSize: "13px",
          margin: "12px 0",
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
        display: "flex",
        justifyContent: "center",
        width: "100%",
        margin: "12px 0",
      }}
    />
  );
};
