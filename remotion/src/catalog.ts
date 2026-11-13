// The list of compositions: used by the render (Root.tsx registers every entry with Remotion) and by the InstAI page (the picker, the form
// and the live preview). One file, so the preview and the rendered video can never disagree.
import type React from 'react'
import { Explainer, explainerDuration, type ExplainerProps } from './compositions/Explainer'
import { KineticText, kineticDuration, type KineticTextProps } from './compositions/KineticText'
import { LowerThird, lowerThirdDuration, type LowerThirdProps } from './compositions/LowerThird'
import { TitleCard, titleCardDuration, type TitleCardProps } from './compositions/TitleCard'
import { DEFAULT_KIT, type StyleKit } from './kit/theme'

export const FPS = 30

export const SIZES = {
  landscape: { w: 1920, h: 1080, fa: 'افقی ۱۶:۹ (یوتیوب، وب)', en: 'Landscape 16:9 (YouTube, web)' },
  vertical: { w: 1080, h: 1920, fa: 'عمودی ۹:۱۶ (ریلز، شورت، استوری)', en: 'Vertical 9:16 (Reels, Shorts, Stories)' },
  square: { w: 1080, h: 1080, fa: 'مربع ۱:۱ (پست)', en: 'Square 1:1 (post)' },
} as const
export type SizeId = keyof typeof SIZES

export type Lang = 'fa' | 'en'

export type Field = {
  key: string
  type: 'text' | 'textarea' | 'lines' | 'steps' | 'select' | 'checkbox'
  fa: string
  en: string
  options?: { value: string; fa: string; en: string }[]
}

/** The props every composition gets from the page / the render job: the style kit, the output size, and its own content. */
export type CommonProps = { kit: StyleKit; size: SizeId; fontBase?: string }

export type CompositionDef = {
  id: 'TitleCard' | 'KineticText' | 'Explainer' | 'LowerThird'
  group: 'titles' | 'kinetic' | 'explainers'
  fa: string
  en: string
  descFa: string
  descEn: string
  /** the file that holds its code (shown on the page) */
  file: string
  component: React.FC<any>
  defaults: (lang: Lang) => Record<string, unknown>
  duration: (props: any, fps: number) => number
  fields: Field[]
}

const ANIMS = [
  { value: 'auto', fa: 'مطابق سبک (پیشنهادی)', en: 'As the style says (recommended)' },
  { value: 'none', fa: 'بدون حرکت', en: 'None' },
  { value: 'fade', fa: 'محو شدن', en: 'Fade' },
  { value: 'pop', fa: 'پاپ (بزرگ شدن)', en: 'Pop' },
  { value: 'slide', fa: 'لغزیدن', en: 'Slide' },
  { value: 'typewriter', fa: 'ماشین‌تحریر', en: 'Typewriter' },
]

export const COMPOSITIONS: CompositionDef[] = [
  {
    id: 'TitleCard',
    group: 'titles',
    fa: 'تیتر',
    en: 'Title card',
    descFa: 'یک تیتر بزرگ با زیرعنوان و خط تأکید؛ ورود تیتر (پاپ، لغزش، ماشین‌تحریر ...) از سبک و تم انتخاب‌شده می‌آید.',
    descEn: 'A big title with a subtitle and an accent bar; the way it enters (pop, slide, typewriter ...) comes from the chosen style and theme.',
    file: 'compositions/TitleCard.tsx',
    component: TitleCard,
    defaults: (lang) =>
      lang === 'fa'
        ? { title: 'عنوان ویدیوی شما', subtitle: 'یک زیرعنوان کوتاه و روشن', kicker: 'قسمت ۱', animation: 'auto' }
        : { title: 'Your video title', subtitle: 'A short, clear subtitle', kicker: 'Episode 1', animation: 'auto' },
    duration: (p: TitleCardProps, fps) => titleCardDuration(p, fps),
    fields: [
      { key: 'kicker', type: 'text', fa: 'سرتیتر کوچک', en: 'Kicker' },
      { key: 'title', type: 'text', fa: 'عنوان', en: 'Title' },
      { key: 'subtitle', type: 'text', fa: 'زیرعنوان', en: 'Subtitle' },
      { key: 'animation', type: 'select', fa: 'حرکت تیتر', en: 'Title motion', options: ANIMS },
    ],
  },
  {
    id: 'KineticText',
    group: 'kinetic',
    fa: 'متن متحرک',
    en: 'Kinetic text',
    descFa: 'متن کلمه‌به‌کلمه روی صفحه می‌آید؛ ضرب‌آهنگ و نوع ورود هر کلمه از سبک می‌آید. کلمهٔ مهم را بین ستاره بگذارید: *مهم*.',
    descEn: 'The script appears word by word; the beat and the way each word enters come from the style. Put an important word between stars: *important*.',
    file: 'compositions/KineticText.tsx',
    component: KineticText,
    defaults: (lang) =>
      lang === 'fa'
        ? { lines: ['*یک* ایده، *یک* ویدیو', 'هر کلمه با ضرب‌آهنگ سبک انتخاب‌شده می‌آید', 'متن را عوض کنید و *پیش‌نمایش* را ببینید'] }
        : { lines: ['*One* idea, *one* video', 'every word enters with the beat of the chosen style', 'change the text and watch the *preview*'] },
    duration: (p: KineticTextProps, fps) => kineticDuration(p, fps),
    fields: [{ key: 'lines', type: 'lines', fa: 'متن (هر خط = یک صحنه؛ کلمهٔ مهم: *کلمه*)', en: 'Text (one line per screen; important word: *word*)' }],
  },
  {
    id: 'Explainer',
    group: 'explainers',
    fa: 'توضیحی (مرحله‌به‌مرحله)',
    en: 'Explainer (step by step)',
    descFa: 'یک موضوع، سپس یک کارت برای هر مرحله با شماره، عنوان و یک جمله، نوار پیشرفت و جملهٔ پایانی.',
    descEn: 'A topic, then one card per step with a number, a title and a sentence, a progress bar and a closing line.',
    file: 'compositions/Explainer.tsx',
    component: Explainer,
    defaults: (lang) =>
      lang === 'fa'
        ? { title: 'چطور کار می‌کند؟', steps: [{ title: 'یک سبک انتخاب کنید', body: 'سبک رنگ، حرکت و حس ویدیو را تعیین می‌کند.' }, { title: 'متن را بنویسید', body: 'عنوان، مرحله‌ها و جملهٔ پایانی را وارد کنید.' }, { title: 'پیش‌نمایش و ساخت', body: 'اول پیش‌نمایش را ببینید، بعد ویدیو را بسازید.' }], outro: 'همین‌قدر ساده' }
        : { title: 'How does it work?', steps: [{ title: 'Pick a style', body: 'The style sets the colour, the motion and the feel.' }, { title: 'Write the text', body: 'Enter the title, the steps and the closing line.' }, { title: 'Preview and render', body: 'Watch the preview first, then make the video.' }], outro: 'It is that simple' },
    duration: (p: ExplainerProps, fps) => explainerDuration(p, fps),
    fields: [
      { key: 'title', type: 'text', fa: 'موضوع', en: 'Topic' },
      { key: 'steps', type: 'steps', fa: 'مرحله‌ها (هر خط: عنوان | توضیح)', en: 'Steps (one per line: title | explanation)' },
      { key: 'outro', type: 'text', fa: 'جملهٔ پایانی', en: 'Closing line' },
    ],
  },
  {
    id: 'LowerThird',
    group: 'titles',
    fa: 'زیرنویس معرفی (نام و سمت)',
    en: 'Lower third (name and role)',
    descFa: 'نوار معرفی گوینده که از کنار می‌لغزد؛ با گزینهٔ «بدون پس‌زمینه» برای قرار گرفتن روی ویدیوی دیگر.',
    descEn: 'A speaker bar that slides in from the side; with "no backdrop" it can be placed over another video.',
    file: 'compositions/LowerThird.tsx',
    component: LowerThird,
    defaults: (lang) => (lang === 'fa' ? { name: 'نام و نام‌خانوادگی', role: 'سمت یا عنوان', backdrop: true } : { name: 'Full name', role: 'Role or title', backdrop: true }),
    duration: (p: LowerThirdProps, fps) => lowerThirdDuration(p, fps),
    fields: [
      { key: 'name', type: 'text', fa: 'نام', en: 'Name' },
      { key: 'role', type: 'text', fa: 'سمت', en: 'Role' },
      { key: 'backdrop', type: 'checkbox', fa: 'پس‌زمینهٔ سبک نمایش داده شود', en: 'Show the style backdrop' },
    ],
  },
]

export const COMPOSITION_IDS = COMPOSITIONS.map((c) => c.id)

export function byId(id: string): CompositionDef | undefined {
  return COMPOSITIONS.find((c) => c.id === id)
}

/** Width, height, frame rate and length of a composition for these props (the page's player and the render both ask this). */
export function metaFor(id: string, props: Partial<CommonProps> & Record<string, unknown>): { width: number; height: number; fps: number; durationInFrames: number } {
  const def = byId(id)
  const size = SIZES[(props.size as SizeId) in SIZES ? (props.size as SizeId) : 'landscape']
  const full = { kit: DEFAULT_KIT, ...props }
  return { width: size.w, height: size.h, fps: FPS, durationInFrames: Math.max(30, def ? def.duration(full, FPS) : 150) }
}
