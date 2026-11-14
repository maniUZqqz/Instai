// Component library, part 1: DATA pieces - growing bar chart, drawing line chart, donut, counters, before/after split, countdown.
// Every text is auto-fit (FT) and every layout sits inside the safe area. Every number on a chart carries the honesty chip (SourceNote):
// «example» unless the scene names a verified source (InstAI's explainer policy).
// SOURCE: ported from NMarketing:motion/remotion/src/comp-data.tsx (only the pieces an episode needs: the shop pieces - price card, comparison table,
// rating - and the progress pieces were left out), adapted for InstAI (SourceNote, English percent sign).
import React from "react";
import { Img } from "remotion";
import { useAsset, useCtx, useQF } from "./ctx";
import type { Ctx } from "./ctx";
import { FT } from "./fit";
import { Icon, IconTile, Pop, SourceNote, Stage, Rule, accentAt, area, itemDelay, stagger, useGrow } from "./parts";
import { easeOf } from "./presets";
import { Card, T } from "./text";
import type { Scene } from "./types";
import { clamp, col, fmtNumber, onColor, rgba, toEnDigits } from "./util";

type SC = React.FC<{ sc: Scene }>;

/** area in px at 1080 */
const A = (ctx: Ctx) => {
  const a = area(ctx);
  return { w: a.w / ctx.u, h: a.h / ctx.u };
};
const num = (v: any): number => {
  const n = Number(toEnDigits(String(v ?? "0")).replace(/[,٬\s]/g, "").replace(/٫/g, ".").replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(n) ? n : 0;
};
const rows = <T2 = any,>(v: any, max: number): T2[] => (Array.isArray(v) ? (v.slice(0, max) as T2[]) : []);
const Title: React.FC<{ text?: string; w: number; max?: number }> = ({ text, w, max = 88 }) => (text ? <FT box={[w, 150]} max={max} min={40} maxLines={2} delay={0}>{String(text)}</FT> : null);

// ───────────────────────────────────────────── bar chart

const BarCol: React.FC<{ i: number; n: number; label: string; value: number; max: number; unit: string; colW: number; h: number; delay: number; show: boolean }> = ({ i, n, label, value, max, unit, colW, h, delay, show }) => {
  const ctx = useCtx();
  const { u, faDigits, fps } = ctx;
  const g = useGrow(delay, Math.round(fps * 1.1));
  const bh = Math.max(6 * u, (value / max) * h * clamp(g, 0, 1.08));
  const c = accentAt(ctx, i);
  return (
    <div style={{ width: colW * u, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: (h + 190) * u, gap: 10 * u }}>
      {show ? <T noAnim fixed role="label" size={44} fx="plain">{fmtNumber(value * clamp(g), faDigits, value % 1 ? 1 : 0) + (unit ? " " + unit : "")}</T> : null}
      <div style={{ width: colW * 0.62 * u, height: bh, background: c, borderRadius: `${14 * u}px ${14 * u}px ${4 * u}px ${4 * u}px`, boxShadow: `0 ${8 * u}px ${18 * u}px ${rgba(c, 0.35)}` }} />
      <FT box={[colW, 88]} max={42} min={24} maxLines={2} role="body" noAnim weight={700}>{label}</FT>
    </div>
  );
};

const HBar: React.FC<{ i: number; label: string; value: number; max: number; unit: string; w: number; delay: number; show: boolean }> = ({ i, label, value, max, unit, w, delay, show }) => {
  const ctx = useCtx();
  const { u, faDigits, fps, rtl } = ctx;
  const g = useGrow(delay, Math.round(fps * 1.1));
  const c = accentAt(ctx, i);
  const labelW = Math.min(360, w * 0.34);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 20 * u, width: "100%", direction: rtl ? "rtl" : "ltr" }}>
      <div style={{ width: labelW * u, flex: "none" }}><FT box={[labelW, 90]} max={44} min={26} maxLines={2} role="body" noAnim weight={700} align="start">{label}</FT></div>
      <div style={{ flex: 1, height: 52 * u, background: rgba(col(ctx.pal, "ink"), 0.1), borderRadius: 26 * u, overflow: "hidden" }}>
        <div style={{ width: `${(value / max) * 100 * clamp(g)}%`, height: "100%", background: c, borderRadius: 26 * u }} />
      </div>
      {show ? <div style={{ width: 170 * u, flex: "none" }}><T noAnim fixed role="label" size={42} fx="plain" align="start">{fmtNumber(value * clamp(g), faDigits, value % 1 ? 1 : 0) + (unit ? " " + unit : "")}</T></div> : null}
    </div>
  );
};

const BarChart: SC = ({ sc }) => {
  const ctx = useCtx();
  const { u, fps } = ctx;
  const a = A(ctx);
  const bars = rows<{ label: string; value: number }>(sc.bars, 6).map((b) => ({ label: String(b.label ?? ""), value: Math.max(0, num(b.value)) }));
  const max = Math.max(1, ...bars.map((b) => b.value)) * 1.08;
  const unit = String(sc.unit ?? "");
  const show = sc.show_values !== false;
  const horizontal = sc.horizontal === true || (sc.horizontal == null && (bars.length > 4 || Math.max(0, ...bars.map((b) => Array.from(b.label).length)) > 12));
  const st = stagger(ctx, 5);
  const cardW = a.w;
  return (
    <Stage gap={30}>
      <Title text={sc.title} w={a.w} />
      <Card pad={34} delay={4} style={{ width: cardW * u, display: "flex", flexDirection: horizontal ? "column" : "row", gap: (horizontal ? 24 : 18) * u, justifyContent: "space-around", alignItems: horizontal ? "stretch" : "flex-end", direction: ctx.rtl ? "rtl" : "ltr" }}>
        {bars.map((b, i) =>
          horizontal ? (
            <HBar key={i} i={i} label={b.label} value={b.value} max={max} unit={unit} w={cardW - 70} delay={itemDelay(ctx, i, bars.length, Math.round(fps * 0.5), st)} show={show} />
          ) : (
            <BarCol key={i} i={i} n={bars.length} label={b.label} value={b.value} max={max} unit={unit} colW={Math.min(230, (cardW - 70 - 18 * bars.length) / Math.max(1, bars.length))} h={Math.min(a.h * 0.42, 620)} delay={itemDelay(ctx, i, bars.length, Math.round(fps * 0.5), st)} show={show} />
          ),
        )}
      </Card>
      {sc.note ? <FT box={[a.w, 110]} max={44} min={26} maxLines={2} role="body" delay={Math.round(fps * 1.2)}>{String(sc.note)}</FT> : null}
      <SourceNote sc={sc} />
    </Stage>
  );
};

// ───────────────────────────────────────────── line chart

const LineChart: SC = ({ sc }) => {
  const ctx = useCtx();
  const { u, fps, rtl, faDigits } = ctx;
  const qf = useQF();
  const a = A(ctx);
  const pts = rows<{ label: string; value: number }>(sc.points, 8).map((p) => ({ label: String(p.label ?? ""), value: num(p.value) }));
  const unit = String(sc.unit ?? "");
  const w = a.w - 70, h = Math.min(a.h * 0.38, 560);
  const vals = pts.map((p) => p.value);
  const lo = Math.min(0, ...vals), hi = Math.max(1, ...vals) * 1.12;
  const px = (i: number) => (pts.length < 2 ? 0.5 : rtl ? 1 - i / (pts.length - 1) : i / (pts.length - 1)) * w;
  const py = (v: number) => h - ((v - lo) / (hi - lo || 1)) * h;
  const g = useGrow(Math.round(fps * 0.5), Math.round(fps * 1.6));
  const d = pts.map((p, i) => `${i ? "L" : "M"}${px(i).toFixed(1)} ${py(p.value).toFixed(1)}`).join(" ");
  const area2 = pts.length ? `${d} L${px(pts.length - 1).toFixed(1)} ${h} L${px(0).toFixed(1)} ${h} Z` : "";
  const c = col(ctx.pal, "accent");
  const pad = 22;
  return (
    <Stage gap={26}>
      <Title text={sc.title} w={a.w} />
      <Card pad={34} delay={4} style={{ width: a.w * u }}>
        <div style={{ position: "relative", width: w * u, height: (h + 190) * u, direction: "ltr" }}>
          <svg width={w * u} height={h * u} viewBox={`${-pad} ${-pad} ${w + pad * 2} ${h + pad * 2}`} style={{ overflow: "visible", position: "absolute", left: 0, top: 20 * u }}>
            <defs>
              <linearGradient id="nm-line-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={c} stopOpacity="0.35" /><stop offset="1" stopColor={c} stopOpacity="0" /></linearGradient>
              <clipPath id="nm-line-clip"><rect x={rtl ? w - w * clamp(g) : 0} y={-pad} width={w * clamp(g)} height={h + pad * 2} /></clipPath>
            </defs>
            {[0, 0.5, 1].map((t) => <line key={t} x1={0} x2={w} y1={h * t} y2={h * t} stroke={rgba(col(ctx.pal, "ink"), 0.12)} strokeWidth={3} />)}
            <g clipPath="url(#nm-line-clip)">
              <path d={area2} fill="url(#nm-line-fill)" />
              <path d={d} fill="none" stroke={c} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round" />
            </g>
            {pts.map((p, i) => {
              const shown = clamp((clamp(g) * (pts.length - 1) - i) * 3 + 1);
              const x = px(i), y = py(p.value);
              return <circle key={i} cx={x} cy={y} r={13 * shown} fill={col(ctx.pal, "paper")} stroke={c} strokeWidth={7} />;
            })}
          </svg>
          {pts.map((p, i) => {
            const shown = clamp((clamp(g) * (pts.length - 1) - i) * 3 + 1);
            const last = i === pts.length - 1 || i === 0;
            const edge = px(i) < 100 ? "left" : px(i) > w - 100 ? "right" : "center";       // the labels at the two ends stay inside the card (and the safe area)
            const lx = edge === "left" ? 0 : edge === "right" ? w - 180 : px(i) - 90;
            return (
              <React.Fragment key={i}>
                <div style={{ position: "absolute", left: lx * u, top: Math.max(0, py(p.value) - 78) * u + 20 * u, width: 180 * u, textAlign: edge === "center" ? "center" : edge, opacity: last ? shown : 0 }}>
                  <T noAnim fixed role="label" size={40} fx="plain">{fmtNumber(p.value, faDigits, p.value % 1 ? 1 : 0) + (unit ? " " + unit : "")}</T>
                </div>
                <div style={{ position: "absolute", left: (px(i) - Math.min(95, w / Math.max(2, pts.length) / 2)) * u, top: (h + 70) * u, width: Math.min(190, w / Math.max(2, pts.length)) * u, display: "flex", justifyContent: "center", opacity: shown }}>
                  <FT box={[Math.min(190, w / Math.max(2, pts.length)), 90]} max={38} min={22} maxLines={2} role="body" noAnim weight={600}>{p.label}</FT>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </Card>
      {sc.note ? <FT box={[a.w, 110]} max={44} min={26} maxLines={2} role="body" delay={Math.round(fps * 1.6)}>{String(sc.note)}</FT> : null}
      <SourceNote sc={sc} />
    </Stage>
  );
};

// ───────────────────────────────────────────── donut / pie

const Donut: SC = ({ sc }) => {
  const ctx = useCtx();
  const { u, fps, faDigits, rtl } = ctx;
  const a = A(ctx);
  const slices = rows<{ label: string; value: number }>(sc.slices, 5).map((s) => ({ label: String(s.label ?? ""), value: Math.max(0, num(s.value)) }));
  const total = Math.max(1e-9, slices.reduce((t, s) => t + s.value, 0));
  const size = Math.min(a.w * 0.8, a.h * 0.4, 640);
  const r = size * 0.38, sw = size * 0.2, C = 2 * Math.PI * r;
  const g = useGrow(Math.round(fps * 0.4), Math.round(fps * 1.5));
  let acc = 0;
  const wide = ctx.wide;
  return (
    <Stage gap={28} row={wide}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 24 * u }}>
        {!wide ? <Title text={sc.title} w={a.w} /> : null}
        <Pop delay={2}>
          <div style={{ position: "relative", width: size * u, height: size * u }}>
            <svg width={size * u} height={size * u} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
              <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={rgba(col(ctx.pal, "ink"), 0.1)} strokeWidth={sw} />
              {slices.map((s, i) => {
                const frac = s.value / total;
                const start = acc;
                acc += frac;
                const vis = clamp(clamp(g) * 1 - start) ;
                const len = Math.min(frac, vis) * C;
                return <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={accentAt(ctx, i)} strokeWidth={sw} strokeDasharray={`${Math.max(0, len - 3)} ${C}`} strokeDashoffset={-start * C} />;
              })}
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
              <FT box={[size * 0.5, size * 0.3]} max={size * 0.16} min={26} maxLines={2} noAnim fx="plain" role="display">{String(sc.center_label ?? "")}</FT>
            </div>
          </div>
        </Pop>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 * u, alignItems: "stretch", direction: rtl ? "rtl" : "ltr", width: wide ? "46%" : "100%" }}>
        {wide ? <Title text={sc.title} w={a.w * 0.46} max={72} /> : null}
        {slices.map((s, i) => (
          <Card key={i} i={i} delay={itemDelay(ctx, i, slices.length, Math.round(fps * 0.7), stagger(ctx))} pad={16} style={{ display: "flex", alignItems: "center", gap: 18 * u }}>
            <div style={{ width: 30 * u, height: 30 * u, borderRadius: 9 * u, background: accentAt(ctx, i), flex: "none" }} />
            <div style={{ flex: 1 }}><FT box={[wide ? a.w * 0.3 : a.w - 330, 80]} max={44} min={24} maxLines={2} role="body" noAnim weight={600} align="start">{s.label}</FT></div>
            <T noAnim fixed role="label" size={44} fx="plain">{fmtNumber((s.value / total) * 100, faDigits, 0) + (rtl ? "٪" : "%")}</T>
          </Card>
        ))}
        <SourceNote sc={sc} />
      </div>
    </Stage>
  );
};

// ───────────────────────────────────────────── counters (count-up numbers with a unit)

const CounterItem: React.FC<{ value: number; decimals: number; unit: string; label: string; delay: number; big: number; w: number; i: number }> = ({ value, decimals, unit, label, delay, big, w, i }) => {
  const ctx = useCtx();
  const { u, fps, faDigits } = ctx;
  const g = useGrow(delay + 4, Math.round(fps * 1.5));
  const shown = fmtNumber(value * clamp(g), faDigits, decimals);
  return (
    <Pop delay={delay} i={i}>
      <div style={{ width: w * u, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 * u }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "center", gap: 12 * u, direction: "ltr" }}>
          <FT box={[w * 0.74, big * 1.25]} max={big} min={50} maxLines={1} noAnim>{shown}</FT>
          {unit ? <FT box={[w * 0.3, big * 0.5]} max={big * 0.42} min={30} maxLines={1} noAnim color="accent">{unit}</FT> : null}
        </div>
        <FT box={[w, 110]} max={46} min={26} maxLines={2} role="body" noAnim>{label}</FT>
      </div>
    </Pop>
  );
};

const Counter: SC = ({ sc }) => {
  const ctx = useCtx();
  const { fps, wide, u } = ctx;
  const a = A(ctx);
  const items = rows<{ value: any; unit?: string; label?: string; decimals?: number }>(sc.items, 3);
  const n = Math.max(1, items.length);
  const row = wide || n === 1 ? n : 1;
  const w = row > 1 ? Math.min(560, (a.w - 40 * (row - 1)) / row) : a.w;
  const big = n === 1 ? (wide ? 280 : 300) : row > 1 ? 190 : 200;
  return (
    <Stage gap={32}>
      {sc.kicker ? <T role="label" size={46} delay={0} color="accent" upper>{String(sc.kicker)}</T> : null}
      <div style={{ display: "flex", flexDirection: row > 1 ? (ctx.rtl ? "row-reverse" : "row") : "column", gap: 40 * u, alignItems: "center", justifyContent: "center" }}>
        {items.map((it, i) => (
          <CounterItem key={i} i={i} value={num(it.value)} decimals={Number(it.decimals ?? (String(it.value ?? "").match(/[.٫]/) ? 1 : 0))} unit={String(it.unit ?? "")} label={String(it.label ?? "")} delay={itemDelay(ctx, i, n, 4, stagger(ctx, 8))} big={big} w={w} />
        ))}
      </div>
      <Rule delay={Math.round(fps * 0.8)} w={200} />
      {sc.note ? <FT box={[a.w, 110]} max={48} min={26} maxLines={2} role="body" delay={Math.round(fps * 1.1)}>{String(sc.note)}</FT> : null}
      <SourceNote sc={sc} />
    </Stage>
  );
};
// ───────────────────────────────────────────── before / after split

const BeforeAfter: SC = ({ sc }) => {
  const ctx = useCtx();
  const { u, fps, pal, rtl, style } = ctx;
  const qf = useQF();
  const a = A(ctx);
  const bi = useAsset(sc.before_image), ai = useAsset(sc.after_image);
  const w = Math.min(a.w, ctx.wide ? a.h * 1.4 : a.w), h = Math.min(a.h * 0.58, ctx.wide ? a.h * 0.72 : 880);
  const t = easeOf("smooth")(clamp((qf - fps * 0.8) / (fps * 1.8)));
  const split = t * 100;
  const bl = String(sc.before_label ?? (rtl ? "قبل" : "Before")), al = String(sc.after_label ?? (rtl ? "بعد" : "After"));
  const accent = col(pal, "accent");
  const panel = (txt: string, img: string | null, bg: string, fg: string, hidden = false) => (
    <div data-nm-excl="before-after" data-nm-hidden={hidden ? "1" : undefined} style={{ position: "absolute", inset: 0, background: bg, display: "flex", alignItems: "center", justifyContent: "center", padding: `${60 * u}px`, boxSizing: "border-box" }}>
      {img ? <Img src={img} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }} /> : null}
      {!img ? <FT box={[w - 200, h - 220]} max={92} min={34} maxLines={5} noAnim color={fg} fx="plain" weight={800}>{txt}</FT> : null}
    </div>
  );
  const clipRest = rtl ? `inset(0 ${split}% 0 0)` : `inset(0 0 0 ${split}%)`;     // the BEFORE panel stays on the side the divider has not reached yet; the AFTER is uncovered from the start edge
  return (
    <Stage gap={28}>
      <Title text={sc.title} w={a.w} max={80} />
      <Pop delay={4}>
        <div style={{ position: "relative", width: w * u, height: h * u, borderRadius: Math.max(18, style.shape.radius ?? 0) * u, overflow: "hidden", boxShadow: `0 ${20 * u}px ${44 * u}px rgba(0,0,0,0.3)` }}>
          {panel(String(sc.after ?? ""), ai, accent, onColor(accent), split <= 0.5)}
          <div style={{ position: "absolute", inset: 0, clipPath: clipRest }}>{panel(String(sc.before ?? ""), bi, col(pal, "paper"), col(pal, "ink"), split >= 99.5)}</div>
          <div style={{ position: "absolute", top: 0, bottom: 0, [rtl ? "right" : "left"]: `${split}%`, width: 8 * u, marginLeft: rtl ? 0 : -4 * u, marginRight: rtl ? -4 * u : 0, background: "#ffffff", boxShadow: "0 0 18px rgba(0,0,0,0.45)" }} />
          <div style={{ position: "absolute", top: 22 * u, [rtl ? "right" : "left"]: 22 * u, background: "rgba(0,0,0,0.6)", padding: `${6 * u}px ${22 * u}px`, borderRadius: 40 * u }}><T noAnim fixed role="label" size={40} color="#ffffff" fx="plain">{bl}</T></div>
          <div style={{ position: "absolute", top: 22 * u, [rtl ? "left" : "right"]: 22 * u, background: "#ffffff", padding: `${6 * u}px ${22 * u}px`, borderRadius: 40 * u }}><T noAnim fixed role="body" weight={700} size={40} color="#111111" fx="plain">{al}</T></div>
        </div>
      </Pop>
    </Stage>
  );
};
// ───────────────────────────────────────────── countdown

const Countdown: SC = ({ sc }) => {
  const ctx = useCtx();
  const { u, fps, faDigits, scene } = ctx;
  const qf = useQF();
  const a = A(ctx);
  const from = Math.max(1, Math.min(10, Math.round(num(sc.from) || 3)));
  const sec = qf / fps;
  const step = Math.min(from, Math.floor(sec / 1.0));
  const cur = from - step;
  const done = step >= from;
  const frac = sec - step;
  const size = Math.min(a.w * 0.7, a.h * 0.42, 620);
  const c = col(ctx.pal, "accent");
  const r = size * 0.44, C = 2 * Math.PI * r;
  const pop = 1 + Math.max(0, 0.18 - frac * 0.5);
  return (
    <Stage gap={30}>
      {sc.label ? <FT box={[a.w, 150]} max={70} min={34} maxLines={2} delay={0}>{String(sc.label)}</FT> : null}
      <div style={{ position: "relative", width: size * u, height: size * u }}>
        <svg width={size * u} height={size * u} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={rgba(col(ctx.pal, "ink"), 0.12)} strokeWidth={size * 0.06} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c} strokeWidth={size * 0.06} strokeLinecap="round" strokeDasharray={`${done ? C : (1 - frac) * C} ${C}`} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${pop})`, direction: "ltr" }}>
          {done && sc.finish_text ? <FT box={[size * 0.7, size * 0.5]} max={size * 0.2} min={30} maxLines={2} noAnim>{String(sc.finish_text)}</FT> : <FT box={[size * 0.6, size * 0.6]} max={size * 0.5} min={60} maxLines={1} noAnim>{fmtNumber(done ? 0 : cur, faDigits, 0)}</FT>}
        </div>
      </div>
      {scene.count < 0 ? null : null}
    </Stage>
  );
};

export const DATA_COMPONENTS: { [k: string]: SC } = {
  bar_chart: BarChart, line_chart: LineChart, donut: Donut, counter: Counter, before_after: BeforeAfter, countdown: Countdown,
};
void IconTile;
