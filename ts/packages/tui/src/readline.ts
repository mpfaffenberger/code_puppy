/**
 * useReadline — a cursor-aware input line hook for Ink. Replaces the
 * append-only `useState("")` pattern with a proper {value, cursor} pair and
 * the prompt_toolkit-style key vocabulary the TUI was missing.
 *
 * Supports:
 *   - cursor motion: ← → Ctrl+A Ctrl+E (surrogate-pair aware)
 *   - word motion: Ctrl+W (delete prev word), Alt+B / Alt+F (jump word)
 *   - line kill: Ctrl+U (kill to start), Ctrl+K (kill to end)
 *   - char delete: Backspace, Delete (Ctrl+D)
 *   - multiline: Alt+M / Ctrl+J (newline insert)
 *   - history: ↑ ↓ (via onHistoryNav or the built-in draft-preserving nav)
 *   - reverse search: Ctrl+R (Esc cancels)
 *   - paste: multi-char chunks insert wholesale
 *
 * State lives in REFS (single source of truth) with a render tick — input()
 * mutates synchronously, so multi-key batches (pastes, tests) never operate
 * on stale closures, and handle.state is always fresh. (Ctrl+T is NOT bound
 * here: the host app owns it for the plan-panel toggle.)
 */

import { useCallback, useRef, useState } from "react";

export interface ReadlineState {
  value: string;
  cursor: number;
}

export interface ReadlineHandle {
  state: ReadlineState;
  setValue: (v: string, cursor?: number) => void;
  reset: () => void;
}

export interface ReadlineOptions {
  initial?: string;
  history?: string[];
  onHistoryNav?: (direction: "up" | "down") => string | undefined;
}

interface SearchState {
  active: boolean;
  query: string;
  result: string | undefined;
  resultIndex: number;
}

const EMPTY_SEARCH: SearchState = { active: false, query: "", result: undefined, resultIndex: -1 };

export function useReadline(opts: ReadlineOptions = {}): {
  handle: ReadlineHandle;
  search: SearchState;
  /** Process an Ink (ch, key) pair. Returns true if consumed. */
  input: (ch: string, key: InkKey) => boolean;
  /** Submit the current line (Enter). Returns the value, or undefined if empty. */
  submit: () => string | undefined;
} {
  const st = useRef<ReadlineState>({ value: opts.initial ?? "", cursor: (opts.initial ?? "").length });
  const searchRef = useRef<SearchState>({ ...EMPTY_SEARCH });
  const draftRef = useRef("");
  const histIndex = useRef<number | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;
  const [, force] = useState(0);
  const bump = useCallback(() => force((n) => n + 1), []);

  const setBoth = useCallback(
    (v: string, c?: number) => {
      st.current = { value: v, cursor: c === undefined ? v.length : Math.max(0, Math.min(c, v.length)) };
      bump();
    },
    [bump],
  );

  const setSearch = useCallback(
    (s: SearchState) => {
      searchRef.current = s;
      bump();
    },
    [bump],
  );

  const input = useCallback(
    (ch: string, key: InkKey): boolean => {
      const { value, cursor } = st.current;
      const history = optsRef.current.history ?? [];
      const search = searchRef.current;

      // Ctrl+R: enter search / cycle to next older match while searching.
      if (key.ctrl && ch === "r") {
        if (search.active) {
          setSearch({ ...search, ...findMatch(history, search.query, search.resultIndex - 1) });
        } else {
          setSearch({ active: true, query: "", result: undefined, resultIndex: -1 });
        }
        return true;
      }
      // While in search mode, keys build the query; Esc cancels; Enter accepts.
      if (search.active) {
        if (key.escape) {
          setSearch({ ...EMPTY_SEARCH });
          return true;
        }
        if (key.return) {
          if (search.result) setBoth(search.result);
          setSearch({ ...EMPTY_SEARCH });
          return true;
        }
        if (key.backspace || key.delete) {
          const q = search.query.slice(0, -1);
          setSearch({ ...search, query: q, ...findMatch(history, q, -1) });
          return true;
        }
        if (ch && !key.ctrl && !key.meta) {
          const q = search.query + ch;
          setSearch({ ...search, query: q, ...findMatch(history, q, -1) });
          return true;
        }
        return false;
      }

      // Enter / return — let the caller handle submit; don't consume.
      if (key.return) return false;

      // Multiline: Alt+M or Ctrl+J inserts a newline.
      if ((key.meta && ch === "m") || (key.ctrl && ch === "j")) {
        setBoth(value.slice(0, cursor) + "\n" + value.slice(cursor), cursor + 1);
        return true;
      }

      // ---- deletion ----
      if (key.backspace || (key.ctrl && ch === "h")) {
        if (cursor === 0) return true;
        const prev = prevBoundary(value, cursor);
        setBoth(value.slice(0, prev) + value.slice(cursor), prev);
        return true;
      }
      if (key.delete || (key.ctrl && ch === "d")) {
        if (cursor >= value.length) return true;
        setBoth(value.slice(0, cursor) + value.slice(nextBoundary(value, cursor)), cursor);
        return true;
      }
      if (key.ctrl && ch === "w") {
        const { text, pos } = deleteWordBack(value, cursor);
        setBoth(text, pos);
        return true;
      }
      if (key.ctrl && ch === "u") {
        setBoth(value.slice(cursor), 0);
        return true;
      }
      if (key.ctrl && ch === "k") {
        setBoth(value.slice(0, cursor), cursor);
        return true;
      }

      // ---- cursor motion (surrogate-pair aware) ----
      if (key.leftArrow) {
        setBoth(value, prevBoundary(value, cursor));
        return true;
      }
      if (key.rightArrow) {
        setBoth(value, nextBoundary(value, cursor));
        return true;
      }
      if (key.ctrl && ch === "a") {
        setBoth(value, 0);
        return true;
      }
      if (key.ctrl && ch === "e") {
        setBoth(value, value.length);
        return true;
      }
      if (key.meta && ch === "b") {
        setBoth(value, wordBackPos(value, cursor));
        return true;
      }
      if (key.meta && ch === "f") {
        setBoth(value, wordForwardPos(value, cursor));
        return true;
      }

      // ---- history (↑/↓) ----
      if (key.upArrow) {
        if (optsRef.current.onHistoryNav) {
          const v = optsRef.current.onHistoryNav("up");
          if (v !== undefined) setBoth(v);
        } else {
          if (histIndex.current === null) {
            if (!history.length) return true;
            draftRef.current = value;
            histIndex.current = history.length - 1;
          } else if (histIndex.current > 0) {
            histIndex.current -= 1;
          }
          const v = history[histIndex.current];
          if (v !== undefined) setBoth(v);
        }
        return true;
      }
      if (key.downArrow) {
        if (optsRef.current.onHistoryNav) {
          const v = optsRef.current.onHistoryNav("down");
          if (v !== undefined) setBoth(v);
        } else {
          if (histIndex.current === null) return true;
          histIndex.current += 1;
          if (histIndex.current > history.length - 1) {
            histIndex.current = null;
            setBoth(draftRef.current);
          } else {
            setBoth(history[histIndex.current]!);
          }
        }
        return true;
      }

      // ---- printable chars & pastes: insert the whole chunk (emoji, CJK,
      // bracketed-paste multi-char events — everything non-control) ----
      if (ch && !key.ctrl && !key.meta && !key.escape) {
        setBoth(value.slice(0, cursor) + ch + value.slice(cursor), cursor + ch.length);
        return true;
      }

      return false;
    },
    [setBoth, setSearch],
  );

  const submit = useCallback((): string | undefined => {
    const v = st.current.value.trim();
    if (searchRef.current.active) setSearch({ ...EMPTY_SEARCH });
    histIndex.current = null;
    return v ? st.current.value : undefined;
  }, [setSearch]);

  const handle: ReadlineHandle = {
    get state() {
      return { ...st.current };
    },
    setValue: setBoth,
    reset: () => {
      setBoth("");
      setSearch({ ...EMPTY_SEARCH });
      histIndex.current = null;
    },
  };

  return { handle, search: searchRef.current, input, submit };
}

// ---- helpers ----

interface InkKey {
  upArrow?: boolean;
  downArrow?: boolean;
  leftArrow?: boolean;
  rightArrow?: boolean;
  return?: boolean;
  escape?: boolean;
  ctrl?: boolean;
  meta?: boolean;
  backspace?: boolean;
  delete?: boolean;
  tab?: boolean;
}

/** Previous cursor boundary — steps over a full surrogate pair, not into it. */
function prevBoundary(s: string, i: number): number {
  if (i <= 0) return 0;
  const cu = s.charCodeAt(i - 1);
  // Low surrogate preceded by a high surrogate → step over both.
  if (cu >= 0xdc00 && cu <= 0xdfff && i >= 2) {
    const hi = s.charCodeAt(i - 2);
    if (hi >= 0xd800 && hi <= 0xdbff) return i - 2;
  }
  return i - 1;
}

/** Next cursor boundary — steps over a full surrogate pair, not into it. */
function nextBoundary(s: string, i: number): number {
  if (i >= s.length) return s.length;
  const cp = s.codePointAt(i);
  return i + (cp !== undefined && cp > 0xffff ? 2 : 1);
}

function deleteWordBack(text: string, cursor: number): { text: string; pos: number } {
  let i = cursor;
  while (i > 0 && /\s/.test(text[i - 1]!)) i -= 1;
  while (i > 0 && /\S/.test(text[i - 1]!)) i -= 1;
  return { text: text.slice(0, i) + text.slice(cursor), pos: i };
}

function wordBackPos(text: string, cursor: number): number {
  let i = cursor;
  while (i > 0 && /\s/.test(text[i - 1]!)) i -= 1;
  while (i > 0 && /\S/.test(text[i - 1]!)) i -= 1;
  return i;
}

function wordForwardPos(text: string, cursor: number): number {
  let i = cursor;
  while (i < text.length && /\s/.test(text[i]!)) i += 1;
  while (i < text.length && /\S/.test(text[i]!)) i += 1;
  return i;
}

function findMatch(
  history: string[],
  query: string,
  fromIndex: number,
): { result: string | undefined; resultIndex: number } {
  if (!query) return { result: undefined, resultIndex: -1 };
  const start = fromIndex < 0 ? history.length - 1 : Math.min(fromIndex, history.length - 1);
  for (let i = start; i >= 0; i--) {
    if (history[i]!.includes(query)) return { result: history[i], resultIndex: i };
  }
  return { result: undefined, resultIndex: -1 };
}
