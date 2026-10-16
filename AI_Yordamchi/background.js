async function openPanel() {
  const url = chrome.runtime.getURL('panel.html');
  const tabs = await chrome.tabs.query({url});
  if (tabs.length) {
    await chrome.tabs.update(tabs[0].id, {active:true});
    await chrome.windows.update(tabs[0].windowId, {focused:true});
  } else await chrome.tabs.create({url});
}
chrome.action.onClicked.addListener(openPanel);
chrome.runtime.onInstalled.addListener(({reason}) => {
  chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
  if (reason === 'install') openPanel();
});
