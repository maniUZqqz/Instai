// Types of the scene-plan engine (the component library). SOURCE: ported from NMarketing:motion/remotion/src/types.ts, adapted for InstAI:
// the plan names an InstAI style KIT (remotion/src/kit/theme.ts) instead of NMarketing's catalog of styles, the size is one of the three
// sizes of catalog.ts (landscape / vertical / square) and the shop vocabulary (brand colours, store logo) became the series context.

export type Any = { [k: string]: any };

/** The eight colour roles every component draws with. Built from the style kit's six roles by `styleFromKit` (ctx.tsx), never written by hand:
 *  `ink` and the accents always pass readableOn / accentOn against `bg`, `paper` is the card surface. */
export type Pal = {
  bg: string; bg2: string; ink: string; paper: string;
  accent: string; accent2: string; accent3: string; muted: string;
};

/** What a component needs to know about one style (derived from a StyleKit; see ctx.tsx `styleFromKit`). */
export type StyleDef = {
  id: string;
  name_fa: string;
  name_en: string;
  group: string;
  palette: Pal;
  font: {
    latin: string; fa: string; weight: number;
    body_latin?: string; body_fa?: string;
    case?: "upper" | "none"; track?: number; lh?: number; italic?: boolean;
  };
  text: Any & { fx: string };
  shape: Any;
  motion: {
    enter: string; spring: [number, number, number]; stagger: number;
    stepFps?: number | null; wobble?: number; cam?: Any; hold?: number;
  };
  trans: { kind: string; frames: number };
  fx?: Any;
};

/** Who the episode is about: the series (and its characters) the plan is made for. Everything optional. */
export type SeriesInfo = {
  title?: string;           // series name
  episode?: number;         // episode number
  episode_title?: string;
  channel?: string;
  characters?: string[];
};

export type Cue = { w: string; s: number; e: number };      // one spoken word: start / end in SECONDS from the start of its scene

export type Overlay = {
  type: string;                  // a component that can be an overlay (lower_third, sticker, captions, social_cta ...)
  at?: number;                   // seconds from the scene start (default 0)
  dur?: number;                  // seconds shown (default: until the scene ends)
  anchor?: string;               // top | upper | center | lower | bottom | top-start | top-end | bottom-start | bottom-end
  dx?: number; dy?: number;      // offset as a fraction of the safe area (-0.5..0.5)
  [k: string]: any;
};

export type Scene = {
  type: string;                  // component id (see registry.ts): title, list, quote, stat ... bar_chart, kinetic_title ...
  duration: number;              // seconds
  enter?: string;                // enter animation (ENTER_KINDS) instead of the style's
  exit?: string;                 // none | fade | slide | zoom | drop
  ease?: string;                 // easing preset name (presets.ts EASES)
  spring?: string;               // spring preset name (presets.ts SPRINGS)
  emphasis?: string[];           // words that are drawn in the accent colour and pop
  camera?: { move?: string; amount?: number };
  transition?: string;           // the transition into the NEXT scene
  tokens?: { accent?: string; text?: string; bg?: string; font_scale?: number; align?: string };
  overlays?: Overlay[];
  narration?: string;            // what the voice says over this scene
  cues?: Cue[];                  // word timings of the narration (filled in by the server)
  [k: string]: any;
};

export type Spec = {
  version?: number;
  style?: string;                // the key of the InstAI style (informational; the kit prop carries the colours)
  size?: "landscape" | "vertical" | "square";
  fps?: number;
  lang?: "fa" | "en";
  digits?: "fa" | "en" | "auto";
  series?: SeriesInfo;
  scenes: Scene[];
  assets?: { [name: string]: string };   // name -> data: URI (filled in by the server, never by the user)
  intensity?: number;                    // 0.5..1.5 motion strength
  transition?: string | null;            // override the style's transition kind
  platform?: string;                     // youtube | shorts | reels | story | feed : which UI bars the safe area keeps clear
  safe?: { top: number; right: number; bottom: number; left: number };   // fractions of the frame (filled in by the server from platform)
  captions?: { on?: boolean; position?: string };                      // a captions track over the whole video (needs cues)
  bare?: boolean;                        // no backdrop: a clip that is laid over a picture
  qa?: boolean;                          // QA mode: the page reports the geometry of every text block (console, prefix INSTAI_QA:)
};

export const SIZE_PIXELS: { [k: string]: [number, number] } = {
  landscape: [1920, 1080],
  vertical: [1080, 1920],
  square: [1080, 1080],
};
