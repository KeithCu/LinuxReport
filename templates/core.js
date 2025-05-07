// Core module: theme, font, scroll restore, auto-refresh, redirect, and pagination

// Apply theme, font, no-underlines and restore scroll
document.addEventListener('DOMContentLoaded', function() {
  // Read theme cookie or default
  var match = document.cookie.match(/(?:^|; )Theme=([^;]+)/);
  var theme = match ? match[1] : 'silver';
  document.body.classList.add('theme-' + theme);
  var select = document.getElementById('theme-select'); if (select) select.value = theme;

  // Read font cookie or default
  var fontMatch = document.cookie.match(/(?:^|; )FontFamily=([^;]+)/);
  var font = fontMatch ? fontMatch[1] : 'sans-serif';
  document.body.classList.remove(
    'font-system','font-monospace','font-inter','font-roboto','font-open-sans','font-source-sans','font-noto-sans','font-lato','font-raleway','font-sans-serif'
  );
  document.body.classList.add('font-' + font);
  var fontSelect = document.getElementById('font-select'); if (fontSelect) fontSelect.value = font;

  // No underlines setting
  var nu = document.cookie.match(/(?:^|; )NoUnderlines=([^;]+)/);
  if (!nu || nu[1] === '1') document.body.classList.add('no-underlines');

  // Restore scroll position
  restoreScrollPosition();
});

let pendingScrollRestoreAfterFontChange = false;

function finalRestoreScroll() {
  if (pendingScrollRestoreAfterFontChange) {
    restoreScrollPosition();
    pendingScrollRestoreAfterFontChange = false;
  }
}

function redirect() { window.location = "/config"; }

var timer = setInterval(autoRefresh, 3601 * 1000);
function autoRefresh() { self.location.reload(); }

function setTheme(theme) {
  localStorage.setItem('scrollPosition', JSON.stringify({position: window.scrollY, timestamp: Date.now()}));
  document.cookie = 'Theme=' + theme + ';path=/';
  window.location.reload();
}

function setFont(font) {
  localStorage.setItem('scrollPosition', JSON.stringify({position: window.scrollY, timestamp: Date.now()}));
  pendingScrollRestoreAfterFontChange = true;
  document.cookie = 'FontFamily=' + font + ';path=/';
  document.body.classList.remove(
    'font-system','font-monospace','font-inter','font-roboto','font-open-sans','font-source-sans','font-noto-sans','font-lato','font-raleway','font-sans-serif'
  );
  document.body.classList.add('font-' + font);
  var fontSelect = document.getElementById('font-select'); if (fontSelect) fontSelect.value = font;
  document.body.style.display = 'none'; document.body.offsetHeight; document.body.style.display = '';
  document.querySelectorAll('*').forEach(el => el.style.fontFamily = 'inherit');
  setTimeout(finalRestoreScroll, 1000);
}

function restoreScrollPosition() {
  try {
    const saved = localStorage.getItem('scrollPosition'); if (!saved) return;
    const data = JSON.parse(saved);
    if (Date.now() - data.timestamp > 10000) { localStorage.removeItem('scrollPosition'); return; }
    window.scrollTo(0, data.position); localStorage.removeItem('scrollPosition');
  } catch (e) { console.error(e); localStorage.removeItem('scrollPosition'); }
}

// Pagination controls
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.pagination-controls').forEach(feedControls => {
    const feedId = feedControls.dataset.feedId;
    const items = document.getElementById(feedId).querySelectorAll('.linkclass');
    const prevBtn = feedControls.querySelector('.prev-btn');
    const nextBtn = feedControls.querySelector('.next-btn');
    const itemsPerPage = 8; let currentPage = 0;
    const totalPages = Math.ceil(items.length / itemsPerPage);
    function update() {
      items.forEach((item,i) => item.style.display = (i>=currentPage*itemsPerPage && i<(currentPage+1)*itemsPerPage)?'block':'none');
      if (prevBtn) prevBtn.disabled = currentPage===0;
      if (nextBtn) nextBtn.disabled = currentPage>=totalPages-1;
    }
    if (prevBtn) prevBtn.addEventListener('click', ()=>{ if(currentPage>0){currentPage--;update();} });
    if (nextBtn) nextBtn.addEventListener('click', ()=>{ if(currentPage<totalPages-1){currentPage++;update();} });
    update();
  });
});