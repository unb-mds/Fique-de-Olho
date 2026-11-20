import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import Header from '@/components/Header';
import Hero from '@/components/Hero';
import FilterBar from '@/components/FilterBar';
import EditalCard from '@/components/EditalCard';
import Footer from '@/components/Footer';

import { getEditais, getEditaisStats } from '@/services/editaisService';

import type { Edital } from '@/services/types';

export default function HomePage() {
  const PAGE_SIZE = 12;
  const [editais, setEditais] = useState<Edital[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [categoria, setCategoria] = useState<string | null>(null);

  const [situacao, setSituacao] = useState<'aberto' | 'fechado' | null>(null);
  const [totalAbertos, setTotalAbertos] = useState(0);
  const [destaquesAbertos, setDestaquesAbertos] = useState<Edital[]>([]);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    getEditaisStats().then((stats) => setTotalAbertos(stats.abertos)).catch(() => setTotalAbertos(0));
    getEditais({ status: 'aberto', limit: 3 }).then(setDestaquesAbertos).catch(() => setDestaquesAbertos([]));
  }, []);


  useEffect(() => {
    setLoading(true);
    setError(null);
    getEditais({
      q: deferredSearch,
      categoria,
      status: situacao,
      skip: 0,
      limit: PAGE_SIZE,
    })
      .then((dados) => {
        setEditais(dados);
        setHasMore(dados.length === PAGE_SIZE);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [deferredSearch, categoria, situacao]);

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


  async function carregarMais() {
    setLoadingMore(true);
    try {
      const dados = await getEditais({
        q: deferredSearch,
        categoria,
        status: situacao,
        skip: editais.length,
        limit: PAGE_SIZE,
      });
      setEditais((atuais) => [...atuais, ...dados]);
      setHasMore(dados.length === PAGE_SIZE);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível carregar mais editais.');
    } finally {
      setLoadingMore(false);
    }
  }

  function clearSearchAndFilters() {
    setCategoria(null);
    setSituacao(null);
    setSearch('');
  }

  return (
    <div>
      <Header />
      <Hero editaisAbertos={destaquesAbertos} totalAbertos={totalAbertos} />
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
          activeStatus={situacao}
          onSelectCategoria={setCategoria}
          onSelectStatus={setSituacao}
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
          editais.length === 0 ? (
            <div className="empty-state">
              <strong>Nenhum edital encontrado</strong>
              <span>Não encontramos resultados para os termos e filtros selecionados.</span>
              <button type="button" onClick={clearSearchAndFilters}>Limpar busca e filtros</button>
            </div>

          ) : (
            <div className="edital-list">
              {editais.map((edital) => (
                <EditalCard key={edital.id} edital={edital} />
              ))}
            </div>
          )
        )}
        {!loading && !error && hasMore && (
          <nav className="pagination" aria-label="Mais editais">
            <button
              type="button"
              onClick={carregarMais}
              disabled={loadingMore}
            >
              {loadingMore ? 'Carregando...' : 'Carregar mais'}
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
