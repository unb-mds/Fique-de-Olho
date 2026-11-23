import { useEffect, useMemo, useRef, useState } from 'react';
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
  const [campus, setCampus] = useState<string | null>(null);
  const [ano, setAno] = useState<number | null>(null);
  const [totalAbertos, setTotalAbertos] = useState(0);
  const [destaquesAbertos, setDestaquesAbertos] = useState<Edital[]>([]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const loadMoreControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!search.trim()) {
      setDebouncedSearch('');
      return;
    }
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search);
    }, 220);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let ativo = true;
    getEditaisStats()
      .then((stats) => {
        if (ativo) setTotalAbertos(stats.abertos);
      })
      .catch(() => {
        if (ativo) setTotalAbertos(0);
      });
    getEditais({ status: 'aberto', limit: 3 })
      .then((dados) => {
        if (ativo) setDestaquesAbertos(dados);
      })
      .catch(() => {
        if (ativo) setDestaquesAbertos([]);
      });
    return () => {
      ativo = false;
    };
  }, [reloadTick]);

  useEffect(() => {
    loadMoreControllerRef.current?.abort();
    loadMoreControllerRef.current = null;
    setLoadingMore(false);
    setLoadMoreError(null);

    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getEditais({
      q: debouncedSearch,
      categoria,
      status: situacao,
      campus,
      ano,
      skip: 0,
      limit: PAGE_SIZE,
      signal: controller.signal,
    })
      .then((dados) => {
        if (controller.signal.aborted) return;
        setEditais(dados);
        setHasMore(dados.length === PAGE_SIZE);
      })
      .catch((err: Error) => {
        if (controller.signal.aborted || err.name === 'AbortError') return;
        setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      loadMoreControllerRef.current?.abort();
    };
  }, [debouncedSearch, categoria, situacao, campus, ano, reloadTick]);

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
    loadMoreControllerRef.current?.abort();
    const controller = new AbortController();
    loadMoreControllerRef.current = controller;

    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const dados = await getEditais({
        q: debouncedSearch,
        categoria,
        status: situacao,
        campus,
        ano,
        skip: editais.length,
        limit: PAGE_SIZE,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setEditais((atuais) => [...atuais, ...dados]);
      setHasMore(dados.length === PAGE_SIZE);
    } catch (err: unknown) {
      if (
        controller.signal.aborted ||
        (err instanceof Error && err.name === 'AbortError')
      ) {
        return;
      }
      setLoadMoreError(
        err instanceof Error
          ? err.message
          : 'Não foi possível carregar mais editais.',
      );
    } finally {
      if (!controller.signal.aborted) {
        setLoadingMore(false);
      }
    }
  }

  function clearSearchAndFilters() {
    setCategoria(null);
    setSituacao(null);
    setCampus(null);
    setAno(null);
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
          activeCampus={campus}
          activeAno={ano}
          onSelectCategoria={setCategoria}
          onSelectStatus={setSituacao}
          onSelectCampus={setCampus}
          onSelectAno={setAno}
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
          <div className="status-message status-message--error" role="alert">
            <div className="status-message-copy">
              <strong>Não foi possível carregar os editais</strong>
              <p>A conexão com o servidor falhou. Tente carregar a listagem novamente.</p>
            </div>
            <div className="status-message-actions">
              <button
                type="button"
                className="button button-accent"
                onClick={() => setReloadTick((prev) => prev + 1)}
              >
                Tentar novamente
              </button>
            </div>
          </div>
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
        {!loading && !error && loadMoreError && (
          <div className="status-message status-message--error status-message--compact" role="alert">
            <div className="status-message-copy">
              <p>{loadMoreError}</p>
            </div>
            <div className="status-message-actions">
              <button
                type="button"
                className="button button-accent"
                onClick={() => void carregarMais()}
              >
                Tentar novamente
              </button>
            </div>
          </div>
        )}
        {!loading && !error && hasMore && !loadMoreError && (
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
