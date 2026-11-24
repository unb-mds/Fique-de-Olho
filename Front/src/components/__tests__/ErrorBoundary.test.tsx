import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ErrorBoundary from '../ErrorBoundary';

function BuggyComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Erro simulado de renderização');
  }
  return <p>Conteúdo saudável</p>;
}

function renderDynamicBoundary(getShouldThrow: () => boolean) {
  function DynamicChild() {
    return <BuggyComponent shouldThrow={getShouldThrow()} />;
  }

  return render(
    <ErrorBoundary>
      <DynamicChild />
    </ErrorBoundary>,
  );
}

describe('ErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('captura erro de renderização e permite tentar novamente após recuperação', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    let shouldThrow = true;
    renderDynamicBoundary(() => shouldThrow);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Não foi possível exibir esta página')).toBeInTheDocument();

    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }));

    expect(screen.getByText('Conteúdo saudável')).toBeInTheDocument();
  });

  it('reseta o estado de erro automaticamente ao navegar via popstate (botão Voltar)', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    let shouldThrow = true;
    renderDynamicBoundary(() => shouldThrow);

    expect(screen.getByRole('alert')).toBeInTheDocument();

    shouldThrow = false;
    fireEvent(window, new PopStateEvent('popstate'));

    expect(screen.getByText('Conteúdo saudável')).toBeInTheDocument();
  });
});
