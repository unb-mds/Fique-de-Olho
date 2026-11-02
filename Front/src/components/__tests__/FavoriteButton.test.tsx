import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FavoriteButton from '../FavoriteButton';

describe('FavoriteButton Component', () => {
  it('deve renderizar o botão com estado inicial não favoritado', () => {
    render(<FavoriteButton />);
    const button = screen.getByRole('button', { name: /favoritar edital/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('☆');
  });

  it('deve exibir aviso de login quando usuário não autenticado tenta favoritar', () => {
    render(<FavoriteButton />);
    const button = screen.getByRole('button', { name: /favoritar edital/i });
    
    fireEvent.click(button);

    expect(screen.getByText('Faça login para favoritar este edital.')).toBeInTheDocument();
  });

  it('deve fechar o aviso de login ao clicar no botão fechar', () => {
    render(<FavoriteButton />);
    const favButton = screen.getByRole('button', { name: /favoritar edital/i });
    fireEvent.click(favButton);

    const closeButton = screen.getByRole('button', { name: /fechar/i });
    fireEvent.click(closeButton);

    expect(screen.queryByText('Faça login para favoritar este edital.')).not.toBeInTheDocument();
  });
});

