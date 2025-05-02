// Self-executing function to make it runnable in console
// (function() { // REMOVED
    // Store the result in a global variable for console access
    window.domTreeResult = (
        args = {
            doHighlightElements: false, // CHANGED: Default to false
            focusHighlightIndex: -1,
            viewportExpansion: 0,
            debugMode: false, // Changed from False to false
        }
    ) => {
        const { doHighlightElements, focusHighlightIndex, viewportExpansion, debugMode } = args;
        let highlightIndex = 0;

        // Improved caching mechanism for DOM tree analysis
        const DOM_CACHE = {
            boundingRects: new WeakMap(),
            computedStyles: new WeakMap(),
            previousWindowSize: { width: window.innerWidth, height: window.innerHeight },
            lastRunTimestamp: Date.now(),
            clearCache: function(force = false) {
                const currentWindowSize = { width: window.innerWidth, height: window.innerHeight };
                const currentTime = Date.now();
                // Only clear cache when necessary:
                // 1. When forced
                // 2. When viewport size changes
                // 3. When significant time has passed (30+ seconds)
                if (force || 
                    currentWindowSize.width !== this.previousWindowSize.width || 
                    currentWindowSize.height !== this.previousWindowSize.height ||
                    (currentTime - this.lastRunTimestamp > 30000)) {
                    
                    this.boundingRects = new WeakMap();
                    this.computedStyles = new WeakMap();
                    this.previousWindowSize = currentWindowSize;
                    this.lastRunTimestamp = currentTime;
                    return true;
                }
                // Just update the timestamp but keep the cache
                this.lastRunTimestamp = currentTime;
                return false;
            }
        };

        function getWebsiteInfo() {
            const info = {
                url: window.location.href,
                title: document.title || "",
                domain: window.location.hostname,
                path: window.location.pathname,
            };
            
            // Get meta description
            const metaDescription = document.querySelector('meta[name="description"]');
            if (metaDescription) {
                info.description = metaDescription.getAttribute('content');
            }
            
            // Get meta keywords
            const metaKeywords = document.querySelector('meta[name="keywords"]');
            if (metaKeywords) {
                info.keywords = metaKeywords.getAttribute('content');
            }
            
            // Get Open Graph metadata
            const ogTitle = document.querySelector('meta[property="og:title"]');
            const ogDescription = document.querySelector('meta[property="og:description"]');
            const ogType = document.querySelector('meta[property="og:type"]');
            
            info.openGraph = {};
            if (ogTitle) info.openGraph.title = ogTitle.getAttribute('content');
            if (ogDescription) info.openGraph.description = ogDescription.getAttribute('content');
            if (ogType) info.openGraph.type = ogType.getAttribute('content');
            
            // Try to get main content text sample
            try {
                // Get h1 text content
                const h1Elements = Array.from(document.querySelectorAll('h1')).filter(el => 
                    el.offsetWidth > 0 && 
                    el.offsetHeight > 0 && 
                    window.getComputedStyle(el).display !== 'none'
                );
                
                info.mainHeadings = h1Elements.map(el => el.textContent.trim()).filter(text => text.length > 0);
                
                // Get text from potential main content areas
                const mainContentSelectors = [
                    'main', 
                    'article', 
                    '#content', 
                    '.content', 
                    '[role="main"]'
                ];
                
                for (const selector of mainContentSelectors) {
                    const element = document.querySelector(selector);
                    if (element) {
                        const text = element.textContent.trim().substring(0, 500);
                        if (text.length > 100) {
                            info.mainContentSample = text;
                            break;
                        }
                    }
                }
                
                // If no main content found, get a sample from body text
                if (!info.mainContentSample) {
                    const bodyText = document.body.textContent.trim();
                    info.mainContentSample = bodyText.substring(0, 500);
                }
            } catch (e) {
                console.warn('Error extracting main content:', e);
            }
            
            // Get JSON-LD structured data if available
            try {
                const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
                if (jsonLdScripts.length > 0) {
                    info.structuredData = [];
                    jsonLdScripts.forEach(script => {
                        try {
                            const data = JSON.parse(script.textContent);
                            info.structuredData.push(data);
                        } catch (err) {
                            console.warn('Error parsing JSON-LD:', err);
                        }
                    });
                }
            } catch (e) {
                console.warn('Error extracting structured data:', e);
            }
            
            return info;
        }

        // Cache helper functions
        function getCachedBoundingRect(element) {
            if (!element) return null;

            if (DOM_CACHE.boundingRects.has(element)) {
                return DOM_CACHE.boundingRects.get(element);
            }

            const rect = element.getBoundingClientRect();
            if (rect) {
                DOM_CACHE.boundingRects.set(element, rect);
            }
            return rect;
        }

        function getCachedComputedStyle(element) {
            if (!element) return null;

            if (DOM_CACHE.computedStyles.has(element)) {
                return DOM_CACHE.computedStyles.get(element);
            }

            const style = window.getComputedStyle(element);
            if (style) {
                DOM_CACHE.computedStyles.set(element, style);
            }
            return style;
        }

        // Store highlighted elements
        const HIGHLIGHT_CONTAINER_ID = "playwright-highlight-container";
        const highlightedElements = [];
        
        // Track elements and their bounding rectangles to detect duplicates
        const processedElementAreas = [];

        /**
         * Highlights an element in the DOM and returns the index of the next element.
         */
        function highlightElement(element, index, iframeElement = null) {
            if (!element) return index;

            try {
                // Create or get highlight container
                let container = document.getElementById(HIGHLIGHT_CONTAINER_ID);
                if (!container) {
                    container = document.createElement("div");
                    container.id = HIGHLIGHT_CONTAINER_ID;
                    container.style.position = "fixed";
                    container.style.pointerEvents = "none";
                    container.style.top = "0";
                    container.style.left = "0";
                    container.style.width = "100%";
                    container.style.height = "100%";
                    container.style.zIndex = "2147483647";
                    document.body.appendChild(container);
                }

                // Get element position
                const elementRect = element.getBoundingClientRect();
                
                // Default to element's own coordinates
                let top = elementRect.top;
                let left = elementRect.left;
                let width = elementRect.width;
                let height = elementRect.height;
                
                // If element is in an iframe, adjust coordinates
                if (iframeElement) {
                    const iframeRect = iframeElement.getBoundingClientRect();
                    top = iframeRect.top + elementRect.top;
                    left = iframeRect.left + elementRect.left;
                }

                // Generate a color based on the index
                const colors = [
                    "#FF0000", "#00FF00", "#0000FF", "#FFA500", "#800080", 
                    "#008080", "#FF69B4", "#4B0082", "#FF4500", "#2E8B57"
                ];
                const colorIndex = index % colors.length;
                const baseColor = colors[colorIndex];
                const backgroundColor = baseColor + "1A"; // 10% opacity

                // Create highlight overlay
                const overlay = document.createElement("div");
                overlay.style.position = "fixed";
                overlay.style.border = `2px solid ${baseColor}`;
                overlay.style.backgroundColor = backgroundColor;
                overlay.style.pointerEvents = "none";
                overlay.style.boxSizing = "border-box";
                overlay.style.top = `${top}px`;
                overlay.style.left = `${left}px`;
                overlay.style.width = `${width}px`;
                overlay.style.height = `${height}px`;

                // Create label
                const label = document.createElement("div");
                label.className = "playwright-highlight-label";
                label.style.position = "fixed";
                label.style.background = baseColor;
                label.style.color = "white";
                label.style.padding = "1px 4px";
                label.style.borderRadius = "4px";
                label.style.fontSize = `${Math.min(12, Math.max(8, height / 2))}px`;
                label.textContent = index;

                // Position label
                const labelWidth = 20;
                const labelHeight = 16;
                let labelTop = top + 2;
                let labelLeft = left + width - labelWidth - 2;

                if (width < labelWidth + 4 || height < labelHeight + 4) {
                    labelTop = top - labelHeight - 2;
                    labelLeft = left + width - labelWidth;
                }

                label.style.top = `${labelTop}px`;
                label.style.left = `${labelLeft}px`;

                // Add to container
                container.appendChild(overlay);
                container.appendChild(label);

                return index + 1;
            } catch (e) {
                console.warn("Error highlighting element:", e);
                return index;
            }
        }

        /**
         * Highlights a scrollbar with a special color and styling
         */
        function highlightScrollbar(element, index, isVertical = true, isHorizontal = true, isMainScrollbar = false) {
            if (!element) return index;

            try {
                // Create or get highlight container
                let container = document.getElementById(HIGHLIGHT_CONTAINER_ID);
                if (!container) {
                    container = document.createElement("div");
                    container.id = HIGHLIGHT_CONTAINER_ID;
                    container.style.position = "fixed";
                    container.style.pointerEvents = "none";
                    container.style.top = "0";
                    container.style.left = "0";
                    container.style.width = "100%";
                    container.style.height = "100%";
                    container.style.zIndex = "2147483647";
                    document.body.appendChild(container);
                }

                // Get element position
                const elementRect = isMainScrollbar ? 
                    { top: 0, left: 0, right: window.innerWidth, bottom: window.innerHeight } : 
                    element.getBoundingClientRect();
                
                const scrollBarWidth = isMainScrollbar ? 
                    window.innerWidth - document.documentElement.clientWidth : 
                    element.offsetWidth - element.clientWidth;
                    
                const scrollBarHeight = isMainScrollbar ? 
                    window.innerHeight - document.documentElement.clientHeight : 
                    element.offsetHeight - element.clientHeight;

                // Use a special color for scrollbars - purple
                const baseColor = "#9932CC"; // Dark orchid
                const backgroundColor = baseColor + "33"; // 20% opacity

                // Create scrollbar highlights
                if (isVertical && scrollBarWidth > 0) {
                    // Vertical scrollbar
                    const verticalOverlay = document.createElement("div");
                    verticalOverlay.style.position = "fixed";
                    verticalOverlay.style.border = `2px solid ${baseColor}`;
                    verticalOverlay.style.backgroundColor = backgroundColor;
                    verticalOverlay.style.pointerEvents = "none";
                    verticalOverlay.style.boxSizing = "border-box";
                    
                    if (isMainScrollbar) {
                        verticalOverlay.style.top = "0";
                        verticalOverlay.style.right = "0";
                        verticalOverlay.style.width = `${scrollBarWidth}px`;
                        verticalOverlay.style.height = "100%";
                    } else {
                        verticalOverlay.style.top = `${elementRect.top}px`;
                        verticalOverlay.style.left = `${elementRect.right - scrollBarWidth}px`;
                        verticalOverlay.style.width = `${scrollBarWidth}px`;
                        verticalOverlay.style.height = `${elementRect.height}px`;
                    }
                    
                    container.appendChild(verticalOverlay);

                    // Calculate and show thumb position (if possible)
                    if (isMainScrollbar) {
                        if (document.documentElement.scrollHeight > window.innerHeight) {
                            const thumbHeight = Math.max(40, (window.innerHeight / document.documentElement.scrollHeight) * window.innerHeight);
                            const scrollPercentage = document.documentElement.scrollTop / 
                                                   (document.documentElement.scrollHeight - window.innerHeight);
                            const thumbPosition = scrollPercentage * (window.innerHeight - thumbHeight);
                            
                            const thumbOverlay = document.createElement("div");
                            thumbOverlay.style.position = "fixed";
                            thumbOverlay.style.backgroundColor = baseColor;
                            thumbOverlay.style.pointerEvents = "none";
                            thumbOverlay.style.boxSizing = "border-box";
                            thumbOverlay.style.top = `${thumbPosition}px`;
                            thumbOverlay.style.right = "0";
                            thumbOverlay.style.width = `${scrollBarWidth}px`;
                            thumbOverlay.style.height = `${thumbHeight}px`;
                            thumbOverlay.style.borderRadius = "3px";
                            container.appendChild(thumbOverlay);
                        }
                    } else if (element.scrollHeight > element.clientHeight) {
                        const thumbHeight = Math.max(30, (element.clientHeight / element.scrollHeight) * elementRect.height);
                        const thumbPosition = (element.scrollTop / (element.scrollHeight - element.clientHeight)) * 
                                             (elementRect.height - thumbHeight);
                        
                        const thumbOverlay = document.createElement("div");
                        thumbOverlay.style.position = "fixed";
                        thumbOverlay.style.backgroundColor = baseColor;
                        thumbOverlay.style.pointerEvents = "none";
                        thumbOverlay.style.boxSizing = "border-box";
                        thumbOverlay.style.top = `${elementRect.top + thumbPosition}px`;
                        thumbOverlay.style.left = `${elementRect.right - scrollBarWidth + 2}px`;
                        thumbOverlay.style.width = `${scrollBarWidth - 4}px`;
                        thumbOverlay.style.height = `${thumbHeight}px`;
                        thumbOverlay.style.borderRadius = "3px";
                        container.appendChild(thumbOverlay);
                    }
                }

                if (isHorizontal && scrollBarHeight > 0) {
                    // Horizontal scrollbar
                    const horizontalOverlay = document.createElement("div");
                    horizontalOverlay.style.position = "fixed";
                    horizontalOverlay.style.border = `2px solid ${baseColor}`;
                    horizontalOverlay.style.backgroundColor = backgroundColor;
                    horizontalOverlay.style.pointerEvents = "none";
                    horizontalOverlay.style.boxSizing = "border-box";
                    
                    if (isMainScrollbar) {
                        horizontalOverlay.style.bottom = "0";
                        horizontalOverlay.style.left = "0";
                        horizontalOverlay.style.height = `${scrollBarHeight}px`;
                        horizontalOverlay.style.width = "100%";
                    } else {
                        horizontalOverlay.style.top = `${elementRect.bottom - scrollBarHeight}px`;
                        horizontalOverlay.style.left = `${elementRect.left}px`;
                        horizontalOverlay.style.width = `${elementRect.width}px`;
                        horizontalOverlay.style.height = `${scrollBarHeight}px`;
                    }
                    
                    container.appendChild(horizontalOverlay);

                    // Calculate and show thumb position (if possible)
                    if (isMainScrollbar) {
                        if (document.documentElement.scrollWidth > window.innerWidth) {
                            const thumbWidth = Math.max(40, (window.innerWidth / document.documentElement.scrollWidth) * window.innerWidth);
                            const scrollPercentage = document.documentElement.scrollLeft / 
                                                   (document.documentElement.scrollWidth - window.innerWidth);
                            const thumbPosition = scrollPercentage * (window.innerWidth - thumbWidth);
                            
                            const thumbOverlay = document.createElement("div");
                            thumbOverlay.style.position = "fixed";
                            thumbOverlay.style.backgroundColor = baseColor;
                            thumbOverlay.style.pointerEvents = "none";
                            thumbOverlay.style.boxSizing = "border-box";
                            thumbOverlay.style.bottom = "0";
                            thumbOverlay.style.left = `${thumbPosition}px`;
                            thumbOverlay.style.height = `${scrollBarHeight}px`;
                            thumbOverlay.style.width = `${thumbWidth}px`;
                            thumbOverlay.style.borderRadius = "3px";
                            container.appendChild(thumbOverlay);
                        }
                    } else if (element.scrollWidth > element.clientWidth) {
                        const thumbWidth = Math.max(30, (element.clientWidth / element.scrollWidth) * elementRect.width);
                        const thumbPosition = (element.scrollLeft / (element.scrollWidth - element.clientWidth)) * 
                                            (elementRect.width - thumbWidth);
                        
                        const thumbOverlay = document.createElement("div");
                        thumbOverlay.style.position = "fixed";
                        thumbOverlay.style.backgroundColor = baseColor;
                        thumbOverlay.style.pointerEvents = "none";
                        thumbOverlay.style.boxSizing = "border-box";
                        thumbOverlay.style.top = `${elementRect.bottom - scrollBarHeight + 2}px`;
                        thumbOverlay.style.left = `${elementRect.left + thumbPosition}px`;
                        thumbOverlay.style.width = `${thumbWidth}px`;
                        thumbOverlay.style.height = `${scrollBarHeight - 4}px`;
                        thumbOverlay.style.borderRadius = "3px";
                        container.appendChild(thumbOverlay);
                    }
                }

                // Add label
                const label = document.createElement("div");
                label.className = "playwright-highlight-label";
                label.style.position = "fixed";
                label.style.background = baseColor;
                label.style.color = "white";
                label.style.padding = "1px 4px";
                label.style.borderRadius = "4px";
                label.style.fontSize = "10px";
                label.style.fontWeight = "bold";
                
                if (isMainScrollbar) {
                    if (isVertical && !isHorizontal) {
                        label.textContent = `M-V:${index}`;
                        label.style.top = "5px";
                        label.style.right = `${scrollBarWidth + 5}px`;
                    } else if (isHorizontal && !isVertical) {
                        label.textContent = `M-H:${index}`;
                        label.style.bottom = `${scrollBarHeight + 5}px`;
                        label.style.left = "5px";
                    } else {
                        label.textContent = `M-B:${index}`;
                        label.style.top = "5px";
                        label.style.right = `${scrollBarWidth + 5}px`;
                    }
                } else {
                    label.textContent = `S:${index}`;
                    // Position label in the corner near scrollbar
                    let labelTop = elementRect.top + 2;
                    let labelLeft = elementRect.right - 25;

                    if (isHorizontal && !isVertical) {
                        labelTop = elementRect.bottom - 18;
                        labelLeft = elementRect.right - 25;
                    }

                    label.style.top = `${labelTop}px`;
                    label.style.left = `${labelLeft}px`;
                }
                
                container.appendChild(label);

                return index + 1;
            } catch (e) {
                console.warn("Error highlighting scrollbar:", e);
                return index;
            }
        }

        /**
         * Returns a JSPath selector for an element
         * This is a more JavaScript-friendly way to uniquely identify elements
         */
        function getJSPathForElement(element) {
            if (!element || !element.tagName) return '';
            
            const path = [];
            let current = element;

            while (current && current.nodeType === Node.ELEMENT_NODE) {
                let selector = current.tagName.toLowerCase();
                
                // Add id if available (most specific)
                if (current.id) {
                    selector += '#' + CSS.escape(current.id);
                    path.unshift(selector);
                    break; // ID is unique, so we can stop here
                }
                
                // Add useful attributes to make the selector more specific
                const attrs = [];
                
                // Add classes
                if (current.classList && current.classList.length) {
                    const classSelector = Array.from(current.classList)
                        .map(c => '.' + CSS.escape(c))
                        .join('');
                    if (classSelector) {
                        selector += classSelector;
                    }
                }
                
                // Add other distinguishing attributes
                if (current.hasAttribute('name')) {
                    attrs.push(`[name="${CSS.escape(current.getAttribute('name'))}"]`);
                }
                
                if (current.hasAttribute('role')) {
                    attrs.push(`[role="${CSS.escape(current.getAttribute('role'))}"]`);
                }
                
                if (current.hasAttribute('aria-label')) {
                    const ariaLabel = current.getAttribute('aria-label');
                    if (ariaLabel.length < 20) { // Only use short aria-labels
                        attrs.push(`[aria-label="${CSS.escape(ariaLabel)}"]`);
                    }
                }
                
                // If element has no distinguishing features, add nth-child
                if (!selector.includes('#') && !selector.includes('.') && attrs.length === 0) {
                    // Find position among siblings of same type
                    let position = 1;
                    let sibling = current.previousElementSibling;
                    
                while (sibling) {
                        if (sibling.tagName === current.tagName) {
                            position++;
                        }
                        sibling = sibling.previousElementSibling;
                    }
                    
                    if (position > 1) {
                        selector += `:nth-of-type(${position})`;
                    }
                }
                
                // Add any additional attributes
                selector += attrs.join('');
                
                // Add to path
                path.unshift(selector);
                
                // Move up to parent
                current = current.parentElement;
            }
            
            return path.join(' > ');
        }


        /**
         * Robustly checks if an element is in the viewport
         */
        function isInViewport(element) {
            if (viewportExpansion === -1) {
                return true; // Consider all elements in viewport if expansion is -1
            }

            const rect = getCachedBoundingRect(element);
            if (!rect) return false;

            // Get real viewport size
            const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
            const viewportHeight = window.innerHeight || document.documentElement.clientHeight;

            // Check if element is at least partially in the expanded viewport
            return !(
                    rect.bottom < -viewportExpansion ||
                rect.top > viewportHeight + viewportExpansion ||
                    rect.right < -viewportExpansion ||
                rect.left > viewportWidth + viewportExpansion
            );
        }

        /**
         * Checks if an element is visible
         */
        function isElementVisible(element) {
            // Quick check for basic visibility
            if (element.offsetWidth === 0 && element.offsetHeight === 0) {
                // Special case for hidden file inputs
                if (element.tagName.toLowerCase() === 'input' && 
                    element.getAttribute('type') === 'file' && 
                    (element.classList.contains('hidden') || element.style.display === 'none')) {
                    return true; // Consider hidden file inputs as visible for interaction
                }
                return false;
            }

            const style = getCachedComputedStyle(element);
            return (
                style.visibility !== "hidden" &&
                style.display !== "none" &&
                style.opacity !== "0"
            );
        }

        /**
         * Checks if element is the topmost at its position
         */
        function isTopElement(element) {
            const rect = getCachedBoundingRect(element);
            if (!rect) return false;

            // Check if element is in viewport
            const isInViewportArea = (
                rect.left < window.innerWidth &&
                rect.right > 0 &&
                rect.top < window.innerHeight &&
                rect.bottom > 0
            );

            if (!isInViewportArea) {
                    return false;
            }

            // Check if element is topmost at center point
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;

            try {
                const topEl = document.elementFromPoint(centerX, centerY);
                if (!topEl) return false;

                // Walk up the DOM tree to see if our element is in the chain
                let current = topEl;
                while (current && current !== document.documentElement) {
                    if (current === element) return true;
                    current = current.parentElement;
                }
                return false;
            } catch (e) {
                return false;
            }
        }

        /**
         * Checks if an element is interactive
         */
        function isInteractiveElement(element) {
            if (!element || element.nodeType !== Node.ELEMENT_NODE) {
                return false;
            }
            
            // Skip presentation elements
            if (element.getAttribute("role") === "presentation") {
                return false;
            }

            function doesElementHaveInteractivePointer(element) {
                if (element.tagName.toLowerCase() === "html") return false;
                const style = getCachedComputedStyle(element);

                let interactiveCursors = ["pointer", "move", "text", "grab", "cell"];

                if (interactiveCursors.includes(style.cursor)) return true;

                return false;
            }

            let isInteractiveCursor = doesElementHaveInteractivePointer(element);

            if (isInteractiveCursor) {
                return true;
            }

            // Special handling for cookie banner elements
            const isCookieBannerElement =
                (typeof element.closest === 'function') && (
                    element.closest('[id*="onetrust"]') ||
                    element.closest('[class*="onetrust"]') ||
                    element.closest('[data-nosnippet="true"]') ||
                    element.closest('[aria-label*="cookie"]')
                );

            if (isCookieBannerElement) {
                // Check if it's a button or interactive element within the banner
                if (
                    element.tagName.toLowerCase() === 'button' ||
                    element.getAttribute('role') === 'button' ||
                    element.onclick ||
                    element.getAttribute('onclick') ||
                    (element.classList && (
                        element.classList.contains('ot-sdk-button') ||
                        element.classList.contains('accept-button') ||
                        element.classList.contains('reject-button')
                    )) ||
                    element.getAttribute('aria-label')?.toLowerCase().includes('accept') ||
                    element.getAttribute('aria-label')?.toLowerCase().includes('reject')
                ) {
                    return true;
                }
            }

            // Base interactive elements and roles
            const interactiveElements = new Set([
                "a", "button", "details", "embed", "input", "menu", "menuitem",
                "object", "select", "textarea", "canvas", "summary", "dialog",
                "banner"
            ]);

            const interactiveRoles = new Set(['button-icon', 'dialog', 'button-text-icon-only', 'treeitem', 'alert', 'grid', 'progressbar', 'radio', 'checkbox', 'menuitem', 'option', 'switch', 'dropdown', 'scrollbar', 'combobox', 'a-button-text', 'button', 'region', 'textbox', 'tabpanel', 'tab', 'click', 'button-text', 'spinbutton', 'a-button-inner', 'link', 'menu', 'slider', 'listbox', 'a-dropdown-button', 'button-icon-only', 'searchbox', 'menuitemradio', 'tooltip', 'tree', 'menuitemcheckbox']);

            const tagName = element.tagName.toLowerCase();
            const role = element.getAttribute("role");
            const ariaRole = element.getAttribute("aria-role");
            const tabIndex = element.getAttribute("tabindex");

            // Add check for specific class
            const hasAddressInputClass = element.classList && (
                element.classList.contains("address-input__container__input") ||
                element.classList.contains("nav-btn") ||
                element.classList.contains("pull-left")
            );

            // Added enhancement to capture dropdown interactive elements
            if (element.classList && (
                element.classList.contains("button") ||
                element.classList.contains('dropdown-toggle') ||
                element.getAttribute('data-index') ||
                element.getAttribute('data-toggle') === 'dropdown' ||
                element.getAttribute('aria-haspopup') === 'true'
            )) {
                return true;
            }

            // Basic role/attribute checks
            const hasInteractiveRole =
                hasAddressInputClass ||
                interactiveElements.has(tagName) ||
                interactiveRoles.has(role) ||
                interactiveRoles.has(ariaRole) ||
                (tabIndex !== null &&
                    tabIndex !== "-1" &&
                    element.parentElement?.tagName.toLowerCase() !== "body") ||
                element.getAttribute("data-action") === "a-dropdown-select" ||
                element.getAttribute("data-action") === "a-dropdown-button";

            if (hasInteractiveRole) return true;

            // Additional checks for cookie banners and consent UI
            const isCookieBanner =
                element.id?.toString().toLowerCase().includes('cookie') ||
                element.id?.toString().toLowerCase().includes('consent') ||
                element.id?.toString().toLowerCase().includes('notice') ||
                (element.classList && (
                    element.classList.contains('otCenterRounded') ||
                    element.classList.contains('ot-sdk-container')
                )) ||
                element.getAttribute('data-nosnippet') === 'true' ||
                element.getAttribute('aria-label')?.toString().toLowerCase().includes('cookie') ||
                element.getAttribute('aria-label')?.toString().toLowerCase().includes('consent') ||
                (element.tagName.toLowerCase() === 'div' && (
                    element.id?.toString().toLowerCase().includes('onetrust') ||
                    (element.classList && (
                        element.classList.contains('onetrust') ||
                        element.classList.contains('cookie') ||
                        element.classList.contains('consent')
                    ))
                ));

            if (isCookieBanner) return true;

            // Additional check for buttons in cookie banners
            const isInCookieBanner = typeof element.closest === 'function' && element.closest(
                '[id*="cookie"],[id*="consent"],[class*="cookie"],[class*="consent"],[id*="onetrust"]'
            );

            if (isInCookieBanner && (
                element.tagName.toLowerCase() === 'button' ||
                element.getAttribute('role') === 'button' ||
                (element.classList && element.classList.contains('button')) ||
                element.onclick ||
                element.getAttribute('onclick')
            )) {
                return true;
            }

            // Check for event listeners
            const hasClickHandler =
                element.onclick !== null ||
                element.getAttribute("onclick") !== null ||
                element.hasAttribute("ng-click") ||
                element.hasAttribute("@click") ||
                element.hasAttribute("v-on:click");

            // Helper function to safely get event listeners
            function getEventListeners(el) {
                try {
                    return window.getEventListeners?.(el) || {};
                } catch (e) {
                    const listeners = {};
                    const eventTypes = [
                        "click",
                        "mousedown",
                        "mouseup",
                        "touchstart",
                        "touchend",
                        "keydown",
                        "keyup",
                        "focus",
                        "blur",
                    ];

                    for (const type of eventTypes) {
                        const handler = el[`on${type}`];
                        if (handler) {
                            listeners[type] = [{ listener: handler, useCapture: false }];
                        }
                    }
                    return listeners;
                }
            }

            // Check for click-related events
            const listeners = getEventListeners(element);
            const hasClickListeners =
                listeners &&
                (listeners.click?.length > 0 ||
                    listeners.mousedown?.length > 0 ||
                    listeners.mouseup?.length > 0 ||
                    listeners.touchstart?.length > 0 ||
                    listeners.touchend?.length > 0);

            // Check for ARIA properties
            const hasAriaProps =
                element.hasAttribute("aria-expanded") ||
                element.hasAttribute("aria-pressed") ||
                element.hasAttribute("aria-selected") ||
                element.hasAttribute("aria-checked");

            const isContentEditable = element.getAttribute("contenteditable") === "true" ||
                element.isContentEditable ||
                element.id === "tinymce" ||
                element.classList.contains("mce-content-body") ||
                (element.tagName.toLowerCase() === "body" && element.getAttribute("data-id")?.startsWith("mce_"));

            // Check if element is draggable
            const isDraggable =
                element.draggable || element.getAttribute("draggable") === "true";

            return (
                hasAriaProps ||
                hasClickHandler ||
                hasClickListeners ||
                isDraggable ||
                isContentEditable
            );
        }

        /**
         * Check if an element is a child of another interactive element
         * or significantly overlaps with another element
         */
        function isDuplicateInteractiveElement(element, rect) {
            // Skip tiny elements (under 5px)
            if (rect.width < 5 || rect.height < 5) {
                return true;
            }
            
            // Get tag and role information for element priority decisions
            const elementTag = element.tagName.toLowerCase();
            const elementRole = element.getAttribute("role");
            
            // Enhanced element scoring system
            // ===============================
            
            // Define tag priority - higher priority tags are preferred over lower priority tags
            const tagPriority = {
                // Primary interactive elements
                'a': 10,
                'button': 10,
                'input': 10,
                'select': 10,
                'textarea': 10,
                
                // Media and canvas elements
                'canvas': 9,
                'video': 9,
                'audio': 9, 
                
                // Form elements
                'label': 8,
                'option': 8,
                'fieldset': 8,
                
                // Content organization
                'summary': 9,
                'details': 8,
                'li': 8,
                'td': 8,
                'th': 8,
                'tr': 7,
                
                // Content containers
                'form': 7,
                'dialog': 9,
                'menu': 8,
                
                // Generic elements
                'div': 5,
                'span': 3,
                'i': 2,
                'img': 7,
                'p': 4,
                'hr': 3,
                'br': 1
            };
            
            // Define role priority
            const rolePriority = {
                // Interactive controls
                'button': 10,
                'link': 10,
                'menuitem': 9,
                'tab': 9,
                'checkbox': 9,
                'radio': 9,
                'combobox': 9,
                'switch': 9,
                'textbox': 9,
                'searchbox': 9,
                'spinbutton': 8,
                'slider': 8,
                
                // Interactive containers
                'tabpanel': 8,
                'dialog': 9,
                'toolbar': 8,
                'menu': 8,
                'menubar': 8,
                'tooltip': 7,
                
                // Content organization
                'treeitem': 8,
                'listitem': 8,
                'gridcell': 8,
                'row': 7,
                'cell': 7,
                
                // Lower priority roles
                'presentation': 2,
                'none': 1,
                'img': 6
            };
            
            // Calculate the element's priority score with an enhanced algorithm
            const getElementPriority = (el) => {
                if (!el) return 0;
                
                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute("role");
                const style = getCachedComputedStyle(el);
                
                // Starting score based on tag and role
                let score = Math.max(tagPriority[tag] || 5, rolePriority[role] || 0);
                
                // Factor in attributes with weighted importance
                
                // Critical interactive attributes
                if (el.getAttribute("contenteditable") === "true" || el.isContentEditable) score += 5;
                if (el.getAttribute("onclick") || el.onclick) score += 4;
                if (el.getAttribute("href")) score += (tag === 'a' ? 4 : 2); // More important for links
                
                // ARIA attributes - important for accessibility and interaction
                if (el.getAttribute("aria-expanded")) score += 3;
                if (el.getAttribute("aria-controls")) score += 3;
                if (el.getAttribute("aria-checked")) score += 3;
                if (el.getAttribute("aria-selected")) score += 3;
                if (el.getAttribute("aria-pressed")) score += 3;
                if (el.getAttribute("aria-haspopup")) score += 2;
                if (el.getAttribute("aria-label")) score += 1;
                
                // Form element attributes
                if (el.getAttribute("type") === "submit" || el.getAttribute("type") === "button") score += 3;
                if (el.getAttribute("placeholder")) score += 1;
                if (el.getAttribute("required")) score += 1;
                
                // Other interactive attributes
                if (el.getAttribute("draggable") === "true") score += 2;
                if (el.getAttribute("tabindex") && el.getAttribute("tabindex") !== "-1") score += 2;
                if (el.getAttribute("data-action")) score += 2;
                if (el.getAttribute("data-toggle")) score += 2;
                if (el.getAttribute("data-target")) score += 1;
                
                // Identifier attributes
                if (el.getAttribute("id")) score += 1;
                if (el.getAttribute("name")) score += 1;
                
                // Content factors
                const hasText = el.textContent?.trim().length > 0;
                const hasChildren = el.children.length > 0;
                
                // Adjust score based on content
                if (hasText) {
                    // Elements with text are more likely to be important
                    score += Math.min(2, el.textContent.trim().length / 20); // Max +2 for text
                } else if ((tag === 'div' || tag === 'span') && !hasChildren) {
                    // Empty divs and spans with no children are less important
                    score -= 3;
                }
                
                // Visual style factors that indicate interactive elements
                if (style) {
                    // Cursor style is a strong indicator of interactivity
                    if (style.cursor === 'pointer') score += 2;
                    if (style.cursor === 'grab' || style.cursor === 'grabbing') score += 2;
                    
                    // Elements with borders, backgrounds, and hover effects are more likely interactive
                    if (style.border && style.border !== 'none' && !style.border.startsWith('0')) score += 0.5;
                    if (style.backgroundColor && style.backgroundColor !== 'transparent' && style.backgroundColor !== 'rgba(0, 0, 0, 0)') score += 0.5;
                    
                    // Z-index can indicate importance
                    if (style.zIndex && parseInt(style.zIndex) > 1) {
                        score += Math.min(1, parseInt(style.zIndex) / 100); // Max +1 for z-index
                    }
                    
                    // Fixed/absolute positioning often indicates special UI elements
                    if (style.position === 'fixed' || style.position === 'absolute') score += 1;
                }
                
                // Element size factor - larger elements might be more significant
                const elRect = getCachedBoundingRect(el);
                if (elRect) {
                    const area = elRect.width * elRect.height;
                    if (area > 10000) score += 1; // Large elements
                    else if (area < 400 && tag !== 'button' && tag !== 'input') score -= 1; // Small non-button elements
                }
                
                // Special case for common UI patterns
                const className = el.className?.toString().toLowerCase() || '';
                if (
                    className.includes('btn') || 
                    className.includes('button') || 
                    className.includes('link') ||
                    className.includes('control') ||
                    className.includes('clickable') ||
                    className.includes('selectable') ||
                    className.includes('interactive')
                ) {
                    score += 2;
                }
                
                return score;
            };
            
            // Get priority of this element
            const elementPriority = getElementPriority(element);
            const elementArea = rect.width * rect.height;
            
            // Fast path for high-priority elements
            // Certain elements should never be considered duplicates regardless of context
            const isHighPriorityElement = 
                (elementPriority >= 12) || // Very high score elements
                (element.getAttribute("contenteditable") === "true" && rect.width >= 15 && rect.height >= 15) || // Contenteditable areas
                (elementTag === 'input' && rect.width >= 15 && rect.height >= 15) || // Input fields
                (elementTag === 'textarea' && rect.width >= 15 && rect.height >= 15) || // Textareas
                (elementTag === 'select' && rect.width >= 15 && rect.height >= 15); // Select dropdowns
            
            if (isHighPriorityElement) {
                // Still add to processed areas to track them
                processedElementAreas.push({
                    left: rect.left,
                    top: rect.top,
                    right: rect.right,
                    bottom: rect.bottom,
                    element: element,
                    priority: elementPriority,
                    area: elementArea
                });
                return false; // Not a duplicate
            }
            
            // Check if this element is contained within another interactive parent
            let parent = element.parentElement;
            let foundSignificantParent = false;
            
            while (parent && !foundSignificantParent) {
                if (isInteractiveElement(parent)) {
                    const parentRect = getCachedBoundingRect(parent);
                    if (parentRect) {
                        // Calculate overlap
                        const overlapX = Math.max(0, Math.min(rect.right, parentRect.right) - Math.max(rect.left, parentRect.left));
                        const overlapY = Math.max(0, Math.min(rect.bottom, parentRect.bottom) - Math.max(rect.top, parentRect.top));
                        const overlapArea = overlapX * overlapY;
                        
                        // If element is substantially contained within parent
                        const containmentRatio = overlapArea / elementArea;
                        if (containmentRatio > 0.85) {
                            // Get parent's priority
                            const parentPriority = getElementPriority(parent);
                            const priorityDiff = elementPriority - parentPriority;
                            
                            // More sophisticated comparison based on element roles and context
                            const parentTag = parent.tagName.toLowerCase();
                            
                            // Special case for common UI patterns
                            
                            // Case 1: Links inside list items - usually keep both
                            if ((elementTag === 'a' && parentTag === 'li') || 
                                (elementTag === 'li' && parentTag === 'a')) {
                                foundSignificantParent = false;
                                break;
                            }
                            
                            // Case 2: Buttons inside forms - usually keep both
                            if (elementTag === 'button' && parentTag === 'form') {
                                foundSignificantParent = false;
                                break;
                            }
                            
                            // Case 3: Inputs inside labels - usually keep both
                            if (elementTag === 'input' && parentTag === 'label') {
                                foundSignificantParent = false;
                                break;
                            }
                            
                            // Case 4: Icons inside buttons - usually keep just the button
                            if ((elementTag === 'i' || elementTag === 'span') && 
                                (parentTag === 'button' || parent.getAttribute('role') === 'button')) {
                                return true; // Skip this element
                            }
                            
                            // Standard priority comparison with improved thresholds
                            if (priorityDiff > 3) {
                                // Element is much more important than parent, keep it
                                foundSignificantParent = false;
                                break;
                            } else if (priorityDiff < -1) {
                                // Parent is more important, skip this element
                                return true;
                            } else {
                                // Similar priority, use heuristics
                                
                                // If element is small compared to parent (likely a child control)
                                const sizeRatio = elementArea / (parentRect.width * parentRect.height);
                                
                                if (sizeRatio < 0.2) {
                                    // Small child elements in a parent are often important interactive components
                                    foundSignificantParent = false;
                                    break;
                                }
                                
                                // If element has distinct text different from parent text
                                const elementText = element.textContent?.trim() || '';
                                const parentText = parent.textContent?.trim() || '';
                                
                                if (elementText && elementText !== parentText && 
                                    elementText.length < parentText.length * 0.7) {
                                    // Element has distinct text content, likely important
                                    foundSignificantParent = false;
                                    break;
                                }
                                
                                // Default behavior: prefer parent for similar priority
                                return true;
                            }
                        }
                    }
                }
                parent = parent.parentElement;
            }
            
            // Compare against already processed elements to avoid visual duplicates
            for (let i = 0; i < processedElementAreas.length; i++) {
                const processedArea = processedElementAreas[i];
                
                // Calculate overlap
                const overlapX = Math.max(0, Math.min(rect.right, processedArea.right) - Math.max(rect.left, processedArea.left));
                const overlapY = Math.max(0, Math.min(rect.bottom, processedArea.bottom) - Math.max(rect.top, processedArea.top));
                
                if (overlapX <= 0 || overlapY <= 0) continue; // No overlap
                
                const overlapArea = overlapX * overlapY;
                const processedElementArea = (processedArea.right - processedArea.left) * (processedArea.bottom - processedArea.top);
                
                // Calculate overlap ratio based on the smaller element
                const smallerArea = Math.min(elementArea, processedElementArea);
                const overlapRatio = overlapArea / smallerArea;
                
                // If significant overlap
                if (overlapRatio > 0.6) { // Slightly more lenient threshold
                    // Get the existing element
                    const existingElement = processedArea.element;
                    if (!existingElement) continue;
                    
                    // Get cached priority or calculate it
                    const existingPriority = processedArea.priority || getElementPriority(existingElement);
                    const priorityDiff = elementPriority - existingPriority;
                    
                    // Special cases for common UI patterns
                    
                    // Case: Elements with identical absolute positions but different z-indices
                    // Often indicates stacked UI elements like modals, tooltips, etc.
                    if (Math.abs(rect.left - processedArea.left) < 3 && 
                        Math.abs(rect.top - processedArea.top) < 3 &&
                        Math.abs(rect.width - (processedArea.right - processedArea.left)) < 3 &&
                        Math.abs(rect.height - (processedArea.bottom - processedArea.top)) < 3) {
                        
                        // If this element has a higher z-index, it might be more important
                        const elementZIndex = parseInt(getCachedComputedStyle(element)?.zIndex || '0');
                        const existingZIndex = parseInt(getCachedComputedStyle(existingElement)?.zIndex || '0');
                        
                        if (elementZIndex > existingZIndex + 1) {
                            // This element is on top, replace the existing one
                            processedElementAreas.splice(i, 1);
                            i--; // Adjust index
                            continue;
                        } else if (existingZIndex > elementZIndex + 1) {
                            // Existing element is on top
                            return true;
                        }
                    }
                    
                    // Compare priorities with improved thresholds
                    if (priorityDiff > 2) {
                        // This element is significantly more important, replace the existing one
                        processedElementAreas.splice(i, 1);
                        i--; // Adjust index since we removed an item
                    } else if (priorityDiff < -0.5) {
                        // Existing element is at least as important, skip this element
                        return true;
                    } else {
                        // Similar priority, use additional heuristics
                        
                        // 1. Specific element combinations
                        const existingTag = existingElement.tagName.toLowerCase();
                        
                        // Icons inside buttons - keep the button
                        if ((elementTag === 'i' || elementTag === 'span') && !element.textContent?.trim() &&
                            (existingTag === 'button' || existingElement.getAttribute('role') === 'button')) {
                        return true;
                    }
                    
                        // 2. Content-based decisions
                        const elementText = element.textContent?.trim() || '';
                        const existingText = existingElement.textContent?.trim() || '';
                        
                        // If both elements have text, prefer the one with more information
                        if (elementText && existingText) {
                        if (existingText.length > elementText.length * 1.5) {
                            return true;
                            } else if (elementText.length > existingText.length * 1.5) {
                                processedElementAreas.splice(i, 1);
                                i--;
                                continue;
                            }
                        }
                        
                        // 3. Element type decisions
                        
                        // Prefer elements with native semantics over generic divs/spans
                        if (tagPriority[existingTag] > tagPriority[elementTag] + 2) {
                            return true;
                        } else if (tagPriority[elementTag] > tagPriority[existingTag] + 2) {
                            processedElementAreas.splice(i, 1);
                            i--;
                            continue;
                        }
                        
                        // 4. Size-based decisions
                        
                        // Prefer the larger element when sizes differ significantly
                        if (processedElementArea > elementArea * 3) {
                            return true;
                        } else if (elementArea > processedElementArea * 3) {
                            processedElementAreas.splice(i, 1);
                            i--;
                            continue;
                        }
                        
                        // Default: keep the existing element in case of similar priority and characteristics
                        return true;
                    }
                }
            }
            
            // This element should be kept - add it to our tracking
            processedElementAreas.push({
                left: rect.left,
                top: rect.top,
                right: rect.right,
                bottom: rect.bottom,
                element: element
            });
            
            return false;
        }

        /**
         * Find all interactive elements currently in the viewport
         */
        function findViewportInteractiveElements() {
            // Clear any existing highlights if container exists
            const container = document.getElementById(HIGHLIGHT_CONTAINER_ID);
            if (container) {
                container.innerHTML = '';
            }
            
            const result = [];
            highlightIndex = 0;
            
            // Reset the processed elements tracker
            processedElementAreas.length = 0;
            
            // Process main document elements
            processElementsInDocument(document, null, result);
            
            // Process iframes
            const iframes = document.querySelectorAll('iframe');
            for (const iframe of iframes) {
                // Only process iframes that are in viewport
                if (!isInViewport(iframe)) continue;
                
                // Skip invisible iframes
                if (!isElementVisible(iframe)) continue;
                
                try {
                    // Try to access the iframe's document
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
                    if (iframeDoc) {
                        processElementsInDocument(iframeDoc, iframe, result);
                    }
                } catch (e) {
                    // Cross-domain iframe - can't access content
                    // Still add the iframe itself as it might be interactive
                    if (isInteractiveElement(iframe)) {
                        const elementData = createElementData(iframe, highlightIndex);
                        elementData.isIframe = true;
                        elementData.crossDomain = true;
                        result.push(elementData);
                        
                        if (doHighlightElements && 
                            (focusHighlightIndex < 0 || focusHighlightIndex === highlightIndex)) {
                            highlightElement(iframe, highlightIndex);
                        }
                        
                        highlightIndex++;
                    }
                }
            }
            
            // Find scrollable elements and add to the same result array
            findScrollableElements(result);
            
            // Find main browser scrollbars and add to the same result array
            findMainBrowserScrollbars(result);
            
            return result;
        }
        
        /**
         * Process elements within a document (main document or iframe document)
         */
        function processElementsInDocument(doc, iframeElement, result) {
            // Get elements that might be interactive
            let selector = 'a, button, input, select, textarea, [role], [tabindex], [onclick], ' +
                '[contenteditable="true"], .button, .dropdown-toggle, .nav-btn, ' +
                '[class*="btn"], [role="button"], canvas, summary, details, ' + 
                '[aria-haspopup], [data-toggle], [aria-expanded], [aria-pressed], ' +
                '[draggable="true"], [class*="draggable"], [class*="control"], ' +
                '[class*="interactive"], [class*="clickable"], [data-action], ' +
                'label, menu, menuitem, option';
                
            try {
                const potentialElements = doc.querySelectorAll(selector);
                
                // First pass: collect all potential elements and their rectangles
                const candidateElements = [];
                
                for (const element of potentialElements) {
                    // Adjust viewport check for iframe elements
                    if (iframeElement) {
                        if (!isElementInIframeViewport(element, iframeElement)) continue;
                    } else {
                        if (!isInViewport(element)) continue;
                    }
                    
                    // Check if element is visible
                    if (!isElementVisible(element)) continue;
                    
                    // Check if element is the top element at its position
                    if (!isTopElementWithIframeSupport(element, iframeElement)) continue;
                    
                    // Check if element is interactive
                    if (!isInteractiveElement(element)) continue;
                    
                    // Get the bounding rectangle
                    const rect = getCachedBoundingRect(element);
                    if (!rect) continue;
                    
                    candidateElements.push({ element, rect });
                }
                
                // Sort elements by size (smaller elements first)
                candidateElements.sort((a, b) => {
                    const areaA = a.rect.width * a.rect.height;
                    const areaB = b.rect.width * b.rect.height;
                    return areaA - areaB;
                });
                
                // Second pass: check each element for duplicates
                for (const { element, rect } of candidateElements) {
                    // Skip if this element is a duplicate of already processed elements
                    if (isDuplicateInteractiveElement(element, rect)) continue;
                    
                    // Create and add element data
                    const elementData = createElementData(element, highlightIndex);
                    
                    // Add iframe info if in iframe
                    if (iframeElement) {
                        elementData.inIframe = true;
                        elementData.iframeId = iframeElement.id || null;
                        elementData.iframeXpath = getJSPathForElement(iframeElement);
                    }
                    
                    result.push(elementData);
                    
                    // Highlight the element if needed
                    if (doHighlightElements && 
                        (focusHighlightIndex < 0 || focusHighlightIndex === highlightIndex)) {
                        highlightElement(element, highlightIndex, iframeElement);
                    }
                    
                    highlightIndex++;
                }
                
                // Process hidden file inputs
                processHiddenFileInputs(doc, iframeElement, result);
                
                // Look for shadow DOM elements
                processShadowDOMElements(doc, iframeElement, result);
                
            } catch (e) {
                console.warn("Error processing document:", e);
            }
        }
        
        /**
         * Process Shadow DOM elements for interactive elements
         */
        function processShadowDOMElements(doc, iframeElement, result) {
            try {
                // Find elements that might have shadow roots
                const potentialShadowHosts = doc.querySelectorAll('*');
                
                for (const host of potentialShadowHosts) {
                    if (host.shadowRoot) {
                        // Process this shadow root
                        const shadowRoot = host.shadowRoot;
                        
                        // Same selector as main processing function
                        let selector = 'a, button, input, select, textarea, [role], [tabindex], [onclick], ' +
                            '[contenteditable="true"], .button, .dropdown-toggle, .nav-btn, ' +
                            '[class*="btn"], [role="button"], canvas, summary, details, ' + 
                            '[aria-haspopup], [data-toggle], [aria-expanded], [aria-pressed], ' + 
                            '[draggable="true"], [class*="draggable"], [class*="control"], ' +
                            '[class*="interactive"], [class*="clickable"], [data-action], ' +
                            'label, menu, menuitem, option';
                            
                        const shadowElements = shadowRoot.querySelectorAll(selector);
                        
                        // First collect candidates
                        const shadowCandidates = [];
                        
                        for (const element of shadowElements) {
                            // Same checks as for regular elements
                            if (iframeElement) {
                                if (!isElementInIframeViewport(element, iframeElement)) continue;
                            } else {
                                if (!isInViewport(element)) continue;
                            }
                            
                            if (!isElementVisible(element)) continue;
                            if (!isTopElementWithIframeSupport(element, iframeElement)) continue;
                            if (!isInteractiveElement(element)) continue;
                            
                            const rect = getCachedBoundingRect(element);
                            if (!rect) continue;
                            
                            shadowCandidates.push({ element, rect });
                        }
                        
                        // Sort by size and process
                        shadowCandidates.sort((a, b) => {
                            const areaA = a.rect.width * a.rect.height;
                            const areaB = b.rect.width * b.rect.height;
                            return areaA - areaB;
                        });
                        
                        for (const { element, rect } of shadowCandidates) {
                            // Skip duplicates
                            if (isDuplicateInteractiveElement(element, rect)) continue;
                            
                            const elementData = createElementData(element, highlightIndex);
                            
                            elementData.inShadowDOM = true;
                            elementData.shadowHost = {
                                tagName: host.tagName.toLowerCase(),
                                id: host.id || null,
                                xpath: getJSPathForElement(host)
                            };
                            
                            if (iframeElement) {
                                elementData.inIframe = true;
                                elementData.iframeId = iframeElement.id || null;
                                elementData.iframeXpath = getJSPathForElement(iframeElement);
                            }
                            
                            result.push(elementData);
                            
                            if (doHighlightElements && 
                                (focusHighlightIndex < 0 || focusHighlightIndex === highlightIndex)) {
                                highlightElement(element, highlightIndex, iframeElement);
                            }
                            
                            highlightIndex++;
                        }
                    }
                }
            } catch (e) {
                console.warn("Error processing shadow DOM:", e);
            }
        }
        
        /**
         * Get element attributes in a comprehensive way
         */
        function getElementAttributes(element) {
            const attributes = {};
            
            // Standard attributes to always capture
            const standardAttributes = [
                'id', 'class', 'name', 'type', 'href', 'src', 'alt', 'title',
                'placeholder', 'value', 'draggable', 'required', 'disabled',
                'checked', 'selected', 'readonly', 'maxlength', 'minlength',
                'max', 'min', 'step', 'pattern', 'form', 'for', 'tabindex',
                'target', 'action', 'method', 'rel', 'download'
            ];
            
            // All ARIA attributes to capture (comprehensive list)
            const ariaAttributes = [
                'role', 'aria-label', 'aria-labelledby', 'aria-describedby',
                'aria-description', 'aria-details', 'aria-expanded', 'aria-haspopup',
                'aria-hidden', 'aria-invalid', 'aria-keyshortcuts', 'aria-level',
                'aria-live', 'aria-modal', 'aria-multiline', 'aria-multiselectable',
                'aria-orientation', 'aria-placeholder', 'aria-posinset', 'aria-pressed',
                'aria-readonly', 'aria-required', 'aria-roledescription', 'aria-selected',
                'aria-setsize', 'aria-sort', 'aria-valuemax', 'aria-valuemin',
                'aria-valuenow', 'aria-valuetext', 'aria-atomic', 'aria-busy',
                'aria-disabled', 'aria-grabbed', 'aria-activedescendant', 'aria-autocomplete',
                'aria-controls', 'aria-current', 'aria-dropeffect', 'aria-flowto',
                'aria-owns', 'aria-relevant', 'aria-checked'
            ];
            
            // Capture all standard attributes
            for (const attr of standardAttributes) {
                if (element.hasAttribute(attr)) {
                    attributes[attr] = element.getAttribute(attr);
                }
            }
            
            // Capture all ARIA attributes
            for (const attr of ariaAttributes) {
                if (element.hasAttribute(attr)) {
                    attributes[attr] = element.getAttribute(attr);
                }
            }
            
            // Capture all data-* attributes
            const dataAttributes = {};
            let hasDataAttributes = false;
            
            for (const attr of element.attributes) {
                if (attr.name.startsWith('data-')) {
                    dataAttributes[attr.name] = attr.value;
                    hasDataAttributes = true;
                }
            }
            
            if (hasDataAttributes) {
                attributes.dataAttributes = dataAttributes;
            }
            
            return attributes;
        }
        
        /**
         * Add suggested Playwright interactions for the element
         */
        function addPlaywrightInteractions(element, elementData) {
            const tagName = element.tagName.toLowerCase();
            const type = (element.getAttribute('type') || '').toLowerCase();
            const role = (element.getAttribute('role') || '').toLowerCase();
            const isContentEditable = element.getAttribute('contenteditable') === 'true' || element.isContentEditable;
            const isHiddenFileInput = elementData.isHiddenFileInput || false;
            
            // Default interaction info
            const interaction = {
                action: 'click'
            };
            
            // Adjust based on element type
            if (tagName === 'input') {
                if (type === 'file') {
                    // File inputs
                    if (isHiddenFileInput) {
                        interaction.action = 'setInputFiles';
                    } else {
                        interaction.action = 'setInputFiles';
                    }
                } else if (['text', 'email', 'password', 'search', 'tel', 'url', 'number'].includes(type)) {
                    // Text input fields
                    interaction.action = 'fill';
                } else if (type === 'checkbox') {
                    // Checkboxes
                    const isChecked = element.checked;
                    interaction.action = isChecked ? 'uncheck' : 'check';
                } else if (type === 'radio') {
                    // Radio buttons
                    interaction.action = 'check';
                } else if (type === 'range') {
                    // Range sliders
                    interaction.action = 'fill';
                } else if (type === 'date' || type === 'datetime-local' || type === 'month' || type === 'time' || type === 'week') {
                    // Date/time inputs
                    interaction.action = 'fill';
                } else if (type === 'color') {
                    // Color inputs
                    interaction.action = 'fill';
                } else {
                    // Default for other input types
                    interaction.action = 'fill';
                }
            } else if (tagName === 'textarea') {
                // Textarea
                interaction.action = 'fill';
            } else if (tagName === 'select') {
                // Select dropdowns
                interaction.action = 'selectOption';
            } else if (tagName === 'a') {
                // Links
                interaction.action = 'click';
            } else if (tagName === 'button' || role === 'button') {
                // Buttons
                interaction.action = 'click';
            } else if (['checkbox', 'switch'].includes(role)) {
                // ARIA checkboxes/switches
                interaction.action = 'click';
            } else if (role === 'radio') {
                // ARIA radio buttons
                interaction.action = 'click';
            } else if (role === 'tab') {
                // Tabs
                interaction.action = 'click';
            } else if (role === 'combobox' || role === 'listbox') {
                // Combobox/listbox
                interaction.action = 'click';
            } else if (role === 'menuitem') {
                // Menu items
                interaction.action = 'click';
            } else if (role === 'slider') {
                // Slider
                interaction.action = 'fill';
            } else if (isContentEditable) {
                // Contenteditable elements
                interaction.action = 'fill';
            } else if (tagName === 'details' || tagName === 'summary') {
                // Details/summary elements
                interaction.action = 'click';
            } else if (tagName === 'dialog') {
                // Dialog elements
                interaction.action = 'waitFor';
            } else if (tagName === 'canvas') {
                // Canvas elements
                interaction.action = 'click';
            }
            
            // Add drag-and-drop handling for draggable elements
            if (element.getAttribute('draggable') === 'true') {
                interaction.alternativeAction = 'drag';
            }
            
            // Handle hoverable elements with additional interactions
            if (element.getAttribute('data-tooltip') || element.getAttribute('title')) {
                interaction.alternativeAction = 'hover';
            }
            
            return interaction;
        }
        
        /**
         * Create element data object with all needed information
         */
        function createElementData(element, index) {
            // Basic element data
            const elementData = {
                tagName: element.tagName.toLowerCase(),
                jsPath: getJSPathForElement(element),
                highlightIndex: index,
                boundingRect: {
                    top: Math.round(element.getBoundingClientRect().top),
                    left: Math.round(element.getBoundingClientRect().left),
                    width: Math.round(element.getBoundingClientRect().width),
                    height: Math.round(element.getBoundingClientRect().height)
                },
                attributes: getElementAttributes(element),
                text: getElementText(element)
            };
            
            // Add contextual relationships
            addContextualRelationships(element, elementData);
            
            // Add Playwright interaction suggestions
            elementData.playwrightInteraction = addPlaywrightInteractions(element, elementData);
            
            return elementData;
        }
        
        /**
         * Add contextual information about the element's relationships
         */
        function addContextualRelationships(element, elementData) {
            // Find label relationships for form controls
            if (['input', 'select', 'textarea'].includes(element.tagName.toLowerCase())) {
                // Method 1: Check for explicit label with 'for' attribute
                if (element.id) {
                    const explicitLabel = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
                    if (explicitLabel) {
                        elementData.labelText = explicitLabel.textContent?.trim();
                        elementData.labelElement = {
                            tagName: explicitLabel.tagName.toLowerCase(),
                            id: explicitLabel.id || null,
                            jsPath: getJSPathForElement(explicitLabel)
                        };
                    }
                }
                
                // Method 2: Check for implicit label (input is inside label)
                if (!elementData.labelText) {
                    let parent = element.parentElement;
                    while (parent && parent !== document.body) {
                        if (parent.tagName.toLowerCase() === 'label') {
                            // Get label text without the text of the input itself
                            const clone = parent.cloneNode(true);
                            const inputs = clone.querySelectorAll('input, select, textarea, button');
                            for (const input of inputs) {
                                input.remove();
                            }
                            elementData.labelText = clone.textContent?.trim();
                            elementData.labelElement = {
                                tagName: parent.tagName.toLowerCase(),
                                id: parent.id || null,
                                jsPath: getJSPathForElement(parent)
                            };
                            break;
                        }
                        parent = parent.parentElement;
                    }
                }
                
                // Method 3: Check for aria-labelledby
                if (element.hasAttribute('aria-labelledby')) {
                    const labelledbyIds = element.getAttribute('aria-labelledby').split(/\s+/);
                    if (labelledbyIds.length > 0) {
                        const labelTexts = [];
                        const labelElements = [];
                        
                        for (const id of labelledbyIds) {
                            const labelElement = document.getElementById(id);
                            if (labelElement) {
                                labelTexts.push(labelElement.textContent?.trim());
                                labelElements.push({
                                    tagName: labelElement.tagName.toLowerCase(),
                                    id: labelElement.id,
                                    jsPath: getJSPathForElement(labelElement)
                                });
                            }
                        }
                        
                        if (labelTexts.length > 0) {
                            elementData.ariaLabelledbyText = labelTexts.join(' ');
                            elementData.ariaLabelledbyElements = labelElements;
                        }
                    }
                }
                
                // Method 4: Check for aria-describedby
                if (element.hasAttribute('aria-describedby')) {
                    const describedbyIds = element.getAttribute('aria-describedby').split(/\s+/);
                    if (describedbyIds.length > 0) {
                        const descriptionTexts = [];
                        const descriptionElements = [];
                        
                        for (const id of describedbyIds) {
                            const descElement = document.getElementById(id);
                            if (descElement) {
                                descriptionTexts.push(descElement.textContent?.trim());
                                descriptionElements.push({
                                    tagName: descElement.tagName.toLowerCase(),
                                    id: descElement.id,
                                    jsPath: getJSPathForElement(descElement)
                                });
                            }
                        }
                        
                        if (descriptionTexts.length > 0) {
                            elementData.ariaDescribedbyText = descriptionTexts.join(' ');
                            elementData.ariaDescribedbyElements = descriptionElements;
                        }
                    }
                }
            }
            
            // Find parent contextual elements that give meaning to this element
            const contextualContainers = [];
            let parent = element.parentElement;
            let depth = 0;
            const maxDepth = 3; // Limit how far up we go
            
            while (parent && depth < maxDepth && parent !== document.body) {
                // Check if parent has a meaningful role or landmark
                if (parent.hasAttribute('role') || 
                    ['header', 'footer', 'main', 'nav', 'aside', 'section', 'article', 'form'].includes(parent.tagName.toLowerCase())) {
                    
                    contextualContainers.push({
                        tagName: parent.tagName.toLowerCase(),
                        id: parent.id || null,
                        role: parent.getAttribute('role') || null,
                        jsPath: getJSPathForElement(parent)
                    });
                }
                
                // Move up the tree
                parent = parent.parentElement;
                depth++;
            }
            
            if (contextualContainers.length > 0) {
                elementData.contextualContainers = contextualContainers;
            }
        }
        
        /**
         * Get element text with safe trimming and limiting
         */
        function getElementText(element) {
            try {
                const textContent = element.textContent?.trim() || '';
                return textContent.substring(0, 100); // Limit text length
                    } catch (e) {
                return '';
            }
        }
        
        /**
         * Check if element in iframe is in viewport by combining iframe and element positions
         */
        function isElementInIframeViewport(element, iframe) {
            if (viewportExpansion === -1) {
                return true; // Consider all elements in viewport if expansion is -1
            }
            
            try {
                const iframeRect = iframe.getBoundingClientRect();
                const elementRect = element.getBoundingClientRect();
                
                // Calculate element position relative to main document
                const absoluteTop = iframeRect.top + elementRect.top;
                const absoluteLeft = iframeRect.left + elementRect.left;
                const absoluteBottom = absoluteTop + elementRect.height;
                const absoluteRight = absoluteLeft + elementRect.width;
                
                // Get real viewport size
                const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                
                // Check if combined position is in viewport
                return !(
                    absoluteBottom < -viewportExpansion ||
                    absoluteTop > viewportHeight + viewportExpansion ||
                    absoluteRight < -viewportExpansion ||
                    absoluteLeft > viewportWidth + viewportExpansion
                );
            } catch (e) {
                return false;
            }
        }
        
        /**
         * Enhanced topmost element check with iframe support
         */
        function isTopElementWithIframeSupport(element, iframe) {
            if (!iframe) {
                return isTopElement(element);
            }
            
            try {
                const iframeRect = iframe.getBoundingClientRect();
                const elementRect = element.getBoundingClientRect();
                
                // Calculate absolute position in parent document
                const absoluteTop = iframeRect.top + elementRect.top;
                const absoluteLeft = iframeRect.left + elementRect.left;
                const absoluteCenterX = absoluteLeft + (elementRect.width / 2);
                const absoluteCenterY = absoluteTop + (elementRect.height / 2);
                
                // First check if iframe itself is visible at this point
                const iframeElementAtPoint = document.elementFromPoint(absoluteCenterX, absoluteCenterY);
                if (!iframeElementAtPoint) return false;
                
                let current = iframeElementAtPoint;
                while (current && current !== document.documentElement) {
                    if (current === iframe) {
                        // The iframe is visible at this point, now check within iframe
                        const elementAtPoint = element.ownerDocument.elementFromPoint(
                            elementRect.left + (elementRect.width / 2),
                            elementRect.top + (elementRect.height / 2)
                        );
                        
                        if (!elementAtPoint) return false;
                        
                        // Check if this element is in the hierarchy
                        current = elementAtPoint;
                        while (current && current !== element.ownerDocument.documentElement) {
                            if (current === element) return true;
                            current = current.parentElement;
                        }
                        
                        return false;
                    }
                    current = current.parentElement;
                }
                
                return false;
            } catch (e) {
                // If we can't determine, assume it's visible
                return true;
            }
        }

        /**
         * Special handler for hidden file inputs
         */
        function processHiddenFileInputs(doc, iframeElement, result) {
            try {
                // Find all hidden file inputs
                const fileInputs = doc.querySelectorAll('input[type="file"].hidden, input[type="file"][style*="display: none"]');
                
                for (const fileInput of fileInputs) {
                    // Find parent element that might be visible
                    let parentElement = fileInput.parentElement;
                    let visibleParent = null;
                    
                    // Look up the DOM tree for a visible parent
                    while (parentElement && parentElement !== doc.body) {
                        if (isTopElementWithIframeSupport(parentElement, iframeElement) && 
                            isElementVisible(parentElement)) {
                            visibleParent = parentElement;
                            break;
                        }
                        parentElement = parentElement.parentElement;
                    }
                    
                    // If we found a visible parent, use its coordinates for the file input
                    if (visibleParent) {
                        const elementData = createElementData(fileInput, highlightIndex);
                        const parentRect = getCachedBoundingRect(visibleParent);
                        
                        // Override the bounding rect with the parent's rect
                        if (parentRect) {
                            elementData.boundingRect = {
                                top: Math.round(parentRect.top),
                                left: Math.round(parentRect.left),
                                width: Math.round(parentRect.width),
                                height: Math.round(parentRect.height)
                            };
                        }
                        
                        // Add special note that this is a hidden file input
                        elementData.isHiddenFileInput = true;
                        elementData.visibleParentTag = visibleParent.tagName.toLowerCase();
                        
                        // Add iframe info if in iframe
                        if (iframeElement) {
                            elementData.inIframe = true;
                            elementData.iframeId = iframeElement.id || null;
                            elementData.iframeXpath = getJSPathForElement(iframeElement);
                        }
                        
                        result.push(elementData);
                        
                        // Highlight the visible parent instead of the hidden input
                        if (doHighlightElements && 
                            (focusHighlightIndex < 0 || focusHighlightIndex === highlightIndex)) {
                            highlightElement(visibleParent, highlightIndex, iframeElement);
                        }
                        
                        highlightIndex++;
                    }
                }
            } catch (e) {
                console.warn("Error processing hidden file inputs:", e);
            }
        }

        /**
         * Find main browser scrollbars and add them to interactiveElements
         */
        function findMainBrowserScrollbars(interactiveElementsArray) {
            try {
                // Check for vertical scrollbar
                const hasVerticalScrollbar = document.documentElement.scrollHeight > window.innerHeight;
                const verticalScrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
                
                // Check for horizontal scrollbar
                const hasHorizontalScrollbar = document.documentElement.scrollWidth > window.innerWidth;
                const horizontalScrollbarHeight = window.innerHeight - document.documentElement.clientHeight;
                
                // On some systems like macOS, scrollbars can be overlay style with 0 width
                // So we should detect them based on content overflow even if width is 0
                if (hasVerticalScrollbar && verticalScrollbarWidth >= 0) {
                    // Calculate thumb data
                    const thumbHeight = Math.max(40, (window.innerHeight / document.documentElement.scrollHeight) * window.innerHeight);
                    const scrollPercentage = document.documentElement.scrollTop / 
                                           (document.documentElement.scrollHeight - window.innerHeight) || 0;
                    const thumbPosition = scrollPercentage * (window.innerHeight - thumbHeight);
                    
                    // Ensure minimum width for rendering
                    const displayWidth = Math.max(verticalScrollbarWidth, 8);
                    
                    // Create scrollbar element data
                    const scrollbarData = {
                        tagName: "scrollbar:main-vertical",
                        jsPath: "document.documentElement:vertical-scrollbar",
                        highlightIndex: highlightIndex,
                        boundingRect: {
                            top: 0,
                            left: window.innerWidth - displayWidth,
                            width: displayWidth,
                            height: window.innerHeight
                        },
                        scrollData: {
                            hasVerticalScrollbar: true,
                            hasHorizontalScrollbar: false,
                            scrollbarWidth: verticalScrollbarWidth,
                            scrollbarHeight: 0,
                            contentHeight: document.documentElement.scrollHeight,
                            contentWidth: document.documentElement.scrollWidth,
                            visibleHeight: window.innerHeight,
                            visibleWidth: window.innerWidth,
                            scrollTop: document.documentElement.scrollTop,
                            scrollLeft: document.documentElement.scrollLeft,
                            maxScrollTop: document.documentElement.scrollHeight - window.innerHeight,
                            maxScrollLeft: document.documentElement.scrollWidth - window.innerWidth,
                            verticalThumb: {
                                height: thumbHeight,
                                position: thumbPosition
                            },
                            horizontalThumb: null,
                            isOverlayScrollbar: verticalScrollbarWidth === 0
                        },
                        attributes: {
                            role: "scrollbar",
                            "aria-orientation": "vertical"
                        },
                        text: "",
                        isMainScrollbar: true
                    };
                    
                    // Add browser scrollbar to interactive elements
                    interactiveElementsArray.push(scrollbarData);
                    
                    // Highlight if needed
                    if (doHighlightElements && 
                        (focusHighlightIndex < 0 || focusHighlightIndex === highlightIndex)) {
                        highlightScrollbar(document.documentElement, highlightIndex, true, false, true);
                    }
                    
                    highlightIndex++;
                }
                
                if (hasHorizontalScrollbar && horizontalScrollbarHeight >= 0) {
                    // Calculate thumb data
                    const thumbWidth = Math.max(40, (window.innerWidth / document.documentElement.scrollWidth) * window.innerWidth);
                    const scrollPercentage = document.documentElement.scrollLeft / 
                                           (document.documentElement.scrollWidth - window.innerWidth) || 0;
                    const thumbPosition = scrollPercentage * (window.innerWidth - thumbWidth);
                    
                    // Ensure minimum height for rendering
                    const displayHeight = Math.max(horizontalScrollbarHeight, 8);
                    
                    // Create scrollbar element data
                    const scrollbarData = {
                        tagName: "scrollbar:main-horizontal",
                        jsPath: "document.documentElement:horizontal-scrollbar",
                        highlightIndex: highlightIndex,
                        boundingRect: {
                            top: window.innerHeight - displayHeight,
                            left: 0,
                            width: window.innerWidth,
                            height: displayHeight
                        },
                        scrollData: {
                            hasVerticalScrollbar: false,
                            hasHorizontalScrollbar: true,
                            scrollbarWidth: 0,
                            scrollbarHeight: horizontalScrollbarHeight,
                            contentHeight: document.documentElement.scrollHeight,
                            contentWidth: document.documentElement.scrollWidth,
                            visibleHeight: window.innerHeight,
                            visibleWidth: window.innerWidth,
                            scrollTop: document.documentElement.scrollTop,
                            scrollLeft: document.documentElement.scrollLeft,
                            maxScrollTop: document.documentElement.scrollHeight - window.innerHeight,
                            maxScrollLeft: document.documentElement.scrollWidth - window.innerWidth,
                            verticalThumb: null,
                            horizontalThumb: {
                                width: thumbWidth,
                                position: thumbPosition
                            },
                            isOverlayScrollbar: horizontalScrollbarHeight === 0
                        },
                        attributes: {
                            role: "scrollbar",
                            "aria-orientation": "horizontal"
                        },
                        text: "",
                        isMainScrollbar: true
                    };
                    
                    // Add browser scrollbar to interactive elements
                    interactiveElementsArray.push(scrollbarData);
                    
                    // Highlight if needed
                    if (doHighlightElements && 
                        (focusHighlightIndex < 0 || focusHighlightIndex === highlightIndex)) {
                        highlightScrollbar(document.documentElement, highlightIndex, false, true, true);
                    }
                    
                    highlightIndex++;
                }
            } catch (e) {
                console.warn("Error finding main browser scrollbars:", e);
            }
        }

        /**
         * Find scrollable elements in the viewport and add them to interactiveElements
         */
        function findScrollableElements(interactiveElementsArray) {
            try {
                // Process all elements to check for scrollability
                const allElements = document.querySelectorAll('*');
                
                for (const element of allElements) {
                    // Skip tiny elements or elements not in viewport
                    if (!isInViewport(element) || !isElementVisible(element)) continue;
                    if (element.clientWidth < 10 || element.clientHeight < 10) continue;
                    
                    const style = getCachedComputedStyle(element);
                    const overflow = style.overflow;
                    const overflowX = style.overflowX;
                    const overflowY = style.overflowY;
                    
                    // Check if element has scrollbars
                    const hasVerticalScrollbar = element.scrollHeight > element.clientHeight && 
                        (overflow === 'scroll' || overflow === 'auto' || 
                         overflowY === 'scroll' || overflowY === 'auto');
                    
                    const hasHorizontalScrollbar = element.scrollWidth > element.clientWidth && 
                        (overflow === 'scroll' || overflow === 'auto' || 
                         overflowX === 'scroll' || overflowX === 'auto');
                    
                    // Only include if it actually has scrollbars
                    if (hasVerticalScrollbar || hasHorizontalScrollbar) {
                        // Check if element is topmost at its position (not hidden behind an overlay)
                        if (!isTopElement(element)) continue;
                        
                        // Calculate scrollbar dimensions
                        const scrollbarWidth = element.offsetWidth - element.clientWidth;
                        const scrollbarHeight = element.offsetHeight - element.clientHeight;
                        
                        // Skip if scrollbars are too small
                        if ((hasVerticalScrollbar && scrollbarWidth < 1) || 
                            (hasHorizontalScrollbar && scrollbarHeight < 1)) continue;
                        
                        // Calculate thumb dimensions and positions
                        let verticalThumbHeight = 0;
                        let verticalThumbPosition = 0;
                        let horizontalThumbWidth = 0;
                        let horizontalThumbPosition = 0;
                        
                        if (hasVerticalScrollbar) {
                            verticalThumbHeight = Math.max(30, (element.clientHeight / element.scrollHeight) * element.clientHeight);
                            verticalThumbPosition = (element.scrollTop / (element.scrollHeight - element.clientHeight)) * 
                                                  (element.clientHeight - verticalThumbHeight);
                        }
                        
                        if (hasHorizontalScrollbar) {
                            horizontalThumbWidth = Math.max(30, (element.clientWidth / element.scrollWidth) * element.clientWidth);
                            horizontalThumbPosition = (element.scrollLeft / (element.scrollWidth - element.clientWidth)) * 
                                                    (element.clientWidth - horizontalThumbWidth);
                        }
                        
                        // Get scrollbar type
                        let scrollbarType = "";
                        if (hasVerticalScrollbar && hasHorizontalScrollbar) {
                            scrollbarType = "both";
                        } else if (hasVerticalScrollbar) {
                            scrollbarType = "vertical";
                        } else if (hasHorizontalScrollbar) {
                            scrollbarType = "horizontal";
                        }
                        
                        // Create a unique name that includes the element info
                        const rect = getCachedBoundingRect(element);
                        if (!rect) continue;
                        
                        // Special handling for scrollbars - skip duplicate check or check only against other scrollbars
                        // This ensures we don't miss scrollbars due to overlap with their parent elements
                        let isDuplicate = false;
                        
                        // Only check for duplication with other scrollbars, not with regular interactive elements
                        for (let i = 0; i < processedElementAreas.length; i++) {
                            const processedArea = processedElementAreas[i];
                            // Only compare with other elements that are specifically scrollbars
                            if (!processedArea.isScrollbar) continue;
                            
                            // Calculate overlap
                            const overlapX = Math.max(0, Math.min(rect.right, processedArea.right) - Math.max(rect.left, processedArea.left));
                            const overlapY = Math.max(0, Math.min(rect.bottom, processedArea.bottom) - Math.max(rect.top, processedArea.top));
                            
                            if (overlapX <= 0 || overlapY <= 0) continue; // No overlap
                            
                            const overlapArea = overlapX * overlapY;
                            const elementArea = (rect.right - rect.left) * (rect.bottom - rect.top);
                            const processedElementArea = (processedArea.right - processedArea.left) * (processedArea.bottom - processedArea.top);
                            
                            // Calculate overlap ratio based on the smaller element
                            const smallerArea = Math.min(elementArea, processedElementArea);
                            const overlapRatio = overlapArea / smallerArea;
                            
                            // If significant overlap with another scrollbar
                            if (overlapRatio > 0.8) {
                                isDuplicate = true;
                                break;
                            }
                        }
                        
                        if (isDuplicate) continue;
                        
                        // Create scrollbar element data
                        const scrollbarData = {
                            tagName: `scrollbar:${element.tagName.toLowerCase()}-${scrollbarType}`,
                            jsPath: getJSPathForElement(element) + ":scrollbar",
                            highlightIndex: highlightIndex,
                            boundingRect: {
                                top: Math.round(rect.top),
                                left: Math.round(rect.left),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height)
                            },
                            scrollData: {
                                hasVerticalScrollbar,
                                hasHorizontalScrollbar,
                                scrollbarWidth,
                                scrollbarHeight,
                                contentHeight: element.scrollHeight,
                                contentWidth: element.scrollWidth,
                                visibleHeight: element.clientHeight,
                                visibleWidth: element.clientWidth,
                                scrollTop: element.scrollTop,
                                scrollLeft: element.scrollLeft,
                                maxScrollTop: element.scrollHeight - element.clientHeight,
                                maxScrollLeft: element.scrollWidth - element.clientWidth,
                                backgroundColor: style.backgroundColor,
                                verticalThumb: hasVerticalScrollbar ? {
                                    height: verticalThumbHeight,
                                    position: verticalThumbPosition
                                } : null,
                                horizontalThumb: hasHorizontalScrollbar ? {
                                    width: horizontalThumbWidth,
                                    position: horizontalThumbPosition
                                } : null
                            },
                            attributes: {
                                role: "scrollbar",
                                "aria-orientation": hasVerticalScrollbar && hasHorizontalScrollbar ? 
                                    "both" : (hasVerticalScrollbar ? "vertical" : "horizontal"),
                                elementTagName: element.tagName.toLowerCase(),
                                elementId: element.id || null,
                                elementClass: element.className || null
                            },
                            text: getElementText(element),
                            playwrightInteraction: {
                                action: "scroll"
                            }
                        };
                        
                        // Add to processed areas to avoid duplicates
                        processedElementAreas.push({
                            left: rect.left,
                            top: rect.top,
                            right: rect.right,
                            bottom: rect.bottom,
                            element: element,
                            isScrollbar: true // Mark as scrollbar for special duplicate handling
                        });
                        
                        // Add scrollbar to interactive elements
                        interactiveElementsArray.push(scrollbarData);
                        
                        // Highlight if needed
                        if (doHighlightElements && 
                            (focusHighlightIndex < 0 || focusHighlightIndex === highlightIndex)) {
                            highlightScrollbar(element, highlightIndex, 
                                             hasVerticalScrollbar, 
                                             hasHorizontalScrollbar);
                        }
                        
                        highlightIndex++;
                    }
                }
            } catch (e) {
                console.warn("Error finding scrollable elements:", e);
            }
        }

        // Clear cache before processing
        const cacheClearedOnThisRun = DOM_CACHE.clearCache(false);
        if (debugMode && cacheClearedOnThisRun) {
            console.log("Cache cleared due to viewport size change or timeout");
        }

        // Find elements and return result
        const interactiveElements = findViewportInteractiveElements();
        const websiteInfo = getWebsiteInfo();
        
        // Return the final dataset-friendly result
        return {
            url: window.location.href,
            websiteInfo: websiteInfo,
            timestamp: new Date().toISOString(),
            viewportSize: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            scrollPosition: {
                x: window.pageXOffset,
                y: window.pageYOffset
            },
            interactiveElements: interactiveElements
        };
    };
    
    // Execute the function with default parameters and store results
    // window.domTreeData = window.domTreeResult(); // REMOVED
    
    // console.log("Viewport interactive elements analysis complete! Found", // REMOVED
    //             window.domTreeData.interactiveElements.length, // REMOVED
    //             "interactive elements in viewport (including scrollbars)"); // REMOVED
    
    // return window.domTreeData; // REMOVED
// })(); // REMOVED

// Can be called on scroll events with:
// window.domTreeData = window.domTreeResult();
