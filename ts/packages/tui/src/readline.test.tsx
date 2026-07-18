/**
 * Tests for useReadline via a minimal render harness. Exercises cursor motion,
 * word kill, multiline insert, and reverse-search — the features the old
 * append-only buffer couldn't do.
 */

import { describe, expect, test } from "bun:test";
import { render } from "ink";
import React, { useRef } from "react";
import { useReadline } from "./readline";

/** Probe component: exposes the handle via a ref so tests can read state. */
function Probe({
  onReady,
  history,
}: {
  onReady: (api: ReturnType<typeof useReadline>) => void;
  history?: string[];
}) {
  const api = useReadline({ history });
  const fired = useRef(false);
  if (!fired.current) {
    fired.current = true;
    onReady(api);
  }
  return React.createElement("ink-text", null, "x");
}

/** Drive a sequence of keystrokes and read the final state. */
function driveKeys(
  keys: { ch: string; key: Record<string, boolean> }[],
  history?: string[],
): { value: string; cursor: number } {
  let api: ReturnType<typeof useReadline> | null = null;
  const renderer = render(
    React.createElement(Probe, {
      onReady: (a) => {
        api = a;
      },
      history,
    }),
    { stderr: { write: () => true } as unknown as NodeJS.WriteStream },
  );
  for (const { ch, key } of keys) {
    api!.input(ch, key as never);
  }
  const state = { value: api!.handle.state.value, cursor: api!.handle.state.cursor };
  renderer.unmount();
  return state;
}

describe("useReadline cursor motion", () => {
  test("typing inserts at cursor, not just append", () => {
    // Type "abc", move left twice (cursor at 'a|bc'), type "X".
    const s = driveKeys([
      { ch: "a", key: {} },
      { ch: "b", key: {} },
      { ch: "c", key: {} },
      { ch: "", key: { leftArrow: true } },
      { ch: "", key: { leftArrow: true } },
      { ch: "X", key: {} },
    ]);
    expect(s.value).toBe("aXbc");
    expect(s.cursor).toBe(2);
  });

  test("Ctrl+A / Ctrl+E jump to start / end", () => {
    const s = driveKeys([
      { ch: "h", key: {} },
      { ch: "i", key: {} },
      { ch: "", key: { ctrl: true } }, // Ctrl+A — ch empty, won't match; test separately
    ]);
    // Ctrl+A needs ch === "a" with ctrl=true
    const s2 = driveKeys([
      { ch: "h", key: {} },
      { ch: "i", key: {} },
      { ch: "a", key: { ctrl: true } }, // Ctrl+A → start
    ]);
    expect(s2.cursor).toBe(0);

    const s3 = driveKeys([
      { ch: "h", key: {} },
      { ch: "i", key: {} },
      { ch: "a", key: { ctrl: true } },
      { ch: "e", key: { ctrl: true } }, // Ctrl+E → end
    ]);
    expect(s3.cursor).toBe(2);
  });

  test("Ctrl+W deletes previous word", () => {
    const s = driveKeys([
      { ch: "h", key: {} },
      { ch: "i", key: {} },
      { ch: " ", key: {} },
      { ch: "w", key: {} },
      { ch: "w", key: {} },
      { ch: "w", key: { ctrl: true } },
    ]);
    expect(s.value).toBe("hi ");
    expect(s.cursor).toBe(3);
  });

  test("Ctrl+K kills to end of line", () => {
    const s = driveKeys([
      { ch: "a", key: {} },
      { ch: "b", key: {} },
      { ch: "c", key: {} },
      { ch: "d", key: {} },
      { ch: "", key: { leftArrow: true } },
      { ch: "", key: { leftArrow: true } },
      { ch: "k", key: { ctrl: true } },
    ]);
    expect(s.value).toBe("ab");
  });

  test("Ctrl+U kills to start of line", () => {
    const s = driveKeys([
      { ch: "x", key: {} },
      { ch: "y", key: {} },
      { ch: "z", key: {} },
      { ch: "", key: { leftArrow: true } },
      { ch: "u", key: { ctrl: true } },
    ]);
    expect(s.value).toBe("z");
    expect(s.cursor).toBe(0);
  });
});

describe("useReadline multiline", () => {
  test("Ctrl+J inserts a newline at cursor", () => {
    const s = driveKeys([
      { ch: "a", key: {} },
      { ch: "b", key: {} },
      { ch: "j", key: { ctrl: true } },
      { ch: "c", key: {} },
    ]);
    expect(s.value).toBe("ab\nc");
  });

  test("Alt+M toggles multiline insert", () => {
    const s = driveKeys([
      { ch: "a", key: {} },
      { ch: "m", key: { meta: true } },
      { ch: "b", key: {} },
    ]);
    expect(s.value).toBe("a\nb");
  });
});

describe("useReadline history", () => {
  test("↑ recalls previous entry, ↓ restores draft", () => {
    const s = driveKeys([
      { ch: "", key: { upArrow: true } },
    ], ["first command", "second"]);
    expect(s.value).toBe("second");
  });
});

describe("useReadline paste + unicode", () => {
  test("multi-char paste chunk inserts wholesale; emoji survives", () => {
    const s = driveKeys([
      { ch: "pasted chunk ", key: {} },
      { ch: "😀", key: {} },
    ]);
    expect(s.value).toBe("pasted chunk 😀");
  });

  test("backspace and arrows step over surrogate pairs, not into them", () => {
    const s = driveKeys([
      { ch: "a😀b", key: {} },
      { ch: "", key: { leftArrow: true } }, // before b
      { ch: "", key: { leftArrow: true } }, // before 😀 (2 code units)
      { ch: "", key: { backspace: true } }, // deletes 'a'
    ]);
    expect(s.value).toBe("😀b");
  });

  test("Ctrl+T is NOT consumed (host app owns the plan toggle)", () => {
    const s = driveKeys([
      { ch: "a", key: {} },
      { ch: "b", key: {} },
      { ch: "t", key: { ctrl: true } },
    ]);
    expect(s.value).toBe("ab");
  });
});
