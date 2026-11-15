// The component registry: scene id -> the React component that draws it. A test (tests/test_motion_plan.py) keeps this list identical to
// instai/motion_plan/components.py - one id on one side and not the other fails the build.
// SOURCE: ported from NMarketing:motion/remotion/src/registry.ts (the 19 components InstAI ships).
import type React from "react";
import { DATA_COMPONENTS } from "./comp-data";
import { OVERLAY_BODIES, TEXT_COMPONENTS } from "./comp-text";
import { SCENES } from "./scenes";
import type { Scene } from "./types";

export type SceneComponent = React.FC<{ sc: Scene }>;

export const COMPONENTS: { [id: string]: SceneComponent } = {
  ...SCENES,
  ...DATA_COMPONENTS,
  ...TEXT_COMPONENTS,
};

/** components that can also be laid over another scene (placed by anchor inside the safe area) */
export const OVERLAYS: { [id: string]: SceneComponent } = OVERLAY_BODIES;
