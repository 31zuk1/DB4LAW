"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

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

const RECENT_STORAGE_KEY = "db4law-ui-recent";
const PAGE_SIZE = 120;

export function VaultBrowser(): JSX.Element {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [visibleLimit, setVisibleLimit] = useState(PAGE_SIZE);
  const [status, setStatus] = useState<VaultStatus | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [isLoadingSearch, setIsLoadingSearch] = useState(false);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<LinkTab>("outgoing");
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [knownTitles, setKnownTitles] = useState<Record<string, string>>({});
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
  const [candidatePopup, setCandidatePopup] = useState<{
    label: string;
    options: LinkCandidate[];
  } | null>(null);
  const [pendingAnchor, setPendingAnchor] = useState<string | null>(null);

  const pushRecent = useCallback((id: string) => {
    setRecentIds((previous) => {
      const next = [id, ...previous.filter((item) => item !== id)].slice(0, 20);
      localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const runSearch = useCallback(async function runSearchImpl(
    input: string,
    limit: number,
    retries = 2,
  ) {
    setSearchError(null);
    setIsLoadingSearch(true);

    try {
      const response = await fetch(
        `/api/search?q=${encodeURIComponent(input)}&limit=${limit}`,
      );
      const data = (await response.json()) as SearchResponse;

      if (!response.ok || data.error || !data.results) {
        throw new Error(data.error || "Search failed");
      }

      setResults(data.results);
      setTotalResults(
        typeof data.total === "number" ? data.total : data.results.length,
      );

      setKnownTitles((previous) => {
        const next = { ...previous };
        for (const result of data.results) {
          next[result.id] = result.title;
        }
        return next;
      });

      if (data.results.length > 0) {
        setSelectedId((previous) =>
          previous && data.results.some((result) => result.id === previous)
            ? previous
            : data.results[0].id,
        );
      }
    } catch (error) {
      setResults([]);
      setTotalResults(0);
      setSearchError(error instanceof Error ? error.message : "Search failed");

      if (retries > 0) {
        window.setTimeout(() => {
          void runSearchImpl(input, limit, retries - 1);
        }, 1200);
      }
    } finally {
      setIsLoadingSearch(false);
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

    try {
      const raw = localStorage.getItem(RECENT_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as string[];
        if (Array.isArray(parsed)) {
          setRecentIds(parsed.slice(0, 20));
        }
      }
    } catch {
      // ignore malformed storage
    }

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
        pushRecent(data.doc.id);
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
  }, [pushRecent, selectedId]);

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

  const recentItems = useMemo(
    () => recentIds.map((id) => ({ id, title: knownTitles[id] || id })),
    [knownTitles, recentIds],
  );

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

        setSelectedId(nextId);
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
    [doc?.id, preparedMarkdown],
  );

  const isIncomingLoading = !!doc && loadingIncomingFor === doc.id;
  const hasMoreResults = results.length < totalResults;

  return (
    <main className="app-shell">
      <section className="panel panel-left">
        <h1>DB4LAW Vault Reader</h1>
        <p className="panel-caption">Read-only Obsidian-compatible viewer</p>

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

        <div className="recent-block">
          <h2>Recent Opened</h2>
          {recentItems.length === 0 ? (
            <p className="small muted">No recent items.</p>
          ) : (
            <ul>
              {recentItems.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => setSelectedId(item.id)}>
                    {item.title}
                  </button>
                </li>
              ))}
            </ul>
          )}
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
                onClick={() => setSelectedId(result.id)}
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
              <FrontmatterPanel frontmatter={doc.frontmatter} />
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
                        onClick={() => setSelectedId(link.resolvedId!)}
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
                        onClick={() => setSelectedId(link.id)}
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
                </div>
                {graphLoading ? (
                  <p className="small muted">Loading graph...</p>
                ) : null}
                {graphError ? <p className="error-box">{graphError}</p> : null}
                {graphData ? (
                  <GraphView
                    graph={graphData}
                    rootTitle={doc.title}
                    onSelect={(id) => setSelectedId(id)}
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
                      setSelectedId(candidate.id);
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
}): JSX.Element {
  const { frontmatter } = props;
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
            {renderFrontmatterValue(key, value)}
          </div>
        </div>
      ))}
    </div>
  );
}

function renderFrontmatterValue(key: string, value: unknown): JSX.Element {
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
          <div key={`${key}-${index}`}>{renderFrontmatterValue(key, item)}</div>
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
            {renderFrontmatterValue(nestedKey, nestedValue)}
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
  onSelect: (id: string) => void;
}

function GraphView(props: GraphViewProps): JSX.Element {
  const { graph, rootTitle, onSelect } = props;
  const width = 860;
  const height = 360;
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

      const radius = 56 + depth * 66;
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
  }, [cx, cy, graph.nodes]);

  return (
    <div className="graph-shell">
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
