// The component library as the InstAI PAGE sees it: for every ready-made component (remotion/src/components/registry.ts) its labels (fa + en), its form fields, a sample
// scene in both languages and its usual duration. The page lists them as compositions («SceneTitle», «SceneKineticTitle» ...); each one plays ONE scene through ScenePlan,
// the very code that renders a motion-graphics shot of an episode. instai/motion_plan/components.py is the server's copy of the same list (a test keeps them identical).
// Nothing here imports Remotion: the file is also read by the page and by tests.

export type DefField = {
  key: string
  type: 'text' | 'textarea' | 'lines' | 'rows' | 'number' | 'select' | 'checkbox'
  fa: string
  en: string
  /** rows: the columns of one line («label | value») */
  cols?: { key: string; kind: 'text' | 'number'; fa: string; en: string }[]
  min?: number
  max?: number
  options?: { value: string; fa: string; en: string }[]
}

export type ComponentDef = {
  /** the plan's component id (registry.ts / components.py) */
  type: string
  /** the id of its composition: Scene + the PascalCase name */
  id: string
  group: 'scene' | 'data' | 'text'
  fa: string
  en: string
  descFa: string
  descEn: string
  duration: number
  data: boolean
  fields: DefField[]
  sample: (lang: 'fa' | 'en') => Record<string, any>
}

const T = (key: string, fa: string, en: string): DefField => ({ key, type: 'text', fa, en })
const TA = (key: string, fa: string, en: string): DefField => ({ key, type: 'textarea', fa, en })
const CK = (key: string, fa: string, en: string): DefField => ({ key, type: 'checkbox', fa, en })
const LN = (key: string, fa: string, en: string): DefField => ({ key, type: 'lines', fa, en })
const NUM = (key: string, fa: string, en: string, min: number, max: number): DefField => ({ key, type: 'number', fa, en, min, max })
const ROWS = (key: string, fa: string, en: string, cols: DefField['cols']): DefField => ({ key, type: 'rows', fa, en, cols })
const SRC = T('source', 'منبع تأییدشده (اگر دارید؛ خالی = «نمونهٔ نمایشی»)', 'Verified source (if any; empty = «example»)')
const lab = (key: string) => ({ key, kind: 'text' as const, fa: 'برچسب', en: 'Label' })
const val = (key: string) => ({ key, kind: 'number' as const, fa: 'مقدار', en: 'Value' })

const PLATFORMS = ['youtube', 'aparat', 'instagram', 'telegram', 'tiktok', 'eitaa', 'rubika', 'website', 'phone']
const PLATFORM_LABELS: Record<string, [string, string]> = {
  youtube: ['یوتیوب', 'YouTube'], aparat: ['آپارات', 'Aparat'], instagram: ['اینستاگرام', 'Instagram'], telegram: ['تلگرام', 'Telegram'], tiktok: ['تیک‌تاک', 'TikTok'],
  eitaa: ['ایتا', 'Eitaa'], rubika: ['روبیکا', 'Rubika'], website: ['وب‌سایت', 'Website'], phone: ['تلفن', 'Phone'],
}

export const COMPONENT_DEFS: ComponentDef[] = [
  {
    type: 'title', id: 'SceneTitle', group: 'scene', fa: 'کارت قسمت', en: 'Episode card', duration: 4, data: false,
    descFa: 'کارت شروع قسمت: نام سریال، شمارهٔ قسمت، عنوان و یک جملهٔ کنجکاوی‌برانگیز.', descEn: 'The opening card of an episode: series name, episode number, title and a curiosity hook line.',
    fields: [T('kicker', 'سرتیتر کوچک', 'Kicker'), T('series', 'نام سریال', 'Series name'), NUM('number', 'شمارهٔ قسمت', 'Episode number', 0, 999), T('title', 'عنوان قسمت', 'Episode title'), T('hook', 'جملهٔ کنجکاوی‌برانگیز', 'Hook line')],
    sample: (l) => (l === 'fa' ? { kicker: 'فصل اول', series: 'سفر به ستاره‌ها', number: 1, title: 'نخستین پرواز', hook: 'اما کسی نمی‌داند در آسمان چه منتظر است' } : { kicker: 'Season one', series: 'Journey to the Stars', number: 1, title: 'The first flight', hook: 'but nobody knows what waits in the sky' }),
  },
  {
    type: 'kinetic_title', id: 'SceneKineticTitle', group: 'text', fa: 'تیتر کلمه‌به‌کلمه', en: 'Kinetic title', duration: 4, data: false,
    descFa: 'تیتری که کلمه‌ها یکی‌یکی همزمان با گفتار می‌آیند.', descEn: 'A headline whose words pop in one by one, in step with the narration.',
    fields: [T('kicker', 'سرتیتر کوچک', 'Kicker'), TA('text', 'متن تیتر', 'Headline')],
    sample: (l) => (l === 'fa' ? { kicker: 'ویژه', text: 'هر ستاره یک داستان دارد' } : { kicker: 'Special', text: 'Every star has a story' }),
  },
  {
    type: 'quote', id: 'SceneQuote', group: 'scene', fa: 'نقل‌قول', en: 'Quote', duration: 5, data: false,
    descFa: 'یک جملهٔ ماندگار با نام گوینده.', descEn: 'One memorable line with its speaker.',
    fields: [TA('text', 'جمله', 'Quote'), T('author', 'گوینده', 'Speaker')],
    sample: (l) => (l === 'fa' ? { text: 'جمله‌ای که می‌ارزد به یاد بماند.', author: 'نام گوینده' } : { text: 'A sentence worth remembering.', author: 'Speaker name' }),
  },
  {
    type: 'stat', id: 'SceneStat', group: 'scene', fa: 'عدد بزرگ', en: 'Big number', duration: 4, data: true,
    descFa: 'یک عدد درشت که از صفر شمرده می‌شود؛ بدون منبعِ تأییدشده با برچسب «نمونهٔ نمایشی» می‌آید.', descEn: 'One big number that counts up; without a verified source it carries the «example» label.',
    fields: [T('kicker', 'سرتیتر کوچک', 'Kicker'), T('value', 'عدد', 'Number'), T('prefix', 'پیشوند', 'Prefix'), T('suffix', 'پسوند / واحد', 'Suffix / unit'), T('label', 'توضیح عدد', 'What it means'), CK('count_up', 'از صفر شمرده شود', 'Count up from zero'), SRC],
    sample: (l) => (l === 'fa' ? { kicker: 'عدد', value: '12', suffix: 'ساعت', label: 'توضیحِ عدد', count_up: true } : { kicker: 'Number', value: '12', suffix: 'h', label: 'What the number means', count_up: true }),
  },
  {
    type: 'counter', id: 'SceneCounter', group: 'data', fa: 'شمارنده با واحد', en: 'Counters with units', duration: 5, data: true,
    descFa: 'یک تا سه عدد که با واحدشان شمرده می‌شوند.', descEn: 'One to three numbers that count up with their units.',
    fields: [T('kicker', 'سرتیتر کوچک', 'Kicker'), ROWS('items', 'عددها (هر خط: مقدار | واحد | برچسب)', 'Numbers (one per line: value | unit | label)', [val('value'), { key: 'unit', kind: 'text', fa: 'واحد', en: 'Unit' }, lab('label')]), T('note', 'یادداشت', 'Note'), SRC],
    sample: (l) => (l === 'fa' ? { kicker: 'در یک نگاه', items: [{ value: '8', unit: 'قسمت', label: 'در هر فصل' }, { value: '20', unit: 'دقیقه', label: 'هر قسمت' }] } : { kicker: 'At a glance', items: [{ value: '8', unit: 'episodes', label: 'per season' }, { value: '20', unit: 'min', label: 'each' }] }),
  },
  {
    type: 'list', id: 'SceneList', group: 'scene', fa: 'نکته‌های کلیدی (فهرست)', en: 'Key points (list)', duration: 7, data: false,
    descFa: 'نکته‌های کلیدی یک قسمت توضیحی به‌صورت فهرست شمارهٔ‌دار.', descEn: 'The key takeaways of an explainer as a numbered list.',
    fields: [T('title', 'عنوان', 'Title'), LN('items', 'نکته‌ها (هر خط یکی)', 'Points (one per line)'), CK('numbered', 'شماره‌دار', 'Numbered')],
    sample: (l) => (l === 'fa' ? { title: 'سه نکتهٔ مهم', items: ['نکتهٔ اول', 'نکتهٔ دوم', 'نکتهٔ سوم'], numbered: true } : { title: 'Three key points', items: ['First point', 'Second point', 'Third point'], numbered: true }),
  },
  {
    type: 'steps', id: 'SceneSteps', group: 'text', fa: 'مراحل / خط زمان', en: 'Steps / timeline', duration: 7, data: false,
    descFa: 'مرحله‌های شماره‌دار که با یک خط به هم وصل‌اند.', descEn: 'Numbered steps joined by a line.',
    fields: [T('title', 'عنوان', 'Title'), ROWS('steps', 'مرحله‌ها (هر خط: عنوان | توضیح)', 'Steps (one per line: title | text)', [{ key: 'title', kind: 'text', fa: 'عنوان', en: 'Title' }, { key: 'text', kind: 'text', fa: 'توضیح', en: 'Text' }]),
      { key: 'layout', type: 'select', fa: 'چیدمان', en: 'Layout', options: [{ value: 'horizontal', fa: 'افقی', en: 'Horizontal' }, { value: 'vertical', fa: 'عمودی', en: 'Vertical' }] }],
    sample: (l) => (l === 'fa' ? { title: 'چهار گام', steps: [{ title: 'پرسش' }, { title: 'بررسی' }, { title: 'آزمایش' }, { title: 'نتیجه' }], layout: 'horizontal' } : { title: 'Four steps', steps: [{ title: 'Ask' }, { title: 'Look' }, { title: 'Test' }, { title: 'Conclude' }], layout: 'horizontal' }),
  },
  {
    type: 'checklist', id: 'SceneChecklist', group: 'text', fa: 'چک‌لیست تیک‌دار', en: 'Checklist', duration: 6, data: false,
    descFa: 'موردها یکی‌یکی تیک می‌خورند؛ برای جمع‌بندی.', descEn: 'Items get a drawn tick one after another; good for a recap.',
    fields: [T('title', 'عنوان', 'Title'), LN('items', 'موردها (هر خط یکی)', 'Items (one per line)')],
    sample: (l) => (l === 'fa' ? { title: 'چه چیزهایی را یاد گرفتیم؟', items: ['مورد اول', 'مورد دوم', 'مورد سوم'] } : { title: 'What did we learn?', items: ['First thing', 'Second thing', 'Third thing'] }),
  },
  {
    type: 'before_after', id: 'SceneBeforeAfter', group: 'data', fa: 'قبل و بعد (تقسیم‌شونده)', en: 'Before / after (what if)', duration: 6, data: false,
    descFa: 'دو نیمه که با یک جاروی نوری عوض می‌شوند؛ برای قسمت‌های «اگر چنین می‌شد؟».', descEn: 'Two halves swapped by a light wipe; for «what if» episodes.',
    fields: [T('title', 'عنوان', 'Title'), T('before', 'متن «قبل»', '“Before” text'), T('after', 'متن «بعد»', '“After” text'), T('before_label', 'برچسب قبل', 'Before label'), T('after_label', 'برچسب بعد', 'After label')],
    sample: (l) => (l === 'fa' ? { title: 'اگر چنین می‌شد؟', before: 'دنیای امروز', after: 'دنیای دیگر', before_label: 'واقعیت', after_label: 'اگر…' } : { title: 'What if?', before: 'The world today', after: 'Another world', before_label: 'Reality', after_label: 'What if' }),
  },
  {
    type: 'bar_chart', id: 'SceneBarChart', group: 'data', fa: 'نمودار میله‌ای', en: 'Bar chart', duration: 6, data: true,
    descFa: 'میله‌هایی که از صفر بالا می‌آیند؛ برای مقایسهٔ چند چیز.', descEn: 'Bars that grow from zero, to compare a few things.',
    fields: [T('title', 'عنوان', 'Title'), ROWS('bars', 'میله‌ها (هر خط: برچسب | مقدار)', 'Bars (one per line: label | value)', [lab('label'), val('value')]), T('unit', 'واحد', 'Unit'), CK('show_values', 'عددها نمایش داده شود', 'Show the values'), CK('horizontal', 'افقی', 'Horizontal'), T('note', 'یادداشت', 'Note'), SRC],
    sample: (l) => (l === 'fa' ? { title: 'مقایسهٔ سه گزینه', bars: [{ label: 'الف', value: 40 }, { label: 'ب', value: 65 }, { label: 'ج', value: 90 }], unit: '٪', show_values: true } : { title: 'Three options compared', bars: [{ label: 'A', value: 40 }, { label: 'B', value: 65 }, { label: 'C', value: 90 }], unit: '%', show_values: true }),
  },
  {
    type: 'line_chart', id: 'SceneLineChart', group: 'data', fa: 'نمودار خطی', en: 'Line chart', duration: 6, data: true,
    descFa: 'خطی که خودش کشیده می‌شود؛ برای نشان‌دادن روند.', descEn: 'A line that draws itself, to show a trend.',
    fields: [T('title', 'عنوان', 'Title'), ROWS('points', 'نقطه‌ها (هر خط: برچسب | مقدار)', 'Points (one per line: label | value)', [lab('label'), val('value')]), T('unit', 'واحد', 'Unit'), T('note', 'یادداشت', 'Note'), SRC],
    sample: (l) => (l === 'fa' ? { title: 'روند در طول زمان', points: [{ label: 'اول', value: 10 }, { label: 'دوم', value: 25 }, { label: 'سوم', value: 22 }, { label: 'چهارم', value: 48 }] } : { title: 'A trend over time', points: [{ label: '1', value: 10 }, { label: '2', value: 25 }, { label: '3', value: 22 }, { label: '4', value: 48 }] }),
  },
  {
    type: 'donut', id: 'SceneDonut', group: 'data', fa: 'نمودار دونات', en: 'Donut chart', duration: 6, data: true,
    descFa: 'سهم هر بخش از کل.', descEn: 'The share of each part in a whole.',
    fields: [T('title', 'عنوان', 'Title'), ROWS('slices', 'بخش‌ها (هر خط: برچسب | مقدار)', 'Parts (one per line: label | value)', [lab('label'), val('value')]), T('center_label', 'نوشتهٔ وسط', 'Centre label'), SRC],
    sample: (l) => (l === 'fa' ? { title: 'سهم هر بخش', slices: [{ label: 'الف', value: 50 }, { label: 'ب', value: 30 }, { label: 'ج', value: 20 }], center_label: 'کل' } : { title: 'Share of each part', slices: [{ label: 'A', value: 50 }, { label: 'B', value: 30 }, { label: 'C', value: 20 }], center_label: 'Total' }),
  },
  {
    type: 'lower_third', id: 'SceneLowerThird', group: 'text', fa: 'نوار نام شخصیت', en: 'Character name bar', duration: 4, data: false,
    descFa: 'نوار نام و نقش یک شخصیت که از کنار می‌لغزد؛ روی صحنهٔ دیگر هم می‌نشیند.', descEn: 'A name and role bar for a character that slides in; it can also sit over another scene.',
    fields: [T('name', 'نام شخصیت', 'Character name'), T('role', 'نقش', 'Role')],
    sample: (l) => (l === 'fa' ? { name: 'سارا', role: 'خلبان' } : { name: 'Sara', role: 'Pilot' }),
  },
  {
    type: 'captions', id: 'SceneCaptions', group: 'text', fa: 'زیرنویس کلمه‌به‌کلمه', en: 'Word-by-word captions', duration: 5, data: false,
    descFa: 'زیرنویسی که کلمهٔ در حال گفتن را پررنگ می‌کند (به زمان‌بندی گفتار نیاز دارد).', descEn: 'A caption track that highlights the word being spoken (uses the narration timing).',
    fields: [TA('text', 'متن گفتار', 'Spoken text')],
    sample: (l) => (l === 'fa' ? { text: 'این جمله کلمه به کلمه زیرنویس می‌شود' } : { text: 'This line is captioned word by word' }),
  },
  {
    type: 'logo', id: 'SceneLogo', group: 'scene', fa: 'نشان سریال (استینگ)', en: 'Series sting', duration: 3, data: false,
    descFa: 'نام یا نشان سریال با حلقه‌های نوری و یک شعار.', descEn: 'The series name or logo with pulsing rings and a tagline.',
    fields: [T('title', 'نام سریال', 'Series name'), T('tagline', 'شعار', 'Tagline')],
    sample: (l) => (l === 'fa' ? { title: 'سفر به ستاره‌ها', tagline: 'هر هفته یک ماجرا' } : { title: 'Journey to the Stars', tagline: 'A new adventure every week' }),
  },
  {
    type: 'image_hero', id: 'SceneImageHero', group: 'text', fa: 'تصویر تمام‌صفحه با عنوان', en: 'Key art with title', duration: 4, data: false,
    descFa: 'تصویر کلیدی نما به‌صورت تمام‌صفحه با یک عنوان.', descEn: "The shot's key picture full-bleed with a caption.",
    fields: [T('kicker', 'سرتیتر کوچک', 'Kicker'), T('caption', 'عنوان روی تصویر', 'Caption')],
    sample: (l) => (l === 'fa' ? { kicker: 'ویژه', caption: 'عنوان روی تصویر' } : { kicker: 'Special', caption: 'Title over the picture' }),
  },
  {
    type: 'social_cta', id: 'SceneSocialCta', group: 'text', fa: 'دعوت به دنبال‌کردن + قسمت بعد', en: 'Subscribe + next episode', duration: 4, data: false,
    descFa: 'کارت پایانی: نشانی کانال، دکمهٔ دنبال‌کردن و نام قسمت بعد.', descEn: 'The end card: channel handle, a follow button and the next episode.',
    fields: [T('title', 'جملهٔ دعوت', 'Call line'), { key: 'platform', type: 'select', fa: 'شبکه', en: 'Network', options: PLATFORMS.map((p) => ({ value: p, fa: PLATFORM_LABELS[p][0], en: PLATFORM_LABELS[p][1] })) }, T('handle', 'نشانی کانال', 'Channel handle'), T('button', 'دکمه', 'Button'), T('note', 'یادداشت', 'Note'), T('next_episode', 'قسمت بعد', 'Next episode')],
    sample: (l) => (l === 'fa' ? { title: 'قسمت بعد را از دست ندهید', platform: 'youtube', handle: '@example', button: 'دنبال کردن', next_episode: 'فرود در سیارهٔ سرخ' } : { title: "Don't miss the next one", platform: 'youtube', handle: '@example', button: 'Subscribe', next_episode: 'Landing on the red planet' }),
  },
  {
    type: 'countdown', id: 'SceneCountdown', group: 'data', fa: 'شمارش معکوس (پریمیر)', en: 'Countdown (premiere)', duration: 5, data: false,
    descFa: 'شمارش معکوس تا پخش قسمت.', descEn: 'A countdown to the premiere of an episode.',
    fields: [T('label', 'نوشته', 'Label'), NUM('from', 'شروع از', 'Start from', 1, 10), T('finish_text', 'نوشتهٔ پایان', 'Finish text')],
    sample: (l) => (l === 'fa' ? { label: 'پخش قسمت بعد تا', from: 3, finish_text: 'شروع!' } : { label: 'Next episode in', from: 3, finish_text: 'Go!' }),
  },
  {
    type: 'sticker', id: 'SceneSticker', group: 'text', fa: 'استیکر پاپ', en: 'Pop sticker', duration: 3, data: false,
    descFa: 'برچسبی که با پاپ می‌آید (ستاره، دایره یا برچسب).', descEn: 'A sticker that pops in (burst, circle or tag).',
    fields: [{ key: 'kind', type: 'select', fa: 'شکل', en: 'Shape', options: [{ value: 'burst', fa: 'ستاره', en: 'Burst' }, { value: 'circle', fa: 'دایره', en: 'Circle' }, { value: 'tag', fa: 'برچسب', en: 'Tag' }] }, T('text', 'نوشته', 'Text')],
    sample: (l) => (l === 'fa' ? { kind: 'burst', text: 'تازه' } : { kind: 'burst', text: 'New' }),
  },
]

export const COMPONENT_BY_ID: Record<string, ComponentDef> = Object.fromEntries(COMPONENT_DEFS.map((c) => [c.id, c]))
export const COMPONENT_TYPES = COMPONENT_DEFS.map((c) => c.type)

/** The form values of a component (as the page's draft holds them) => the scene object the plan needs. `rows` stay arrays of objects, numbers become numbers. */
export function sceneOf(def: ComponentDef, values: Record<string, any>): Record<string, any> {
  const sc: Record<string, any> = { type: def.type, duration: def.duration }
  for (const f of def.fields) {
    const v = values[f.key]
    if (v === undefined || v === null || v === '') continue
    sc[f.key] = f.type === 'number' ? Number(v) : v
  }
  return sc
}

/** The quick starts of the plan editor (instai/motion_plan/specs.py TEMPLATES has the same list). */
export const PLAN_TEMPLATES: { id: string; fa: string; en: string; types: string[] }[] = [
  { id: 'episode_intro', fa: 'شروع قسمت', en: 'Episode opening', types: ['title', 'kinetic_title'] },
  { id: 'explainer', fa: 'توضیح مفهوم', en: 'Concept explainer', types: ['kinetic_title', 'list', 'stat', 'social_cta'] },
  { id: 'what_if', fa: 'اگر چنین می‌شد؟', en: 'What if?', types: ['title', 'before_after', 'quote', 'social_cta'] },
  { id: 'data_story', fa: 'روایت داده', en: 'Data story', types: ['title', 'bar_chart', 'donut', 'social_cta'] },
  { id: 'recap', fa: 'جمع‌بندی و قسمت بعد', en: 'Recap and next episode', types: ['checklist', 'countdown', 'social_cta'] },
]

/** A plan of one of those templates in a language: the samples of its components, one after the other. */
export function templatePlan(templateId: string, lang: 'fa' | 'en', size = 'vertical'): Record<string, any> {
  const tpl = PLAN_TEMPLATES.find((t) => t.id === templateId) ?? PLAN_TEMPLATES[0]
  const scenes = tpl.types.map((type) => {
    const d = COMPONENT_DEFS.find((c) => c.type === type) as ComponentDef
    return { type, duration: d.duration, ...d.sample(lang) }
  })
  return { version: 1, size, lang, fps: 30, series: {}, scenes }
}
