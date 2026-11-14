// The context every component reads (colours, motion, text, safe area, the scene's own tokens).
// SOURCE: ported from NMarketing:motion/remotion/src/ctx.tsx, adapted for InstAI: NMarketing builds it from one of 66 catalogued styles; here it is built
// from an InstAI StyleKit (remotion/src/kit/theme.ts: the six palette roles, the motion personality, the typography) by `styleFromKit`, so every
// component draws in the art style of the series (one of the 116 looks). The shop vocabulary (brand colours, store logo) is gone.
// Rule kept from InstAI: a colour is never used without readableOn / accentOn against its own surface (see `styleFromKit`).
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { continueRender, delayRender, staticFile, useCurrentFrame } from "remotion";
import { motionFor } from "../kit/motion";
import { accentOn, mix as mixHex, readableOn, type StyleKit } from "../kit/theme";
import ADAPTER from "./adapter.json";
import { easeOf, springOf } from "./presets";
import type { Cue, Pal, Scene, Spec, StyleDef } from "./types";
import { hasArabic, hex2rgb, mix } from "./util";

export type Ctx = {
  style: StyleDef;
  spec: Spec;
  W: number; H: number; fps: number;
  u: number;                // min(W,H)/1080: every size in the library is written for a 1080 short side
  wide: boolean;
  rtl: boolean;             // the video is Persian
  faDigits: boolean;
  pal: Pal;                 // the style's palette (eight roles)
  intensity: number;
  scene: { index: number; frames: number; count: number };
  safe: { top: number; right: number; bottom: number; left: number };   // px of the frame that the platform's UI covers (the layout keeps clear of it)
  platform: string;
  fonts: boolean;           // the fonts are loaded: text measured now is measured right
  qa: boolean;
  cues: Cue[];              // word timings of this scene's narration (scene-local seconds)
  emphasis: string[];       // lower-case words drawn in the accent colour
  fontScale: number;        // scene token: every text of the scene grows / shrinks (auto-fit still keeps it inside its box)
  enter: string;            // the enter animation of this scene (the style's, or the scene's own)
  spring: [number, number, number];
  easeName: string;
  align: "center" | "start" | "end";
  capBand: { top: number; bottom: number };   // px kept free for the word-highlight captions track (only while this scene has narration words)
};

export const CtxC = createContext<Ctx | null>(null);
export function useCtx(): Ctx {
  const c = useContext(CtxC);
  if (!c) throw new Error("instai-motion: no style context (render inside <ScenePlan>)");
  return c;
}

/** frame of the current scene, quantised for "on twos / on fours" styles (stepFps) */
export function useQF(): number {
  const f = useCurrentFrame();
  const { style, fps } = useCtx();
  const s = style.motion.stepFps;
  if (!s) return f;
  const step = Math.max(1, fps / s);
  return Math.floor(f / step) * step;
}

// ───────────────────────────────────────────── the adapter: StyleKit -> component tokens

type Personality = { enter: string; spring: string; trans: { kind: string; frames: number } };
type Family = { radius: number; border: number; shadow: string; fx: string; rule: string; offset?: number; badgeRound?: boolean; fillGradient?: number; extra?: string; dash?: boolean };
const PERSONALITIES = (ADAPTER as any).personalities as { [k: string]: Personality };
const FAMILIES = (ADAPTER as any).families as { [k: string]: Family };
const HARD_ANIMATIONS: string[] = (ADAPTER as any).hard_animations;

/** The kit's typed title animation wins when the theme asks for something specific; the "fade" default leaves the way of moving to the style's personality. */
function enterOf(kit: StyleKit, pers: Personality): string {
  switch (kit.typography.title_animation) {
    case "pop": return "pop";
    case "slide": return "slide";
    case "typewriter": return "type";
    default: return pers.enter;
  }
}

/** The eight palette roles from the six of the kit. `ink` is the text colour that reads on `bg`; the accents are pulled until they read on `bg` too
 *  (accentOn); `paper` is the surface of cards (a step toward the primary colour), and every text on a card picks its own tone from it (Card). */
export function paletteFromKit(kit: StyleKit): Pal {
  const p = kit.palette;
  const bg = p.background;
  const ink = readableOn(bg, [p.highlight, "#FFFFFF"]);
  return {
    bg,
    bg2: mixHex(bg, p.primary, 0.35),
    ink,
    paper: mixHex(bg, p.primary, 0.55),
    accent: accentOn(bg, p.accent),
    accent2: accentOn(bg, p.secondary),
    accent3: accentOn(bg, mixHex(p.primary, p.highlight, 0.4)),
    muted: mixHex(ink, bg, 0.5),
  };
}

export function styleFromKit(kit: StyleKit, fps: number): StyleDef {
  const m = motionFor(kit.animation, kit.fps_feel, fps);
  const pers = PERSONALITIES[m.id] ?? PERSONALITIES.motion_graphics;
  const fam = FAMILIES[kit.family] ?? FAMILIES.graphic;
  const hard = HARD_ANIMATIONS.includes(m.id);
  const pal = paletteFromKit(kit);
  const spring = springOf(pers.spring) ?? [30, 120, 1];
  return {
    id: kit.key, name_fa: kit.name, name_en: kit.name, group: kit.family,
    palette: pal,
    font: { latin: "vazirmatn", fa: "vazirmatn", weight: 700, case: kit.typography.title_case === "upper" ? "upper" : "none", lh: 1.3 },
    text: { fx: fam.fx, color: "ink", body_color: "ink", body_fx: "plain", shadow: "accent2", hi: "accent", depth: kit.typography.title_weight === "black" ? 8 : 6 },
    shape: {
      fill: "paper", radius: hard ? Math.min(fam.radius, 8) : fam.radius, border: hard ? Math.max(fam.border, 5) : fam.border, bc: "ink",
      shadow: hard ? "hard" : fam.shadow, offset: fam.offset ?? 8, rule: fam.rule, badge: "accent", badgeRound: fam.badgeRound !== false && !hard,
      fillGradient: fam.fillGradient, extra: fam.extra, dash: fam.dash,
    },
    motion: {
      enter: enterOf(kit, pers), spring, stagger: m.stagger, stepFps: m.step > 1 ? kit.fps_feel : null,
      wobble: m.wobbleDeg * 2 + m.jitterPx, cam: m.camera > 0 ? { zoom: m.camera, zoomIn: true } : undefined,
    },
    trans: pers.trans,
    fx: undefined,
  };
}

// ───────────────────────────────────────────── fonts (Vazirmatn, SIL OFL: remotion/public/fonts)

export function fontFamily(_key: string): string {
  return "Vazirmatn";
}
export function fontStack(_latin: string, _fa: string): string {
  return `"Vazirmatn", "Segoe UI", Tahoma, Arial, sans-serif`;
}
/** the display font stack of the current style (for pieces that draw their own text: captions) */
export function fontStackOf(_ctx: Ctx, _role: "display" | "body" = "display"): string {
  return fontStack("vazirmatn", "vazirmatn");
}

/** Blocks the frame until Vazirmatn is in the page, then returns true (the tree has re-rendered with the real font: text measured before that
 *  was measured with a fallback). `fontBase === 'page'` (the InstAI page's player) means the page's own @font-face is already there. */
export function useFontsReady(fontBase?: string): boolean {
  const page = fontBase === "page";
  const [handle] = useState(() => (page ? null : delayRender("instai-motion fonts", { timeoutInMilliseconds: 60000 })));
  const [ready, setReady] = useState(false);
  const released = useRef(false);
  useEffect(() => {
    let cancelled = false;
    if (!page) {
      const base = (fontBase || staticFile("fonts/")).replace(/\/?$/, "/");
      const id = "vazirmatn-face";
      if (!document.getElementById(id)) {
        const st = document.createElement("style");
        st.id = id;
        st.textContent =
          `@font-face{font-family:'Vazirmatn';font-weight:400;src:url('${base}Vazirmatn-Regular.woff2') format('woff2');}` +
          `@font-face{font-family:'Vazirmatn';font-weight:700;src:url('${base}Vazirmatn-Bold.woff2') format('woff2');}`;
        document.head.appendChild(st);
      }
    }
    Promise.all([document.fonts.load("400 40px 'Vazirmatn'"), document.fonts.load("700 40px 'Vazirmatn'")])
      .then(() => document.fonts.ready)
      .catch(() => undefined)
      .then(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!ready) return;
    (globalThis as any).__INSTAI_FONTS_READY = true;
    if (handle !== null && !released.current) {
      released.current = true;
      continueRender(handle);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);
  return page ? true : ready;
}

// ───────────────────────────────────────────── context builder

/** the platform's UI bars in px of this frame */
export function safePx(spec: Spec, W: number, H: number): { top: number; right: number; bottom: number; left: number } {
  const s = spec.safe;
  if (!s) return { top: 0, right: 0, bottom: 0, left: 0 };
  const f = (v: any) => Math.max(0, Math.min(0.4, Number(v) || 0));
  return { top: f(s.top) * H, right: f(s.right) * W, bottom: f(s.bottom) * H, left: f(s.left) * W };
}

export function buildCtx(kit: StyleKit, spec: Spec, W: number, H: number, fps: number): Omit<Ctx, "scene"> {
  const style = styleFromKit(kit, fps);
  const rtl = (spec.lang || "fa") === "fa";
  const digits = spec.digits || "auto";
  return {
    style, spec, W, H, fps,
    u: Math.min(W, H) / 1080,
    wide: W > H * 1.2,
    rtl,
    faDigits: digits === "fa" || (digits === "auto" && rtl),
    pal: style.palette,
    intensity: Math.max(0.4, Math.min(1.8, spec.intensity ?? 1)),
    safe: safePx(spec, W, H),
    platform: spec.platform || "",
    fonts: false,
    qa: !!spec.qa,
    cues: [],
    emphasis: [],
    fontScale: 1,
    enter: style.motion.enter,
    spring: style.motion.spring,
    easeName: "out-expo",
    align: "center",
    capBand: { top: 0, bottom: 0 },
  };
}

function captionBand(base: Omit<Ctx, "scene">, sc: any, nCues: number): { top: number; bottom: number } {
  const cap = base.spec.captions;
  const own = Array.isArray(sc?.overlays) && sc.overlays.some((o: any) => o && o.type === "captions");
  if (!cap?.on || !nCues || own) return { top: 0, bottom: 0 };
  const band = 230 * base.u;
  const pos = cap.position || "lower";
  return { top: pos === "upper" ? band : 0, bottom: pos === "lower" || pos === "bottom" ? band : 0 };
}

/** the context of ONE scene: the base context + the scene's own tokens (palette, text scale, enter / spring / ease presets, words of the narration) */
export function sceneCtx(base: Omit<Ctx, "scene">, sc: Scene | any, frames: number, index: number, count: number, fonts: boolean): Ctx {
  const t = (sc && sc.tokens) || {};
  const hex = (c: any) => (typeof c === "string" && /^#?[0-9a-fA-F]{6}$/.test(c.trim()) ? (c.startsWith("#") ? c : "#" + c) : null);
  const pal = { ...base.pal };
  const acc = hex(t.accent), txt = hex(t.text), bg = hex(t.bg);
  if (acc) pal.accent = acc;
  if (txt) pal.ink = txt;
  if (bg) { pal.bg = bg; pal.bg2 = bg; }
  const style = txt || bg || acc ? { ...base.style, palette: pal, text: { ...base.style.text, color: txt ? "ink" : base.style.text.color, body_color: txt ? "ink" : base.style.text.body_color } } : base.style;
  const fs = Math.max(0.6, Math.min(1.6, Number(t.font_scale) || 1));
  const cues = Array.isArray(sc?.cues) ? sc.cues.filter((c: any) => c && typeof c.w === "string" && Number.isFinite(c.s)) : [];
  const emphasis = (Array.isArray(sc?.emphasis) ? sc.emphasis : []).map((w: any) => String(w).trim().toLowerCase()).filter(Boolean);
  return {
    ...base, style, pal, fonts, cues, emphasis, fontScale: fs,
    scene: { index, frames, count },
    enter: typeof sc?.enter === "string" && sc.enter ? sc.enter : base.style.motion.enter,
    spring: springOf(sc?.spring) ?? base.style.motion.spring,
    easeName: typeof sc?.ease === "string" && sc.ease ? sc.ease : "out-expo",
    align: t.align === "start" || t.align === "end" ? t.align : "center",
    capBand: captionBand(base, sc, cues.length),
  };
}

export { easeOf };

/** A picture of the plan: `data:` / `blob:` URIs as they are, a name (`keyframe`, `asset:12`) looked up in `spec.assets` (filled in by the server). */
export function useAsset(ref?: string | null): string | null {
  const { spec } = useCtx();
  if (!ref) return null;
  if (ref.startsWith("data:") || ref.startsWith("blob:")) return ref;
  return spec.assets?.[ref] ?? null;
}

export { hasArabic, hex2rgb, mix };
