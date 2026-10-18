# 0001. Escolha da Stack do Backend

---
status: accepted
date: 2026-09-22
---

## Contexto e Decisão

Para viabilizar a plataforma **Fique de Olho** (centralização, extração, busca e notificação de editais da UnB), decidimos adotar a seguinte stack tecnológica no backend:

1. **FastAPI**: framework web assíncrono em Python para construção da API REST.
2. **BeautifulSoup (bs4)**: biblioteca para raspagem de dados (*scraping*) e monitoramento das páginas de editais da UnB (DEG, DAC, etc.).
3. **pdfplumber**: biblioteca para extração e *parsing* estruturado de texto e tabelas a partir dos arquivos PDF dos editais.
4. **sentence-transformers**: modelo de *embeddings* vetoriais para viabilizar busca semântica em linguagem natural, planejado para a segunda entrega do produto.

Essa combinação garante uma arquitetura leve, moderna e orientada a APIs assíncronas, aproveitando o ecossistema maduro de manipulação de dados e Processamento de Linguagem Natural (PLN) em Python sem custos recorrentes de APIs externas proprietárias.

## Opções Consideradas

* **Framework Web:**
  * *FastAPI (Escolhida)*: Alto desempenho assíncrono (`asyncio`), geração nativa de documentação OpenAPI/Swagger e tipagem estrita com Pydantic.
  * *Django / Django Rest Framework*: Robusto, porém excessivamente pesado e opinativo para uma aplicação focada em microsserviço de API e pipelines de ingestão.
  * *Flask*: Leve, porém com suporte assíncrono menos integrado e sem validação declarativa de dados nativa.

* **Raspagem de Dados (Scraping):**
  * *BeautifulSoup (Escolhida)*: Simples, rápido e suficiente para os portais institucionais da UnB, cujo conteúdo principal é HTML estático acessível via requisições HTTP (`httpx` / `requests`).
  * *Scrapy*: Poderoso, porém traz complexidade desnecessária para o volume inicial de fontes.
  * *Selenium / Playwright*: Descartados no momento por demandarem navegadores *headless* pesados e alto consumo de memória/CPU.

* **Extração de Texto e Tabelas de PDF:**
  * *pdfplumber (Escolhida)*: Oferece inspeção detalhada de layout e extração confiável de tabelas estruturadas (essenciais para cronogramas e vagas de editais), superando leitores de texto plano.
  * *PyPDF / pypdf2*: Rápido para texto corrido, mas frágil para extrair tabelas e layouts de editais diagramados.
  * *Tesseract / OCR*: Desnecessário inicialmente, já que a maioria dos editais publicados pelo DEG/UnB possui camada nativa de texto pesquisável.

* **Mecanismo de Busca Semântica (Entrega 2):**
  * *sentence-transformers local (Escolhida)*: Permite busca baseada no significado da consulta (ex.: "auxílio para moradia no Gama") sem depender de casamento exato de termos ou custos por requisição de APIs externas.
  * *APIs de Embeddings Comerciais (OpenAI, Cohere)*: Descartadas para evitar custos recorrentes e dependência de serviços externos no escopo acadêmico/universitário.
  * *Busca textual simples (Full-text search SQL)*: Será usada na entrega 1 como *baseline*, sendo complementada pelos vetores na entrega 2.

## Consequências

* **Positivas:**
  * Alta produtividade no desenvolvimento de endpoints com validação automática de esquemas.
  * Pipeline completo de dados (scraping -> parsing de PDF -> indexação) mantido em uma única linguagem (Python).
  * Solução 100% livre de custos com licenças ou chamadas a provedores de IA de terceiros.
* **Trade-offs / Riscos identificados:**
  * O carregamento do modelo de `sentence-transformers` na memória durante a entrega 2 exigirá atenção ao dimensionamento do servidor (consumo de RAM e CPU na inferência de embeddings).
  * Mudanças na estrutura HTML dos portais da UnB exigirão manutenção e testes nos seletores do BeautifulSoup.

