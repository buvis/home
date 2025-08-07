// ==UserScript==
// @name         Siebel: Obsidian Integration
// @namespace    https://github.com/buvis/home
// @downloadURL  https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-obsidian-integration.user.js
// @updateURL    https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-obsidian-integration.user.js
// @version      0.4.0
// @description  Add button to open/create notes in Obsidian for SR numbers
// @author       Tomáš Bouška
// @icon         https://www.oracle.com/asset/web/favicons/favicon-32.png
// @match        *://*/siebel/app/*
// @grant        GM.xmlHttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // Constants
    // Register menu commands
    GM_registerMenuCommand('Configure Omnisearch Port', () => {
        const port = prompt('Enter Omnisearch port:', GM_getValue('omnisearch_port', '51361'));
        if (port && !isNaN(port)) {
            GM_setValue('omnisearch_port', port.trim());
            alert('Omnisearch port updated.');
        }
    });

    GM_registerMenuCommand('Configure Note Folder', () => {
        const folder = prompt('Enter folder for new notes (leave empty for root):', GM_getValue('note_folder', ''));
        GM_setValue('note_folder', folder?.trim() || '');
        alert('Note folder updated.');
    });

    const CONFIG = {
        OMNISEARCH_PORT: GM_getValue('omnisearch_port', '51361'),
        NOTE_FOLDER: GM_getValue('note_folder', ''),
        BUTTON_CLASS: 'sr-obsidian-btn',
        COPY_BUTTON_CLASS: 'sr-copy-btn',
        SR_SELECTOR: 'span.noquery[title]',
        FORBIDDEN_CHARS: /[<>:/\\|?*"]/g,
        TICKET_PATTERNS: {
            EXACT: 'ticket::',
            RELATED: /ticket-related::\s*([^\n\r]*)/gi
        },
        FEEDBACK_DURATION: 2000,
        INITIAL_DELAY: 2000,
        MUTATION_DELAY: 500
    };

    const OBSIDIAN_ICON = `
<svg height="1em" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 256 256" style="vertical-align: middle;">
  <style>
    .purple { fill: #9974F8; }
    @media (prefers-color-scheme: dark) { .purple { fill: #A88BFA; } }
  </style>
  <path class="purple" d="M94.82 149.44c6.53-1.94 17.13-4.9 29.26-5.71a102.97 102.97 0 0 1-7.64-48.84c1.63-16.51 7.54-30.38 13.25-42.1l3.47-7.14 4.48-9.18c2.35-5 4.08-9.38 4.9-13.56.81-4.07.81-7.64-.2-11.11-1.03-3.47-3.07-7.14-7.15-11.21a17.02 17.02 0 0 0-15.8 3.77l-52.81 47.5a17.12 17.12 0 0 0-5.5 10.2l-4.5 30.18a149.26 149.26 0 0 1 38.24 57.2ZM54.45 106l-1.02 3.06-27.94 62.2a17.33 17.33 0 0 0 3.27 18.96l43.94 45.16a88.7 88.7 0 0 0 8.97-88.5A139.47 139.47 0 0 0 54.45 106Z"/>
  <path class="purple" d="m82.9 240.79 2.34.2c8.26.2 22.33 1.02 33.64 3.06 9.28 1.73 27.73 6.83 42.82 11.21 11.52 3.47 23.45-5.8 25.08-17.73 1.23-8.67 3.57-18.46 7.75-27.53a94.81 94.81 0 0 0-25.9-40.99 56.48 56.48 0 0 0-29.56-13.35 96.55 96.55 0 0 0-40.99 4.79 98.89 98.89 0 0 1-15.29 80.34h.1Z"/>
  <path class="purple" d="M201.87 197.76a574.87 574.87 0 0 0 19.78-31.6 8.67 8.67 0 0 0-.61-9.48 185.58 185.58 0 0 1-21.82-35.9c-5.91-14.16-6.73-36.08-6.83-46.69 0-4.07-1.22-8.05-3.77-11.21l-34.16-43.33c0 1.94-.4 3.87-.81 5.81a76.42 76.42 0 0 1-5.71 15.9l-4.7 9.8-3.36 6.72a111.95 111.95 0 0 0-12.03 38.23 93.9 93.9 0 0 0 8.67 47.92 67.9 67.9 0 0 1 39.56 16.52 99.4 99.4 0 0 1 25.8 37.31Z"/>
</svg>`;

    class ObsidianSearchService {
        async search(query) {
            return new Promise((resolve, reject) => {
                GM.xmlHttpRequest({
                    method: "GET",
                    url: `http://localhost:${CONFIG.OMNISEARCH_PORT}/search?q=${encodeURIComponent(query)}`,
                    headers: { "Content-Type": "application/json" },
                    onload: (res) => {
                        try {
                            resolve(JSON.parse(res.response));
                        } catch (e) {
                            reject(e);
                        }
                    },
                    onerror: reject
                });
            });
        }

        filterExactMatches(results, srNumber) {
            if (!results?.length) return [];
            const exactPattern = `${CONFIG.TICKET_PATTERNS.EXACT} ${srNumber}`;
            return results.filter(result => result.excerpt?.includes(exactPattern));
        }

        filterRelatedMatches(results, srNumber) {
            if (!results?.length) return [];
            return results.filter(result => {
                if (!result.excerpt) return false;
                const matches = [...result.excerpt.matchAll(CONFIG.TICKET_PATTERNS.RELATED)];
                return matches.some(match => {
                    const srNumbers = match[1].split(/\s+/).filter(sr => sr.trim());
                    return srNumbers.includes(srNumber);
                });
            });
        }

        async findSRNote(srNumber) {
            const exactResults = await this.search(`${CONFIG.TICKET_PATTERNS.EXACT} ${srNumber}`);
            const exactMatches = this.filterExactMatches(exactResults, srNumber);

            if (exactMatches.length > 0) return exactMatches;

            const relatedResults = await this.search(`ticket-related:: ${srNumber}`);
            return this.filterRelatedMatches(relatedResults, srNumber);
        }
    }

    class ObsidianNoteService {
        open(vault, path) {
            const noteUrl = `obsidian://open?vault=${encodeURIComponent(vault)}&file=${encodeURIComponent(path)}`;
            window.open(noteUrl, '_blank');
        }

        create(noteTitle) {
            const folder = CONFIG.NOTE_FOLDER;
            let noteUrl;
            
            if (folder) {
                const fullPath = `${folder}/${noteTitle}.md`;
                noteUrl = `obsidian://advanced-uri?filepath=${encodeURIComponent(fullPath)}&mode=new`;
            } else {
                noteUrl = `obsidian://new?name=${encodeURIComponent(noteTitle)}`;
            }
            
            window.open(noteUrl, '_blank');
        }

        sanitizeTitle(title) {
            return title.replace(CONFIG.FORBIDDEN_CHARS, '-');
        }
    }

    class ClipboardService {
        async copy(text) {
            try {
                await navigator.clipboard.writeText(text);
                console.log('SR number copied to clipboard:', text);
            } catch (err) {
                console.error('Failed to copy to clipboard:', err);
                this.fallbackCopy(text);
            }
        }

        fallbackCopy(text) {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
        }
    }

    class DialogService {
        showCreateNoteDialog(srNumber) {
            const shouldCreate = confirm(`No existing note found for SR ${srNumber}.\n\nWould you like to create a new note in Obsidian?`);
            if (!shouldCreate) return null;

            const noteTitle = prompt(`Enter the title for the new note:`, `SR ${srNumber}`);
            return noteTitle?.trim() || null;
        }
    }

    class ButtonManager {
        constructor(searchService, noteService, clipboardService, dialogService) {
            this.searchService = searchService;
            this.noteService = noteService;
            this.clipboardService = clipboardService;
            this.dialogService = dialogService;
        }

        hasExistingButton(span) {
            const nextSibling = span.nextElementSibling;
            if (nextSibling?.classList.contains(CONFIG.BUTTON_CLASS)) return true;
            return nextSibling?.nextElementSibling?.classList.contains(CONFIG.BUTTON_CLASS);
        }

        createButton(srNumber) {
            const button = document.createElement('button');
            button.innerHTML = OBSIDIAN_ICON;
            button.title = 'Open/Create note in Obsidian';
            button.className = CONFIG.BUTTON_CLASS;
            Object.assign(button.style, {
                cursor: 'pointer',
                border: 'none',
                background: 'transparent',
                fontSize: '1.2em'
            });
            button.addEventListener('click', (e) => this.handleClick(e, button, srNumber));
            return button;
        }

        async handleClick(e, button, srNumber) {
            e.preventDefault();
            e.stopPropagation();

            const originalHTML = button.innerHTML;
            this.showLoading(button);

            try {
                const results = await this.searchService.findSRNote(srNumber);

                if (results?.length > 0) {
                    this.noteService.open(results[0].vault, results[0].path);
                    this.showSuccess(button);
                } else {
                    await this.handleNoteCreation(button, srNumber);
                }
            } catch (error) {
                console.error('Obsidian search error:', error);
                this.showError(button);
            }

            this.resetButton(button, originalHTML);
        }

        async handleNoteCreation(button, srNumber) {
            const noteTitle = this.dialogService.showCreateNoteDialog(srNumber);
            if (noteTitle) {
                const sanitizedTitle = this.noteService.sanitizeTitle(noteTitle);
                await this.clipboardService.copy(srNumber);
                this.noteService.create(sanitizedTitle);
                this.showSuccess(button);
            } else {
                this.restoreButton(button);
            }
        }

        showLoading(button) {
            button.innerHTML = '⏳';
            button.style.opacity = '0.6';
        }

        showSuccess(button) {
            button.innerHTML = '✓';
            button.style.color = 'green';
        }

        showError(button) {
            button.innerHTML = '❌';
            button.style.color = 'red';
            button.title = 'Error: Obsidian not running or Omnisearch not enabled';
        }

        restoreButton(button) {
            button.innerHTML = OBSIDIAN_ICON;
            button.style.opacity = '';
        }

        resetButton(button, originalHTML) {
            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.style.color = '';
                button.style.opacity = '';
                button.title = 'Open/Create note in Obsidian';
            }, CONFIG.FEEDBACK_DURATION);
        }

        insertButton(span, button) {
            if (!span.parentNode) return;

            const nextSibling = span.nextElementSibling;
            const insertAfter = nextSibling?.classList.contains(CONFIG.COPY_BUTTON_CLASS)
                ? nextSibling.nextSibling
                : span.nextSibling;

            span.parentNode.insertBefore(button, insertAfter);
        }

        addButtons() {
            const srSpans = document.querySelectorAll(CONFIG.SR_SELECTOR);

            srSpans.forEach(span => {
                if (this.hasExistingButton(span)) return;

                const srNumber = span.title;
                const button = this.createButton(srNumber);
                this.insertButton(span, button);
            });
        }
    }

    // Initialize services
    const searchService = new ObsidianSearchService();
    const noteService = new ObsidianNoteService();
    const clipboardService = new ClipboardService();
    const dialogService = new DialogService();
    const buttonManager = new ButtonManager(searchService, noteService, clipboardService, dialogService);

    // Initialize the application
    setTimeout(() => buttonManager.addButtons(), CONFIG.INITIAL_DELAY);

    const observer = new MutationObserver((mutations) => {
        if (mutations.some(mutation => mutation.addedNodes.length > 0)) {
            setTimeout(() => buttonManager.addButtons(), CONFIG.MUTATION_DELAY);
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
})()
