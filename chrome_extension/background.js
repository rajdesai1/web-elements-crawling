// Background script
chrome.runtime.onInstalled.addListener(() => {
  console.log('DOM Tree Analyzer extension installed');
});

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'domAnalysisComplete') {
    console.log('DOM analysis completed for tab', sender.tab.id);
    console.log('Result:', message.result);
  }
}); 