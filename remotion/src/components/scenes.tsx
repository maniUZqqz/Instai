// The basic scene templates: episode card, key-takeaways list, quote, big number, series sting.
// SOURCE: ported from NMarketing:motion/remotion/src/scenes.tsx (title, list, quote, stat, logo), adapted for InstAI: the title is the EPISODE CARD
// (series, episode number, title, hook line), the logo is the SERIES STING (a series name / logo, not a shop brand), the big number carries the honesty
// chip. The shop scenes (compare, product, app, cta) were left out.
import React from "react";
import { Img, Easing } from "remotion";
import { useAsset, useCtx, useQF } from "./ctx";
import { Badge, Pop, Rule, SourceNote, Stage } from "./parts";
import { Card, T } from "./text";
import type { Scene } from "./types";
import { clamp, col, fitSize, fmtNumber, rgba, toEnDigits } from "./util";

type SC = React.FC<{ sc: Scene }>;

// ───────────────────────────────────────────── scene templates

/** The episode card: a number badge with the series name, the episode title, an accent rule and the hook (cliffhanger) line. */
const Title: SC = ({ sc }) => {
  const { wide, rtl, faDigits, spec, u } = useCtx();
  const series = spec.series ?? {};
  const seriesName = String(sc.series || series.title || "");
  const ep = Math.round(Number(sc.number ?? series.episode ?? 0)) || 0;
  const title = String(sc.title || series.episode_title || "");
  const hook = String(sc.hook ?? sc.subtitle ?? "");
  const epLabel = ep ? (rtl ? `قسمت ${fmtNumber(ep, faDigits, 0)}` : `Episode ${ep}`) : "";
  return (
    <Stage gap={34}>
      {sc.kicker ? <T role="label" size={46} delay={0} color="accent" upper>{String(sc.kicker)}</T> : null}
      {ep || seriesName ? (
        <Pop delay={0}>
          <div style={{ display: "flex", alignItems: "center", gap: 26 * u, direction: rtl ? "rtl" : "ltr" }}>
            {ep ? <Badge n={fmtNumber(ep, faDigits, 0)} size={wide ? 128 : 150} /> : null}
            <div style={{ display: "flex", flexDirection: "column", gap: 4 * u, alignItems: "flex-start" }}>
              {seriesName ? <T noAnim role="label" size={wide ? 50 : 56} color="accent" align="start" upper>{seriesName}</T> : null}
              {epLabel ? <T noAnim role="body" size={wide ? 40 : 44} align="start">{epLabel}</T> : null}
            </div>
          </div>
        </Pop>
      ) : null}
      <T size={fitSize(title, wide ? 124 : 138, 16)} delay={3} maxWidth={wide ? 1500 : 940}>{title}</T>
      <Rule delay={10} />
      {hook ? <T role="body" size={wide ? 52 : 56} delay={16} maxWidth={wide ? 1200 : 900}>{hook}</T> : null}
    </Stage>
  );
};

const List: SC = ({ sc }) => {
  const { u, wide, style, rtl, fps, pal } = useCtx();
  const items: string[] = (sc.items || []).map(String).slice(0, 6);
  const numbered = sc.numbered !== false;
  const bodySize = items.length > 4 ? 46 : 54;
  const two = wide && items.length > 3;
  const stag = Math.max(4, style.motion.stagger);
  return (
    <Stage gap={30}>
      {sc.title ? <T size={fitSize(String(sc.title), wide ? 92 : 100, 20)} delay={0} maxWidth={wide ? 1500 : 940}>{String(sc.title)}</T> : null}
      <div style={{ width: "100%", display: "grid", gridTemplateColumns: two ? "1fr 1fr" : "1fr", gap: 22 * u, direction: rtl ? "rtl" : "ltr" }}>
        {items.map((it, i) => (
          <Card key={i} i={i} delay={Math.round(fps * 0.35) + i * stag} pad={22} style={{ display: "flex", alignItems: "center", gap: 22 * u }}>
            {numbered ? <Badge n={String(i + 1)} size={bodySize * 1.45} /> : <div style={{ width: 14 * u, height: 14 * u, background: col(pal, "accent"), borderRadius: "50%" }} />}
            <T noAnim role="body" align="start" size={bodySize} weight={600} style={{ flex: 1 }}>{it}</T>
          </Card>
        ))}
      </div>
    </Stage>
  );
};

const Quote: SC = ({ sc }) => {
  const { wide, u } = useCtx();
  const text = String(sc.text || "");
  return (
    <Stage gap={22}>
      <T size={wide ? 220 : 280} delay={0} color="accent" fx="plain" style={{ lineHeight: 0.7, height: (wide ? 120 : 170) * u }}>{"“"}</T>
      <T size={fitSize(text, wide ? 76 : 84, 60, 0.5)} delay={6} lh={1.4} maxWidth={wide ? 1500 : 920}>{text}</T>
      {sc.author ? <T role="label" size={46} delay={30} color="accent" fx="plain">{`— ${sc.author}`}</T> : null}
    </Stage>
  );
};

const Stat: SC = ({ sc }) => {
  const ctx = useCtx();
  const { fps, u, faDigits, wide } = ctx;
  const qf = useQF();
  const target = Number(toEnDigits(String(sc.value ?? 0)).replace(/[^0-9.\-]/g, "")) || 0;
  const dec = Number(sc.decimals ?? (String(sc.value ?? "").includes(".") ? 1 : 0));
  const prog = sc.count_up === false ? 1 : Easing.out(Easing.cubic)(clamp((qf - 6) / (fps * 1.5)));
  const shown = fmtNumber(target * prog, faDigits, dec);
  const base = fitSize(shown + String(sc.suffix || "") + String(sc.prefix || ""), wide ? 300 : 340, 6, 0.4);
  return (
    <Stage gap={26}>
      {sc.kicker ? <T role="label" size={46} delay={0} color="accent" upper>{String(sc.kicker)}</T> : null}
      <Pop delay={2}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "center", gap: 10 * u, direction: "ltr" }}>
          {sc.prefix ? <T noAnim size={base * 0.4}>{String(sc.prefix)}</T> : null}
          <T noAnim size={base}>{shown}</T>
          {sc.suffix ? <T noAnim size={base * 0.5} color="accent">{String(sc.suffix)}</T> : null}
        </div>
      </Pop>
      <Rule delay={14} w={200} />
      {sc.label ? <T role="body" size={wide ? 54 : 60} delay={18} maxWidth={wide ? 1300 : 900}>{String(sc.label)}</T> : null}
      <SourceNote sc={sc} />
    </Stage>
  );
};

/** The series sting: rings that pulse out of the series logo (or its name written big), and a tagline. */
const LogoSting: SC = ({ sc }) => {
  const ctx = useCtx();
  const { u, W, H, pal, spec, fps } = ctx;
  const qf = useQF();
  const logo = useAsset(sc.logo);
  const name = String(sc.title || spec.series?.title || "");
  const rings = [0, 1, 2].map((i) => {
    const t = ((qf / fps) * 0.8 + i / 3) % 1;
    return <div key={i} style={{ position: "absolute", left: "50%", top: "50%", width: Math.min(W, H) * (0.3 + t * 0.9), height: Math.min(W, H) * (0.3 + t * 0.9), marginLeft: -Math.min(W, H) * (0.3 + t * 0.9) / 2, marginTop: -Math.min(W, H) * (0.3 + t * 0.9) / 2, borderRadius: "50%", border: `${5 * u}px solid ${rgba(col(pal, "accent"), (1 - t) * 0.7)}` }} />;
  });
  return (
    <>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, bottom: 0, transform: "translateY(-6%)" }}>{rings}</div>
      <Stage gap={30}>
        <Pop delay={2}>{logo ? <Img src={logo} style={{ height: Math.min(W, H) * 0.34, maxWidth: W * 0.7, objectFit: "contain" }} /> : <T noAnim size={fitSize(name, 170, 10)}>{name}</T>}</Pop>
        {logo && name ? <T size={78} delay={14}>{name}</T> : null}
        {sc.tagline ? <T role="body" size={52} delay={22} maxWidth={W * 0.8 / u}>{String(sc.tagline)}</T> : null}
      </Stage>
    </>
  );
};

export const SCENES: { [k: string]: SC } = {
  title: Title, list: List, quote: Quote, stat: Stat, logo: LogoSting,
};
