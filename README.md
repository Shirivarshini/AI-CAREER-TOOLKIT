# AI Career Toolkit — Frontend

A production-quality, framework-free frontend for the AI Career Toolkit
described in the PRD: Resume ATS Analyzer, GitHub Profile Analysis,
LinkedIn Optimizer, and Skill-Gap Analysis, plus auth and a history
dashboard.

**Stack:** plain HTML, CSS, vanilla JavaScript (ES2017+), [Chart.js](https://www.chartjs.org/)
via CDN. No build step, no framework, no bundler required.

This module contains **no business logic**. Every score, parsed section,
matched keyword, or suggestion comes from the FastAPI backend over REST.
The frontend's job is forms, file handling, client-side validation
(format only — never authoritative), rendering, and UX polish (loading
states, toasts, drag-and-drop, accessibility).

## Running locally

No build step — just serve the folder statically:

```bash
python3 -m http.server 5500
# open http://localhost:5500/index.html
```

Point the frontend at your FastAPI backend by setting the API base URL
(defaults to `http://localhost:8000/api`):

```js
localStorage.setItem('act_api_base', 'https://your-api.example.com/api');
```

or edit `js/config.js` directly for a fixed deployment.

## Project structure

```
index.html                 Landing page
login.html                 Login
signup.html                 Signup
dashboard.html              History + score trend (app shell)
resume-analyzer.html        Resume ATS analyzer (app shell)
github-analysis.html        GitHub profile analysis (app shell)
linkedin-optimizer.html     LinkedIn optimizer (app shell)
skill-gap.html               Skill-gap analysis (app shell)

css/
  tokens.css                 Design tokens: color, type, spacing, radius, shadow
  base.css                    Reset + element defaults + a11y focus styles
  layout.css                  Marketing nav/footer, app shell (sidebar/topbar), grid
  components.css               Buttons, cards, forms, chips, modal, toast, dropzone,
                                score dial, progress bar, tabs, table, etc.
  pages/                       One stylesheet per page, loaded only where needed

js/
  config.js                    API base URL + endpoint map + upload limits
  utils/
    dom.js                      qs/qsa/el/escapeHTML/formatBytes/formatDate/debounce
    api.js                      fetch() wrapper: JSON + FormData, timeouts, ApiError
    toast.js                    Accessible toast notifications
    validation.js                Client-side format validation (not authoritative)
    storage.js                   localStorage wrapper — UI prefs only, never tokens
    theme.js                     Dark-mode toggle
  components/
    navbar.js                    Mobile menu + sidebar toggle + active-link state
    gauge.js                     Score dial (signature visual, used everywhere a
                                  score is shown)
    dropzone.js                  Accessible drag-and-drop file upload
    modal.js                     Focus-trapped modal dialog
    chips.js                     Skill/keyword chip list rendering
    charts.js                    Chart.js wrapper: language donut, score trend line,
                                  category breakdown bar — themed from CSS variables
  pages/
    landing.js, login.js, signup.js, dashboard.js, resume-analyzer.js,
    github-analysis.js, linkedin-optimizer.js, skill-gap.js
    — one module per page; each only talks to Api + renders responses.
```

## Backend API contract

Matches the endpoints defined in the PRD (`§7.2`). The frontend assumes:

| Method | Path | Notes |
|---|---|---|
| POST | `/api/resume/analyze` | `multipart/form-data`: `file`, optional `job_description` |
| POST | `/api/resume/match-jd` | Reserved for the standalone JD-matcher add-on (not wired to a page yet) |
| POST | `/api/github/analyze` | JSON: `{ username }` |
| POST | `/api/linkedin/analyze` | JSON (paste mode) or `multipart/form-data` (PDF mode) |
| POST | `/api/skills/gap` | JSON: `{ target_role }` |
| GET | `/api/report/{analysis_id}` | Returns a PDF blob for download |
| POST | `/api/auth/signup` | JSON: `{ name, email, password }` |
| POST | `/api/auth/login` | JSON: `{ email, password }` — expects the backend to set an httpOnly session cookie |
| GET | `/api/history` | Returns `{ stats, trend, history }` for the dashboard; `401` renders the guest empty state |

Every `fetch()` call sends `credentials: 'include'` so session auth works
via cookie — **no auth token is ever stored in `localStorage` or
`sessionStorage`**, per the PRD's non-functional requirements. See the
`Expected response shape` comment at the top of each file in `js/pages/`
for the exact JSON shape each page renders.

## Accessibility

- Semantic landmarks (`header`, `nav`, `main`, `footer`), skip-to-content link
- Visible keyboard focus everywhere, full keyboard support for the dropzone and modal (focus trap, Escape to close)
- Form fields have associated `<label>`s and `aria-describedby` error text
- Toasts use `role="status"` / `role="alert"` with polite live regions
- Respects `prefers-reduced-motion`
- Color is never the only signal (status badges/chips pair color with text)

## Extending for future phases

- Add a new tool page by copying an existing app-shell page, adding its
  own `css/pages/<name>.css` and `js/pages/<name>.js`, and wiring a new
  endpoint into `js/config.js`.
- The score dial, toast system, dropzone, and modal are all
  page-agnostic — reuse them rather than writing new markup/JS.
- The `/api/resume/match-jd` and cover-letter/email-report add-ons from
  PRD §5 are intentionally left unwired since they're outside the Phase 1
  scope — add a page module + endpoint mapping when the backend ships them.
