// Single content script that injects scripts properly
console.log('DOM Tree Analyzer: Content script running');

// One-time initialization
if (document.documentElement.hasAttribute('data-dom-analyzer-loaded')) {
  console.log('DOM Tree Analyzer: Already loaded on this page');
} else {
  // Mark document as initialized
  document.documentElement.setAttribute('data-dom-analyzer-loaded', 'true');
  
  // First, inject the core DOM analysis script
  injectScript('buildDOMTree.js', function() {
    // Once the core script is loaded, inject the interface script
    injectScript('pageScript.js', function() {
      console.log('DOM Tree Analyzer: Both scripts loaded successfully');
      notifyBackground('success');
    });
  });
}

// Helper function to inject a script by URL
function injectScript(scriptName, onloadCallback) {
  try {
    const scriptUrl = chrome.runtime.getURL(scriptName);
    const script = document.createElement('script');
    script.src = scriptUrl;
    script.onload = function() {
      console.log('DOM Tree Analyzer: Loaded ' + scriptName);
      if (onloadCallback) onloadCallback();
    };
    script.onerror = function(error) {
      console.error('DOM Tree Analyzer: Failed to load ' + scriptName, error);
      notifyBackground('error', 'Failed to load ' + scriptName);
    };
    (document.head || document.documentElement).appendChild(script);
  } catch (error) {
    console.error('DOM Tree Analyzer: Error injecting ' + scriptName, error);
    notifyBackground('error', error.toString());
  }
}

// Helper to notify the background script
function notifyBackground(status, message) {
  try {
    chrome.runtime.sendMessage({
      action: 'scriptInjected',
      status: status,
      message: message || ''
    });
  } catch (error) {
    console.error('DOM Tree Analyzer: Error sending message to background', error);
  }
}

// Listen for messages from page scripts
window.addEventListener('message', function(event) {
  // Only accept messages from the same frame
  if (event.source !== window) return;
  
  // Check if message contains DOM analysis results
  if (event.data && event.data.type === 'DOM_ANALYSIS_RESULT') {
    try {
      chrome.runtime.sendMessage({
        action: 'domAnalysisComplete',
        result: event.data.result
      });
    } catch (error) {
      console.error('DOM Tree Analyzer: Error sending analysis results', error);
    }
  }
}); 