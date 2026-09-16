#!/usr/bin/env python3
"""
doc-to-markdown: Utilitário para converter PDFs, imagens e documentos em Markdown.
Utiliza a biblioteca MarkItDown (Microsoft) com suporte a múltiplos formatos.
"""

import sys
import os
import argparse
from pathlib import Path

def convert_to_markdown(input_path: str, output_path: str = None, print_stdout: bool = False) -> str:
    """
    Converte um arquivo (PDF, imagem, Office, etc.) para Markdown.
    
    Args:
        input_path: Caminho do arquivo a ser convertido.
        output_path: Caminho opcional do arquivo .md de saída.
        print_stdout: Se True, imprime o Markdown gerado na saída padrão.
        
    Returns:
        Texto em formato Markdown resultante da conversão.
    """
    input_file = Path(input_path).resolve()
    
    if not input_file.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {input_file}")

    try:
        from markitdown import MarkItDown
    except ImportError:
        raise ImportError(
            "A biblioteca 'markitdown' não está instalada no ambiente Python.\n"
            "Instale executando: pip install markitdown pdfminer.six pillow"
        )

    # Inicializa o conversor
    md_converter = MarkItDown()
    
    # Executa a conversão
    result = md_converter.convert(str(input_file))
    markdown_content = result.text_content if hasattr(result, "text_content") else str(result)

    # Se um caminho de saída foi especificado, salva o arquivo
    if output_path:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(markdown_content, encoding="utf-8")
        print(f"[SUCESSO] Conteúdo convertido e salvo em: {out_file}", file=sys.stderr)
    elif not print_stdout:
        # Se não especificou saída e não pediu stdout exclusivo, gera arquivo .md no mesmo diretório
        default_output = input_file.with_suffix(".md")
        default_output.write_text(markdown_content, encoding="utf-8")
        print(f"[SUCESSO] Conteúdo salvo automaticamente em: {default_output}", file=sys.stderr)

    if print_stdout or not output_path:
        print(markdown_content)

    return markdown_content


def main():
    parser = argparse.ArgumentParser(
        description="Converte arquivos PDF, fotos, imagens e documentos para Markdown formatado."
    )
    parser.add_argument("input", help="Caminho do arquivo de entrada (PDF, imagem, DOCX, etc.)")
    parser.add_argument("-o", "--output", help="Caminho opcional do arquivo Markdown (.md) de saída", default=None)
    parser.add_argument("--stdout", action="store_true", help="Imprime o Markdown na saída padrão sem salvar em arquivo automático")

    args = parser.parse_args()

    try:
        convert_to_markdown(args.input, output_path=args.output, print_stdout=args.stdout)
    except Exception as e:
        print(f"[ERRO] Falha na conversão: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

