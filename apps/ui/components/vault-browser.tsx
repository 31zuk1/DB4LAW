"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";

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

interface GlobalGraphResponse {
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
type GraphLayoutMode = "cloud" | "mindmap";
type SearchSortMode = "relevance" | "title_asc" | "title_desc";

interface SideOutgoingLinkItem {
  key: string;
  label: string;
  subtitle: string;
  targetId: string | null;
  targetTitle: string | null;
  candidates: LinkCandidate[];
}

const PAGE_SIZE = 120;
const LAW_INDEX_CANDIDATES = ["laws_index", "law_index", "law-index"];

export function VaultBrowser(): JSX.Element {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [visibleLimit, setVisibleLimit] = useState(PAGE_SIZE);
  const [searchSortMode, setSearchSortMode] =
    useState<SearchSortMode>("relevance");
  const [searchSortOpen, setSearchSortOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [linkSortMode, setLinkSortMode] = useState<SearchSortMode>("relevance");
  const [viewerSplitRatio, setViewerSplitRatio] = useState(0.76);
  const [isViewerSplitResizing, setIsViewerSplitResizing] = useState(false);
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
  const [graphMode, setGraphMode] = useState<GraphLayoutMode>("mindmap");
  const [graphData, setGraphData] = useState<GraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [graphExpanded, setGraphExpanded] = useState(false);
  const [globalGraphOpen, setGlobalGraphOpen] = useState(false);
  const [globalGraphNodeLimit, setGlobalGraphNodeLimit] = useState(360);
  const [globalGraphData, setGlobalGraphData] = useState<GraphPayload | null>(
    null,
  );
  const [globalGraphLoading, setGlobalGraphLoading] = useState(false);
  const [globalGraphError, setGlobalGraphError] = useState<string | null>(null);
  const [globalGraphExpanded, setGlobalGraphExpanded] = useState(false);
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
  const searchSortPanelRef = useRef<HTMLDivElement | null>(null);
  const commandSearchInputRef = useRef<HTMLInputElement | null>(null);
  const viewerSplitRef = useRef<HTMLDivElement | null>(null);
  const viewerSplitDragRef = useRef<{
    startX: number;
    startRatio: number;
    containerWidth: number;
  } | null>(null);

  const openDocument = useCallback((id: string) => {
    setGlobalGraphOpen(false);
    setGlobalGraphExpanded(false);
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

  const closeCommandPalette = useCallback(() => {
    setCommandPaletteOpen(false);
    setSearchSortOpen(false);
  }, []);

  const openCommandPalette = useCallback(() => {
    setCommandPaletteOpen(true);
  }, []);

  const beginViewerSplitResize = useCallback(
    (clientX: number) => {
      if (!viewerSplitRef.current) {
        return;
      }

      const rect = viewerSplitRef.current.getBoundingClientRect();
      if (rect.width < 80) {
        return;
      }

      viewerSplitDragRef.current = {
        startX: clientX,
        startRatio: viewerSplitRatio,
        containerWidth: rect.width,
      };
      setIsViewerSplitResizing(true);
    },
    [viewerSplitRatio],
  );

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
    if (!searchSortOpen) {
      return;
    }

    const onPointerDown = (event: PointerEvent) => {
      if (!searchSortPanelRef.current) {
        return;
      }
      const target = event.target;
      if (target instanceof Node && !searchSortPanelRef.current.contains(target)) {
        setSearchSortOpen(false);
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSearchSortOpen(false);
      }
    };

    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [searchSortOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if ((event.metaKey || event.ctrlKey) && key === "k") {
        event.preventDefault();
        setCommandPaletteOpen(true);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!commandPaletteOpen) {
      return;
    }

    const timer = window.setTimeout(() => {
      commandSearchInputRef.current?.focus();
      commandSearchInputRef.current?.select();
    }, 12);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeCommandPalette();
      }
    };

    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [closeCommandPalette, commandPaletteOpen]);

  useEffect(() => {
    if (!isViewerSplitResizing) {
      return;
    }

    const onPointerMove = (event: PointerEvent) => {
      const drag = viewerSplitDragRef.current;
      if (!drag) {
        return;
      }

      const deltaRatio = (event.clientX - drag.startX) / drag.containerWidth;
      setViewerSplitRatio(clampNumber(drag.startRatio + deltaRatio, 0.45, 0.88));
    };

    const stopDragging = () => {
      setIsViewerSplitResizing(false);
      viewerSplitDragRef.current = null;
      document.body.classList.remove("viewer-split-resizing");
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopDragging);
    document.body.classList.add("viewer-split-resizing");

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopDragging);
      document.body.classList.remove("viewer-split-resizing");
    };
  }, [isViewerSplitResizing]);

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
  }, [doc, incomingByDocId, loadingIncomingFor]);

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
    if (!globalGraphOpen) {
      setGlobalGraphExpanded(false);
    }
  }, [globalGraphOpen]);

  useEffect(() => {
    if (!graphExpanded && !globalGraphExpanded) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setGraphExpanded(false);
        setGlobalGraphExpanded(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [globalGraphExpanded, graphExpanded]);

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
    return (incomingByDocId[doc.id] || []).filter(
      (link) => !isSearchHiddenId(link.id),
    );
  }, [doc, incomingByDocId]);

  const sortedOutgoingLinks = useMemo(() => {
    if (!doc) {
      return [] as SideOutgoingLinkItem[];
    }

    const items = doc.outgoing.map((link, index) => ({
      key: `${link.raw}-${index}`,
      label: link.display,
      subtitle: link.resolvedId || link.target || link.raw,
      targetId: link.resolvedId || null,
      targetTitle: link.resolvedTitle || null,
      candidates: link.candidates || [],
    }));

    return sortGenericItems(
      items,
      linkSortMode,
      query,
      (item) => item.targetTitle || item.label,
      (item) => `${item.label} ${item.subtitle} ${item.targetTitle || ""}`.trim(),
    );
  }, [doc, linkSortMode, query]);

  const sortedIncomingLinks = useMemo(() => {
    const items = incomingLinks.map((link) => ({
      ...link,
      subtitle: link.relPath || link.id,
    }));

    return sortGenericItems(
      items,
      linkSortMode,
      query,
      (item) => item.title,
      (item) => `${item.title} ${item.id} ${item.subtitle}`.trim(),
    );
  }, [incomingLinks, linkSortMode, query]);

  const viewerSplitStyle = useMemo(
    () =>
      ({
        "--viewer-main-width": `${(viewerSplitRatio * 100).toFixed(1)}%`,
      }) as CSSProperties,
    [viewerSplitRatio],
  );

  const sortedResults = useMemo(
    () => sortSearchResults(results, query, searchSortMode),
    [query, results, searchSortMode],
  );

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

  const loadGlobalGraph = useCallback(
    async (nodeLimit: number) => {
      setGlobalGraphLoading(true);
      setGlobalGraphError(null);

      try {
        const response = await fetch(
          `/api/graph/global?node_limit=${Math.min(
            Math.max(nodeLimit, 120),
            900,
          )}`,
        );
        const data = (await response.json()) as GlobalGraphResponse;

        if (!response.ok || data.error || !data.graph) {
          throw new Error(data.error || "Failed to load global graph");
        }

        setGlobalGraphData(data.graph);
      } catch (error) {
        setGlobalGraphData(null);
        setGlobalGraphError(
          error instanceof Error
            ? error.message
            : "Failed to load global graph",
        );
      } finally {
        setGlobalGraphLoading(false);
      }
    },
    [setGlobalGraphData],
  );

  const openGlobalGraph = useCallback(() => {
    setGlobalGraphOpen(true);
    if (!globalGraphData && !globalGraphLoading) {
      void loadGlobalGraph(globalGraphNodeLimit);
    }
  }, [
    globalGraphData,
    globalGraphLoading,
    globalGraphNodeLimit,
    loadGlobalGraph,
  ]);

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
  const hasMoreResults = sortedResults.length < totalResults;

  return (
    <main className="app-shell">
      <section className="panel panel-left" aria-label="Sidebar tools">
        <div className="rail-group">
          <button
            type="button"
            className={`rail-btn ${commandPaletteOpen ? "active" : ""}`}
            title="検索 (Cmd/Ctrl+K)"
            onClick={openCommandPalette}
          >
            <IconSearchFile />
          </button>
          <button
            type="button"
            className={`rail-btn ${globalGraphOpen ? "active" : ""}`}
            title={
              globalGraphOpen ? "グローバルグラフを閉じる" : "グローバルグラフを開く"
            }
            onClick={() => {
              if (globalGraphOpen) {
                setGlobalGraphOpen(false);
                setGlobalGraphExpanded(false);
                return;
              }
              openGlobalGraph();
            }}
            disabled={globalGraphLoading && !globalGraphOpen}
          >
            <IconGraphNodes />
          </button>
          <button
            type="button"
            className="rail-btn"
            title={
              lawIndexLoading
                ? "laws.index を読み込み中..."
                : "laws.index を表示"
            }
            onClick={() => void openLawIndex()}
            disabled={lawIndexLoading}
          >
            <IconListDoc />
          </button>
        </div>

        <div className="rail-divider" />

        <div className="rail-group">
          <button
            type="button"
            className={`rail-btn ${activeTab === "outgoing" ? "active" : ""}`}
            title="Outgoing"
            onClick={() => setActiveTab("outgoing")}
            disabled={!doc}
          >
            <IconArrowOut />
          </button>
          <button
            type="button"
            className={`rail-btn ${activeTab === "incoming" ? "active" : ""}`}
            title="Incoming"
            onClick={() => setActiveTab("incoming")}
            disabled={!doc}
          >
            <IconArrowIn />
          </button>
          <button
            type="button"
            className={`rail-btn ${activeTab === "graph" ? "active" : ""}`}
            title="Doc Graph"
            onClick={() => setActiveTab("graph")}
            disabled={!doc}
          >
            <IconNodeView />
          </button>
        </div>

        <div className="rail-spacer" />

        <div className="rail-group">
          <button
            type="button"
            className={`rail-btn ${searchSortOpen ? "active" : ""}`}
            title="検索結果の並び順を調整"
            onClick={() => {
              setCommandPaletteOpen(true);
              setSearchSortOpen((current) => !current);
            }}
          >
            <IconTune />
          </button>
        </div>
      </section>

      <section className="panel panel-right">
        <div className="viewer-meta">
          <span className="viewer-meta-item">
            Documents:{" "}
            {status?.totalDocs != null
              ? status.totalDocs.toLocaleString()
              : "indexing..."}
          </span>
          <span className="viewer-meta-item">
            {status?.indexing ? "Indexing in background" : "Index ready"}
          </span>
          <span
            className="viewer-meta-item mono"
            title={status?.vaultPath || "loading"}
          >
            {status?.vaultPath || "loading"}
          </span>
        </div>

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

        {globalGraphOpen ? (
          <>
            <header className="global-graph-header">
              <h2>Global Graph View</h2>
              <div className="global-graph-actions">
                <button
                  type="button"
                  className="graph-expand"
                  onClick={() => setGlobalGraphOpen(false)}
                >
                  Close
                </button>
              </div>
            </header>

            <div className="graph-toolbar">
              <div
                className="graph-mode-switch"
                role="tablist"
                aria-label="Global graph mode"
              >
                <button
                  type="button"
                  className={graphMode === "cloud" ? "active" : ""}
                  onClick={() => setGraphMode("cloud")}
                >
                  Node Cloud
                </button>
                <button
                  type="button"
                  className={graphMode === "mindmap" ? "active" : ""}
                  onClick={() => setGraphMode("mindmap")}
                >
                  Mindmap
                </button>
              </div>
              <label htmlFor="global-graph-limit">Nodes</label>
              <select
                id="global-graph-limit"
                value={globalGraphNodeLimit}
                onChange={(event) =>
                  setGlobalGraphNodeLimit(Number(event.target.value))
                }
              >
                <option value={180}>180</option>
                <option value={260}>260</option>
                <option value={360}>360</option>
                <option value={520}>520</option>
              </select>
              <button
                type="button"
                className="graph-expand"
                onClick={() => void loadGlobalGraph(globalGraphNodeLimit)}
              >
                Reload
              </button>
              <button
                type="button"
                className={
                  globalGraphExpanded ? "graph-expand active" : "graph-expand"
                }
                onClick={() => setGlobalGraphExpanded((current) => !current)}
              >
                {globalGraphExpanded ? "Shrink" : "Expand"}
              </button>
            </div>

            {globalGraphLoading ? (
              <p className="small muted">Loading global graph...</p>
            ) : null}
            {globalGraphError ? (
              <p className="error-box">{globalGraphError}</p>
            ) : null}
            {globalGraphData ? (
              <GraphView
                graph={globalGraphData}
                rootTitle="Global Vault"
                mode={graphMode}
                expanded={globalGraphExpanded}
                onClose={() => setGlobalGraphExpanded(false)}
                onSelect={(id) => {
                  if (isVirtualGlobalGraphNodeId(id)) {
                    return;
                  }
                  openDocument(id);
                }}
              />
            ) : null}
          </>
        ) : (
          <>
            <div className="viewer-toolbar">
              <div className="viewer-tools">
                <button
                  type="button"
                  className={`viewer-tool-btn ${activeTab === "graph" ? "" : "active"}`}
                  onClick={() =>
                    setActiveTab((current) =>
                      current === "graph" ? "outgoing" : current,
                    )
                  }
                  title="リンクパネル"
                  disabled={!doc}
                >
                  <IconLinksPanel />
                </button>
                <button
                  type="button"
                  className={`viewer-tool-btn ${activeTab === "graph" ? "active" : ""}`}
                  onClick={() => setActiveTab("graph")}
                  title="ローカルグラフ"
                  disabled={!doc}
                >
                  <IconLocalGraph />
                </button>
              </div>
              <span className="small muted">
                {doc
                  ? `Right panel: ${activeTab === "graph" ? "Local graph" : "Linked mentions"}`
                  : "ドキュメントを開くと、右側にリンクとローカルグラフを表示します。"}
              </span>
            </div>

            {isLoadingDoc ? <p>Loading preview...</p> : null}
            {docError ? <p className="error-box">{docError}</p> : null}

            {!isLoadingDoc && !doc && !docError ? (
              <p>Select a document.</p>
            ) : null}

            {doc ? (
              <div
                ref={viewerSplitRef}
                className={`viewer-split ${isViewerSplitResizing ? "resizing" : ""}`}
                style={viewerSplitStyle}
              >
                <div className="viewer-main-pane">
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
                </div>

                <div
                  className="viewer-splitter"
                  role="separator"
                  aria-orientation="vertical"
                  aria-label="Resize right panel"
                  onPointerDown={(event) => {
                    event.preventDefault();
                    beginViewerSplitResize(event.clientX);
                  }}
                />

                <aside className="viewer-side-pane">
                  {activeTab === "graph" ? (
                    <>
                      <header className="side-panel-header">
                        <h3>Local Graph</h3>
                        <button
                          type="button"
                          className="viewer-tool-btn"
                          onClick={() => setActiveTab("outgoing")}
                          title="リンクパネルへ戻る"
                        >
                          <IconLinksPanel />
                        </button>
                      </header>
                      <div className="graph-toolbar side-graph-toolbar">
                        <div
                          className="graph-mode-switch"
                          role="tablist"
                          aria-label="Graph mode"
                        >
                          <button
                            type="button"
                            className={graphMode === "cloud" ? "active" : ""}
                            onClick={() => setGraphMode("cloud")}
                          >
                            Node
                          </button>
                          <button
                            type="button"
                            className={graphMode === "mindmap" ? "active" : ""}
                            onClick={() => setGraphMode("mindmap")}
                          >
                            Mind
                          </button>
                        </div>
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
                          mode={graphMode}
                          expanded={graphExpanded}
                          onClose={() => setGraphExpanded(false)}
                          onSelect={(id) => openDocument(id)}
                        />
                      ) : (
                        !graphLoading && (
                          <p className="small muted">No graph data.</p>
                        )
                      )}
                    </>
                  ) : (
                    <>
                      <header className="side-panel-header">
                        <h3>Linked Mentions</h3>
                        <div className="side-panel-controls">
                          <label htmlFor="link-sort-mode">Sort</label>
                          <select
                            id="link-sort-mode"
                            value={linkSortMode}
                            onChange={(event) =>
                              setLinkSortMode(event.target.value as SearchSortMode)
                            }
                          >
                            <option value="relevance">関連度順</option>
                            <option value="title_asc">名前順 (昇順)</option>
                            <option value="title_desc">名前順 (降順)</option>
                          </select>
                        </div>
                      </header>

                      {isIncomingLoading ? (
                        <p className="small muted">Loading incoming...</p>
                      ) : null}
                      {incomingError ? <p className="error-box">{incomingError}</p> : null}

                      <section
                        className={`side-link-group ${activeTab === "outgoing" ? "active" : ""}`}
                      >
                        <button
                          type="button"
                          className="side-link-heading"
                          onClick={() => setActiveTab("outgoing")}
                        >
                          Outgoing ({sortedOutgoingLinks.length})
                        </button>
                        <ul className="side-link-list">
                          {sortedOutgoingLinks.map((item) => (
                            <li key={item.key} className="side-link-item">
                              {item.targetId ? (
                                <button
                                  type="button"
                                  onClick={() => openDocument(item.targetId!)}
                                >
                                  {item.label} →{" "}
                                  {item.targetTitle || pathLikeTitle(item.targetId)}
                                </button>
                              ) : item.candidates.length > 0 ? (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setCandidatePopup({
                                      label: item.label,
                                      options: item.candidates,
                                    })
                                  }
                                >
                                  {item.label} (ambiguous: {item.candidates.length})
                                </button>
                              ) : (
                                <span className="side-link-unresolved">
                                  {item.label} (unresolved)
                                </span>
                              )}
                              <span className="mono small side-link-meta">
                                {item.subtitle}
                              </span>
                            </li>
                          ))}
                          {sortedOutgoingLinks.length === 0 ? (
                            <li className="small muted side-link-empty">
                              No outgoing links detected.
                            </li>
                          ) : null}
                        </ul>
                      </section>

                      <section
                        className={`side-link-group ${activeTab === "incoming" ? "active" : ""}`}
                      >
                        <button
                          type="button"
                          className="side-link-heading"
                          onClick={() => setActiveTab("incoming")}
                        >
                          Incoming ({sortedIncomingLinks.length})
                        </button>
                        <ul className="side-link-list">
                          {sortedIncomingLinks.map((link) => (
                            <li key={link.id} className="side-link-item">
                              <button
                                type="button"
                                onClick={() => openDocument(link.id)}
                              >
                                {link.title}
                              </button>
                              <span className="mono small side-link-meta">
                                {link.subtitle}
                              </span>
                            </li>
                          ))}
                          {!isIncomingLoading && sortedIncomingLinks.length === 0 ? (
                            <li className="small muted side-link-empty">
                              No incoming links detected.
                            </li>
                          ) : null}
                        </ul>
                      </section>
                    </>
                  )}
                </aside>
              </div>
            ) : null}
          </>
        )}
      </section>

      {commandPaletteOpen ? (
        <div className="command-overlay" onClick={closeCommandPalette}>
          <div
            className="command-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="command-input-wrap" ref={searchSortPanelRef}>
              <input
                ref={commandSearchInputRef}
                id="command-search-box"
                className="command-input"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setVisibleLimit(PAGE_SIZE);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && sortedResults[0]) {
                    openDocument(sortedResults[0].id);
                    setActiveTab("outgoing");
                    closeCommandPalette();
                  }
                }}
                placeholder="ファイル名 / law_id / article_id / キーワード"
                autoComplete="off"
                spellCheck={false}
              />
              <button
                type="button"
                className={`command-adjust-btn ${searchSortOpen ? "active" : ""}`}
                onClick={() => setSearchSortOpen((current) => !current)}
              >
                調整
              </button>
              <button
                type="button"
                className="command-close-btn"
                onClick={closeCommandPalette}
                aria-label="Close search"
              >
                ×
              </button>
              {searchSortOpen ? (
                <div className="search-adjust-panel command-adjust-panel">
                  <div className="search-adjust-title">検索結果の並び順</div>
                  <label className="search-adjust-option">
                    <input
                      type="radio"
                      name="search-sort"
                      checked={searchSortMode === "relevance"}
                      onChange={() => setSearchSortMode("relevance")}
                    />
                    関連度順 (一致回数が多い順)
                  </label>
                  <label className="search-adjust-option">
                    <input
                      type="radio"
                      name="search-sort"
                      checked={searchSortMode === "title_asc"}
                      onChange={() => setSearchSortMode("title_asc")}
                    />
                    名前順 (昇順)
                  </label>
                  <label className="search-adjust-option">
                    <input
                      type="radio"
                      name="search-sort"
                      checked={searchSortMode === "title_desc"}
                      onChange={() => setSearchSortMode("title_desc")}
                    />
                    名前順 (降順)
                  </label>
                </div>
              ) : null}
            </div>

            <div className="command-meta">
              <span>
                {isLoadingSearch
                  ? "Searching..."
                  : `${sortedResults.length.toLocaleString()} shown / ${totalResults.toLocaleString()} total`}
              </span>
              <span>Enterで先頭項目を開く / Escで閉じる</span>
            </div>

            {searchError ? <p className="error-box">{searchError}</p> : null}
            <ul className="command-list">
              {sortedResults.map((result) => (
                <li key={result.id}>
                  <button
                    type="button"
                    className={`command-item ${selectedId === result.id ? "active" : ""}`}
                    onClick={() => {
                      openDocument(result.id);
                      setActiveTab("outgoing");
                      closeCommandPalette();
                    }}
                  >
                    <span className="command-item-title">{result.title}</span>
                    <span className="command-item-path mono">
                      {result.relPath || `${result.id}.md`}
                    </span>
                    <span className="command-item-meta small muted">
                      {renderFrontmatterHint(result.frontmatter) || result.id}
                    </span>
                  </button>
                </li>
              ))}
              {!isLoadingSearch && sortedResults.length === 0 ? (
                <li className="small muted command-empty">No results.</li>
              ) : null}
            </ul>

            {hasMoreResults ? (
              <button
                type="button"
                className="load-more command-load-more"
                onClick={() =>
                  setVisibleLimit((previous) => previous + PAGE_SIZE)
                }
              >
                さらに読み込む
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

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

function isVirtualGlobalGraphNodeId(id: string): boolean {
  const normalized = id.trim();
  return normalized.startsWith("__global__/");
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

function sortGenericItems<T>(
  items: T[],
  sortMode: SearchSortMode,
  query: string,
  getTitle: (item: T) => string,
  getSearchBlob: (item: T) => string,
): T[] {
  const out = [...items];
  const normalizedQuery = query.trim().toLowerCase();

  if (sortMode === "title_asc" || sortMode === "title_desc") {
    const direction = sortMode === "title_asc" ? 1 : -1;
    out.sort(
      (a, b) => getTitle(a).localeCompare(getTitle(b), "ja") * direction,
    );
    return out;
  }

  out.sort((a, b) => {
    const scoreA = normalizedQuery
      ? countOccurrences(getSearchBlob(a).toLowerCase(), normalizedQuery)
      : 0;
    const scoreB = normalizedQuery
      ? countOccurrences(getSearchBlob(b).toLowerCase(), normalizedQuery)
      : 0;

    if (scoreA !== scoreB) {
      return scoreB - scoreA;
    }
    return getTitle(a).localeCompare(getTitle(b), "ja");
  });

  return out;
}

function IconSearchFile(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
      <path d="M14 3v5h5" />
      <circle cx="11" cy="13" r="3.1" />
      <path d="m13.6 15.6 2.2 2.2" />
    </svg>
  );
}

function IconGraphNodes(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="6" cy="6" r="2.2" />
      <circle cx="18" cy="6" r="2.2" />
      <circle cx="12" cy="18" r="2.2" />
      <path d="M8 7.2l2.5 7.2M16 7.2l-2.5 7.2M8.2 6h7.6" />
    </svg>
  );
}

function IconListDoc(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
      <path d="M14 3v5h5M8 12h8M8 16h8M8 8h3" />
    </svg>
  );
}

function IconArrowOut(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 16h8M13 11l5 5-5 5" />
    </svg>
  );
}

function IconArrowIn(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M16 8H8M11 13l-5-5 5-5" />
    </svg>
  );
}

function IconNodeView(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="4" y="4" width="6" height="6" rx="1.2" />
      <rect x="14" y="4" width="6" height="6" rx="1.2" />
      <rect x="4" y="14" width="6" height="6" rx="1.2" />
      <rect x="14" y="14" width="6" height="6" rx="1.2" />
      <path d="M10 7h4M7 10v4M17 10v4M10 17h4" />
    </svg>
  );
}

function IconTune(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h8M14 7h6M9 7v10M4 17h5M11 17h9M15 7v10" />
      <circle cx="9" cy="7" r="1.8" />
      <circle cx="15" cy="17" r="1.8" />
    </svg>
  );
}

function IconLinksPanel(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M10 13.8 13.7 10.2" />
      <path d="M8.2 16a3.5 3.5 0 0 1 0-5l2-2a3.5 3.5 0 1 1 5 5l-.7.7" />
      <path d="M15.8 8a3.5 3.5 0 0 1 0 5l-2 2a3.5 3.5 0 1 1-5-5l.7-.7" />
    </svg>
  );
}

function IconLocalGraph(): JSX.Element {
  return (
    <svg className="rail-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="6" cy="7" r="2" />
      <circle cx="17.5" cy="5.5" r="2" />
      <circle cx="12" cy="18" r="2.2" />
      <path d="M8 7.3 15.4 5.8M7.2 8.7l3.7 7.2M16.8 7l-3.6 8" />
    </svg>
  );
}

function sortSearchResults(
  results: SearchResult[],
  query: string,
  sortMode: SearchSortMode,
): SearchResult[] {
  const sorted = [...results];

  if (sortMode === "title_asc" || sortMode === "title_desc") {
    const direction = sortMode === "title_asc" ? 1 : -1;
    sorted.sort((a, b) => {
      const titleCompare = a.title.localeCompare(b.title, "ja");
      if (titleCompare !== 0) {
        return titleCompare * direction;
      }
      return a.id.localeCompare(b.id, "ja") * direction;
    });
    return sorted;
  }

  const scoreById = new Map<string, number>();
  for (const result of sorted) {
    scoreById.set(result.id, searchRelevanceScore(result, query));
  }

  sorted.sort((a, b) => {
    const scoreDiff = (scoreById.get(b.id) || 0) - (scoreById.get(a.id) || 0);
    if (scoreDiff !== 0) {
      return scoreDiff;
    }
    const titleCompare = a.title.localeCompare(b.title, "ja");
    if (titleCompare !== 0) {
      return titleCompare;
    }
    return a.id.localeCompare(b.id, "ja");
  });

  return sorted;
}

function searchRelevanceScore(result: SearchResult, query: string): number {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return 0;
  }

  const text = [
    result.title,
    result.id,
    result.relPath,
    flattenFrontmatterValue(result.frontmatter),
  ]
    .join(" ")
    .toLowerCase();

  return countOccurrences(text, normalizedQuery);
}

function flattenFrontmatterValue(value: unknown): string {
  if (value == null) {
    return "";
  }

  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value.map((item) => flattenFrontmatterValue(item)).join(" ");
  }

  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nestedValue]) =>
        `${key} ${flattenFrontmatterValue(nestedValue)}`.trim(),
      )
      .join(" ");
  }

  return "";
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) {
    return 0;
  }

  let index = 0;
  let count = 0;
  while (index < haystack.length) {
    const hit = haystack.indexOf(needle, index);
    if (hit < 0) {
      break;
    }
    count += 1;
    index = hit + needle.length;
  }
  return count;
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
  mode: GraphLayoutMode;
  expanded: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
}

interface GraphPoint {
  id: string;
  x: number;
  y: number;
  depth: number;
  title: string;
}

interface GraphLayoutResult {
  points: Map<string, GraphPoint>;
  treeEdgeKeys: Set<string>;
  maxDepth: number;
}

function GraphView(props: GraphViewProps): JSX.Element {
  const { graph, rootTitle, mode, expanded, onClose, onSelect } = props;
  const width = expanded ? 1520 : 860;
  const height = expanded ? 920 : 360;

  const layout = useMemo(() => {
    if (mode === "mindmap") {
      return buildMindmapLayout(graph, width, height);
    }
    return buildCloudLayout(graph, width, height);
  }, [graph, height, mode, width]);
  const labelMaxLen = mode === "mindmap" ? 26 : 18;
  const layerCount = Math.max(layout.maxDepth + 1, 1);

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
          {Array.from({ length: layerCount }).map((_, depth) => {
            if (mode === "mindmap") {
              const x = graphLayerX(depth, layout.maxDepth, width, 34);
              return (
                <g key={`guide-col-${depth}`}>
                  <line
                    x1={x}
                    y1={10}
                    x2={x}
                    y2={height - 10}
                    className="graph-layer-line"
                  />
                  <text x={x + 4} y={20} className="graph-layer-label">
                    L{depth}
                  </text>
                </g>
              );
            }

            const y = graphLayerY(depth, layout.maxDepth, height, 24);
            return (
              <g key={`guide-row-${depth}`}>
                <line
                  x1={10}
                  y1={y}
                  x2={width - 10}
                  y2={y}
                  className="graph-layer-line"
                />
                <text x={12} y={y - 4} className="graph-layer-label">
                  L{depth}
                </text>
              </g>
            );
          })}
        </g>
        <g>
          {graph.edges.map((edge, index) => {
            const from = layout.points.get(edge.from);
            const to = layout.points.get(edge.to);
            if (!from || !to) {
              return null;
            }

            const edgeKey = toUndirectedEdgeKey(edge.from, edge.to);
            const isTreeEdge =
              mode === "mindmap" ? layout.treeEdgeKeys.has(edgeKey) : true;

            const stroke = edge.kind === "incoming" ? "#4f6f8f" : "#0d7a5f";
            const strokeOpacity =
              mode === "mindmap" ? (isTreeEdge ? "0.58" : "0.23") : "0.42";
            const strokeWidth =
              mode === "mindmap" ? (isTreeEdge ? "1.7" : "1.1") : "1.35";
            const dashArray =
              mode === "mindmap" && !isTreeEdge ? "3 3" : undefined;

            if (mode === "mindmap") {
              return (
                <path
                  key={`${edge.from}-${edge.to}-${index}`}
                  d={buildCurvePath(from, to)}
                  fill="none"
                  stroke={stroke}
                  strokeOpacity={strokeOpacity}
                  strokeWidth={strokeWidth}
                  strokeDasharray={dashArray}
                />
              );
            }

            return (
              <line
                key={`${edge.from}-${edge.to}-${index}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={stroke}
                strokeOpacity={strokeOpacity}
                strokeWidth={strokeWidth}
              />
            );
          })}

          {graph.nodes.map((node) => {
            const point = layout.points.get(node.id);
            if (!point) {
              return null;
            }

            const isRoot = node.id === graph.rootId;
            const fill = graphNodeColor(node.depth);
            const radius = isRoot ? 7 : 6;
            const labelRight = point.x < width - 120;
            const label =
              node.title || (isRoot ? rootTitle : pathLikeTitle(node.id));

            return (
              <g key={node.id}>
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={radius}
                  fill={fill}
                  className="graph-node"
                  stroke={isRoot ? "#102233" : "#f8fbff"}
                  strokeWidth={isRoot ? "2.2" : "1.2"}
                  onClick={() => onSelect(node.id)}
                />
                <text
                  x={point.x + (labelRight ? radius + 4 : -(radius + 4))}
                  y={point.y + 4}
                  textAnchor={labelRight ? "start" : "end"}
                  className="graph-label"
                >
                  {truncateLabel(label, labelMaxLen)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <p className="small muted">
        {mode === "mindmap" ? "Mindmap layer view" : "Node cloud layer view"}.
        Click node to navigate. nodes: {graph.nodes.length.toLocaleString()} /
        edges: {graph.edges.length.toLocaleString()}
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

function graphNodeColor(depth: number): string {
  if (depth <= 0) {
    return "#0d5b7a";
  }
  if (depth === 1) {
    return "#44ad8e";
  }
  if (depth === 2) {
    return "#7b9cba";
  }
  return "#b79662";
}

function buildCloudLayout(
  graph: GraphPayload,
  width: number,
  height: number,
): GraphLayoutResult {
  interface SimNode extends GraphNodePayload {
    x: number;
    y: number;
    vx: number;
    vy: number;
  }

  const maxDepth = Math.max(...graph.nodes.map((node) => node.depth), 0);
  const padding = 24;
  const usableWidth = Math.max(10, width - padding * 2);
  const usableHeight = Math.max(10, height - padding * 2);
  const layerCount = Math.max(maxDepth + 1, 1);
  const layerHeight = usableHeight / layerCount;

  const simNodes: SimNode[] = [...graph.nodes]
    .sort((a, b) => a.id.localeCompare(b.id, "ja"))
    .map((node) => {
      const seedX = seededUnit(node.id, 17);
      const seedY = seededUnit(node.id, 43);
      const baseY = graphLayerY(node.depth, maxDepth, height, padding);

      return {
        ...node,
        x: clampNumber(padding + seedX * usableWidth, padding, width - padding),
        y: clampNumber(
          baseY + (seedY - 0.5) * layerHeight * 0.7,
          padding,
          height - padding,
        ),
        vx: 0,
        vy: 0,
      };
    });

  const nodeById = new Map(simNodes.map((node) => [node.id, node]));
  const edges: Array<{ from: SimNode; to: SimNode }> = [];
  for (const edge of graph.edges) {
    const from = nodeById.get(edge.from);
    const to = nodeById.get(edge.to);
    if (!from || !to || from.id === to.id) {
      continue;
    }
    edges.push({ from, to });
  }

  const iterations = Math.min(120, 40 + simNodes.length);
  for (let iter = 0; iter < iterations; iter += 1) {
    for (let i = 0; i < simNodes.length; i += 1) {
      const a = simNodes[i];
      for (let j = i + 1; j < simNodes.length; j += 1) {
        const b = simNodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distSq = dx * dx + dy * dy + 0.01;
        const dist = Math.sqrt(distSq);
        const force = 2200 / distSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }

    for (const edge of edges) {
      const dx = edge.to.x - edge.from.x;
      const dy = edge.to.y - edge.from.y;
      const dist = Math.sqrt(dx * dx + dy * dy) + 0.001;
      const target = 58 + Math.abs(edge.to.depth - edge.from.depth) * 16;
      const spring = (dist - target) * 0.016;
      const fx = (dx / dist) * spring;
      const fy = (dy / dist) * spring;
      edge.from.vx += fx;
      edge.from.vy += fy;
      edge.to.vx -= fx;
      edge.to.vy -= fy;
    }

    for (const node of simNodes) {
      const targetY = graphLayerY(node.depth, maxDepth, height, padding);
      node.vy += (targetY - node.y) * 0.035;
      node.vx += (width / 2 - node.x) * 0.0018;

      node.vx *= 0.86;
      node.vy *= 0.86;

      node.x = clampNumber(node.x + node.vx, padding, width - padding);
      node.y = clampNumber(node.y + node.vy, padding, height - padding);
    }
  }

  const points = new Map<string, GraphPoint>();
  for (const node of simNodes) {
    points.set(node.id, {
      id: node.id,
      x: node.x,
      y: node.y,
      depth: node.depth,
      title: node.title,
    });
  }

  return {
    points,
    treeEdgeKeys: new Set<string>(),
    maxDepth,
  };
}

function buildMindmapLayout(
  graph: GraphPayload,
  width: number,
  height: number,
): GraphLayoutResult {
  const nodes = [...graph.nodes].sort((a, b) => compareGraphNodeMeta(a, b));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const maxDepth = Math.max(...nodes.map((node) => node.depth), 0);
  const adjacency = new Map<string, Set<string>>();
  const preferred = new Map<string, Set<string>>();
  const children = new Map<string, string[]>();

  for (const node of nodes) {
    adjacency.set(node.id, new Set<string>());
    preferred.set(node.id, new Set<string>());
    children.set(node.id, []);
  }

  for (const edge of graph.edges) {
    if (!nodeById.has(edge.from) || !nodeById.has(edge.to)) {
      continue;
    }

    adjacency.get(edge.from)?.add(edge.to);
    adjacency.get(edge.to)?.add(edge.from);

    const fromNode = nodeById.get(edge.from)!;
    const toNode = nodeById.get(edge.to)!;
    let parentId = edge.from;
    let childId = edge.to;

    if (fromNode.depth > toNode.depth) {
      parentId = edge.to;
      childId = edge.from;
    } else if (fromNode.depth === toNode.depth && edge.kind === "incoming") {
      parentId = edge.to;
      childId = edge.from;
    }

    preferred.get(parentId)?.add(childId);
  }

  const visited = new Set<string>();
  const treeEdgeKeys = new Set<string>();
  const seeds = [graph.rootId, ...nodes.map((node) => node.id)];

  for (const seed of seeds) {
    if (visited.has(seed) || !nodeById.has(seed)) {
      continue;
    }

    if (seed !== graph.rootId && nodeById.has(graph.rootId)) {
      const rootChildren = children.get(graph.rootId);
      if (rootChildren && !rootChildren.includes(seed)) {
        rootChildren.push(seed);
        treeEdgeKeys.add(toUndirectedEdgeKey(graph.rootId, seed));
      }
    }

    const queue: string[] = [seed];
    visited.add(seed);

    while (queue.length > 0) {
      const current = queue.shift();
      if (!current) {
        continue;
      }

      const prioritized = Array.from(preferred.get(current) || []);
      const adjacent = Array.from(adjacency.get(current) || []);
      const nextCandidates = uniqueOrdered([...prioritized, ...adjacent])
        .filter((next) => next !== current && !visited.has(next))
        .sort((a, b) => compareGraphNodeIds(a, b, nodeById));

      for (const next of nextCandidates) {
        const bucket = children.get(current);
        if (bucket) {
          bucket.push(next);
        }
        treeEdgeKeys.add(toUndirectedEdgeKey(current, next));
        visited.add(next);
        queue.push(next);
      }
    }
  }

  for (const bucket of children.values()) {
    bucket.sort((a, b) => compareGraphNodeIds(a, b, nodeById));
  }

  const paddingX = 34;
  const paddingY = 16;
  const usableHeight = Math.max(10, height - paddingY * 2);
  const rowStep = usableHeight / Math.max(nodes.length, 1);
  let rowCursor = 0;
  const yById = new Map<string, number>();
  const evaluating = new Set<string>();

  const placeY = (id: string): number => {
    const cached = yById.get(id);
    if (cached != null) {
      return cached;
    }
    if (evaluating.has(id)) {
      const fallback = paddingY + (rowCursor + 0.5) * rowStep;
      rowCursor += 1;
      yById.set(id, fallback);
      return fallback;
    }

    evaluating.add(id);
    const kids = children.get(id) || [];
    if (kids.length === 0) {
      const y = paddingY + (rowCursor + 0.5) * rowStep;
      rowCursor += 1;
      yById.set(id, y);
      evaluating.delete(id);
      return y;
    }

    const avgY =
      kids
        .map((childId) => placeY(childId))
        .reduce((sum, value) => sum + value, 0) / kids.length;
    yById.set(id, avgY);
    evaluating.delete(id);
    return avgY;
  };

  placeY(graph.rootId);
  for (const node of nodes) {
    placeY(node.id);
  }

  const points = new Map<string, GraphPoint>();
  for (const node of nodes) {
    points.set(node.id, {
      id: node.id,
      x: graphLayerX(node.depth, maxDepth, width, paddingX),
      y: clampNumber(
        yById.get(node.id) ?? height / 2,
        paddingY,
        height - paddingY,
      ),
      depth: node.depth,
      title: node.title,
    });
  }

  return {
    points,
    treeEdgeKeys,
    maxDepth,
  };
}

function graphLayerX(
  depth: number,
  maxDepth: number,
  width: number,
  padding: number,
): number {
  const usableWidth = Math.max(10, width - padding * 2);
  const layerCount = Math.max(maxDepth + 1, 1);
  const layerWidth = usableWidth / layerCount;
  return padding + layerWidth * (depth + 0.5);
}

function graphLayerY(
  depth: number,
  maxDepth: number,
  height: number,
  padding: number,
): number {
  const usableHeight = Math.max(10, height - padding * 2);
  const layerCount = Math.max(maxDepth + 1, 1);
  const layerHeight = usableHeight / layerCount;
  return padding + layerHeight * (depth + 0.5);
}

function seededUnit(input: string, salt: number): number {
  let hash = (2166136261 ^ salt) >>> 0;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function compareGraphNodeMeta(
  a: GraphNodePayload,
  b: GraphNodePayload,
): number {
  if (a.depth !== b.depth) {
    return a.depth - b.depth;
  }
  return a.title.localeCompare(b.title, "ja");
}

function compareGraphNodeIds(
  aId: string,
  bId: string,
  nodeById: Map<string, GraphNodePayload>,
): number {
  const a = nodeById.get(aId);
  const b = nodeById.get(bId);
  if (a && b) {
    return compareGraphNodeMeta(a, b);
  }
  return aId.localeCompare(bId, "ja");
}

function uniqueOrdered(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    out.push(value);
  }
  return out;
}

function toUndirectedEdgeKey(a: string, b: string): string {
  return a < b ? `${a}::${b}` : `${b}::${a}`;
}

function buildCurvePath(from: GraphPoint, to: GraphPoint): string {
  const dx = to.x - from.x;
  const dir = dx >= 0 ? 1 : -1;
  const bend = Math.max(18, Math.abs(dx) * 0.36);
  const c1x = from.x + bend * dir;
  const c2x = to.x - bend * dir;
  return `M ${from.x} ${from.y} C ${c1x} ${from.y}, ${c2x} ${to.y}, ${to.x} ${to.y}`;
}
