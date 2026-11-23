import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GoogleSignInButton } from '../GoogleSignInButton';
import { loginWithGoogle } from '@/services/authService';

vi.mock('@/services/authService', () => ({
  loginWithGoogle: vi.fn(),
}));

describe('GoogleSignInButton', () => {
  const initializeMock = vi.fn();
  const renderButtonMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-google-client-id');
    delete window.google;
    document
      .querySelectorAll('script[src="https://accounts.google.com/gsi/client"]')
      .forEach((node) => node.remove());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete window.google;
    document
      .querySelectorAll('script[src="https://accounts.google.com/gsi/client"]')
      .forEach((node) => node.remove());
  });

  it('não reinicializa o botão Google a cada digitação de formulário', () => {
    window.google = {
      accounts: {
        id: {
          initialize: initializeMock,
          renderButton: renderButtonMock,
        },
      },
    };

    function FormWrapper() {
      const [email, setEmail] = useState('');
      return (
        <div>
          <input
            aria-label="E-mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <GoogleSignInButton
            onSuccess={() => {}}
            onError={() => {}}
          />
        </div>
      );
    }

    render(<FormWrapper />);
    expect(initializeMock).toHaveBeenCalledTimes(1);
    expect(renderButtonMock).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'a' } });
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'ab' } });
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'abc@unb.br' } });

    expect(initializeMock).toHaveBeenCalledTimes(1);
    expect(renderButtonMock).toHaveBeenCalledTimes(1);
  });

  it('injeta apenas uma tag script quando re-renderiza antes do script carregar e invoca o callback mais recente', async () => {
    let capturedCallback: ((res: { credential: string }) => Promise<void> | void) | undefined;
    initializeMock.mockImplementation((cfg) => {
      capturedCallback = cfg.callback;
    });

    vi.mocked(loginWithGoogle).mockResolvedValueOnce({
      access_token: 'jwt-google',
      token_type: 'bearer',
      usuario: {
        id: 10,
        nome: 'Ana',
        email: 'ana@unb.br',
        receber_emails: true,
      },
    });

    const firstSuccess = vi.fn();
    const latestSuccess = vi.fn();

    const { rerender } = render(<GoogleSignInButton onSuccess={firstSuccess} />);
    rerender(<GoogleSignInButton onSuccess={latestSuccess} />);

    const scripts = document.querySelectorAll(
      'script[src="https://accounts.google.com/gsi/client"]',
    );
    expect(scripts).toHaveLength(1);

    window.google = {
      accounts: {
        id: {
          initialize: initializeMock,
          renderButton: renderButtonMock,
        },
      },
    };

    await act(async () => {
      scripts[0].dispatchEvent(new Event('load'));
    });

    expect(initializeMock).toHaveBeenCalledTimes(1);
    expect(capturedCallback).toBeDefined();

    await act(async () => {
      await capturedCallback?.({ credential: 'cred-123' });
    });

    expect(firstSuccess).not.toHaveBeenCalled();
    expect(latestSuccess).toHaveBeenCalledTimes(1);
  });
});
