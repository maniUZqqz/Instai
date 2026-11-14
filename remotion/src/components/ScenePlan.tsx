// ScenePlan: the composition that plays a SCENE PLAN (JSON: scenes of components, each with its duration, motion tokens and overlays) in the art style of
// an InstAI StyleKit. One backdrop (kit/Stage.tsx: the style's world) stays under the scenes; every scene is drawn by its component, in the safe area,
// with the style's motion; scenes meet through the style's transition.
// SOURCE: ported from NMarketing:motion/remotion/src/Template.tsx, adapted for InstAI: the 66-style background / decor / texture stack is replaced by the
// kit's own Stage, the style comes from `styleFromKit` (ctx.tsx), the brand badge and the cut overlays were left out.
import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import { Stage } from "../kit/Stage";
import { normalizeKit, type StyleKit } from "../kit/theme";
import { cameraCss, exitCss, transitionCss } from "./anim";
import { CaptionsLine } from "./comp-text";
import { CtxC, buildCtx, sceneCtx, useCtx, useFontsReady, styleFromKit } from "./ctx";
import type { Ctx } from "./ctx";
import { area } from "./parts";
import { QaProbe } from "./qa";
import { COMPONENTS, OVERLAYS } from "./registry";
import { SvgDefs } from "./text";
import { computeTimeline } from "./timeline";
import type { Timeline } from "./timeline";
import { SIZE_PIXELS } from "./types";
import type { Overlay, Scene, Spec } from "./types";

export type ScenePlanProps = { kit: StyleKit; size?: "landscape" | "vertical" | "square"; spec: Spec; fontBase?: string }

/** Width, height, frame rate and length of a plan (the page's player and the render both ask this). */
export function planMeta(props: Partial<ScenePlanProps>): { width: number; height: number; fps: number; durationInFrames: number } {
  const spec = (props.spec ?? { scenes: [] }) as Spec;
  const [width, height] = SIZE_PIXELS[(props.size ?? spec.size ?? "vertical") as string] ?? SIZE_PIXELS.vertical;
  const fps = Math.max(10, Math.min(60, Number(spec.fps) || 30));
  const style = styleFromKit(normalizeKit(props.kit), fps);
  const tl = computeTimeline(spec, style, fps);
  return { width, height, fps, durationInFrames: tl.total };
}

/** where an overlay sits inside the safe area (anchor + offsets as fractions of the area) */
function overlayBox(ctx: Ctx, ov: Overlay): React.CSSProperties {
  const a = area(ctx, ov.type === "captions");            // the captions track sits in its own band below / above the content area
  const { W, H, rtl, safe } = ctx;
  let anchor = String(ov.anchor || (ov.type === "lower_third" ? "lower" : ov.type === "captions" ? "lower" : ov.type === "sticker" ? "top-end" : "lower"));
  if (ov.type === "captions") anchor = anchor === "lower" ? "bottom" : anchor === "upper" ? "top" : anchor;
  const dx = (Number(ov.dx) || 0) * a.w, dy = (Number(ov.dy) || 0) * a.h;
  const side = anchor.endsWith("-start") ? (rtl ? "flex-end" : "flex-start") : anchor.endsWith("-end") ? (rtl ? "flex-start" : "flex-end") : "center";
  const base: React.CSSProperties = { position: "absolute", left: a.x + dx, width: a.w, display: "flex", justifyContent: side };
  if (anchor === "top" || anchor.startsWith("top")) return { ...base, top: a.y + dy };
  if (anchor === "upper") return { ...base, top: a.y + a.h * 0.2 + dy };
  if (anchor === "center") return { ...base, top: a.y + a.h * 0.5 + dy, transform: "translateY(-50%)" };
  if (anchor === "bottom" || anchor.startsWith("bottom")) return { ...base, bottom: H - (a.y + a.h) - dy };
  void safe;
  return { ...base, bottom: H - (a.y + a.h * 0.86) - dy };       // lower (the lower third of the safe area)
}

const OverlayLayer: React.FC<{ overlays: Overlay[]; sc: Scene }> = ({ overlays, sc }) => {
  const ctx = useCtx();
  const { fps } = ctx;
  return (
    <>
      {overlays.map((ov, k) => {
        const Body = OVERLAYS[ov.type];
        if (!Body) return null;
        const from = Math.max(0, Math.round((Number(ov.at) || 0) * fps));
        const len = ov.dur ? Math.max(1, Math.round(Number(ov.dur) * fps)) : Math.max(1, ctx.scene.frames - from);
        return (
          <Sequence key={k} from={from} durationInFrames={len} layout="none">
            <div data-nm-overlay={ov.type} style={overlayBox(ctx, ov)}>
              <Body sc={{ ...(ov as any), duration: sc.duration } as Scene} />
            </div>
          </Sequence>
        );
      })}
    </>
  );
};

const SceneView: React.FC<{ sc: Scene; i: number; base: Omit<Ctx, "scene">; tl: Timeline; fonts: boolean }> = ({ sc, i, base, tl, fonts }) => {
  const f = useCurrentFrame();
  const count = tl.frames.length;
  const ctx: Ctx = sceneCtx(base, sc, tl.frames[i], i, count, fonts);
  const Body = COMPONENTS[sc.type] ?? COMPONENTS.title;
  const seed = i * 7 + 1;
  let wrap: React.CSSProperties = {};
  const inTf = i > 0 ? tl.tfs[i - 1] : 0, outTf = i < count - 1 ? tl.tfs[i] : 0;
  if (inTf > 0 && f < inTf) wrap = { ...wrap, ...transitionCss(tl.kinds[i - 1], f / inTf, "in", { W: base.W, H: base.H, rtl: base.rtl, seed }) };
  const outStart = tl.frames[i] - outTf;
  if (outTf > 0 && f >= outStart) wrap = { ...wrap, ...transitionCss(tl.kinds[i], (f - outStart) / outTf, "out", { W: base.W, H: base.H, rtl: base.rtl, seed: seed + 1 }) };
  // the scene's own exit (only where nothing covers the cut)
  const exitKind = typeof sc.exit === "string" ? sc.exit : "none";
  const EX = Math.max(6, Math.round(base.fps * 0.3));
  const exiting = exitKind !== "none" && outTf === 0 && f >= tl.frames[i] - EX;
  const exit = exiting ? exitCss(exitKind, (f - (tl.frames[i] - EX)) / EX, base.rtl ? -1 : 1) : {};
  const par = sc.camera?.move === "parallax";
  // the slow camera (the style's push-in, the scene's own move) is decoration: the QA measures the layout itself, without the zoom that would push a text over a safe-area line
  const cam = (layer: "mid" | "fg") => (base.qa ? {} : cameraCss(ctx, f, tl.frames[i], sc.camera, par ? layer : "all"));
  const overlays: Overlay[] = (Array.isArray(sc.overlays) ? sc.overlays : []).filter((o) => o && OVERLAYS[o.type]);
  const globalCaptions = !!base.spec.captions?.on && ctx.cues.length > 0 && !overlays.some((o) => o.type === "captions");
  return (
    <CtxC.Provider value={ctx}>
      <AbsoluteFill style={{ ...wrap }} data-nm-scene={i}>
        <AbsoluteFill style={{ ...cam("mid"), ...exit }}>
          <Body sc={sc} />
          {overlays.length ? <OverlayLayer overlays={overlays} sc={sc} /> : null}
          {globalCaptions ? (
            <div data-nm-overlay="captions" style={overlayBox(ctx, { type: "captions", anchor: base.spec.captions?.position || "lower" })}>
              <CaptionsLine words={ctx.cues} />
            </div>
          ) : null}
        </AbsoluteFill>
      </AbsoluteFill>
    </CtxC.Provider>
  );
};

export const ScenePlan: React.FC<ScenePlanProps> = (props) => {
  const { width, height, fps } = useVideoConfig();
  const kit = normalizeKit(props.kit);
  const spec = (props.spec ?? { scenes: [] }) as Spec;
  const base = buildCtx(kit, spec, width, height, fps);
  const tl = computeTimeline(spec, base.style, fps);
  const fonts = useFontsReady(props.fontBase);
  const rootCtx: Ctx = { ...base, fonts, scene: { index: 0, frames: tl.total, count: tl.frames.length } };
  return (
    <CtxC.Provider value={rootCtx}>
      <Stage kit={kit} backdrop={!spec.bare} zoom={!spec.qa}>
        <SvgDefs />
        {(spec.scenes ?? []).map((sc, i) => (
          <Sequence key={i} from={tl.starts[i]} durationInFrames={tl.frames[i]} layout="none">
            <SceneView sc={sc} i={i} base={base} tl={tl} fonts={fonts} />
          </Sequence>
        ))}
        {spec.qa ? <QaProbe /> : null}
      </Stage>
    </CtxC.Provider>
  );
};
