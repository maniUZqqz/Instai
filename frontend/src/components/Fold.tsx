import type { ReactNode } from 'react'

/** A card that opens and closes (a native <details>: keyboard, screen readers and "find in page" work without any script). It keeps the long, rarely needed
 *  parts of a page (estimates, finished jobs, the full catalogue) one line tall until the owner asks for them. `badge` stays visible when it is closed. */
export function Fold({ title, badge, open, testid, children }: { title: ReactNode; badge?: ReactNode; open?: boolean; testid?: string; children: ReactNode }) {
  return (
    <details className="card fold" open={open} data-testid={testid}>
      <summary>
        <span className="strong">{title}</span>
        {badge}
      </summary>
      <div className="stack fold-body">{children}</div>
    </details>
  )
}
