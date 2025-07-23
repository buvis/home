// ==UserScript==
// @name         Siebel: Obsidian Integration
// @namespace    https://github.com/buvis/home
// @downloadURL  https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-obsidian-integration.user.js
// @updateURL    https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-obsidian-integration.user.js
// @version      0.1.0
// @description  Add button to open/create notes in Obsidian for SR numbers
// @author       Tomáš Bouška
// @icon         https://www.oracle.com/asset/web/favicons/favicon-32.png
// @match        *://*/siebel/app/*
// @grant        GM.xmlHttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // Configuration - default Omnisearch port
    const OMNISEARCH_PORT = GM_getValue('omnisearch_port', '51361');

    // Obsidian SVG icon (inline)
    const obsidianIcon = `
<svg height="1em" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 256 256" style="vertical-align: middle;">
  <style>
    .purple { fill: #9974F8; }
    @media (prefers-color-scheme: dark) { .purple { fill: #A88BFA; } }
  </style>
  <path class="purple" d="M94.82 149.44c6.53-1.94 17.13-4.9 29.26-5.71a102.97 102.97 0 0 1-7.64-48.84c1.63-16.51 7.54-30.38 13.25-42.1l3.47-7.14 4.48-9.18c2.35-5 4.08-9.38 4.9-13.56.81-4.07.81-7.64-.2-11.11-1.03-3.47-3.07-7.14-7.15-11.21a17.02 17.02 0 0 0-15.8 3.77l-52.81 47.5a17.12 17.12 0 0 0-5.5 10.2l-4.5 30.18a149.26 149.26 0 0 1 38.24 57.2ZM54.45 106l-1.02 3.06-27.94 62.2a17.33 17.33 0 0 0 3.27 18.96l43.94 45.16a88.7 88.7 0 0 0 8.97-88.5A139.47 139.47 0 0 0 54.45 106Z"/>
  <path class="purple" d="m82.9 240.79 2.34.2c8.26.2 22.33 1.02 33.64 3.06 9.28 1.73 27.73 6.83 42.82 11.21 11.52 3.47 23.45-5.8 25.08-17.73 1.23-8.67 3.57-18.46 7.75-27.53a94.81 94.81 0 0 0-25.9-40.99 56.48 56.48 0 0 0-29.56-13.35 96.55 96.55 0 0 0-40.99 4.79 98.89 98.89 0 0 1-15.29 80.34h.1Z"/>
  <path class="purple" d="M201.87 197.76a574.87 574.87 0 0 0 19.78-31.6 8.67 8.67 0 0 0-.61-9.48 185.58 185.58 0 0 1-21.82-35.9c-5.91-14.16-6.73-36.08-6.83-46.69 0-4.07-1.22-8.05-3.77-11.21l-34.16-43.33c0 1.94-.4 3.87-.81 5.81a76.42 76.42 0 0 1-5.71 15.9l-4.7 9.8-3.36 6.72a111.95 111.95 0 0 0-12.03 38.23 93.9 93.9 0 0 0 8.67 47.92 67.9 67.9 0 0 1 39.56 16.52 99.4 99.4 0 0 1 25.8 37.31Z"/>
</svg>`;

    // Function to search Obsidian using Omnisearch
    function searchObsidian(query) {
        return new Promise((resolve, reject) => {
            GM.xmlHttpRequest({
                method: "GET",
                url: `http://localhost:${OMNISEARCH_PORT}/search?q=${encodeURIComponent(query)}`,
                headers: { "Content-Type": "application/json" },
                onload: (res) => {
                    try {
                        const data = JSON.parse(res.response);
                        resolve(data);
                    } catch (e) {
                        reject(e);
                    }
                },
                onerror: (res) => {
                    reject(res);
                }
            });
        });
    }

    // Function to filter results for exact ticket:: matches
    function filterExactTicketMatches(results, srNumber) {
        if (!results || !results.length) return [];

        const exactPattern = `ticket:: ${srNumber}`;
        return results.filter(result => {
            if (!result.excerpt) return false;
            return result.excerpt.includes(exactPattern);
        });
    }

    // Function to filter results for exact ticket-related:: matches
    function filterExactTicketRelatedMatches(results, srNumber) {
        if (!results || !results.length) return [];

        // Look for ticket-related:: followed by content that contains the SR number
        // The SR number can be anywhere between the :: and end of line, separated by spaces
        const ticketRelatedPattern = /ticket-related::\s*([^\n\r]*)/gi;

        return results.filter(result => {
            if (!result.excerpt) return false;

            const matches = [...result.excerpt.matchAll(ticketRelatedPattern)];
            return matches.some(match => {
                const content = match[1];
                // Split by spaces and check if any part matches our SR number exactly
                const srNumbers = content.split(/\s+/).filter(sr => sr.trim());
                return srNumbers.includes(srNumber);
            });
        });
    }

    // Enhanced search function that tries both ticket:: and ticket-related:: patterns
    async function searchForSRNote(srNumber) {
        try {
            // First search: exact ticket:: match
            const ticketQuery = `ticket:: ${srNumber}`;
            const ticketResults = await searchObsidian(ticketQuery);
            const exactTicketMatches = filterExactTicketMatches(ticketResults, srNumber);

            if (exactTicketMatches.length > 0) {
                return exactTicketMatches;
            }

            // Second search: ticket-related:: match if no exact ticket:: matches found
            const ticketRelatedQuery = `ticket-related:: ${srNumber}`;
            const ticketRelatedResults = await searchObsidian(ticketRelatedQuery);
            const exactTicketRelatedMatches = filterExactTicketRelatedMatches(ticketRelatedResults, srNumber);

            return exactTicketRelatedMatches;

        } catch (error) {
            throw error;
        }
    }

    // Function to open note in Obsidian
    function openObsidianNote(vault, path) {
        const noteUrl = `obsidian://open?vault=${encodeURIComponent(vault)}&file=${encodeURIComponent(path)}`;
        window.open(noteUrl, '_blank');
    }

    // Function to create new note in Obsidian with custom title
    function createObsidianNote(noteTitle) {
        const noteUrl = `obsidian://new?name=${encodeURIComponent(noteTitle)}`;
        window.open(noteUrl, '_blank');
    }

    // Function to copy text to clipboard
    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            console.log('SR number copied to clipboard:', text);
        }).catch(err => {
            console.error('Failed to copy to clipboard:', err);
            // Fallback method for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
        });
    }

    // Function to sanitize note title by replacing forbidden characters
    function sanitizeNoteTitle(title) {
        // Replace forbidden characters: < > : / \ | ? * " with dashes
        return title.replace(/[<>:/\\|?*"]/g, '-');
    }

    // Function to show confirmation dialog and get note title
    function showCreateNoteDialog(srNumber) {
        const shouldCreate = confirm(`No existing note found for SR ${srNumber}.\n\nWould you like to create a new note in Obsidian?`);

        if (shouldCreate) {
            const noteTitle = prompt(`Enter the title for the new note:`, `SR ${srNumber}`);
            if (noteTitle !== null && noteTitle.trim() !== '') {
                // Sanitize the title and copy SR number to clipboard
                const sanitizedTitle = sanitizeNoteTitle(noteTitle.trim());
                copyToClipboard(srNumber);
                return sanitizedTitle;
            }
        }
        return null;
    }

    // Function to add the Obsidian buttons
    function addObsidianButtons() {
        // Find the span with the SR number
        const srSpans = document.querySelectorAll('span.noquery[title]');

        srSpans.forEach(span => {
            // Check if we already added an Obsidian button to this span to avoid duplicates
            if (span.nextElementSibling && span.nextElementSibling.classList.contains('sr-obsidian-btn')) {
                return;
            }
            // Also check if there's already an obsidian button after a copy button
            if (span.nextElementSibling && span.nextElementSibling.nextElementSibling &&
                span.nextElementSibling.nextElementSibling.classList.contains('sr-obsidian-btn')) {
                return;
            }

            const srNumber = span.title;

            // Create Obsidian button
            const obsidianButton = document.createElement('button');
            obsidianButton.innerHTML = obsidianIcon;
            obsidianButton.title = 'Open/Create note in Obsidian';
            obsidianButton.className = 'sr-obsidian-btn';
            obsidianButton.style.cursor = 'pointer';
            obsidianButton.style.border = 'none';
            obsidianButton.style.background = 'transparent';
            obsidianButton.style.fontSize = '1.2em';

            // Add click event to search/create Obsidian note
            obsidianButton.addEventListener('click', async function (e) {
                e.preventDefault();
                e.stopPropagation();

                // Visual feedback - show loading
                const originalHTML = obsidianButton.innerHTML;
                obsidianButton.innerHTML = '⏳';
                obsidianButton.style.opacity = '0.6';

                try {
                    // Search for existing note using enhanced search
                    const results = await searchForSRNote(srNumber);

                    if (results && results.length > 0) {
                        // Found existing note - open the first result
                        const firstResult = results[0];
                        openObsidianNote(firstResult.vault, firstResult.path);

                        // Visual feedback - success
                        obsidianButton.innerHTML = '✓';
                        obsidianButton.style.color = 'green';
                    } else {
                        // No results found - ask user if they want to create a new note
                        const noteTitle = showCreateNoteDialog(srNumber);
                        if (noteTitle) {
                            createObsidianNote(noteTitle);

                            // Visual feedback - success
                            obsidianButton.innerHTML = '✓';
                            obsidianButton.style.color = 'green';
                        } else {
                            // User cancelled - restore original state
                            obsidianButton.innerHTML = originalHTML;
                            obsidianButton.style.opacity = '';
                            return;
                        }
                    }
                } catch (error) {
                    console.error('Obsidian search error:', error);
                    // Show error feedback
                    obsidianButton.innerHTML = '❌';
                    obsidianButton.style.color = 'red';
                    obsidianButton.title = 'Error: Obsidian not running or Omnisearch not enabled';
                }

                // Reset button after delay
                setTimeout(() => {
                    obsidianButton.innerHTML = originalHTML;
                    obsidianButton.style.color = '';
                    obsidianButton.style.opacity = '';
                    obsidianButton.title = 'Open/Create note in Obsidian';
                }, 2000);
            });

            // Insert the button after the SR number span (or after existing copy button if present)
            if (span.parentNode) {
                // Check if there's already a copy button next to this span
                const nextSibling = span.nextElementSibling;
                if (nextSibling && nextSibling.classList.contains('sr-copy-btn')) {
                    // Insert after the copy button
                    span.parentNode.insertBefore(obsidianButton, nextSibling.nextSibling);
                } else {
                    // Insert directly after the span
                    span.parentNode.insertBefore(obsidianButton, span.nextSibling);
                }
            }
        });
    }

    // Run the function initially
    setTimeout(addObsidianButtons, 2000);

    // Set up a mutation observer to detect when the SR info might be loaded
    // (in case the page loads dynamically)
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            if (mutation.addedNodes.length > 0) {
                setTimeout(addObsidianButtons, 500);
            }
        });
    });

    // Start observing the document with the configured parameters
    observer.observe(document.body, { childList: true, subtree: true });
})()
