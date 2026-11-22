---
status: accepted
---

# ADR 0005 — Pipeline Híbrido de Enriquecimento (Camada 1 determinística + Camada 2 Gemini opcional)

Para extrair datas de inscrição, bolsas, vagas, resumos e títulos padronizados de PDFs heterogêneos publicados por 33 portais da UnB dentro do limite de **512 MB de RAM** do Render Free e sem custo operacional obrigatório, decidimos adotar um pipeline em duas camadas: uma **Camada 1 determinística e offline** (`pdfplumber` + regex/heurísticas em `parser.py`) sempre executada primeiro, seguida por uma **Camada 2 opcional via Google Gemini (`gemini-3.5-flash-lite`)** acionada em no máximo 1 chamada unificada apenas quando faltam metadados ou o título/resumo continua genérico — com degradação graciosa para a Camada 1 em qualquer falha ou ausência de `GEMINI_API_KEY`.

## Opções consideradas

- **Apenas regex/heurísticas locais:** custo zero e baixa latência, mas frágil diante de títulos vagos (`"AQUI"`, `"Edital"`) e PDFs com cronogramas fora do padrão.
- **Pipeline local de Document AI / OCR (`Docling`, `PyTorch`, `RapidOCR`, `Airflow`):** excelente em documentos escaneados e tabelas complexas recorrentes, mas inviável no container único de 512 MB do Render Free e excessivo para editais cujos layouts mudam a cada publicação.
- **LLM obrigatório em todos os editais:** simplifica o parser, mas esgota rapidamente a cota gratuita (RPM/RPD), aumenta a latência da coleta e quebra o sistema caso a API externa fique indisponível.

## Consequências

- A coleta continua funcionando 100% offline/sem chave (`GEMINI_API_KEY=""`), garantindo previsibilidade em CI, testes e picos de rate limit (`429`/`503`).
- Toda saída do LLM passa por validação e sanitização determinística antes de persistir no PostgreSQL, impedindo datas invertidas ou valores espúrios.
- PDFs puramente escaneados (sem camada de texto) ainda não passam por OCR local; caso se tornem relevantes, o caminho previsto é enviar o PDF diretamente à API multimodal sem adicionar dependências de ML ao container.
