import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HelpAndFeedbackButton from '../HelpAndFeedbackButton';
import { enviarFeedback } from '@/services/feedbackService';

vi.mock('@/services/feedbackService', () => ({
  enviarFeedback: vi.fn(),
}));

describe('HelpAndFeedbackButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('abre a central de ajuda pelo botão ? e envia feedback com sucesso', async () => {
    vi.mocked(enviarFeedback).mockResolvedValue({
      id: 1,
      tipo: 'sugestao',
      mensagem: 'Muito bom o filtro por campus!',
      email: 'teste@aluno.unb.br',
      pagina: '/',
      criado_em: '2026-11-21T23:55:00Z',
      message: 'Feedback enviado com sucesso. Obrigado por ajudar a melhorar o Fique de Olho!',
    });

    render(<HelpAndFeedbackButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Abrir central de ajuda e feedback' }));
    expect(screen.getByText('Central de Ajuda e Feedback')).toBeInTheDocument();
    expect(screen.getByText('Como buscar e filtrar editais?')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Enviar feedback' }));
    fireEvent.change(screen.getByLabelText('Mensagem'), {
      target: { value: 'Muito bom o filtro por campus!' },
    });
    fireEvent.change(screen.getByLabelText('Seu e-mail (opcional)'), {
      target: { value: 'teste@aluno.unb.br' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar feedback' }));

    expect(
      await screen.findByText('Feedback enviado com sucesso. Obrigado por ajudar a melhorar o Fique de Olho!'),
    ).toBeInTheDocument();
    expect(enviarFeedback).toHaveBeenCalledWith({
      tipo: 'sugestao',
      mensagem: 'Muito bom o filtro por campus!',
      email: 'teste@aluno.unb.br',
    });
  });

  it('exibe validação amigável quando a mensagem tem menos de 5 caracteres', () => {
    render(<HelpAndFeedbackButton />);

    fireEvent.click(screen.getByRole('button', { name: 'Abrir central de ajuda e feedback' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Enviar feedback' }));
    fireEvent.change(screen.getByLabelText('Mensagem'), { target: { value: 'oi' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar feedback' }));

    expect(
      screen.getByText('Escreva pelo menos 5 caracteres para enviar seu feedback.'),
    ).toBeInTheDocument();
    expect(enviarFeedback).not.toHaveBeenCalled();
  });
});
