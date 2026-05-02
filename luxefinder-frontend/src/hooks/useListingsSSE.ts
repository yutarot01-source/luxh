import { useEffect, useMemo, useRef, useState } from "react";
import { fetchListings, mapApiRowToListing } from "@/lib/luxe/api";
import type { Listing } from "@/lib/luxe/types";

export type SseState = "connecting" | "live" | "reconnecting" | "disconnected" | "error";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const MAX_LISTINGS = 1000;

function streamUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function mergeListing(base: Listing, patch: Partial<Listing>): Listing {
  return {
    ...base,
    ...patch,
    platform_prices: { ...base.platform_prices, ...(patch.platform_prices ?? {}) },
    platformLinks: { ...(base.platformLinks ?? {}), ...(patch.platformLinks ?? {}) },
    platform_basis: { ...(base.platform_basis ?? {}), ...(patch.platform_basis ?? {}) },
  };
}

function upsertById(prev: Listing[], incoming: Listing, front = false): Listing[] {
  const idx = prev.findIndex((item) => item.id === incoming.id);
  if (idx < 0) return [incoming, ...prev].slice(0, MAX_LISTINGS);
  const next = [...prev];
  next[idx] = mergeListing(next[idx], incoming);
  if (!front) return next.slice(0, MAX_LISTINGS);
  const [item] = next.splice(idx, 1);
  return [item, ...next].slice(0, MAX_LISTINGS);
}

function patchById(prev: Listing[], id: string, patch: Partial<Listing>): Listing[] {
  return prev.map((item) => (item.id === id ? mergeListing(item, patch) : item)).slice(0, MAX_LISTINGS);
}

function normalizeEventListing(msg: Record<string, unknown>): Listing | null {
  const raw = msg.listing ?? msg.row ?? msg.payload;
  if (raw && typeof raw === "object") return mapApiRowToListing(raw);
  return null;
}

function isFinalVisible(listing: Listing): boolean {
  return listing.status !== "market_updating" && listing.status !== "analyzing";
}

export function useListingsSSE() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [state, setState] = useState<SseState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const hasSnapshot = useRef(false);
  const retryRef = useRef<number | undefined>();

  useEffect(() => {
    let closed = false;
    let es: EventSource | null = null;

    void fetchListings()
      .then((rows) => {
        if (!closed && !hasSnapshot.current) {
          setListings(rows.filter(isFinalVisible).slice(0, MAX_LISTINGS));
          hasSnapshot.current = rows.length > 0;
        }
      })
      .catch((e) => {
        if (!closed) setError(e instanceof Error ? e.message : String(e));
      });

    const connect = () => {
      if (closed) return;
      setState((prev) => (prev === "connecting" ? "connecting" : "reconnecting"));
      es?.close();
      es = new EventSource(streamUrl("/api/listings/stream"));

      es.onopen = () => {
        setState("live");
        setError(null);
      };

      es.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as Record<string, unknown>;
          const type = String(msg.type ?? "");
          if (type === "snapshot" && Array.isArray(msg.listings)) {
            setListings(msg.listings.map(mapApiRowToListing).filter(isFinalVisible).slice(0, MAX_LISTINGS));
            hasSnapshot.current = true;
            return;
          }
          if (type === "new_listing") {
            const listing = normalizeEventListing(msg);
            if (listing && isFinalVisible(listing)) setListings((prev) => upsertById(prev, listing, true));
            return;
          }
          if (type === "market_update") {
            const id = String(msg.id ?? "");
            const listing = normalizeEventListing(msg);
            if (listing && isFinalVisible(listing)) setListings((prev) => upsertById(prev, listing));
            else if (id) setListings((prev) => patchById(prev, id, mapApiRowToListing(msg) as Partial<Listing>));
            return;
          }
          if (type === "market_final") {
            const id = String(msg.id ?? "");
            const listing = normalizeEventListing(msg);
            if (listing) setListings((prev) => upsertById(prev, { ...listing, status: "finalized" }));
            else if (id) setListings((prev) => patchById(prev, id, { status: "finalized" }));
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : "SSE 메시지 파싱 오류");
        }
      };

      es.onerror = () => {
        setState("reconnecting");
        setError("SSE 연결이 끊겼습니다. 재연결 중입니다.");
        es?.close();
        if (!closed) retryRef.current = window.setTimeout(connect, 2500);
      };
    };

    connect();

    return () => {
      closed = true;
      window.clearTimeout(retryRef.current);
      es?.close();
      setState("disconnected");
    };
  }, []);

  const summary = useMemo(() => {
    const visible = listings.filter((item) => item.status !== "excluded" && item.status !== "제외됨");
    const finalized = visible.filter((item) => item.status === "finalized" || item.status === "완료");
    const profits = finalized.map((item) => item.expected_profit || 0);
    return {
      total: visible.length,
      finalized: finalized.length,
      averageProfit: profits.length ? Math.round(profits.reduce((a, b) => a + b, 0) / profits.length) : 0,
      maxProfit: profits.length ? Math.max(...profits) : 0,
      today: visible.filter((item) => {
        const raw = item.created_at || item.collectedAt;
        if (!raw) return false;
        return new Date(raw).toDateString() === new Date().toDateString();
      }).length,
    };
  }, [listings]);

  return { listings, setListings, state, error, summary };
}
