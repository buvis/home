"use strict";
// ==UserScript==
// @name         Obsidian Omnisearch in Kagi
// @namespace    https://github.com/buvis/home
// @downloadURL  https://github.com/buvis/home/raw/master/.config/tampermonkey/kagi-obsidian-omnisearch.user.js
// @updateURL    https://github.com/buvis/home/raw/master/.config/tampermonkey/kagi-obsidian-omnisearch.user.js
// @version      0.3.3
// @description  Injects Obsidian notes in Kagi search results
// @author       Tomáš Bouška
// @match        https://kagi.com/*
// @match        https://www.kagi.com/*
// @icon         https://obsidian.md/favicon.ico
// @require      https://code.jquery.com/jquery-3.7.1.min.js
// @require      https://gist.githubusercontent.com/scambier/109932d45b7592d3decf24194008be4d/raw/9c97aa67ff9c5d56be34a55ad6c18a314e5eb548/waitForKeyElements.js
// @require      https://raw.githubusercontent.com/sizzlemctwizzle/GM_config/master/gm_config.js
// @grant        GM.xmlHttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM.getValue
// @grant        GM.setValue
// @grant        GM_registerMenuCommand
// ==/UserScript==

/* globals GM_config, $, waitForKeyElements */

(function () {
  // Constants
  const CONSTANTS = {
    SELECTORS: {
      SIDEBAR: ".right-content-box",
      LAYOUT: "#layout-v2",
    },
    IDS: {
      RESULTS_DIV: "OmnisearchObsidianResults",
      LOADING_SPAN: "OmnisearchObsidianLoading",
      CONFIG_LINK: "OmnisearchObsidianConfig",
    },
    DEFAULTS: {
      PORT: "51361",
      MAX_RESULTS: 3,
    },
    LOGO: `<svg height="1em" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 256 256">
      <style>.purple { fill: #9974F8; } @media (prefers-color-scheme: dark) { .purple { fill: #A88BFA; } }</style>
      <path class="purple" d="M94.82 149.44c6.53-1.94 17.13-4.9 29.26-5.71a102.97 102.97 0 0 1-7.64-48.84c1.63-16.51 7.54-30.38 13.25-42.1l3.47-7.14 4.48-9.18c2.35-5 4.08-9.38 4.9-13.56.81-4.07.81-7.64-.2-11.11-1.03-3.47-3.07-7.14-7.15-11.21a17.02 17.02 0 0 0-15.8 3.77l-52.81 47.5a17.12 17.12 0 0 0-5.5 10.2l-4.5 30.18a149.26 149.26 0 0 1 38.24 57.2ZM54.45 106l-1.02 3.06-27.94 62.2a17.33 17.33 0 0 0 3.27 18.96l43.94 45.16a88.7 88.7 0 0 0 8.97-88.5A139.47 139.47 0 0 0 54.45 106Z"/>
      <path class="purple" d="m82.9 240.79 2.34.2c8.26.2 22.33 1.02 33.64 3.06 9.28 1.73 27.73 6.83 42.82 11.21 11.52 3.47 23.45-5.8 25.08-17.73 1.23-8.67 3.57-18.46 7.75-27.53a94.81 94.81 0 0 0-25.9-40.99 56.48 56.48 0 0 0-29.56-13.35 96.55 96.55 0 0 0-40.99 4.79 98.89 98.89 0 0 1-15.29 80.34h.1Z"/>
      <path class="purple" d="M201.87 197.76a574.87 574.87 0 0 0 19.78-31.6 8.67 8.67 0 0 0-.61-9.48 185.58 185.58 0 0 1-21.82-35.9c-5.91-14.16-6.73-36.08-6.83-46.69 0-4.07-1.22-8.05-3.77-11.21l-34.16-43.33c0 1.94-.4 3.87-.81 5.81a76.42 76.42 0 0 1-5.71 15.9l-4.7 9.8-3.36 6.72a111.95 111.95 0 0 0-12.03 38.23 93.9 93.9 0 0 0 8.67 47.92 67.9 67.9 0 0 1 39.56 16.52 99.4 99.4 0 0 1 25.8 37.31Z"/>
    </svg>`,
  };

  // Register menu command for Omnisearch port configuration
  GM_registerMenuCommand("Configure Omnisearch Port", () => {
    const port = prompt(
      "Enter Omnisearch port:",
      GM_getValue("omnisearch_port", CONSTANTS.DEFAULTS.PORT),
    );

    if (port && !isNaN(port)) {
      GM_setValue("omnisearch_port", port.trim());
      alert("Omnisearch port updated. Please refresh the page.");
    }
  });

  // Configuration Manager
  class ConfigManager {
    constructor() {
      this.config = new GM_config({
        id: "ObsidianOmnisearchKagi",
        title: "Omnisearch in Kagi - Configuration",
        fields: {
          port: {
            label: "HTTP Port",
            type: "text",
            default: CONSTANTS.DEFAULTS.PORT,
          },
          nbResults: {
            label: "Number of results to display",
            type: "int",
            default: CONSTANTS.DEFAULTS.MAX_RESULTS,
          },
        },
        events: { save: () => location.reload() },
      });
    }

    async waitForInit() {
      return new Promise((resolve) => {
        const check = () =>
          this.config.isInit ? resolve() : setTimeout(check, 0);
        check();
      });
    }

    getPort() {
      return this.config.get("port");
    }

    getMaxResults() {
      return this.config.get("nbResults");
    }

    open() {
      this.config.open();
    }
  }

  // Title Extraction Strategies
  class TitleExtractor {
    constructor() {
      this.strategies = [
        this.extractFromTitle.bind(this),
        this.extractFromH1.bind(this),
        this.extractFromTimestamp.bind(this),
        this.extractFromBasename.bind(this),
      ];
    }

    extract(item) {
      for (const strategy of this.strategies) {
        const title = strategy(item);

        if (title) return title;
      }

      return item.basename;
    }

    extractFromTitle({ excerpt }) {
      const match = excerpt.match(/title: (.+?)<br>/i);

      return match ? match[1].trim() : null;
    }

    extractFromH1({ excerpt }) {
      const match = excerpt.match(/(?:^|<br>)# ([^#].*?)<br>/i);

      return match ? match[1].trim() : null;
    }

    extractFromTimestamp({ basename }) {
      if (!/^\d{14}-/.test(basename)) return null;

      return basename
        .slice(15)
        .replace(/-/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
    }

    extractFromBasename({ basename }) {
      return basename;
    }
  }

  // Text Highlighter
  class TextHighlighter {
    highlight(excerpt, words) {
      if (!words?.length) return excerpt;

      const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const regex = new RegExp(
        `\\b(${words.map(escapeRegex).join("|")})\\b`,
        "gi",
      );

      return excerpt.replace(
        regex,
        '<span style="background-color:#eee8d5;color:#586e75;padding:0.15em 0.2em;">$1</span>',
      );
    }
  }

  // HTML Template Builder
  class TemplateBuilder {
    buildResultsContainer() {
      return `
        <div class="_0_right_sidebar _0_provider-content">
          <div id="omnisearchResults" class="_0_provider-content">
            <div class="scene">
              <div class="wikipediaResult">
                <div class="card__face">
                  <div id="${CONSTANTS.IDS.RESULTS_DIV}" style="margin-bottom: 2em;"></div>
                </div>
              </div>
            </div>
          </div>
        </div>`;
    }

    buildHeader() {
      return `
        <div style="margin-bottom:1em;">
          <span style="font-size:1.2em">${CONSTANTS.LOGO}&nbsp;Omnisearch results</span>
          <span style="font-size:0.8em;">
            (<a id="${CONSTANTS.IDS.CONFIG_LINK}" title="Settings" href="#">settings</a>)
          </span>
        </div>`;
    }

    buildLoadingLabel() {
      return `<span id="${CONSTANTS.IDS.LOADING_SPAN}">Loading...</span>`;
    }

    buildSearchResult(item, noteUrl, title, highlightedExcerpt) {
      return `
        <div class="_0_SRI _ext_ub_r search-result" data-omnisearch-result>
          <div class="_0_TITLE __sri-title">
            <h3 class="__sri-title-box">
              <a class="__sri_title_link _ext_ub_t _0_sri_title_link _0_URL"
                 title="${title}" href="${noteUrl}" rel="noopener noreferrer">
                 ${title}
              </a>
            </h3>
          </div>
          <div class="__sri-url-box">
            <a class="_0_URL __sri-url _ext_ub_u" href="${noteUrl}" style="border-bottom:2px solid transparent;">
              <div class="__sri_url_path_box">
                <span class="host">${CONSTANTS.LOGO}Obsidian</span>&nbsp;<span class="path">› ${item.path}</span>
              </div>
            </a>
          </div>
          <div class="__sri-body">
            <div class="_0_DESC __sri-desc">
              <div>${highlightedExcerpt}</div>
            </div>
          </div>
        </div>`;
    }
  }

  // DOM Manager
  class DOMManager {
    constructor(templateBuilder) {
      this.templateBuilder = templateBuilder;
    }

    injectResultsContainer() {
      $(`#${CONSTANTS.IDS.RESULTS_DIV}`).remove();
      const sidebar = $(CONSTANTS.SELECTORS.SIDEBAR);
      const existingWiki = $('#wikipediaResults');

      if (sidebar.length > 0) {
        if (existingWiki.length > 0) {
          // Insert before existing Wikipedia results
          existingWiki.before(this.templateBuilder.buildResultsContainer());
        } else {
          // Fallback to prepend if no Wikipedia results found
          sidebar.prepend(this.templateBuilder.buildResultsContainer());
        }
      }
    }

    injectHeader() {
      if ($(`#${CONSTANTS.IDS.CONFIG_LINK}`).length) return;
      const resultsDiv = $(`#${CONSTANTS.IDS.RESULTS_DIV}`);

      if (resultsDiv.length > 0) {
        resultsDiv.append(this.templateBuilder.buildHeader());
      }
    }

    showLoading() {
      // Remove any existing loading or error messages first
      $(`#${CONSTANTS.IDS.LOADING_SPAN}`).remove();
      $("[data-omnisearch-result]").remove();

      // Only show loading if not already showing

      if (!$(`#${CONSTANTS.IDS.LOADING_SPAN}`).length) {
        $(`#${CONSTANTS.IDS.RESULTS_DIV}`).append(
          this.templateBuilder.buildLoadingLabel(),
        );
      }
    }

    hideLoading(hasResults) {
      const loadingElement = $(`#${CONSTANTS.IDS.LOADING_SPAN}`);
      loadingElement.remove();

      if (!hasResults) {
        $(`#${CONSTANTS.IDS.RESULTS_DIV}`).append(
          "<span>No result found</span>",
        );
      }
    }

    clearResults() {
      $("[data-omnisearch-result]").remove();
    }

    appendResult(resultHtml) {
      $(`#${CONSTANTS.IDS.RESULTS_DIV}`).append(resultHtml);
    }

    showError(message) {
      $(`#${CONSTANTS.IDS.LOADING_SPAN}`).html(message);
    }

    bindConfigClick(configManager) {
      $(document).on("click", `#${CONSTANTS.IDS.CONFIG_LINK}`, () =>
        configManager.open(),
      );
    }
  }

  // API Client
  class OmnisearchAPI {
    constructor(configManager) {
      this.configManager = configManager;
    }

    async search(query) {
      return new Promise((resolve, reject) => {
        const port = this.configManager.getPort();

        GM.xmlHttpRequest({
          method: "GET",
          url: `http://localhost:${port}/search?q=${query}`,
          headers: { "Content-Type": "application/json" },
          onload: (response) => {
            try {
              const data = JSON.parse(response.response);
              resolve(data);
            } catch (error) {
              reject(error);
            }
          },
          onerror: reject,
        });
      });
    }
  }

  // Search Result Processor
  class SearchResultProcessor {
    constructor(titleExtractor, textHighlighter, templateBuilder) {
      this.titleExtractor = titleExtractor;
      this.textHighlighter = textHighlighter;
      this.templateBuilder = templateBuilder;
    }

    processResults(results, maxResults) {
      return results.slice(0, maxResults).map((item) => this.processItem(item));
    }

    processItem(item) {
      const noteUrl = this.buildNoteUrl(item);
      const title = this.titleExtractor.extract(item);
      const highlightedExcerpt = this.textHighlighter.highlight(
        item.excerpt,
        item.foundWords,
      );

      return this.templateBuilder.buildSearchResult(
        item,
        noteUrl,
        title,
        highlightedExcerpt,
      );
    }

    buildNoteUrl(item) {
      return `obsidian://open?vault=${encodeURIComponent(item.vault)}&file=${encodeURIComponent(item.path)}`;
    }
  }

  // Main Application
  class OmnisearchKagiApp {
    constructor() {
      this.configManager = new ConfigManager();
      this.titleExtractor = new TitleExtractor();
      this.textHighlighter = new TextHighlighter();
      this.templateBuilder = new TemplateBuilder();
      this.domManager = new DOMManager(this.templateBuilder);
      this.apiClient = new OmnisearchAPI(this.configManager);
      this.resultProcessor = new SearchResultProcessor(
        this.titleExtractor,
        this.textHighlighter,
        this.templateBuilder,
      );

      // Add state management for search operations
      this.isSearching = false;
      this.lastQuery = null;
      this.lastUrl = null;
      this.searchTimeout = null; // Add timeout management
    }

    async initialize() {
      await this.configManager.waitForInit();
      this.setupUI();
      this.bindEvents();
      this.startSearch();
    }

    setupUI() {
      this.domManager.injectResultsContainer();
      this.domManager.injectHeader();
    }

    bindEvents() {
      this.domManager.bindConfigClick(this.configManager);

      // Set up multiple ways to detect navigation changes
      this.setupNavigationListeners();

      // Also set up waitForKeyElements as backup
      waitForKeyElements(CONSTANTS.SELECTORS.LAYOUT, () => {
        this.handlePageChange();
      });
    }

    setupNavigationListeners() {
      // Store reference to this for use in event handlers
      const self = this;

      // Listen for popstate events (back/forward navigation)
      window.addEventListener("popstate", () => {
        setTimeout(() => self.handlePageChange(), 100);
      });

      // Listen for pushstate/replacestate (programmatic navigation)
      const originalPushState = history.pushState;
      const originalReplaceState = history.replaceState;

      history.pushState = function () {
        originalPushState.apply(history, arguments);
        setTimeout(() => self.handlePageChange(), 100);
      };

      history.replaceState = function () {
        originalReplaceState.apply(history, arguments);
        setTimeout(() => self.handlePageChange(), 100);
      };

      // Poll for URL changes as fallback (in case SPA uses other navigation methods)
      this.startUrlPolling();
    }

    startUrlPolling() {
      setInterval(() => {
        const currentUrl = window.location.href;

        if (this.lastUrl !== currentUrl) {
          this.debouncedPerformSearch();
        }
      }, 500); // Check every 500ms
    }

    handlePageChange() {
      // Debounce the search to avoid race conditions
      this.debouncedPerformSearch();
    }

    debouncedPerformSearch() {
      // Clear any existing timeout

      if (this.searchTimeout) {
        clearTimeout(this.searchTimeout);
      }

      // Set a new timeout to perform search after a short delay
      this.searchTimeout = setTimeout(() => {
        this.performSearch();
      }, 150); // 150ms delay to handle rapid page changes
    }

    startSearch() {
      // Initialize with current URL and perform initial search
      this.lastUrl = window.location.href;
      this.performSearch();
    }

    async performSearch() {
      const query = this.getSearchQuery();
      const currentUrl = window.location.href;

      if (!query) return;

      // Prevent multiple simultaneous searches

      if (this.isSearching) return;

      // Check if this is the same query we already searched for in the current session
      // But allow searches if the URL has changed (even with the same query)

      if (this.lastQuery === query && this.lastUrl === currentUrl) return;

      this.isSearching = true;
      this.lastQuery = query;
      this.lastUrl = currentUrl;

      // IMPORTANT: Re-setup UI on each search to handle SPA navigation
      this.setupUI();
      this.domManager.showLoading();

      try {
        const results = await this.apiClient.search(query);
        this.displayResults(results);
      } catch (error) {
        this.handleSearchError(error);
      } finally {
        this.isSearching = false;
      }
    }

    getSearchQuery() {
      return new URLSearchParams(location.search).get("q");
    }

    displayResults(results) {
      this.domManager.hideLoading(results.length > 0);

      // Results are already cleared in showLoading(), so no need to clear again
      const maxResults = this.configManager.getMaxResults();
      const processedResults = this.resultProcessor.processResults(
        results,
        maxResults,
      );

      processedResults.forEach((resultHtml) => {
        this.domManager.appendResult(resultHtml);
      });
    }

    handleSearchError(error) {
      console.log("Omnisearch error", error);
      this.domManager.showError(
        `Error: Obsidian is not running or the Omnisearch server is not enabled.<br /><a href="Obsidian://open">Open Obsidian</a>.`,
      );
      // Reset search state on error
      this.isSearching = false;
    }
  }

  // Initialize the application
  const app = new OmnisearchKagiApp();
  app.initialize();
})();
