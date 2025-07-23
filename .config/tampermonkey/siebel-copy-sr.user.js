// ==UserScript==
// @name         Siebel: Copy SR Number
// @namespace    https://github.com/buvis/home
// @downloadURL  https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-copy-sr.user.js
// @updateURL    https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-copy-sr.user.js
// @version      0.1.0
// @description  Add a button to copy SR number in Siebel
// @author       Tomáš Bouška
// @icon         https://www.oracle.com/asset/web/favicons/favicon-32.png
// @match        *://*/siebel/app/*
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // Function to add the copy button
    function addCopyButton() {
        // Find the span with the SR number
        const srSpans = document.querySelectorAll('span.noquery[title]');

        srSpans.forEach(span => {
            // Check if we already added a button to this span to avoid duplicates
            if (span.nextElementSibling && span.nextElementSibling.classList.contains('sr-copy-btn')) {
                return;
            }

            // Create copy button
            const copyButton = document.createElement('button');
            copyButton.innerHTML = '📋';
            copyButton.title = 'Copy SR number';
            copyButton.className = 'sr-copy-btn';
            copyButton.style.cursor = 'pointer';
            copyButton.style.border = 'none';
            copyButton.style.background = 'transparent';
            copyButton.style.fontSize = '1.2em';

            // Add click event to copy the SR number
            copyButton.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();

                const srNumber = span.title;
                GM_setClipboard(srNumber);

                // Visual feedback
                const originalText = copyButton.innerHTML;
                copyButton.innerHTML = '✓';
                copyButton.style.color = 'green';

                setTimeout(() => {
                    copyButton.innerHTML = originalText;
                    copyButton.style.color = '';
                }, 1000);
            });

            // Insert the button after the SR number span
            if (span.parentNode) {
                span.parentNode.insertBefore(copyButton, span.nextSibling);
            }
        });
    }

    // Run the function initially
    setTimeout(addCopyButton, 2000);

    // Set up a mutation observer to detect when the SR info might be loaded
    // (in case the page loads dynamically)
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            if (mutation.addedNodes.length > 0) {
                setTimeout(addCopyButton, 500);
            }
        });
    });

    // Start observing the document with the configured parameters
    observer.observe(document.body, { childList: true, subtree: true });
})()