/**
 * openrouter_models.js
 *
 * Weather-style OpenRouter top/newest models widget for AI Report.
 */

(function(app) {
  'use strict';

  function formatTokens(n) {
    if (n == null || isNaN(n)) return '';
    const abs = Math.abs(n);
    if (abs >= 1e12) return (n / 1e12).toFixed(1).replace(/\.0$/, '') + 'T';
    if (abs >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
    if (abs >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (abs >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
    return String(n);
  }

  function formatPricePerMillion(raw) {
    if (raw == null || raw === '') return '—';
    const perToken = parseFloat(raw);
    if (isNaN(perToken)) return '—';
    if (perToken === 0) return 'Free';
    const perMillion = perToken * 1e6;
    if (perMillion < 0.01) return '$' + perMillion.toFixed(4) + '/M';
    if (perMillion < 1) return '$' + perMillion.toFixed(3) + '/M';
    return '$' + perMillion.toFixed(2) + '/M';
  }

  function formatContext(n) {
    if (n == null || isNaN(n)) return '—';
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 1e3) return Math.round(n / 1e3) + 'K';
    return String(n);
  }

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  class OpenRouterModelsWidget {
    constructor() {
      this.panels = Array.from(document.querySelectorAll('.or-models-panel'));
      if (!this.panels.length) return;

      this.data = null;
      this.activeModelId = null;
      this.ensurePopupChrome();
      this.load();
    }

    ensurePopupChrome() {
      if (!document.getElementById('or-model-overlay')) {
        const overlay = document.createElement('div');
        overlay.id = 'or-model-overlay';
        overlay.className = 'or-model-overlay';
        document.body.appendChild(overlay);
        overlay.addEventListener('click', () => this.closePopup());
      }
      if (!document.getElementById('or-model-popup')) {
        const popup = document.createElement('div');
        popup.id = 'or-model-popup';
        popup.className = 'or-model-popup';
        popup.innerHTML = [
          '<span class="or-model-close" id="or-model-close" title="Close">&times;</span>',
          '<h3 id="or-model-popup-title"></h3>',
          '<dl class="or-model-popup-meta" id="or-model-popup-meta"></dl>',
          '<div class="or-model-popup-desc" id="or-model-popup-desc"></div>',
          '<a class="or-model-popup-link" id="or-model-popup-link" target="_blank" rel="noopener">View on OpenRouter</a>'
        ].join('');
        document.body.appendChild(popup);
        document.getElementById('or-model-close').addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.closePopup();
        });
      }
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') this.closePopup();
      });
    }

    load() {
      fetch('/api/openrouter/models', { credentials: 'same-origin' })
        .then((res) => {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then((data) => {
          this.data = data;
          this.renderAll();
        })
        .catch((err) => {
          if (app.utils && app.utils.logger) {
            app.utils.logger.error('[OpenRouterModels] fetch failed:', err);
          }
          this.panels.forEach((panel) => {
            const inner = panel.querySelector('.or-models-inner') || panel;
            inner.innerHTML = '<div class="or-models-title">OpenRouter</div>' +
              '<div class="or-models-error">Could not load models.</div>';
          });
        });
    }

    renderAll() {
      const html = this.buildPanelHtml(this.data);
      this.panels.forEach((panel) => {
        panel.innerHTML = html;
        this.bindPanel(panel);
        panel.querySelectorAll('.last-updated-time').forEach((el) => {
          if (app.utils && app.utils.TimezoneManager) {
            app.utils.TimezoneManager.convertElement(el);
          }
        });
      });
    }

    buildPanelHtml(data) {
      const top = (data && data.top_weekly) || [];
      const newest = (data && data.newest) || [];
      const lastFetch = (data && data.last_fetch) || 'Unknown';

      return [
        '<div class="or-models-inner">',
        '<div class="or-models-title">OpenRouter</div>',
        '<div class="or-models-columns">',
        this.buildSection('Top this week', top, true),
        this.buildSection('Newest', newest, false),
        '</div>',
        '<small class="or-models-updated">Last updated: ',
        '<span class="last-updated-time" data-utc-time="' + escapeHtml(lastFetch) + '"></span>',
        '</small>',
        '<small class="or-models-attribution">',
        '<a href="https://openrouter.ai/rankings" target="_blank" rel="noopener">Source: OpenRouter</a>',
        '</small>',
        '</div>'
      ].join('');
    }

    buildSection(title, models, showTokens) {
      if (!models.length) {
        return '<div class="or-models-section"><div class="or-models-section-title">' +
          escapeHtml(title) + '</div><div class="or-models-loading">No data</div></div>';
      }
      const items = models.map((m) => {
        const name = m.name || m.id;
        const tokens = showTokens && m.weekly_tokens != null
          ? '<span class="or-models-tokens">' + escapeHtml(formatTokens(m.weekly_tokens)) + '</span>'
          : '';
        return [
          '<li>',
          '<a class="or-models-link" href="' + escapeHtml(m.url || ('https://openrouter.ai/' + m.id)) + '"',
          ' target="_blank" rel="noopener"',
          ' data-model-id="' + escapeHtml(m.id) + '"',
          ' title="' + escapeHtml(name) + '">',
          escapeHtml(name),
          '</a>',
          tokens,
          '</li>'
        ].join('');
      }).join('');
      return [
        '<div class="or-models-section">',
        '<div class="or-models-section-title">' + escapeHtml(title) + '</div>',
        '<ul class="or-models-list">' + items + '</ul>',
        '</div>'
      ].join('');
    }

    findModel(modelId) {
      if (!this.data) return null;
      const lists = [this.data.top_weekly || [], this.data.newest || []];
      for (let i = 0; i < lists.length; i++) {
        for (let j = 0; j < lists[i].length; j++) {
          if (lists[i][j].id === modelId) return lists[i][j];
        }
      }
      return null;
    }

    bindPanel(panel) {
      panel.querySelectorAll('.or-models-link').forEach((link) => {
        const modelId = link.getAttribute('data-model-id');
        link.addEventListener('click', (e) => {
          e.preventDefault();
          this.openPopup(modelId);
        });
      });
    }

    openPopup(modelId) {
      const model = this.findModel(modelId);
      if (!model) return;
      this.activeModelId = modelId;

      const title = document.getElementById('or-model-popup-title');
      const meta = document.getElementById('or-model-popup-meta');
      const desc = document.getElementById('or-model-popup-desc');
      const link = document.getElementById('or-model-popup-link');
      const popup = document.getElementById('or-model-popup');
      const overlay = document.getElementById('or-model-overlay');

      title.textContent = model.name || model.id;
      const rows = [
        ['Input', formatPricePerMillion(model.pricing_prompt)],
        ['Output', formatPricePerMillion(model.pricing_completion)],
        ['Context', formatContext(model.context_length)]
      ];
      if (model.weekly_tokens != null) {
        rows.push(['Week tokens', formatTokens(model.weekly_tokens)]);
      }
      meta.innerHTML = rows.map(([k, v]) =>
        '<dt>' + escapeHtml(k) + '</dt><dd>' + escapeHtml(v) + '</dd>'
      ).join('');
      desc.textContent = model.description || 'No summary available.';
      link.href = model.url || ('https://openrouter.ai/' + model.id);

      popup.classList.add('active');
      overlay.classList.add('active');
    }

    closePopup() {
      this.activeModelId = null;
      const popup = document.getElementById('or-model-popup');
      const overlay = document.getElementById('or-model-overlay');
      if (popup) popup.classList.remove('active');
      if (overlay) overlay.classList.remove('active');
    }
  }

  app.modules.openrouterModels = {
    init() {
      if (!document.querySelector('.or-models-panel')) return;
      try {
        new OpenRouterModelsWidget();
      } catch (error) {
        if (app.utils && app.utils.logger) {
          app.utils.logger.error('[OpenRouterModels] init failed:', error);
        }
      }
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    app.modules.openrouterModels.init();
  });

})(window.app);
