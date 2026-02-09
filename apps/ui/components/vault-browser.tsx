"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ReactMarkdown from "react-markdown";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";

import { normalizeAnchor } from "@/lib/anchor";
import type {
  DocumentDetail,
  IncomingLink,
  LinkCandidate,
  SearchResult,
  VaultStatus,
} from "@/lib/types";

interface SearchResponse {
  results: SearchResult[];
  total: number;
  error?: string;
}

interface DocumentResponse {
  doc: DocumentDetail;
  error?: string;
}

interface IncomingResponse {
  incoming: IncomingLink[];
  error?: string;
}

interface GraphNodePayload {
  id: string;
  title: string;
  depth: number;
}

interface GraphEdgePayload {
  from: string;
  to: string;
  kind: "incoming" | "outgoing";
}

interface GraphPayload {
  rootId: string;
  nodes: GraphNodePayload[];
  edges: GraphEdgePayload[];
}

interface GraphResponse {
  graph: GraphPayload;
  error?: string;
}

interface StatusResponse {
  status: VaultStatus;
  error?: string;
}

interface PreparedMarkdown {
  markdown: string;
  candidatesByKey: Record<string, LinkCandidate[]>;
}

type LinkTab = "outgoing" | "incoming" | "graph";

const PAGE_SIZE = 120;
const LAW_INDEX_CANDIDATES = ["laws_index", "law_index", "law-index"];

export function VaultBrowser(): JSX.Element {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [visibleLimit, setVisibleLimit] = useState(PAGE_SIZE);
  const [status, setStatus] = useState<VaultStatus | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openDocTabs, setOpenDocTabs] = useState<string[]>([]);
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [isLoadingSearch, setIsLoadingSearch] = useState(false);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<LinkTab>("outgoing");
  const [knownTitles, setKnownTitles] = useState<Record<string, string>>({});
  const [knownPaths, setKnownPaths] = useState<Record<string, string>>({});
  const [incomingByDocId, setIncomingByDocId] = useState<
    Record<string, IncomingLink[]>
  >({});
  const [incomingError, setIncomingError] = useState<string | null>(null);
  const [loadingIncomingFor, setLoadingIncomingFor] = useState<string | null>(
    null,
  );
  const [graphDepth, setGraphDepth] = useState(1);
  const [graphData, setGraphData] = useState<GraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [graphExpanded, setGraphExpanded] = useState(false);
  const [candidatePopup, setCandidatePopup] = useState<{
    label: string;
    options: LinkCandidate[];
  } | null>(null);
  const [pendingAnchor, setPendingAnchor] = useState<string | null>(null);
  const [lawIndexId, setLawIndexId] = useState<string | null>(null);
  const [lawIndexLoading, setLawIndexLoading] = useState(false);
  const [lawIndexError, setLawIndexError] = useState<string | null>(null);
  const searchRequestSeqRef = useRef(0);
  const searchAbortRef = useRef<AbortController | null>(null);

  const openDocument = useCallback((id: string) => {
    setOpenDocTabs((previous) => {
      if (previous.includes(id)) {
        return previous;
      }
      return [...previous, id].slice(-24);
    });
    setSelectedId(id);
  }, []);

  const closeDocumentTab = useCallback((id: string) => {
    setOpenDocTabs((previous) => {
      const index = previous.indexOf(id);
      if (index < 0) {
        return previous;
      }

      const next = previous.filter((item) => item !== id);
      setSelectedId((current) => {
        if (current !== id) {
          return current;
        }
        if (next.length === 0) {
          return null;
        }
        return next[Math.max(0, index - 1)] || next[0];
      });
      return next;
    });
  }, []);

  const runSearch = useCallback(async function runSearchImpl(
    input: string,
    limit: number,
    retries = 2,
  ) {
    const requestSeq = searchRequestSeqRef.current + 1;
    searchRequestSeqRef.current = requestSeq;
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    setSearchError(null);
    setIsLoadingSearch(true);

    try {
      const response = await fetch(
        `/api/search?q=${encodeURIComponent(input)}&limit=${limit}`,
        { signal: controller.signal },
      );
      const data = (await response.json()) as SearchResponse;

      if (!response.ok || data.error || !data.results) {
        throw new Error(data.error || "Search failed");
      }

      if (requestSeq !== searchRequestSeqRef.current) {
        return;
      }

      const filteredResults = data.results.filter(
        (item) => !isSearchHiddenId(item.id),
      );
      setResults(filteredResults);
      setTotalResults(
        typeof data.total === "number"
          ? Math.max(filteredResults.length, data.total)
          : filteredResults.length,
      );

      setKnownTitles((previous) => {
        const next = { ...previous };
        for (const result of filteredResults) {
          next[result.id] = result.title;
        }
        return next;
      });

      setKnownPaths((previous) => {
        const next = { ...previous };
        for (const result of filteredResults) {
          next[result.id] = result.relPath || `${result.id}.md`;
        }
        return next;
      });

      if (filteredResults.length > 0) {
        setSelectedId((previous) => previous || filteredResults[0].id);
      }
    } catch (error) {
      if (
        controller.signal.aborted ||
        (error instanceof DOMException && error.name === "AbortError")
      ) {
        return;
      }

      if (requestSeq !== searchRequestSeqRef.current) {
        return;
      }

      setResults([]);
      setTotalResults(0);
      setSearchError(error instanceof Error ? error.message : "Search failed");

      if (retries > 0) {
        window.setTimeout(() => {
          if (requestSeq === searchRequestSeqRef.current) {
            void runSearchImpl(input, limit, retries - 1);
          }
        }, 1200);
      }
    } finally {
      if (
        requestSeq === searchRequestSeqRef.current &&
        !controller.signal.aborted
      ) {
        setIsLoadingSearch(false);
      }
    }
  }, []);

  useEffect(() => {
    let canceled = false;
    const timers = new Set<number>();

    const fetchStatus = async (retries: number): Promise<void> => {
      try {
        const response = await fetch("/api/status");
        const data = (await response.json()) as StatusResponse;

        if (!response.ok || data.error || !data.status) {
          throw new Error(data.error || "Failed to fetch status");
        }

        if (!canceled) {
          setStatus(data.status);
          if (data.status.indexing) {
            const timer = window.setTimeout(() => {
              timers.delete(timer);
              void fetchStatus(0);
            }, 2500);
            timers.add(timer);
          }
        }
      } catch (error) {
        if (!canceled && retries > 0) {
          const timer = window.setTimeout(() => {
            timers.delete(timer);
            void fetchStatus(retries - 1);
          }, 1200);
          timers.add(timer);
        } else if (!canceled) {
          setSearchError(
            error instanceof Error ? error.message : "Failed to fetch status",
          );
        }
      }
    };

    void fetchStatus(4);

    return () => {
      canceled = true;
      for (const timer of timers) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  useEffect(() => {
    const timeout = setTimeout(() => {
      void runSearch(query, visibleLimit);
    }, 220);

    return () => clearTimeout(timeout);
  }, [query, runSearch, visibleLimit]);

  useEffect(() => {
    return () => {
      searchAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDoc(null);
      return;
    }

    setDocError(null);
    setIsLoadingDoc(true);

    fetch(`/api/doc?id=${encodeURIComponent(selectedId)}`)
      .then((res) => res.json() as Promise<DocumentResponse>)
      .then((data) => {
        if (data.error || !data.doc) {
          throw new Error(data.error || "Failed to fetch document");
        }

        setDoc(data.doc);
        setKnownTitles((previous) => ({
          ...previous,
          [data.doc.id]: data.doc.title,
        }));
        setKnownPaths((previous) => ({
          ...previous,
          [data.doc.id]: data.doc.relPath || `${data.doc.id}.md`,
        }));
        setIncomingError(null);
        setGraphError(null);
      })
      .catch((error) => {
        setDoc(null);
        setDocError(
          error instanceof Error ? error.message : "Failed to fetch document",
        );
      })
      .finally(() => {
        setIsLoadingDoc(false);
      });
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    setOpenDocTabs((previous) => {
      if (previous.includes(selectedId)) {
        return previous;
      }
      return [...previous, selectedId].slice(-24);
    });
  }, [selectedId]);

  useEffect(() => {
    if (!doc) {
      return;
    }

    if (activeTab !== "incoming") {
      return;
    }

    if (incomingByDocId[doc.id]) {
      return;
    }

    if (loadingIncomingFor === doc.id) {
      return;
    }

    setLoadingIncomingFor(doc.id);
    setIncomingError(null);

    fetch(`/api/incoming?id=${encodeURIComponent(doc.id)}&limit=260`)
      .then((res) => res.json() as Promise<IncomingResponse>)
      .then((data) => {
        if (data.error || !data.incoming) {
          throw new Error(data.error || "Failed to fetch incoming links");
        }

        setIncomingByDocId((previous) => ({
          ...previous,
          [doc.id]: data.incoming,
        }));

        setKnownTitles((previous) => {
          const next = { ...previous };
          for (const link of data.incoming) {
            next[link.id] = link.title;
          }
          return next;
        });
        setKnownPaths((previous) => {
          const next = { ...previous };
          for (const link of data.incoming) {
            next[link.id] = link.relPath || `${link.id}.md`;
          }
          return next;
        });
      })
      .catch((error) => {
        setIncomingError(
          error instanceof Error ? error.message : "Failed to fetch incoming",
        );
      })
      .finally(() => {
        setLoadingIncomingFor((current) =>
          current === doc.id ? null : current,
        );
      });
  }, [activeTab, doc, incomingByDocId, loadingIncomingFor]);

  useEffect(() => {
    if (!doc || activeTab !== "graph") {
      return;
    }

    let cancelled = false;
    setGraphLoading(true);
    setGraphError(null);

    fetch(
      `/api/graph?id=${encodeURIComponent(doc.id)}&depth=${graphDepth}&node_limit=140`,
    )
      .then((res) => res.json() as Promise<GraphResponse>)
      .then((data) => {
        if (data.error || !data.graph) {
          throw new Error(data.error || "Failed to fetch graph");
        }
        if (!cancelled) {
          setGraphData(data.graph);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setGraphData(null);
          setGraphError(
            error instanceof Error ? error.message : "Failed to fetch graph",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setGraphLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, doc, graphDepth]);

  useEffect(() => {
    setGraphExpanded(false);
  }, [doc?.id]);

  useEffect(() => {
    if (!graphExpanded) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setGraphExpanded(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [graphExpanded]);

  useEffect(() => {
    if (!pendingAnchor || !doc) {
      return;
    }

    const timer = setTimeout(() => {
      if (!scrollToAnchor(pendingAnchor)) {
        const normalized = normalizeAnchor(pendingAnchor);
        const headings = Array.from(
          document.querySelectorAll(
            ".markdown-view h1, .markdown-view h2, .markdown-view h3",
          ),
        );
        const match = headings.find(
          (node) => normalizeAnchor(node.textContent || "") === normalized,
        );
        if (match instanceof HTMLElement) {
          match.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
      setPendingAnchor(null);
    }, 50);

    return () => clearTimeout(timer);
  }, [doc, pendingAnchor]);

  const preparedMarkdown = useMemo(() => {
    if (!doc) {
      return null;
    }
    return convertWikiLinksToMarkdown(doc);
  }, [doc]);

  const incomingLinks = useMemo(() => {
    if (!doc) {
      return [];
    }
    return incomingByDocId[doc.id] || [];
  }, [doc, incomingByDocId]);

  const tabItems = useMemo(
    () =>
      openDocTabs.map((id) => ({
        id,
        title: knownTitles[id] || pathLikeTitle(id),
        path: knownPaths[id] || `${id}.md`,
      })),
    [knownPaths, knownTitles, openDocTabs],
  );

  const activeTabMeta = useMemo(
    () => tabItems.find((item) => item.id === selectedId) || null,
    [selectedId, tabItems],
  );

  const resolveLawIndexDocumentId = useCallback(async (): Promise<
    string | null
  > => {
    if (lawIndexId) {
      return lawIndexId;
    }

    for (const candidate of LAW_INDEX_CANDIDATES) {
      try {
        const response = await fetch(
          `/api/doc?id=${encodeURIComponent(candidate)}`,
        );
        const data = (await response.json()) as DocumentResponse;

        if (!response.ok || data.error || !data.doc) {
          continue;
        }

        setLawIndexId(data.doc.id);
        setKnownTitles((previous) => ({
          ...previous,
          [data.doc.id]: data.doc.title,
        }));
        setKnownPaths((previous) => ({
          ...previous,
          [data.doc.id]: data.doc.relPath || `${data.doc.id}.md`,
        }));
        return data.doc.id;
      } catch {
        // try next candidate
      }
    }

    return null;
  }, [lawIndexId]);

  const openLawIndex = useCallback(async () => {
    setLawIndexError(null);
    setLawIndexLoading(true);

    try {
      const resolved = await resolveLawIndexDocumentId();
      if (!resolved) {
        setLawIndexError("laws.index が見つかりません。");
        return;
      }

      openDocument(resolved);
      setActiveTab("outgoing");
    } finally {
      setLawIndexLoading(false);
    }
  }, [openDocument, resolveLawIndexDocumentId]);

  const onLinkClick = useCallback(
    (href: string | undefined) => {
      if (!href) {
        return;
      }

      if (href.startsWith("db4law://doc/")) {
        const withoutScheme = href.replace("db4law://doc/", "");
        const [encodedId, encodedAnchor] = withoutScheme.split("#", 2);
        const nextId = safeDecodeURIComponent(encodedId);
        const nextAnchor = encodedAnchor
          ? safeDecodeURIComponent(encodedAnchor)
          : null;

        if (nextId === doc?.id && nextAnchor) {
          scrollToAnchor(nextAnchor);
          return;
        }

        openDocument(nextId);
        setActiveTab("outgoing");
        if (nextAnchor) {
          setPendingAnchor(nextAnchor);
        }
        return;
      }

      if (href.startsWith("db4law://candidate/")) {
        const key = decodeURIComponent(href.replace("db4law://candidate/", ""));
        const options = preparedMarkdown?.candidatesByKey[key] || [];
        if (options.length > 0) {
          setCandidatePopup({
            label: key,
            options,
          });
        }
      }
    },
    [doc?.id, openDocument, preparedMarkdown],
  );

  const isIncomingLoading = !!doc && loadingIncomingFor === doc.id;
  const hasMoreResults = results.length < totalResults;

  return (
    <main className="app-shell">
      <section className="panel panel-left">
        <div className="brand-block">
          <h1>DB4LAW Vault Reader</h1>
          <p className="panel-caption">Read-only Obsidian-compatible viewer</p>
        </div>

        <label htmlFor="search-box" className="search-label">
          Search
        </label>
        <input
          id="search-box"
          className="search-box"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setVisibleLimit(PAGE_SIZE);
          }}
          placeholder="法令名 / law_id / article_id / キーワード"
        />

        <div className="status-block">
          <div>
            Documents:{" "}
            {status?.totalDocs != null
              ? status.totalDocs.toLocaleString()
              : "indexing..."}
          </div>
          <div className="mono small">
            Vault: {status?.vaultPath || "loading"}
          </div>
          <div className="small muted">
            {status?.indexing ? "Indexing in background" : "Index ready"}
          </div>
        </div>

        <div className="panel-note">
          <div className="small muted">
            Open tabs: {openDocTabs.length.toLocaleString()}
          </div>
          <div className="small muted">
            検索結果や本文リンクを開くと、右側にタブとして保持されます。
          </div>
        </div>

        <div className="left-panel-footer">
          <button
            type="button"
            className="left-action-btn"
            onClick={() => void openLawIndex()}
            disabled={lawIndexLoading}
          >
            {lawIndexLoading
              ? "laws.index を読み込み中..."
              : "laws.index を表示"}
          </button>
          {lawIndexError ? (
            <div className="small muted">{lawIndexError}</div>
          ) : null}
        </div>
      </section>

      <section className="panel panel-center">
        <header className="panel-header">
          <h2>Results</h2>
          <span className="small muted">
            {isLoadingSearch
              ? "Searching..."
              : `${results.length.toLocaleString()} shown / ${totalResults.toLocaleString()} total`}
          </span>
        </header>
        {searchError ? <p className="error-box">{searchError}</p> : null}
        <ul className="result-list">
          {results.map((result) => (
            <li key={result.id}>
              <button
                type="button"
                className={`result-item ${selectedId === result.id ? "selected" : ""}`}
                onClick={() => openDocument(result.id)}
              >
                <strong>{result.title}</strong>
                <span className="mono">{result.id}</span>
                <span className="small muted">
                  {renderFrontmatterHint(result.frontmatter)}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {hasMoreResults ? (
          <button
            type="button"
            className="load-more"
            onClick={() => setVisibleLimit((previous) => previous + PAGE_SIZE)}
          >
            Load more
          </button>
        ) : null}
      </section>

      <section className="panel panel-right">
        <div className="browser-chrome">
          <div
            className="doc-tabs-scroll"
            role="tablist"
            aria-label="Open documents"
          >
            {tabItems.map((item) => (
              <div
                key={item.id}
                className={`doc-tab ${selectedId === item.id ? "active" : ""}`}
              >
                <button
                  type="button"
                  className="doc-tab-hit"
                  onClick={() => openDocument(item.id)}
                  role="tab"
                  aria-selected={selectedId === item.id}
                  title={item.path}
                >
                  <span className="doc-tab-title">{item.title}</span>
                  <span className="doc-tab-path mono">{item.path}</span>
                </button>
                <button
                  type="button"
                  className="doc-tab-close"
                  onClick={() => closeDocumentTab(item.id)}
                  aria-label={`Close ${item.title}`}
                >
                  ×
                </button>
              </div>
            ))}
            {tabItems.length === 0 ? (
              <div className="doc-tab-empty">
                Open documents appear here as tabs.
              </div>
            ) : null}
          </div>

          <div className="browser-location">
            <span
              className="browser-location-path mono"
              title={doc?.relPath || activeTabMeta?.path || ""}
            >
              {doc?.relPath ||
                activeTabMeta?.path ||
                "Select a document to view its path"}
            </span>
          </div>
        </div>

        {isLoadingDoc ? <p>Loading preview...</p> : null}
        {docError ? <p className="error-box">{docError}</p> : null}

        {!isLoadingDoc && !doc && !docError ? <p>Select a document.</p> : null}

        {doc ? (
          <>
            <header className="doc-header">
              <h2>{doc.title}</h2>
              <div className="mono small">{doc.relPath}</div>
            </header>

            <details open>
              <summary>Frontmatter</summary>
              <FrontmatterPanel
                frontmatter={doc.frontmatter}
                currentDocId={doc.id}
                onNavigate={onLinkClick}
              />
            </details>

            <article className="markdown-view">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeSlug]}
                urlTransform={(url) => url}
                components={{
                  a: ({ href, children }) => {
                    const internalHref = doc
                      ? toInternalNavigationHref(href, doc.id)
                      : null;

                    if (internalHref) {
                      return (
                        <button
                          type="button"
                          className="markdown-link"
                          onClick={() => onLinkClick(internalHref)}
                        >
                          {children}
                        </button>
                      );
                    }

                    return (
                      <a href={href} target="_blank" rel="noreferrer">
                        {children}
                      </a>
                    );
                  },
                }}
              >
                {preparedMarkdown?.markdown || doc.markdown}
              </ReactMarkdown>
            </article>

            <div className="link-tabs">
              <button
                type="button"
                className={activeTab === "outgoing" ? "active" : ""}
                onClick={() => setActiveTab("outgoing")}
              >
                Outgoing ({doc.outgoing.length})
              </button>
              <button
                type="button"
                className={activeTab === "incoming" ? "active" : ""}
                onClick={() => setActiveTab("incoming")}
              >
                Incoming (
                {incomingByDocId[doc.id] ? incomingLinks.length : "..."})
              </button>
              <button
                type="button"
                className={activeTab === "graph" ? "active" : ""}
                onClick={() => setActiveTab("graph")}
              >
                Graph
              </button>
            </div>

            {activeTab === "outgoing" ? (
              <ul className="link-list">
                {doc.outgoing.map((link, index) => (
                  <li key={`${link.raw}-${index}`}>
                    {link.resolvedId ? (
                      <button
                        type="button"
                        onClick={() => openDocument(link.resolvedId!)}
                      >
                        {link.display} → {link.resolvedTitle || link.resolvedId}
                      </button>
                    ) : link.candidates && link.candidates.length > 0 ? (
                      <button
                        type="button"
                        onClick={() =>
                          setCandidatePopup({
                            label: link.display,
                            options: link.candidates!,
                          })
                        }
                      >
                        {link.display} (ambiguous: {link.candidates.length})
                      </button>
                    ) : (
                      <span className="muted">{link.display} (unresolved)</span>
                    )}
                  </li>
                ))}
              </ul>
            ) : null}

            {activeTab === "incoming" ? (
              <>
                {isIncomingLoading ? (
                  <p className="small muted">Loading incoming...</p>
                ) : null}
                {incomingError ? (
                  <p className="error-box">{incomingError}</p>
                ) : null}
                <ul className="link-list">
                  {incomingLinks.map((link) => (
                    <li key={link.id}>
                      <button
                        type="button"
                        onClick={() => openDocument(link.id)}
                      >
                        {link.title}
                      </button>
                      <span className="mono small">{link.id}</span>
                    </li>
                  ))}
                  {!isIncomingLoading && incomingLinks.length === 0 ? (
                    <li className="small muted">No incoming links detected.</li>
                  ) : null}
                </ul>
              </>
            ) : null}

            {activeTab === "graph" ? (
              <>
                <div className="graph-toolbar">
                  <label htmlFor="graph-depth">Depth</label>
                  <select
                    id="graph-depth"
                    value={graphDepth}
                    onChange={(event) =>
                      setGraphDepth(Number(event.target.value))
                    }
                  >
                    <option value={1}>1</option>
                    <option value={2}>2</option>
                    <option value={3}>3</option>
                    <option value={4}>4</option>
                  </select>
                  <button
                    type="button"
                    className={
                      graphExpanded ? "graph-expand active" : "graph-expand"
                    }
                    onClick={() => setGraphExpanded((current) => !current)}
                  >
                    {graphExpanded ? "Shrink" : "Expand"}
                  </button>
                </div>
                {graphLoading ? (
                  <p className="small muted">Loading graph...</p>
                ) : null}
                {graphError ? <p className="error-box">{graphError}</p> : null}
                {graphData ? (
                  <GraphView
                    graph={graphData}
                    rootTitle={doc.title}
                    expanded={graphExpanded}
                    onClose={() => setGraphExpanded(false)}
                    onSelect={(id) => openDocument(id)}
                  />
                ) : null}
              </>
            ) : null}
          </>
        ) : null}
      </section>

      {candidatePopup ? (
        <div
          className="candidate-overlay"
          onClick={() => setCandidatePopup(null)}
        >
          <div
            className="candidate-dialog"
            onClick={(event) => event.stopPropagation()}
          >
            <h3>Candidates: {candidatePopup.label}</h3>
            <ul>
              {candidatePopup.options.map((candidate) => (
                <li key={candidate.id}>
                  <button
                    type="button"
                    onClick={() => {
                      openDocument(candidate.id);
                      setCandidatePopup(null);
                    }}
                  >
                    {candidate.title}
                    <span className="mono small">{candidate.id}</span>
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" onClick={() => setCandidatePopup(null)}>
              Close
            </button>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function pathLikeTitle(id: string): string {
  const parts = id.split("/");
  return parts[parts.length - 1] || id;
}

function isSearchHiddenId(id: string): boolean {
  const normalized = id
    .trim()
    .replace(/\\/g, "/")
    .replace(/\.md$/i, "")
    .replace(/^\/+/, "")
    .toLowerCase();

  if (!normalized) {
    return false;
  }

  return (
    normalized === "laws_index" ||
    normalized === "law_index" ||
    normalized === "law-index"
  );
}

function renderFrontmatterHint(frontmatter: Record<string, unknown>): string {
  const interestingKeys = ["law_id", "article_id", "abbr", "alias"];
  const tokens: string[] = [];

  for (const key of interestingKeys) {
    const value = frontmatter[key];
    if (typeof value === "string" && value.trim()) {
      tokens.push(`${key}:${value}`);
    }
  }

  return tokens.join(" / ");
}

function FrontmatterPanel(props: {
  frontmatter: Record<string, unknown>;
  currentDocId: string;
  onNavigate: (href: string) => void;
}): JSX.Element {
  const { frontmatter, currentDocId, onNavigate } = props;
  const entries = Object.entries(frontmatter);

  if (entries.length === 0) {
    return <p className="small muted">No frontmatter fields.</p>;
  }

  return (
    <div className="frontmatter-view">
      {entries.map(([key, value]) => (
        <div className="frontmatter-row" key={key}>
          <div className="frontmatter-key">{key}</div>
          <div className="frontmatter-value">
            {renderFrontmatterValue(key, value, currentDocId, onNavigate)}
          </div>
        </div>
      ))}
    </div>
  );
}

function renderFrontmatterValue(
  key: string,
  value: unknown,
  currentDocId: string,
  onNavigate: (href: string) => void,
): JSX.Element {
  if (value == null) {
    return <span className="frontmatter-empty">-</span>;
  }

  if (typeof value === "string") {
    const date = normalizeDateString(value);
    if (date) {
      return <span>{date}</span>;
    }

    const url = toExternalUrl(key, value);
    if (url) {
      return (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="frontmatter-link"
        >
          {value}
        </a>
      );
    }

    const wiki = parseFrontmatterWikiLink(value);
    if (wiki) {
      const wikiHref = toInternalNavigationHref(
        `${wiki.target}${wiki.anchor ? `#${wiki.anchor}` : ""}`,
        currentDocId,
      );
      if (wikiHref) {
        return (
          <button
            type="button"
            className="frontmatter-link-button"
            onClick={() => onNavigate(wikiHref)}
          >
            {wiki.display}
          </button>
        );
      }
    }

    return <span>{value}</span>;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return <span>{String(value)}</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="frontmatter-empty">[]</span>;
    }

    const chips =
      key === "tags" || key === "aliases"
        ? value.filter((item): item is string => typeof item === "string")
        : [];

    if (chips.length === value.length) {
      return (
        <div className="frontmatter-chips">
          {chips.map((item, index) => (
            <span key={`${item}-${index}`} className="frontmatter-chip">
              {item}
            </span>
          ))}
        </div>
      );
    }

    return (
      <div className="frontmatter-list">
        {value.map((item, index) => (
          <div key={`${key}-${index}`}>
            {renderFrontmatterValue(key, item, currentDocId, onNavigate)}
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className="frontmatter-empty">{"{}"}</span>;
    }

    return (
      <div className="frontmatter-list">
        {entries.map(([nestedKey, nestedValue]) => (
          <div key={`${key}-${nestedKey}`}>
            <span className="frontmatter-subkey">{nestedKey}: </span>
            {renderFrontmatterValue(
              nestedKey,
              nestedValue,
              currentDocId,
              onNavigate,
            )}
          </div>
        ))}
      </div>
    );
  }

  return <span>{String(value)}</span>;
}

function normalizeDateString(input: string): string | null {
  const trimmed = input.trim();
  const yyyyMmDd = trimmed.match(/^(\d{4})[-/](\d{2})[-/](\d{2})$/);
  if (yyyyMmDd) {
    return `${yyyyMmDd[1]}/${yyyyMmDd[2]}/${yyyyMmDd[3]}`;
  }

  const yyyymmdd = trimmed.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (yyyymmdd) {
    return `${yyyymmdd[1]}/${yyyymmdd[2]}/${yyyymmdd[3]}`;
  }

  return null;
}

function toExternalUrl(key: string, value: string): string | null {
  if (/^https?:\/\//i.test(value)) {
    return value;
  }

  if (key === "id") {
    const match = value.match(/^JPLAW:([0-9A-Z]+)$/i);
    if (match) {
      return `https://laws.e-gov.go.jp/law/${match[1].toUpperCase()}`;
    }
  }

  return null;
}

function parseFrontmatterWikiLink(
  input: string,
): { target: string; display: string; anchor: string | null } | null {
  const trimmed = input.trim();
  const match = trimmed.match(/^\[\[([\s\S]+?)\]\]$/);
  if (!match) {
    return null;
  }

  const inner = match[1].trim();
  if (!inner) {
    return null;
  }

  const pipeIndex = inner.indexOf("|");
  const rawTarget = pipeIndex >= 0 ? inner.slice(0, pipeIndex) : inner;
  const alias = pipeIndex >= 0 ? inner.slice(pipeIndex + 1).trim() : "";

  const hashIndex = rawTarget.indexOf("#");
  const target = (hashIndex >= 0 ? rawTarget.slice(0, hashIndex) : rawTarget)
    .trim()
    .replace(/\.md$/i, "");
  const anchor = hashIndex >= 0 ? rawTarget.slice(hashIndex + 1).trim() : "";

  if (!target) {
    return null;
  }

  return {
    target,
    display: alias || target,
    anchor: anchor || null,
  };
}

function convertWikiLinksToMarkdown(doc: DocumentDetail): PreparedMarkdown {
  const candidatesByKey: Record<string, LinkCandidate[]> = {};
  let linkIndex = 0;

  const markdown = doc.markdown.replace(/\[\[([^\]\n]+?)\]\]/g, (_, inner) => {
    const link = doc.outgoing[linkIndex];
    linkIndex += 1;

    if (!link) {
      return `\`${inner}\``;
    }

    const label = escapeMarkdownLabel(link.display || inner);

    if (link.resolvedId) {
      const anchor = link.anchor ? `#${encodeURIComponent(link.anchor)}` : "";
      return `[${label}](db4law://doc/${encodeURIComponent(link.resolvedId)}${anchor})`;
    }

    if (link.candidates && link.candidates.length > 0) {
      const key = `cand-${linkIndex}`;
      candidatesByKey[key] = link.candidates;
      return `[${label}](db4law://candidate/${encodeURIComponent(key)})`;
    }

    return `\`${label}\``;
  });

  return { markdown, candidatesByKey };
}

function escapeMarkdownLabel(input: string): string {
  return input.replace(/[\[\]]/g, "");
}

function scrollToAnchor(anchor: string): boolean {
  const candidates = [decodeURIComponent(anchor), normalizeAnchor(anchor)];

  for (const candidate of candidates) {
    const byId = document.getElementById(candidate);
    if (byId) {
      byId.scrollIntoView({ behavior: "smooth", block: "start" });
      return true;
    }
  }

  return false;
}

function toInternalNavigationHref(
  href: string | undefined,
  currentId: string,
): string | null {
  if (!href) {
    return null;
  }

  if (href.startsWith("db4law://")) {
    return href;
  }

  if (/^(https?:|mailto:|tel:)/i.test(href)) {
    return null;
  }

  if (href.startsWith("#")) {
    return `db4law://doc/${encodeURIComponent(currentId)}#${encodeURIComponent(href.slice(1))}`;
  }

  const [rawPath, rawAnchor] = href.split("#", 2);
  const decodedPath = safeDecodeURIComponent(rawPath).trim();
  const cleaned = decodedPath.replace(/\\/g, "/").replace(/\.md$/i, "");

  const resolvedId = resolveRelativeId(cleaned, currentId);
  if (!resolvedId) {
    return null;
  }

  const anchor = rawAnchor
    ? `#${encodeURIComponent(safeDecodeURIComponent(rawAnchor))}`
    : "";
  return `db4law://doc/${encodeURIComponent(resolvedId)}${anchor}`;
}

function resolveRelativeId(target: string, currentId: string): string | null {
  if (!target) {
    return currentId;
  }

  const baseDir = currentId.includes("/")
    ? currentId.slice(0, currentId.lastIndexOf("/"))
    : "";

  if (target.startsWith("laws/") || target === "laws_index") {
    return normalizePosixPath(target);
  }

  if (target.startsWith("/")) {
    return normalizePosixPath(target.replace(/^\/+/, ""));
  }

  return normalizePosixPath(`${baseDir}/${target}`);
}

function normalizePosixPath(input: string): string | null {
  const out: string[] = [];
  const parts = input.split("/");

  for (const part of parts) {
    if (!part || part === ".") {
      continue;
    }

    if (part === "..") {
      if (out.length === 0) {
        return null;
      }
      out.pop();
      continue;
    }

    out.push(part);
  }

  return out.join("/");
}

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

interface GraphViewProps {
  graph: GraphPayload;
  rootTitle: string;
  expanded: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
}

function GraphView(props: GraphViewProps): JSX.Element {
  const { graph, rootTitle, expanded, onClose, onSelect } = props;
  const width = expanded ? 1520 : 860;
  const height = expanded ? 920 : 360;
  const cx = width / 2;
  const cy = height / 2;

  const layout = useMemo(() => {
    const points = new Map<
      string,
      { x: number; y: number; depth: number; title: string }
    >();
    const byDepth = new Map<number, GraphNodePayload[]>();

    for (const node of graph.nodes) {
      const bucket = byDepth.get(node.depth) || [];
      bucket.push(node);
      byDepth.set(node.depth, bucket);
    }

    const maxDepth = Math.max(...graph.nodes.map((node) => node.depth), 1);
    const minDim = Math.min(width, height);
    const minRadius = Math.max(56, minDim * 0.16);
    const maxRadius = Math.max(minRadius + 48, minDim * 0.46);
    const radiusStep =
      maxDepth > 0 ? (maxRadius - minRadius) / Math.max(maxDepth, 1) : 0;

    for (const [depth, nodes] of byDepth.entries()) {
      nodes.sort((a, b) => a.title.localeCompare(b.title, "ja"));
      if (depth === 0) {
        const root = nodes[0];
        if (root) {
          points.set(root.id, {
            x: cx,
            y: cy,
            depth,
            title: root.title,
          });
        }
        continue;
      }

      const radius = minRadius + depth * radiusStep;
      for (let index = 0; index < nodes.length; index += 1) {
        const node = nodes[index];
        const angle =
          (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
        points.set(node.id, {
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
          depth,
          title: node.title,
        });
      }
    }

    return points;
  }, [cx, cy, graph.nodes, height, width]);

  return (
    <div className={`graph-shell ${expanded ? "expanded" : ""}`}>
      {expanded ? (
        <button
          type="button"
          className="graph-close"
          onClick={onClose}
          aria-label="Close graph view"
        >
          ×
        </button>
      ) : null}
      <svg className="graph-svg" viewBox={`0 0 ${width} ${height}`}>
        <g>
          {graph.edges.map((edge, index) => {
            const from = layout.get(edge.from);
            const to = layout.get(edge.to);
            if (!from || !to) {
              return null;
            }
            return (
              <line
                key={`${edge.from}-${edge.to}-${index}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={edge.kind === "incoming" ? "#4f6f8f" : "#0d7a5f"}
                strokeOpacity="0.45"
                strokeWidth="1.4"
              />
            );
          })}

          {graph.nodes.map((node) => {
            const point = layout.get(node.id);
            if (!point) {
              return null;
            }

            const fill =
              node.depth === 0
                ? "#0d5b7a"
                : node.depth === 1
                  ? "#4ab393"
                  : node.depth === 2
                    ? "#7d9fbf"
                    : "#bfa36f";

            return (
              <g key={node.id}>
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={node.depth === 0 ? 12 : 8}
                  fill={fill}
                  className="graph-node"
                  onClick={() => onSelect(node.id)}
                />
                <text
                  x={point.x + (point.x >= cx ? 11 : -11)}
                  y={point.y + 4}
                  textAnchor={point.x >= cx ? "start" : "end"}
                  className="graph-label"
                >
                  {truncateLabel(node.depth === 0 ? rootTitle : node.title, 18)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <p className="small muted">
        Depth adjustable graph. Click node to navigate. nodes:{" "}
        {graph.nodes.length.toLocaleString()} / edges:{" "}
        {graph.edges.length.toLocaleString()}
      </p>
    </div>
  );
}

function truncateLabel(value: string, maxLen: number): string {
  if (value.length <= maxLen) {
    return value;
  }
  return `${value.slice(0, maxLen - 1)}...`;
}
