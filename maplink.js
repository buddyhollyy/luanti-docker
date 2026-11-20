// Seed Map button for Antichunk, plus a World button for the /world page.
// Shown only while the mouse is free (menus, inventory, pause), hidden in
// play. The World button only appears where /world/ answers, so visitors
// your proxy keeps out never see it. Picture: maplink.png (left out if missing).
(function () {
  var box = document.createElement('div');
  box.style.cssText = 'position:fixed;right:10px;bottom:10px;z-index:9999;' +
    'display:flex;flex-direction:column;gap:8px;align-items:stretch';
  function button(href, title) {
    var a = document.createElement('a');
    a.href = href;
    a.target = '_blank';
    a.tabIndex = -1;
    a.title = title;
    a.style.cssText = 'display:flex;align-items:center;gap:8px;' +
      'padding:6px 12px 6px 6px;border-radius:8px;' +
      'background:rgba(0,0,0,.75);color:#fff;' +
      'font:bold 15px sans-serif;text-decoration:none';
    return a;
  }
  var map = button('/antichunk/', 'Open the seed map in a new tab');
  var img = document.createElement('img');
  img.width = 36; img.height = 36; img.alt = '';
  img.style.borderRadius = '4px';
  img.onerror = function () { img.remove(); };
  img.src = '/maplink.png';
  map.append(img, 'Seed Map');
  box.appendChild(map);
  document.body.appendChild(box);

  fetch('/world/api/info', { cache: 'no-store' }).then(function (r) {
    if (!r.ok) return;
    var w = button('/world/', 'Download, upload or restore the server world');
    // Up and down arrows: download and upload.
    w.innerHTML = '<svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">' +
      '<rect width="36" height="36" rx="4" fill="#2f6f3e"/>' +
      '<g fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M12 27V9M7 14l5-5 5 5"/><path d="M24 9v18M19 22l5 5 5-5"/></g></svg>World';
    box.appendChild(w);
  }).catch(function () {});

  setInterval(function () {
    var f = window.irrlicht_want_pointerlock, play = false;
    try { play = typeof f === 'function' && f() === 1; } catch (e) {}
    box.style.display = play ? 'none' : 'flex';
  }, 250);
})();
