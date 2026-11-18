import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import Header from '@/components/Header';
import Hero from '@/components/Hero';
import FilterBar from '@/components/FilterBar';
import EditalCard from '@/components/EditalCard';
import Footer from '@/components/Footer';
import { getEditais } from '@/services/editaisService';
import type { Edital } from '@/services/types';

function normalizeSearch(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

export default function HomePage() {
  const PAGE_SIZE = 12;
  const [editais, setEditais] = useState<Edital[]>([]);
  const [loading, setLoading] = useState(true);
  const [categoria, setCategoria] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    getEditais()
      .then(setEditais)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const editaisAbertos = useMemo(
    () => editais.filter((e) => e.status === 'aberto'),
    [editais],
  );

  // "Área" ainda não existe como campo próprio na API — por ora, contamos
  // quantos editais abertos existem por unidade, só para dar visão geral.
  const areaCounts = useMemo(() => {
    const counts = new Map<string, number>();
    editaisAbertos.forEach((e) => {
      if (!e.unidade) return;
      counts.set(e.unidade, (counts.get(e.unidade) ?? 0) + 1);
    });
    return Array.from(counts.entries()).map(([area, count]) => ({ area, count }));
  }, [editaisAbertos]);

  const filtrados = useMemo(() => {
    const searchTerm = normalizeSearch(deferredSearch);
    return editais.filter((e) => {
      const matchesCategory =
        categoria === null ||
        (e.categoria ?? '').toLowerCase() === categoria.toLowerCase();
      const searchableContent = normalizeSearch(
        [e.titulo, e.descricao, e.unidade, e.categoria].filter(Boolean).join(' '),
      );
      return matchesCategory &&
        (!searchTerm || searchableContent.includes(searchTerm));
    });
  }, [editais, categoria, deferredSearch]);

  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / PAGE_SIZE));
  const editaisPagina = useMemo(() => {
    const inicio = (pagina - 1) * PAGE_SIZE;
    return filtrados.slice(inicio, inicio + PAGE_SIZE);
  }, [filtrados, pagina]);

  useEffect(() => {
    setPagina(1);
  }, [deferredSearch, categoria]);

  useEffect(() => {
    if (pagina > totalPaginas) setPagina(totalPaginas);
  }, [pagina, totalPaginas]);

  function mudarPagina(novaPagina: number) {
    setPagina(novaPagina);
    document.getElementById('editais')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function clearSearchAndFilters() {
    setCategoria(null);
    setSearch('');
  }

  return (
    <div>
      <Header />
      <Hero editaisAbertos={editaisAbertos} />
      <main className="catalog-section" id="editais">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Seleção atualizada</p>
            <h2>Oportunidades para você</h2>
          </div>
          <p>Compare prazos, benefícios e unidades. Salve os editais que quiser acompanhar.</p>
        </div>

        <label className="catalog-search">
          <span>Buscar oportunidades</span>
          <div className="catalog-search-control">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
              <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <input
              type="search"
              aria-label="Buscar editais"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Busque por título, unidade ou categoria"
              autoComplete="off"
            />
            {search && (
              <button type="button" onClick={() => setSearch('')} aria-label="Limpar busca">
                ×
              </button>
            )}
          </div>
        </label>

        <FilterBar
          areaCounts={areaCounts}
          activeCategoria={categoria}
          onSelectCategoria={setCategoria}
          onClearFilters={clearSearchAndFilters}
        />

        {loading && (
          <div className="edital-list skeleton-list" aria-label="Carregando editais" aria-busy="true">
            {Array.from({ length: 6 }, (_, index) => (
              <div className="edital-card skeleton-card" key={index} aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            ))}
          </div>
        )}
        {!loading && error && (
          <p className="status-message" role="alert">
            Não foi possível carregar os editais. Verifique se a API está disponível.
          </p>
        )}
        {!loading && !error && (
          filtrados.length === 0 ? (
            <div className="empty-state">
              <strong>Nenhum edital encontrado</strong>
              <span>Não encontramos resultados para os termos e filtros selecionados.</span>
              <button type="button" onClick={clearSearchAndFilters}>Limpar busca e filtros</button>
            </div>
          ) : (
            <div className="edital-list">
              {editaisPagina.map((edital) => (
                <EditalCard key={edital.id} edital={edital} />
              ))}
            </div>
          )
        )}
        {!loading && !error && filtrados.length > PAGE_SIZE && (
          <nav className="pagination" aria-label="Paginação dos editais">
            <button
              type="button"
              onClick={() => mudarPagina(pagina - 1)}
              disabled={pagina === 1}
              aria-label="Página anterior"
            >
              ← Anterior
            </button>
            <span aria-live="polite">Página {pagina} de {totalPaginas}</span>
            <button
              type="button"
              onClick={() => mudarPagina(pagina + 1)}
              disabled={pagina === totalPaginas}
              aria-label="Próxima página"
            >
              Próxima →
            </button>
          </nav>
        )}
      </main>

      <section className="how-it-works" id="como-funciona">
        <p className="eyebrow">Menos abas, mais oportunidades</p>
        <h2>Um radar simples para a vida acadêmica.</h2>
        <div className="steps-grid">
          <article><span>01</span><h3>Descubra</h3><p>Veja editais de diferentes unidades da UnB no mesmo lugar.</p></article>
          <article><span>02</span><h3>Compare</h3><p>Confira prazos, vagas e benefícios antes de abrir o documento.</p></article>
          <article><span>03</span><h3>Acompanhe</h3><p>Salve oportunidades e consulte sua lista sempre que precisar.</p></article>
        </div>
      </section>

      <Footer />
    </div>
  );
}
