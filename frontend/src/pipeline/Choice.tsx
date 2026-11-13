import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { PageDetail } from '../api/types'
import { useConfirm } from '../components/feedback'
import { AreaField, Badge, Button, Card, Empty, ErrorState, Link, Loading, Notice, NumberField, PageHead, SelectField, SwitchField, TextField } from '../components/ui'
import { useAction, useJobRunner, useQuery, useTitle } from '../hooks'
import { useWs } from '../pages/workspace/Workspace'
import { ErrorLine, JobLine, usePL } from './kit'
import { TemplateGallery } from './Templates'

interface Choice { label: string; to: string; loop?: boolean }
interface Node { id: string; number: number; title: string; text: string; kind: 'start' | 'story' | 'choice' | 'ending'; ending: string; choices: Choice[]; scene: Record<string, any>; caption: string; hashtags: string[]; alt: string; intended_dead_end: boolean; asset_id: number | null }
interface Story { id: number; page: number; title: string; premise: string; genre: string; language: 'fa' | 'en'; aspect: string; renderer: 'stick' | 'image'; status: 'draft' | 'planned' | 'approved'; settings: Record<string, any>; version: number; posts: number; graph?: { nodes: Node[] } }
interface Issue { code: string; node?: string; [k: string]: unknown }
interface Report { validation: { ok: boolean; errors: Issue[]; warnings: Issue[]; stats: Record<string, any> }; layout: { positions: Record<string, [number, number]>; columns: number; rows: number }; paths: string[][]; stale: string[] }
interface Opts { genres: string[]; poses: { key: string; fa: string; en: string }[]; expressions: string[]; backgrounds: { key: string; fa: string; en: string }[]; limits: { label: number; text: number } }

const ISSUE: Record<string, [string, string]> = {
  no_nodes: ['هنوز پستی نیست.', 'There are no posts yet.'],
  duplicate_id: ['شناسهٔ پست تکراری است.', 'Duplicate post id.'],
  start_count: ['باید دقیقاً یک پست شروع باشد.', 'There must be exactly one start post.'],
  start_not_first: ['پست شروع باید شمارهٔ ۱ باشد.', 'The start post must be number 1.'],
  numbering_gap: ['شماره‌گذاری پست‌ها پیوسته نیست.', 'The numbering has a gap.'],
  ending_has_choices: ['پست پایانی نباید انتخاب داشته باشد.', 'An ending must not have choices.'],
  dead_end: ['بن‌بست: این پست نه پایان است و نه انتخابی دارد.', 'Dead end: not an ending and no choice.'],
  too_many_choices: ['انتخاب‌ها از چهار تا بیشتر است.', 'More than four choices.'],
  unknown_target: ['یک انتخاب به پستی اشاره می‌کند که نیست.', 'A choice points to a post that does not exist.'],
  self_loop: ['یک انتخاب به خود همین پست برمی‌گردد.', 'A choice points back to the same post.'],
  duplicate_target: ['دو انتخاب به یک پست می‌روند.', 'Two choices lead to the same post.'],
  empty_label: ['متن یکی از انتخاب‌ها خالی است.', 'A choice has no label.'],
  backward_edge: ['یک انتخاب به پستی با شمارهٔ کوچک‌تر می‌رود (هر انتخاب باید رو به جلو باشد).', 'A choice goes back to a lower number (every choice must point forward).'],
  cycle: ['حلقه در داستان (مگر انتخابِ «تلاش دوباره» را علامت بزنید).', 'A cycle (unless you mark the choice as «try again»).'],
  unreachable: ['این پست از پست ۱ قابل رسیدن نیست.', 'This post cannot be reached from post 1.'],
  no_ending: ['هیچ پایانی ندارد.', 'There is no ending.'],
  no_path_to_ending: ['از این پست نمی‌شود به پایان رسید.', 'No ending can be reached from this post.'],
  unknown_placeholder: ['در کپشن، شمارهٔ پستی که نیست نوشته شده.', 'A caption mentions a post that does not exist.'],
  no_good_ending: ['پایان خوب ندارد.', 'No good ending.'],
  many_choices: ['بیش از سه انتخاب؛ در تصویر جا نمی‌شود.', 'More than three choices; they will not fit on the picture.'],
  choice_post_single: ['پست انتخابی فقط یک گزینه دارد.', 'A choice post with one option only.'],
  long_label: ['متن انتخاب بلند است.', 'A choice label is long.'],
  long_text: ['متن پست بلند است.', 'The post text is long.'],
  empty_text: ['متن پست خالی است.', 'The post text is empty.'],
  ending_type_missing: ['نوع پایان مشخص نیست.', 'The ending type is not set.'],
}
const tx = (k: string): [string, string] => ISSUE[k] ?? [k, k]
const KIND_COLOUR: Record<string, string> = { start: '#e8a22b', story: '#78829a', choice: '#2f7fd1', ending: '#2e9e5b' }
const END_COLOUR: Record<string, string> = { good: '#2e9e5b', bad: '#d94a3d', secret: '#8a4fd1', neutral: '#6b7280' }

/** The page's «Choice stories» tab: the list and the form that starts a new one. */
export function ChoiceListTab() {
  const { L, n } = usePL()
  const { page } = useWs()
  const nav = useNavigate()
  const q = useQuery<Story[]>(`/pages/${page.id}/choice-stories`)
  const act = useAction()
  const [f, setF] = useState({ title: '', premise: '', post_count: 14, renderer: 'stick', aspect: '4:5', genre: 'prison_escape' })
  const create = async () => {
    const s = await act.run(() => api.post<Story>(`/pages/${page.id}/choice-stories`, { ...f, language: page.languages[0] ?? 'fa' }))
    if (s) nav(`/choice/${s.id}`)
  }
  const startFrom = async (key: string) => {
    const s = await act.run(() => api.post<Story>(`/pages/${page.id}/choice-stories`, { template: key }))
    if (s) nav(`/choice/${s.id}`)
  }
  const GEN: Record<string, [string, string]> = { prison_escape: ['فرار از زندان', 'Prison escape'], zombie_survival: ['بقا در برابر زامبی', 'Zombie survival'], haunted_house: ['خانهٔ ترسناک', 'Haunted house'], detective: ['کارآگاهی', 'Detective'], space_station: ['ایستگاه فضایی', 'Space station'], custom: ['دلخواه', 'Custom'] }
  return (
    <div className="stack">
      <h2>{L('داستان‌های انتخابی', 'Choice stories')}</h2>
      <p className="muted">{L('داستان شاخه‌شاخه برای اینستاگرام: هر پست با چند انتخاب تمام می‌شود («اگر الف را بزنی برو پست ۷»). برنامه نمودار را می‌چیند، شماره‌ها را به ترتیب انتشار می‌دهد و تصویر و کپشن همهٔ پست‌ها را می‌سازد. چیزی خودکار منتشر نمی‌شود.',
        'A branching story for Instagram: each post ends with choices («if you pick A go to post 7»). The app lays out the graph, numbers the posts in posting order and makes every picture and caption. Nothing is published automatically.')}</p>
      <Card title={L('داستان‌های آماده', 'Ready-made stories')}>
        <div className="stack-sm">
          <p className="small muted">{L('داستان‌هایی که کامل نوشته شده‌اند (متن، انتخاب‌ها، پایان‌ها و شخصیت‌های اورجینال). بدون هیچ مدلی کار می‌کنند: شخصیت‌ها با هویتِ قفل‌شده ساخته می‌شوند و بعداً هر کلمه را می‌توانی عوض کنی.',
            'Complete, hand-written stories (text, choices, endings and original characters). They work with no model: the characters come with a locked identity and you can change every word afterwards.')}</p>
          <TemplateGallery kind="story" busy={act.busy} onPick={startFrom} />
        </div>
      </Card>
      <Card title={L('داستان تازه', 'New story')}>
        <div className="stack-sm">
          <TextField label={L('عنوان', 'Title')} value={f.title} onChange={(v) => setF({ ...f, title: v })} />
          <AreaField label={L('ایده و موقعیت', 'Idea and situation')} compact value={f.premise} onChange={(v) => setF({ ...f, premise: v })} />
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <SelectField label={L('ژانر', 'Genre')} value={f.genre} onChange={(v) => setF({ ...f, genre: v })} options={Object.keys(GEN).map((k) => ({ value: k, label: L(...GEN[k]) }))} />
            <NumberField label={L('تعداد پست‌ها', 'Number of posts')} min={6} max={60} value={f.post_count} onChange={(v) => setF({ ...f, post_count: v ?? 14 })} />
            <SelectField label={L('نوع تصویر', 'Picture style')} value={f.renderer} onChange={(v) => setF({ ...f, renderer: v })} options={[{ value: 'stick', label: L('آدمک چوبی (با کد، بدون GPU)', 'Stick figures (by code, no GPU)') }, { value: 'image', label: L('مدل تصویر با هویت قفل‌شده', 'Image model with locked identities') }]} />
            <SelectField label={L('اندازه', 'Size')} value={f.aspect} onChange={(v) => setF({ ...f, aspect: v })} options={[{ value: '4:5', label: '4:5' }, { value: '1:1', label: '1:1' }, { value: '9:16', label: '9:16' }]} />
          </div>
          <div><Button variant="primary" icon="plus" busy={act.busy} disabled={!f.title.trim()} onClick={create}>{L('ساخت', 'Create')}</Button></div>
          <ErrorLine text={act.error} />
        </div>
      </Card>
      {q.error && !q.data ? <ErrorState error={q.error} onRetry={q.reload} /> : !q.data ? <Loading /> : q.data.length === 0 ? <Empty icon="film" title={L('هنوز داستانی نیست', 'No stories yet')} /> : (
        <div className="stack-sm">
          {q.data.map((s) => (
            <Link key={s.id} to={`/choice/${s.id}`} className="card card-link row between">
              <span><b>{s.title}</b> <span className="muted small">· {n(s.posts)} {L('پست', 'posts')}</span></span>
              <Badge tone={s.status === 'approved' ? 'ok' : s.status === 'planned' ? 'warn' : 'neutral'}>{s.status === 'approved' ? L('تأییدشده', 'Approved') : s.status === 'planned' ? L('در حال ویرایش', 'In progress') : L('پیش‌نویس', 'Draft')}</Badge>
            </Link>))}
        </div>
      )}
    </div>
  )
}

/** The editor of one choice story: plan, graph map, post editor, review (rules), play-through, pictures and the posting package. */
export default function ChoiceEditor() {
  const { L, n } = usePL()
  const { id } = useParams()
  const confirm = useConfirm()
  const q = useQuery<Story>(`/choice-stories/${id}`)
  const rep = useQuery<Report>(`/choice-stories/${id}/report`)
  const opts = useQuery<Opts>('/choice/options')
  const page = useQuery<PageDetail>(q.data ? `/pages/${q.data.page}` : null)
  const act = useAction()
  const [sel, setSel] = useState<string>('')
  const [instruction, setInstruction] = useState('')
  const [previews, setPreviews] = useState<Record<string, string>>({})
  const reloadAll = () => { q.reload(); rep.reload() }
  const planJob = useJobRunner({ onFinished: reloadAll })
  const capJob = useJobRunner({ onFinished: reloadAll })
  const renderJob = useJobRunner({ onFinished: reloadAll })
  const pkgJob = useJobRunner<{ url: string; posts: number }>({ onFinished: reloadAll })
  useTitle(q.data?.title)
  const story = q.data
  const nodes = story?.graph?.nodes ?? []
  useEffect(() => { if (nodes.length && !nodes.find((x) => x.id === sel)) setSel(nodes[0].id) }, [nodes.length]) // eslint-disable-line react-hooks/exhaustive-deps
  const byId = useMemo(() => Object.fromEntries(nodes.map((x) => [x.id, x])), [nodes])
  if (q.error && !story) return <ErrorState error={q.error} onRetry={q.reload} />
  if (!story) return <Loading />
  const v = rep.data?.validation
  const issuesOf = (nid: string) => (v ? [...v.errors, ...v.warnings].filter((i) => i.node === nid) : [])
  const errNodes = new Set((v?.errors ?? []).map((i) => i.node))
  const post = async (path: string, body: unknown = {}) => { const s = await act.run(() => api.post<Story>(`/choice-stories/${story.id}${path}`, body)); if (s) { q.setData(s); rep.reload() } return s }
  const op = (body: Record<string, unknown>) => post('/ops', body)
  const cur = byId[sel]
  const num = (nid: string) => byId[nid]?.number ?? 0
  return (
    <div className="stack">
      <PageHead title={story.title} crumbs={[{ label: L('صفحه‌ها', 'Pages'), to: '/pages' }, { label: page.data?.name ?? '…', to: `/pages/${story.page}/choice` }, { label: story.title }]}>
        <div className="row">
          <Badge tone={story.status === 'approved' ? 'ok' : story.status === 'planned' ? 'warn' : 'neutral'}>{story.status === 'approved' ? L('تأییدشده', 'Approved') : story.status === 'planned' ? L('در حال ویرایش', 'In progress') : L('پیش‌نویس', 'Draft')}</Badge>
          <Badge>{n(nodes.length)} {L('پست', 'posts')}</Badge>
          {v && <Badge tone={v.ok ? 'ok' : 'err'}>{v.ok ? L('قواعد درست است', 'Rules satisfied') : `${n(v.errors.length)} ${L('خطا', 'errors')}`}</Badge>}
        </div>
      </PageHead>
      <Card title={L('۱ · طراحی نمودار', '1 · Plan the graph')}>
        <div className="stack-sm">
          <p className="small muted">{L('هوش مصنوعی نمودار شاخه‌ها را می‌چیند: بدون بن‌بست، همه‌چیز از پست ۱ قابل رسیدن، شماره‌ها به ترتیب انتشار و هر انتخاب رو به جلو. اگر مدل جواب معتبر ندهد، یک طرح پایه ساخته می‌شود و همچنان همهٔ آن را می‌توانید ویرایش کنید.',
            'The AI lays out the branches: no dead ends, everything reachable from post 1, numbers in posting order and every choice pointing forward. If the model gives an invalid answer a basic plan is made instead, and you can still edit all of it.')}</p>
          <TextField label={L('یادداشت برای طراح (اختیاری)', 'Note for the planner (optional)')} value={instruction} onChange={setInstruction} />
          <div className="row">
            <Button icon="spark" variant="primary" busy={planJob.busy} onClick={async () => { if (nodes.length === 0 || await confirm({ title: L('نمودار فعلی جایگزین شود؟ (نسخهٔ قبلی نگه داشته می‌شود)', 'Replace the current graph? (the old one is kept as a version)'), message: '', danger: true })) planJob.start(() => api.post(`/choice-stories/${story.id}/plan`, { instruction })) }}>{nodes.length ? L('طراحی دوباره', 'Plan again') : L('طراحی نمودار', 'Plan the graph')}</Button>
            <Button icon="edit" busy={capJob.busy} disabled={!nodes.length} onClick={() => capJob.start(() => api.post(`/choice-stories/${story.id}/captions`, {}))}>{L('نوشتن کپشن با هوش مصنوعی', 'Write the captions with AI')}</Button>
            <Button variant="ghost" disabled={!nodes.length} busy={act.busy} onClick={() => post('/captions/reset')}>{L('کپشن ساده (بدون مدل)', 'Plain captions (no model)')}</Button>
          </div>
          <details>
            <summary className="small">{L('یا با یک داستان آماده شروع کن (بدون مدل)', 'Or start from a ready-made story (no model)')}</summary>
            <div style={{ marginTop: 8 }}>
              <TemplateGallery kind="story" busy={act.busy} onPick={async (key) => { if (nodes.length === 0 || await confirm({ title: L('نمودار فعلی با داستان آماده جایگزین شود؟', 'Replace the current graph with the ready-made story?'), message: L('نسخهٔ قبلی نگه داشته می‌شود.', 'The old one is kept as a version.'), danger: true })) post('/template', { key }) }} />
            </div>
          </details>
          <JobLine job={planJob.job} offline={planJob.offline} /><JobLine job={capJob.job} offline={capJob.offline} />
          {planJob.result && (planJob.result as any).fallback && <Notice tone="warn">{(planJob.result as any).provider === 'template' ? L('مدل در دسترس نبود یا جواب معتبر نداد؛ به‌جایش یک داستان آمادهٔ همین ژانر گذاشته شد. می‌توانید هر بخشش را ویرایش کنید.', 'No model was available (or its answer was invalid); a ready-made story of this genre was used instead. You can edit any part of it.') : L('مدل جواب معتبر نداد؛ طرح پایه ساخته شد. می‌توانید آن را ویرایش کنید.', 'The model gave no valid answer; a basic plan was made. You can edit it.')}</Notice>}
        </div>
      </Card>
      {nodes.length > 0 && (
        <>
          <Card title={L('۲ · نقشهٔ داستان (بر اساس شمارهٔ پست)', '2 · Story map (by post number)')}>
            {rep.data && <GraphMap nodes={nodes} layout={rep.data.layout} sel={sel} onSel={setSel} errNodes={errNodes} />}
          </Card>
          {cur && (
            <PostEditor key={cur.id + ':' + story.version} story={story} node={cur} nodes={nodes} opts={opts.data} issues={issuesOf(cur.id)} op={op} busy={act.busy} img={previews[cur.id + ':' + story.id] ?? ''} setImg={(u) => setPreviews((p) => ({ ...p, [cur.id + ':' + story.id]: u }))} cast={(page.data?.characters ?? []).map((c) => c.name)} />
          )}
          <Card title={L('۳ · بازبینی قواعد', '3 · Review the rules')}>
            <div className="stack-sm">
              {v && v.errors.length === 0 && v.warnings.length === 0 && <Notice tone="ok">{L('همهٔ قواعد برقرار است.', 'Every rule is satisfied.')}</Notice>}
              {[...(v?.errors ?? []).map((i) => ({ ...i, err: true })), ...(v?.warnings ?? []).map((i) => ({ ...i, err: false }))].map((i, k) => (
                <div key={k} className="row" style={{ gap: 8 }}>
                  <Badge tone={i.err ? 'err' : 'warn'}>{i.err ? L('خطا', 'Error') : L('هشدار', 'Warning')}</Badge>
                  <span>{L(...tx(i.code))}</span>
                  {i.node && <button className="linklike" onClick={() => setSel(i.node as string)}>{L('پست', 'post')} {n(num(i.node as string))}</button>}
                </div>))}
              {rep.data && (
                <div className="small muted">
                  {L('مسیرهای ممکن: ', 'Possible routes: ')}{n(rep.data.validation.stats.paths)} · {L('کوتاه‌ترین: ', 'shortest: ')}{n(rep.data.validation.stats.shortest_path)} {L('پست', 'posts')} · {L('بلندترین: ', 'longest: ')}{n(rep.data.validation.stats.longest_path)} · {L('پایان‌ها: ', 'endings: ')}{Object.entries(rep.data.validation.stats.endings ?? {}).map(([k, c]) => `${k} ${c}`).join('، ')}
                </div>)}
              <div className="row">
                {story.status !== 'approved' ? <Button variant="primary" icon="check" busy={act.busy} disabled={!v?.ok} onClick={() => post('/approve')}>{L('تأیید نمودار', 'Approve the graph')}</Button>
                  : <Button busy={act.busy} onClick={() => post('/revoke')}>{L('برداشتن تأیید', 'Withdraw approval')}</Button>}
              </div>
            </div>
          </Card>
          {rep.data && <PlayThrough nodes={nodes} />}
          <Card title={L('۴ · تصویرها و بستهٔ انتشار', '4 · Pictures and the posting package')}>
            <div className="stack-sm">
              <p className="small muted">{L('تصویر هر پست شمارهٔ پست، متن و انتخاب‌ها را دارد. اگر شماره‌ها عوض شود فقط تصویر پست‌های اثرپذیرفته دوباره ساخته می‌شود. بسته: تصویرها به ترتیب شماره، کپشن‌ها با شمارهٔ درست، زمان‌بندی و نقشهٔ نمودار. بارگذاری دستی است.',
                'Each picture carries the post number, the text and the choices. If numbers change only the affected posts are drawn again. The package: the pictures in number order, captions with the right numbers, the schedule and the graph map. Uploading is by hand.')}</p>
              <div className="row">
                <Button icon="image" busy={renderJob.busy} onClick={() => renderJob.start(() => api.post(`/choice-stories/${story.id}/render`, {}))}>{L('ساخت تصویرها', 'Render the pictures')}{rep.data && rep.data.stale.length > 0 ? ` (${n(rep.data.stale.length)})` : ''}</Button>
                <Button variant="primary" icon="download" busy={pkgJob.busy} disabled={story.status !== 'approved'} onClick={() => pkgJob.start(() => api.post(`/choice-stories/${story.id}/package`, {}))}>{L('ساخت بستهٔ انتشار', 'Build the posting package')}</Button>
                {pkgJob.result?.url && <a className="btn" href={pkgJob.result.url} download>{L('دریافت بسته', 'Download the package')}</a>}
              </div>
              {story.status !== 'approved' && <div className="small muted">{L('بسته فقط برای نمودار تأییدشده ساخته می‌شود.', 'The package is built for an approved graph only.')}</div>}
              <JobLine job={renderJob.job} offline={renderJob.offline} /><JobLine job={pkgJob.job} offline={pkgJob.offline} />
              <ErrorLine text={act.error} />
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

function GraphMap({ nodes, layout, sel, onSel, errNodes }: { nodes: Node[]; layout: Report['layout']; sel: string; onSel: (id: string) => void; errNodes: Set<string | undefined> }) {
  const { n } = usePL()
  const CW = 150, RH = 92, BW = 112, BH = 58, PAD = 16
  const pos = layout.positions
  const W = PAD * 2 + layout.columns * CW
  const H = PAD * 2 + Math.max(layout.rows, 1) * RH
  const xy = (id: string) => ({ x: PAD + (pos[id]?.[0] ?? 0) * CW, y: PAD + (pos[id]?.[1] ?? 0) * RH })
  return (
    <div style={{ overflowX: 'auto' }} dir="ltr">
      <svg width={W} height={H} role="img" aria-label="story map">
        <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#78829a" /></marker></defs>
        {nodes.flatMap((nd) => nd.choices.map((c, i) => {
          if (!pos[c.to]) return null
          const a = xy(nd.id), b = xy(c.to)
          return <path key={nd.id + i} d={`M${a.x + BW},${a.y + BH / 2} C${a.x + BW + 30},${a.y + BH / 2} ${b.x - 30},${b.y + BH / 2} ${b.x},${b.y + BH / 2}`} fill="none" stroke={c.loop ? '#8a4fd1' : '#78829a'} strokeWidth="2" markerEnd="url(#arr)" strokeDasharray={c.loop ? '5 4' : undefined} />
        }))}
        {nodes.map((nd) => {
          const p = xy(nd.id)
          const col = nd.kind === 'ending' ? END_COLOUR[nd.ending] ?? END_COLOUR.neutral : KIND_COLOUR[nd.kind]
          return (
            <g key={nd.id} transform={`translate(${p.x},${p.y})`} onClick={() => onSel(nd.id)} style={{ cursor: 'pointer' }} tabIndex={0} role="button" aria-label={`post ${nd.number}`} onKeyDown={(e) => { if (e.key === 'Enter') onSel(nd.id) }}>
              <rect width={BW} height={BH} rx="12" fill={col} stroke={errNodes.has(nd.id) ? '#ff2d2d' : nd.id === sel ? '#ffffff' : '#1f2430'} strokeWidth={errNodes.has(nd.id) || nd.id === sel ? 4 : 2} />
              <text x={BW / 2} y="25" textAnchor="middle" fill="#fff" fontWeight="700" fontSize="20">{n(nd.number)}</text>
              <text x={BW / 2} y="46" textAnchor="middle" fill="#fff" fontSize="12">{(nd.title || nd.id).slice(0, 14)}</text>
            </g>)
        })}
      </svg>
    </div>
  )
}

function PostEditor({ story, node, nodes, opts, issues, op, busy, img, setImg, cast }: { story: Story; node: Node; nodes: Node[]; opts: Opts | undefined; issues: Issue[]; op: (b: Record<string, unknown>) => Promise<Story | undefined>; busy: boolean; img: string; setImg: (u: string) => void; cast: string[] }) {
  const { L, n, lang } = usePL()
  const confirm = useConfirm()
  const [d, setD] = useState({ title: node.title, text: node.text, ending: node.ending, kind: node.kind, caption: node.caption, scene: node.scene as Record<string, any>, hashtags: node.hashtags.join(' ') })
  const [imgBusy, setImgBusy] = useState(false)
  const [imgErr, setImgErr] = useState('')
  const targets = nodes.filter((x) => x.id !== node.id).map((x) => ({ value: x.id, label: `${n(x.number)} · ${x.title || x.id}` }))
  const save = () => op({ op: 'update_node', id: node.id, fields: { title: d.title, text: d.text, ending: d.ending, kind: d.kind === 'ending' || d.ending ? 'ending' : d.kind === 'start' ? 'start' : 'story', caption: d.caption, scene: d.scene, hashtags: d.hashtags.split(/\s+/).filter(Boolean) } })
  const preview = async () => {
    setImgBusy(true); setImgErr('')
    try { const r = await api.get<{ url: string }>(`/choice-stories/${story.id}/posts/${node.id}/preview`); setImg(r.url + '?t=' + Date.now()) } catch (e) { setImgErr((e as Error).message) } finally { setImgBusy(false) }
  }
  const sc = (k: string, v: unknown) => setD({ ...d, scene: { ...d.scene, [k]: v } })
  return (
    <Card title={`${L('پست', 'Post')} ${n(node.number)} · ${node.id}`} actions={issues.length > 0 ? <Badge tone="err">{n(issues.length)}</Badge> : undefined}>
      <div className="grid2">
        <div className="stack-sm">
          <TextField label={L('عنوان کوتاه', 'Short title')} value={d.title} onChange={(v) => setD({ ...d, title: v })} />
          <AreaField label={`${L('متن روی تصویر', 'Text on the picture')} (${n(d.text.length)}/${n(opts?.limits.text ?? 220)})`} value={d.text} onChange={(v) => setD({ ...d, text: v })} />
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <SelectField label={L('نوع پایان', 'Ending type')} value={d.ending} onChange={(v) => setD({ ...d, ending: v, kind: v ? 'ending' : d.kind === 'ending' ? 'story' : d.kind })} options={[{ value: '', label: L('(پایان نیست)', '(not an ending)') }, { value: 'good', label: L('خوب', 'Good') }, { value: 'bad', label: L('بد', 'Bad') }, { value: 'secret', label: L('مخفی', 'Secret') }, { value: 'neutral', label: L('خنثی', 'Neutral') }]} />
            <SelectField label={L('پس‌زمینه', 'Background')} value={d.scene.location ?? ''} onChange={(v) => sc('location', v)} options={[{ value: '', label: L('(خودکار)', '(automatic)') }, ...(opts?.backgrounds ?? []).map((b) => ({ value: b.key, label: lang === 'fa' ? b.fa : b.en }))]} />
            <SelectField label={L('ژست', 'Pose')} value={d.scene.pose ?? ''} onChange={(v) => sc('pose', v)} options={[{ value: '', label: L('(از متن)', '(from the text)') }, ...(opts?.poses ?? []).map((p) => ({ value: p.key, label: lang === 'fa' ? p.fa : p.en }))]} />
            <SelectField label={L('حالت چهره', 'Expression')} value={d.scene.expression ?? ''} onChange={(v) => sc('expression', v)} options={[{ value: '', label: L('(از متن)', '(from the text)') }, ...(opts?.expressions ?? []).map((x) => ({ value: x, label: x }))]} />
          </div>
          {cast.length > 0 && (
            <div className="stack-sm">
              <b className="small">{L('شخصیت‌های این صحنه (تا ۲ نفر)', 'Characters in this scene (up to 2)')}</b>
              <div className="row" style={{ flexWrap: 'wrap', gap: 14 }}>
                {cast.map((nm) => {
                  const cur: string[] = d.scene.characters ?? []
                  const on = cur.includes(nm)
                  return (
                    <label key={nm} className="row nw small" style={{ gap: 6 }}>
                      <input type="checkbox" checked={on} disabled={!on && cur.length >= 2} onChange={(e) => sc('characters', e.target.checked ? [...cur, nm] : cur.filter((x) => x !== nm))} />{nm}
                    </label>
                  )
                })}
              </div>
            </div>
          )}
          <AreaField label={L('کپشن (به جای شمارهٔ پست‌ها {go:شناسه} بنویسید؛ شماره خودکار پر می‌شود)', 'Caption (write {go:id} instead of post numbers; the number is filled in for you)')} value={d.caption} onChange={(v) => setD({ ...d, caption: v })} />
          <TextField label={L('هشتگ‌ها', 'Hashtags')} value={d.hashtags} onChange={(v) => setD({ ...d, hashtags: v })} />
          <div className="row">
            <Button variant="primary" icon="save" busy={busy} onClick={save}>{L('ذخیره', 'Save')}</Button>
            <Button icon="image" busy={imgBusy} onClick={async () => { await save(); preview() }}>{L('پیش‌نمایش تصویر', 'Preview the picture')}</Button>
            <Button variant="ghost" icon="trash" onClick={async () => { if (await confirm({ title: L('این پست حذف شود؟', 'Delete this post?'), message: '', danger: true })) op({ op: 'remove_node', id: node.id }) }}>{L('حذف پست', 'Delete the post')}</Button>
          </div>
          {issues.map((i, k) => <Notice key={k} tone="warn">{L(...tx(i.code))}</Notice>)}
        </div>
        <div className="stack-sm">
          <b>{L('انتخاب‌ها', 'Choices')}</b>
          {node.choices.map((c, i) => (
            <ChoiceRow key={i + c.to + c.label} c={c} targets={targets} onSave={(label, to, loop) => op({ op: 'set_choice', id: node.id, index: i, label, to, loop })} onRemove={() => op({ op: 'remove_choice', id: node.id, index: i })} maxLabel={opts?.limits.label ?? 28} />
          ))}
          {node.kind !== 'ending' && node.choices.length < 4 && <Button size="sm" icon="plus" disabled={!targets.length} onClick={() => op({ op: 'set_choice', id: node.id, index: node.choices.length, label: L('انتخاب تازه', 'New choice'), to: targets[0]?.value ?? '' })}>{L('افزودن انتخاب', 'Add a choice')}</Button>}
          <Button size="sm" variant="ghost" icon="plus" onClick={() => op({ op: 'add_node', node: { title: L('پست تازه', 'New post'), text: '', kind: 'story' } })}>{L('پست تازهٔ بی‌اتصال (بعد وصلش کنید)', 'New unconnected post (connect it afterwards)')}</Button>
          {imgErr && <Notice tone="warn">{imgErr}</Notice>}
          {img && <img src={img} alt={L('پیش‌نمایش پست', 'Post preview')} style={{ maxWidth: '100%', borderRadius: 12 }} />}
        </div>
      </div>
    </Card>
  )
}

function ChoiceRow({ c, targets, onSave, onRemove, maxLabel }: { c: Choice; targets: { value: string; label: string }[]; onSave: (label: string, to: string, loop: boolean) => void; onRemove: () => void; maxLabel: number }) {
  const { L, n } = usePL()
  const [label, setLabel] = useState(c.label)
  const [to, setTo] = useState(c.to)
  const [loop, setLoop] = useState(!!c.loop)
  const dirty = label !== c.label || to !== c.to || loop !== !!c.loop
  return (
    <div className="card soft stack-sm">
      <TextField label={`${L('متن انتخاب', 'Choice label')} (${n(label.length)}/${n(maxLabel)})`} value={label} onChange={setLabel} />
      <SelectField label={L('برود به پست', 'Goes to post')} value={to} onChange={setTo} options={targets} />
      <SwitchField label={L('«تلاش دوباره» (حلقهٔ عمدی)', '«Try again» (an intended loop)')} checked={loop} onChange={setLoop} />
      <div className="row"><Button size="sm" variant="primary" disabled={!dirty} onClick={() => onSave(label, to, loop)}>{L('ثبت', 'Apply')}</Button><Button size="sm" variant="ghost" icon="trash" onClick={onRemove}>{L('حذف', 'Remove')}</Button></div>
    </div>
  )
}

function PlayThrough({ nodes }: { nodes: Node[] }) {
  const { L, n } = usePL()
  const start = nodes.find((x) => x.kind === 'start') ?? nodes[0]
  const [trail, setTrail] = useState<string[]>([start.id])
  useEffect(() => { setTrail([start.id]) }, [start.id])
  const by = Object.fromEntries(nodes.map((x) => [x.id, x]))
  const cur = by[trail[trail.length - 1]]
  if (!cur) return null
  return (
    <Card title={L('۳ ب · امتحان داستان (مثل خواننده)', '3b · Play it like a reader')}>
      <div className="stack-sm">
        <div className="row"><Badge tone="primary">{L('پست', 'Post')} {n(cur.number)}</Badge><b>{cur.title}</b></div>
        <p>{cur.text}</p>
        {cur.kind === 'ending' ? <Notice tone={cur.ending === 'good' ? 'ok' : cur.ending === 'bad' ? 'err' : 'info'}>{L('پایان ', 'Ending ')}{cur.ending}</Notice> : (
          <div className="row" style={{ flexWrap: 'wrap' }}>{cur.choices.map((c, i) => <Button key={i} onClick={() => setTrail([...trail, c.to])}>{c.label} ← {L('پست', 'post')} {n(by[c.to]?.number)}</Button>)}</div>
        )}
        <div className="row"><Button size="sm" variant="ghost" onClick={() => setTrail([start.id])}>{L('از اول', 'Restart')}</Button>{trail.length > 1 && <Button size="sm" variant="ghost" onClick={() => setTrail(trail.slice(0, -1))}>{L('یک قدم عقب', 'Back')}</Button>}
          <span className="small muted">{trail.map((t) => n(by[t]?.number)).join(' → ')}</span></div>
      </div>
    </Card>
  )
}
