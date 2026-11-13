import React from 'react'
import { Composition } from 'remotion'
import { COMPOSITIONS, FPS, metaFor } from './catalog'
import { DEFAULT_KIT } from './kit/theme'

// Every composition of the catalog, registered with Remotion. The length and the size are decided from the props (`size`, the content, the
// style's motion), exactly as the preview in the InstAI page decides them.
export const Root: React.FC = () => (
  <>
    {COMPOSITIONS.map((c) => (
      <Composition
        key={c.id}
        id={c.id}
        component={c.component as React.FC<any>}
        width={1920}
        height={1080}
        fps={FPS}
        durationInFrames={150}
        defaultProps={{ kit: DEFAULT_KIT, size: 'landscape', ...c.defaults('fa') } as any}
        calculateMetadata={async ({ props }: { props: any }) => metaFor(c.id, props)}
      />
    ))}
  </>
)
