// Seed Map button for Antichunk. Shown only while the
// mouse is free (menus, inventory, pause), hidden in play.
// Picture: maplink.png (left out if missing).
(function () {
  var a = document.createElement('a');
  a.href = '/antichunk/';
  a.target = '_blank';
  a.title = 'Open the seed map in a new tab';
  a.style.cssText = 'position:fixed;right:10px;bottom:10px;' +
    'z-index:9999;display:flex;align-items:center;gap:8px;' +
    'padding:6px 12px 6px 6px;border-radius:8px;' +
    'background:rgba(0,0,0,.75);color:#fff;' +
    'font:bold 15px sans-serif;text-decoration:none';
  var img = document.createElement('img');
  img.width = 36; img.height = 36; img.alt = '';
  img.style.borderRadius = '4px';
  img.onerror = function () { img.remove(); };
  img.src = '/maplink.png';
  a.append(img, 'Seed Map');
  document.body.appendChild(a);
  setInterval(function () {
    var f = window.irrlicht_want_pointerlock, play = false;
    try { play = typeof f === 'function' && f() === 1; } catch (e) {}
    a.style.display = play ? 'none' : 'flex';
  }, 250);
})();
