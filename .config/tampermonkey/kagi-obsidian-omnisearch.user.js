"use strict";
// ==UserScript==
// @name         Obsidian Omnisearch in Kagi
// @namespace    https://github.com/buvis/home
// @downloadURL  https://github.com/buvis/home/raw/master/.config/tampermonkey/kagi-obsidian-omnisearch.user.js
// @updateURL    https://github.com/buvis/home/raw/master/.config/tampermonkey/kagi-obsidian-omnisearch.user.js
// @version      0.1.0
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
// ==/UserScript==
//
// Based on the work of Simon Cambier
//
/* globals GM_config, $, waitForKeyElements */
(function () {
  const sidebarSelector = ".right-content-box";
  const resultsDivId = "OmnisearchObsidianResults";
  const loadingSpanId = "OmnisearchObsidianLoading";

  // Config dialog
  // @ts-ignore
  const config = new GM_config({
    id: "ObsidianOmnisearchKagi",
    title: "Omnisearch in Kagi - Configuration",
    fields: {
      port: { label: "HTTP Port", type: "text", default: "51361" },
      nbResults: {
        label: "Number of results to display",
        type: "int",
        default: 3,
      },
    },
    events: { save: () => location.reload() },
  });

  const onConfigInit = (cfg) =>
    new Promise((resolve) => {
      (function check() {
        cfg.isInit ? resolve() : setTimeout(check, 0);
      })();
    });

  // Obsidian SVG (inline)
  const logo = `
<svg height="1em" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 256 256">
  <style>
    .purple { fill: #9974F8; }
    @media (prefers-color-scheme: dark) { .purple { fill: #A88BFA; } }
  </style>
  <path class="purple" d="M94.82 149.44c6.53-1.94 17.13-4.9 29.26-5.71a102.97 102.97 0 0 1-7.64-48.84c1.63-16.51 7.54-30.38 13.25-42.1l3.47-7.14 4.48-9.18c2.35-5 4.08-9.38 4.9-13.56.81-4.07.81-7.64-.2-11.11-1.03-3.47-3.07-7.14-7.15-11.21a17.02 17.02 0 0 0-15.8 3.77l-52.81 47.5a17.12 17.12 0 0 0-5.5 10.2l-4.5 30.18a149.26 149.26 0 0 1 38.24 57.2ZM54.45 106l-1.02 3.06-27.94 62.2a17.33 17.33 0 0 0 3.27 18.96l43.94 45.16a88.7 88.7 0 0 0 8.97-88.5A139.47 139.47 0 0 0 54.45 106Z"/>
  <path class="purple" d="m82.9 240.79 2.34.2c8.26.2 22.33 1.02 33.64 3.06 9.28 1.73 27.73 6.83 42.82 11.21 11.52 3.47 23.45-5.8 25.08-17.73 1.23-8.67 3.57-18.46 7.75-27.53a94.81 94.81 0 0 0-25.9-40.99 56.48 56.48 0 0 0-29.56-13.35 96.55 96.55 0 0 0-40.99 4.79 98.89 98.89 0 0 1-15.29 80.34h.1Z"/>
  <path class="purple" d="M201.87 197.76a574.87 574.87 0 0 0 19.78-31.6 8.67 8.67 0 0 0-.61-9.48 185.58 185.58 0 0 1-21.82-35.9c-5.91-14.16-6.73-36.08-6.83-46.69 0-4.07-1.22-8.05-3.77-11.21l-34.16-43.33c0 1.94-.4 3.87-.81 5.81a76.42 76.42 0 0 1-5.71 15.9l-4.7 9.8-3.36 6.72a111.95 111.95 0 0 0-12.03 38.23 93.9 93.9 0 0 0 8.67 47.92 67.9 67.9 0 0 1 39.56 16.52 99.4 99.4 0 0 1 25.8 37.31Z"/>
</svg>`;

  function injectResultsContainer() {
    $(`#${resultsDivId}`).remove();
    const html = `
      <div class="_0_right_sidebar _0_provider-content">
        <div id="wikipediaResults" class="_0_provider-content">
          <div class="scene">
            <div class="wikipediaResult">
              <div class="card__face">
                <div id="${resultsDivId}" style="margin-bottom: 2em;"></div>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    $(sidebarSelector).prepend(html);
  }

  function injectHeader() {
    const cfgId = "OmnisearchObsidianConfig";

    if ($("#" + cfgId).length) return;
    const html = `
      <div style="margin-bottom:1em;">
        <span style="font-size:1.2em">${logo}&nbsp;Omnisearch results</span>
        <span style="font-size:0.8em;">
          (<a id="${cfgId}" title="Settings" href="#">settings</a>)
        </span>
      </div>`;
    $(`#${resultsDivId}`).append(html);
    $(document).on("click", "#" + cfgId, () => config.open());
  }

  function injectLoadingLabel() {
    if (!$("#" + loadingSpanId).length) {
      $(`#${resultsDivId}`).append(
        `<span id="${loadingSpanId}">Loading...</span>`,
      );
    }
  }

  function setLoadingDone(foundResults) {
    const label = $("#" + loadingSpanId);

    if (foundResults) label.remove();
    else label.text("No result found");
  }

  function omnisearch() {
    const port = config.get("port");
    const limit = config.get("nbResults");
    const query = new URLSearchParams(location.search).get("q");

    if (!query) return;
    injectLoadingLabel();
    GM.xmlHttpRequest({
      method: "GET",
      url: `http://localhost:${port}/search?q=${query}`,
      headers: { "Content-Type": "application/json" },
      onload: (res) => {
        const data = JSON.parse(res.response);
        setLoadingDone(data.length);
        data.splice(limit);
        $("[data-omnisearch-result]").remove();
        data.forEach((item) => {
          const noteUrl = `obsidian://open?vault=${encodeURIComponent(item.vault)}&file=${encodeURIComponent(item.path)}`;
          const resultHtml = `
<div class="_0_SRI _ext_ub_r search-result" data-omnisearch-result>
  <div class="_0_TITLE __sri-title">
    <h3 class="__sri-title-box">
      <a class="__sri_title_link _ext_ub_t _0_sri_title_link _0_URL"
         title="${extractTitle(item)}"
         href="${noteUrl}" rel="noopener noreferrer">
         ${extractTitle(item)}
      </a>
    </h3>
  </div>
  <div class="__sri-url-box">
    <a class="_0_URL __sri-url _ext_ub_u" href="${noteUrl}" style="border-bottom:2px solid transparent;">
      <div class="__sri_url_path_box">
        <span class="host">${logo}Obsidian</span>&nbsp;<span class="path">› ${item.path}</span>
      </div>
    </a>
  </div>
  <div class="__sri-body">
    <div class="_0_DESC __sri-desc">
      <div>${highlightTerms(item.excerpt, item.foundWords)}</div>
    </div>
  </div>
</div>`;
          $(`#${resultsDivId}`).append(resultHtml);
        });
      },
      onerror: (res) => {
        console.log("Omnisearch error", res);
        $("#" + loadingSpanId).html(
          `Error: Obsidian is not running or the Omnisearch server is not enabled.<br /><a href="Obsidian://open">Open Obsidian</a>.`,
        );
      },
    });
  }

  function highlightTerms(excerpt, words) {
    if (!words || !words.length) return excerpt;
    const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`\\b(${words.map(esc).join("|")})\\b`, "gi");

    return excerpt.replace(
      regex,
      '<span style="background-color:#eee8d5;color:#586e75;padding:0.15em 0.2em;">$1</span>',
    );
  }

  function extractTitle({ excerpt, basename }) {
    const t1 = excerpt.match(/title: (.+?)<br>/i);

    if (t1) return t1[1].trim();
    const h1 = excerpt.match(/(?:^|<br>)# ([^#].*?)<br>/i);

    if (h1) return h1[1].trim();

    if (/^\d{14}-/.test(basename))
      return basename
        .slice(15)
        .replace(/-/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());

    return basename;
  }

  onConfigInit(config).then(() => {
    injectResultsContainer();
    injectHeader();
    waitForKeyElements("#layout-v2", omnisearch);
    omnisearch();
  });
})();
