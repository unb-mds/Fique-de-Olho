---
name: doc-to-markdown
description: Converte documentos, PDFs, fotos, imagens e planilhas em Markdown (.md) estruturado utilizando o utilitário Python com MarkItDown. Use sempre que o usuário solicitar para ler, converter, extrair conteúdo ou transformar um arquivo PDF, foto, imagem ou documento em Markdown.
---

# Doc to Markdown

Esta skill permite ao agente ler arquivos de documentos (PDFs, relatórios, editais), imagens/fotos e apresentações, extraindo seu conteúdo formatado em Markdown limpo (`.md`) para o repositório.

## Quando usar

- Quando o usuário pedir para ler, extrair ou converter um arquivo PDF (por exemplo, um edital do DEG ou especificação).
- Quando o usuário fornecer uma foto, imagem ou captura de tela e quiser o texto formatado em Markdown.
- Quando for necessário transformar documentos Office (DOCX, PPTX, XLSX) ou páginas web em documentação Markdown na pasta `docs/`.

## Pré-requisitos

O utilitário utiliza a biblioteca oficial `markitdown` (Microsoft) com suporte a PDFs (`pdfminer.six`) e imagens (`pillow`):

```powershell
pip install markitdown pdfminer.six pillow
```

*(O ambiente local já possui essas dependências instaladas e validadas).*

## Procedimento de Execução

1. **Identifique o arquivo de entrada**:
   - Obtenha o caminho absoluto ou relativo do arquivo fornecido pelo usuário (ex.: `caminho/do/edital.pdf` ou `imagem.png`).

2. **Defina o destino do Markdown**:
   - Se o usuário especificou onde salvar o Markdown (ex.: `docs/Requissitos/edital.md`), use o parâmetro `-o <caminho>`.
   - Se o usuário apenas pediu para "ler" ou "mostrar" o conteúdo, você pode usar `--stdout` ou ler o resultado gerado.
   - Se não for especificado, o script criará um arquivo `.md` com o mesmo nome e no mesmo diretório do arquivo original.

3. **Execute o script de conversão**:
   Utilize a ferramenta `run_command` com:

   ```powershell
   python .github/skills/doc-to-markdown/scripts/convert.py "<CAMINHO_DO_ARQUIVO>" -o "<CAMINHO_SAIDA_MD>"
   ```

   *Exemplo para ler diretamente na saída do terminal:*
   ```powershell
   python .github/skills/doc-to-markdown/scripts/convert.py "<CAMINHO_DO_ARQUIVO>" --stdout
   ```

4. **Pós-processamento e Refinamento**:
   - Leia o Markdown gerado para verificar a qualidade da estrutura (títulos `#`, tabelas, listas e links).
   - Se o documento for um edital ou especificação complexa com tabelas, ajuste a hierarquia de cabeçalhos caso necessário para manter o padrão do repositório.
   - Apresente ao usuário o resumo da conversão e o link para o arquivo Markdown gerado.

## Formatos Suportados

- **PDF**: `.pdf` (documentos de texto, relatórios, editais)
- **Imagens**: `.png`, `.jpg`, `.jpeg` (fotos de anotações, wireframes, prints)
- **Office / Texto**: `.docx`, `.pptx`, `.xlsx`, `.csv`, `.html`, `.txt`

