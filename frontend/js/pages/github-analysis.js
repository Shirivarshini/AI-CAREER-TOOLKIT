/**
 * github-analysis.js
 * Wires the username form to POST /api/github/analyze. All GitHub API
 * calls, rate-limiting, and scoring happen server-side; this only renders
 * whatever the backend returns.
 *
 * Expected response shape (backend contract):
 * {
 *   profile: { username, name, avatar_url, public_repos, followers },
 *   score: 0-100,
 *   metrics: { repo_count, total_stars, total_forks, contribution_streak },
 *   languages: [{ label, value }],           // value = percentage
 *   top_repos: [{ name, description, stars, forks, has_readme }],
 *   suggestions: string[]
 * }
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const form = DOM.qs("#github-form");
    if (!form) return;

    const usernameInput = DOM.qs("#gh-username");
    const submitBtn = DOM.qs("#gh-submit");
    const resultsPanel = DOM.qs("#gh-results");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const raw = usernameInput.value.trim();
      if (!Validate.required(raw)) {
        Validate.showFieldError(usernameInput, "Enter a GitHub username or profile URL.");
        return;
      }
      const username = Validate.parseGithubInput(raw);
      if (!Validate.githubUsername(username)) {
        Validate.showFieldError(usernameInput, "That doesn't look like a valid GitHub username.");
        return;
      }
      Validate.clearFieldError(usernameInput);

      setLoading(true);
      showLoadingState();
      try {
        const data = await Api.post(window.APP_CONFIG.ENDPOINTS.GITHUB_ANALYZE, { username });
        renderResults(data);
        Toast.success(`Analyzed @${username}'s GitHub profile.`);
      } catch (err) {
        renderError(err, username);
        Toast.error(err.message || "Couldn't analyze that profile.");
      } finally {
        setLoading(false);
      }
    });

    function setLoading(isLoading) {
      submitBtn.disabled = isLoading;
      submitBtn.innerHTML = isLoading
        ? '<span class="spinner" aria-hidden="true"></span> Analyzing\u2026'
        : "Analyze profile";
    }

    function showLoadingState() {
      resultsPanel.innerHTML = `
        <div class="loading-block">
          <span class="spinner spinner-lg" aria-hidden="true"></span>
          <p>Pulling public repo data and scoring credibility signals\u2026</p>
        </div>
      `;
    }

    function renderError(err, username) {
      const notFound = err instanceof Api.ApiError && err.status === 404;
      resultsPanel.innerHTML = `
        <div class="alert alert-error" role="alert">
          <svg class="alert__icon" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 6v5m0 3h.01M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Z" stroke="currentColor" stroke-width="1.6"/></svg>
          <div>
            <strong>${notFound ? "Profile not found." : "Analysis failed."}</strong>
            <p style="margin: 4px 0 0;">
              ${notFound
                ? `We couldn't find a GitHub user named "${DOM.escapeHTML(username)}".`
                : DOM.escapeHTML(err.message || "Please try again.")}
            </p>
          </div>
        </div>
      `;
    }

    function renderResults(data) {
      const p = data.profile || {};
      resultsPanel.innerHTML = `
        <div class="card gh-profile-card mb-5">
          <img class="gh-profile-card__avatar" src="${DOM.escapeHTML(p.avatar_url || "")}" alt="" width="64" height="64" />
          <div style="flex:1; min-width:0;">
            <div class="gh-profile-card__name">${DOM.escapeHTML(p.name || p.username || "")}</div>
            <div class="gh-profile-card__handle">@${DOM.escapeHTML(p.username || "")}</div>
          </div>
          <div id="gh-score-dial"></div>
        </div>

        <div class="grid grid-4 mb-5">
          <div class="card metric-tile">
            <div class="metric-tile__value">${data.metrics?.repo_count ?? "\u2013"}</div>
            <div class="metric-tile__label">Repositories</div>
          </div>
          <div class="card metric-tile">
            <div class="metric-tile__value">${data.metrics?.total_stars ?? "\u2013"}</div>
            <div class="metric-tile__label">Total stars</div>
          </div>
          <div class="card metric-tile">
            <div class="metric-tile__value">${data.metrics?.total_forks ?? "\u2013"}</div>
            <div class="metric-tile__label">Total forks</div>
          </div>
          <div class="card metric-tile">
            <div class="metric-tile__value">${data.metrics?.contribution_streak ?? "\u2013"}</div>
            <div class="metric-tile__label">Day streak</div>
          </div>
        </div>

        <div class="grid grid-2 mb-5">
          <div class="card">
            <h4>Language distribution</h4>
            <div style="height:180px;"><canvas id="gh-lang-chart" role="img" aria-label="Language distribution chart"></canvas></div>
            <div id="gh-lang-legend" class="lang-legend" style="margin-top: var(--sp-4);"></div>
          </div>
          <div class="card">
            <h4>Suggestions</h4>
            <div id="gh-suggestions" class="fix-list"></div>
          </div>
        </div>

        <div class="card">
          <h4>Top repositories</h4>
          <div id="gh-repo-list"></div>
        </div>
      `;

      Gauge.render(DOM.qs("#gh-score-dial", resultsPanel), {
        score: data.score ?? 0,
        max: 100,
        label: "Profile score",
        size: 96,
      });

      const languages = data.languages || [];
      if (languages.length) {
        Charts.languageDonut("gh-lang-chart", languages);
        const legend = DOM.qs("#gh-lang-legend", resultsPanel);
        const colors = Charts.palette();
        languages.forEach((lang, i) => {
          legend.appendChild(
            DOM.el("span", { class: "lang-legend__item" }, [
              DOM.el("span", { class: "lang-legend__dot", style: `background:${colors[i % colors.length]}` }),
              `${lang.label} \u00b7 ${lang.value}%`,
            ])
          );
        });
      }

      const suggestions = DOM.qs("#gh-suggestions", resultsPanel);
      if (!data.suggestions || data.suggestions.length === 0) {
        suggestions.appendChild(DOM.el("p", { class: "text-muted" }, ["No suggestions \u2014 this profile looks strong."]));
      } else {
        data.suggestions.forEach((s) => {
          const item = DOM.el("div", { class: "fix-item severity-medium" });
          item.innerHTML = `
            <svg class="fix-item__icon" viewBox="0 0 18 18" fill="none" aria-hidden="true"><path d="M9 1.5 11 6l5 .7-3.6 3.5.9 5-4.3-2.3L4.7 15l.9-5L2 6.7 7 6l2-4.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
            <span>${DOM.escapeHTML(s)}</span>
          `;
          suggestions.appendChild(item);
        });
      }

      const repoList = DOM.qs("#gh-repo-list", resultsPanel);
      const repos = data.top_repos || [];
      if (!repos.length) {
        repoList.appendChild(DOM.el("p", { class: "text-muted" }, ["No public repositories found."]));
      } else {
        repos.forEach((repo) => {
          repoList.appendChild(
            (() => {
              const row = DOM.el("div", { class: "repo-row" });
              row.innerHTML = `
                <div>
                  <div class="repo-row__name">${DOM.escapeHTML(repo.name)}</div>
                  <div class="repo-row__desc">${DOM.escapeHTML(repo.description || "No description")}</div>
                </div>
                <div class="repo-row__stats">
                  <span>\u2605 ${repo.stars ?? 0}</span>
                  <span>\u2942 ${repo.forks ?? 0}</span>
                  <span class="badge ${repo.has_readme ? "badge-good" : "badge-warn"}">${repo.has_readme ? "README" : "No README"}</span>
                </div>
              `;
              return row;
            })()
          );
        });
      }
    }
  });
})();
