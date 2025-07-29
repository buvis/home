// ==UserScript==
// @name         Siebel: Copy SR Number
// @namespace    https://github.com/buvis/home
// @downloadURL  https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-copy-sr.user.js
// @updateURL    https://github.com/buvis/home/raw/master/.config/tampermonkey/siebel-copy-sr.user.js
// @version      0.2.0
// @description  Add a button to copy SR number in Siebel
// @author       Tomáš Bouška
// @icon         https://www.oracle.com/asset/web/favicons/favicon-32.png
// @match        *://*/siebel/app/*
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const CONFIG = {
        SELECTOR: 'span.noquery[title]',
        BUTTON_CLASS: 'sr-copy-btn',
        TIMEOUTS: {
            INITIAL_LOAD: 2000,
            MUTATION_DELAY: 500,
            FEEDBACK_DURATION: 1000
        },
        BUTTON_STYLES: {
            cursor: 'pointer',
            border: 'none',
            background: 'transparent',
            fontSize: '1.2em'
        },
        ICONS: {
            COPY: '📋',
            SUCCESS: '✓'
        }
    };

    class ClipboardService {
        copy(text) {
            GM_setClipboard(text);
        }
    }

    class ButtonStyler {
        static apply(button, styles) {
            Object.assign(button.style, styles);
        }

        static showFeedback(button, duration) {
            const originalText = button.innerHTML;
            button.innerHTML = CONFIG.ICONS.SUCCESS;
            button.style.color = 'green';

            setTimeout(() => {
                button.innerHTML = originalText;
                button.style.color = '';
            }, duration);
        }
    }

    class CopyButtonFactory {
        constructor(clipboardService) {
            this.clipboardService = clipboardService;
        }

        create(srNumber) {
            const button = document.createElement('button');
            button.innerHTML = CONFIG.ICONS.COPY;
            button.title = 'Copy SR number';
            button.className = CONFIG.BUTTON_CLASS;

            ButtonStyler.apply(button, CONFIG.BUTTON_STYLES);
            this.attachClickHandler(button, srNumber);

            return button;
        }

        attachClickHandler(button, srNumber) {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();

                this.clipboardService.copy(srNumber);
                ButtonStyler.showFeedback(button, CONFIG.TIMEOUTS.FEEDBACK_DURATION);
            });
        }
    }

    class SRElementFinder {
        findElements() {
            return document.querySelectorAll(CONFIG.SELECTOR);
        }

        hasExistingButton(element) {
            return element.nextElementSibling?.classList.contains(CONFIG.BUTTON_CLASS);
        }
    }

    class ButtonInjector {
        constructor(buttonFactory, elementFinder) {
            this.buttonFactory = buttonFactory;
            this.elementFinder = elementFinder;
        }

        injectButtons() {
            const elements = this.elementFinder.findElements();

            elements.forEach(element => {
                if (this.elementFinder.hasExistingButton(element)) {
                    return;
                }

                const button = this.buttonFactory.create(element.title);
                this.insertButton(element, button);
            });
        }

        insertButton(element, button) {
            element.parentNode?.insertBefore(button, element.nextSibling);
        }
    }

    class SiebelCopyManager {
        constructor() {
            this.clipboardService = new ClipboardService();
            this.buttonFactory = new CopyButtonFactory(this.clipboardService);
            this.elementFinder = new SRElementFinder();
            this.buttonInjector = new ButtonInjector(this.buttonFactory, this.elementFinder);
        }

        initialize() {
            setTimeout(() => this.buttonInjector.injectButtons(), CONFIG.TIMEOUTS.INITIAL_LOAD);
            this.setupMutationObserver();
        }

        setupMutationObserver() {
            const observer = new MutationObserver((mutations) => {
                const hasNewNodes = mutations.some(mutation => mutation.addedNodes.length > 0);
                if (hasNewNodes) {
                    setTimeout(() => this.buttonInjector.injectButtons(), CONFIG.TIMEOUTS.MUTATION_DELAY);
                }
            });

            observer.observe(document.body, { childList: true, subtree: true });
        }
    }

    new SiebelCopyManager().initialize();
})()