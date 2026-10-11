/* Paste in Chromium DevTools Console after selecting ONE allowed timeline element
   in Elements. Reads only DOM structure; no clicks, requests or Zalo mutations.
   Does not include text, image URLs, cookies, localStorage or session data. */
(() => {
  const normalize = text => text.normalize('NFC').replace(/\s+/gu, ' ').trim();
  const expectedTitle = 'ĐỐI CHIẾU KL- KẾ TOÁN IJC';
  const expectedId = 'g3144426084883145716';
  const selectedRows = [...document.querySelectorAll("[data-id='div_TabMsg_ThrdChItem']")]
    .filter(row => row.querySelector('.conv-item.selected'));
  if (selectedRows.length !== 1) throw new Error('STOP: selected conversation is ambiguous');
  const row = selectedRows[0];
  const title = row.querySelector('.conv-item-title__name .truncate')?.textContent || '';
  if (normalize(title) !== normalize(expectedTitle) || row.getAttribute('anim-data-id') !== expectedId)
    throw new Error('STOP: selected source differs from observed allowed group');
  const element = typeof $0 !== 'undefined' ? $0 : null;
  if (!(element instanceof Element) || element.closest('#conversationList') ||
      element.closest('[contenteditable], textarea, input') || element === document.body ||
      element === document.documentElement)
    throw new Error('STOP: choose one message text or attachment image in Elements');
  const allowedAttrs = ['id', 'class', 'data-id', 'data-component', 'anim-data-id', 'role'];
  const describe = node => ({
    tag: node.tagName.toLowerCase(),
    attributes: Object.fromEntries(allowedAttrs.filter(a => node.hasAttribute(a))
      .map(a => [a, node.getAttribute(a)])),
    childTags: [...node.children].slice(0, 20).map(n => n.tagName.toLowerCase())
  });
  const ancestors = [];
  let node = element;
  for (let i = 0; i < 7 && node && node !== document.body; i++, node = node.parentElement)
    ancestors.push(describe(node));
  console.log(JSON.stringify({scope: 'manual_selected_element_structure_only', ancestors}, null, 2));
})();
