// Single DOM analysis function with customizable parameters
window.analyzer = function(options) {
  // Default parameters
  const params = {
    doHighlightElements: false,
    focusHighlightIndex: -1,
    viewportExpansion: 0,
    debugMode: false,
    ...options // Override with any user-provided options
  };

  // Check if domTreeResult is available
  if (typeof window.domTreeResult !== 'function') {
    console.warn('DOM Tree Analyzer: domTreeResult function not found');
    return { error: 'domTreeResult function not found' };
  }
  
  // Run the DOM tree analysis with custom parameters
  try {
    const result = window.domTreeResult(params);
    
    // Notify extension
    window.postMessage({
      type: 'DOM_ANALYSIS_RESULT',
      result: result
    }, '*');
    
    return result;
  } catch (error) {
    console.error('DOM Tree Analyzer: Analysis error', error);
    return { error: error.toString() };
  }
};

// Log usage information
console.log('DOM Tree Analyzer ready: Call window.analyzer() or window.analyzer({ /* custom options */ })'); 