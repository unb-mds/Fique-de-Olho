import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

/**
 * Contém exceções de renderização na árvore React, evitando tela branca
 * e permitindo recuperação via retry, navegação ou recarregamento.
 */
export default class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(
      'ErrorBoundary capturou uma falha de renderização:',
      error,
      errorInfo,
    );
  }

  componentDidMount(): void {
    window.addEventListener('popstate', this.handlePopState);
  }

  componentWillUnmount(): void {
    window.removeEventListener('popstate', this.handlePopState);
  }

  private handlePopState = (): void => {
    if (this.state.hasError) {
      this.setState({ hasError: false });
    }
  };

  private handleRetry = (): void => {
    this.setState({ hasError: false });
  };

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleGoHome = (): void => {
    window.location.assign('/');
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <main className="error-boundary-page" role="alert">
          <section className="error-boundary-card">
            <p className="eyebrow">Ops, algo deu errado</p>
            <h1>Não foi possível exibir esta página</h1>
            <p>
              Ocorreu uma falha inesperada ao carregar os componentes da tela. Você pode
              tentar novamente ou voltar para a listagem principal de editais.
            </p>
            <div className="error-boundary-actions">
              <button
                type="button"
                className="button button-accent"
                onClick={this.handleRetry}
              >
                Tentar novamente
              </button>
              <button
                type="button"
                className="button"
                onClick={this.handleGoHome}
              >
                Voltar para o início
              </button>
              <button
                type="button"
                className="button"
                onClick={this.handleReload}
              >
                Recarregar página
              </button>
            </div>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}
