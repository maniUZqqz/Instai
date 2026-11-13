# The idea bank (0.7.0)

`instai/ideabank` + the **بانک ایده** page (`/ideas`). Built-in ideas live in code (`seeds_*.py`, read-only, like the styles); the owner's own ideas,
copies, imported and AI-written ideas live in the database (`UserIdea`); stars and "hidden" are `IdeaMark`; every project started from an idea is an
`IdeaUse` row (so an idea shows "N projects made from it").

## Content

* **121 built-in ideas**, Persian + English, in six categories: psychology (18), personal development (25, eight of them fitness and coaching: `seeds_fitness.py`), economy (18), success (15), business (18),
  mystery scenarios (27). Each has a title, a one-sentence **logline** (what it is), a **hook** (the opening line or question that stops the scroll),
  tags, a best-fitting format (`concept_explainer` for explainers, `custom` for stories, `recurring_character`), 3 suggested styles and an episode
  count. A few have a full `premise`.
* The owner's two ideas are the first mystery ideas: **«تلپورت: دو نسخه از من»** (his text kept word for word in `premise_en`) and **«دزدیِ یک میلیون
  دلار و فرارِ بیست‌وچهار ساعته»** (his opening sentence kept; the continuation after it - one bag, twenty-four hours, every choice branches - is
  ours and marked so in the text).
* Explainers only name well-documented concepts (anchoring, sunk cost, loss aversion, opportunity cost, tragedy of the commons ...) and never carry
  invented figures, studies or quotes; example numbers are made up and said to be. One story that is often told but historically debated (the cobra
  effect) says so. Stories use made-up people only. No real brand, person or franchise.

* Tags are stored as short English words (they stay the filter/search keys). The Persian interface shows Persian names from `frontend/src/ideaTags.ts` (a tag the owner typed himself is shown as written); `tests/test_idea_bank.py` checks every built-in tag has one, and the search box also finds ideas by the Persian tag name.

## API

`GET /api/ideas` (`q`, `category`, `tag`, `fmt`, `favorite`, `source=builtin|mine`, `hidden`) returns `{ideas, categories, formats, tags, total, shown}`;
`POST /api/ideas` creates; `GET/PATCH/DELETE /api/ideas/<key>` (built-ins are read-only: 409); `POST .../duplicate`, `.../mark {favorite, hidden}`,
`GET /api/ideas/random`, `POST /api/ideas/generate {category, count, instruction}` (a job, `ideas.generate`), and
`POST /api/ideas/<key>/start {page_id | page_name, language, style_key, theme_key, episodes, title}` = **«شروعِ پروژه از این ایده»**.

## Starting a project

`bank.start_project` makes a `Series` (title, premise = full description or logline + the opening hook, `target_episodes`, language) and, when no page
is given, a page of the idea's format. The look is chosen **once**: it is stored as `Series.look` (and applied to a new page's visual profile), so every
image, clip, design sheet and storyboard of the project uses it (see `STYLE_LIBRARY.md`). Without `style_key`: a new page gets the idea's first
suggested style; an existing page keeps its own look. Explainers get the "neutral and sourced" content rules. The UI then opens the series.

## More ideas from the model

Job `ideas.generate` (Ollama on the GPU PC, or the chosen text provider; waits by itself when it is not running) asks for N new ideas in both languages,
steered by the starred ideas of that category and told every existing title so it does not repeat them (`agent.idea_generator`, one validated
`call_json`; a deterministic fake keeps tests and demo mode working). New ideas are saved as "mine" (`origin = generated`), duplicates are skipped.
`tests/test_gpu_smoke.py` has a real-Ollama check (`pytest -m gpu`).
