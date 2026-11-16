const $ = (selector) => document.querySelector(selector);
const sessionKey = 'sunlit-tarot-session';
const draftKey = 'yi-wonderland-draft';
let setupPage = 'question';
let routing = false;
let spreads = [];
let reading = null;
let token = '';
let busy = false;
let shuffled = false;
let timer;
let mixDistance = 0;
let mixPointer = null;
let mixLast = null;
let mixCards = [];
let mixRatio = 0;
let mixCheckpoint = -1;
const icons = ['☀', '✧', '↗', '⚖'];

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function notice(message = '', error = false) {
  const element = $('#status-message');
  element.textContent = message;
  element.className = `notice${error ? ' error' : ''}`;
  element.hidden = !message;
}
function step(index) {
  document.querySelectorAll('.steps li').forEach((element, i) => {
    element.classList.toggle('active', i === index);
    element.classList.toggle('done', i < index);
    if (i === index) element.setAttribute('aria-current', 'step');
    else element.removeAttribute('aria-current');
  });
}
function activateScreen(screen, focus = true) {
  const changed = document.body.dataset.screen !== screen;
  document.body.dataset.screen = screen;
  $('#experience').hidden = screen === 'home';
  const hash = screen === 'home' ? '' : `#${screen}`;
  if (location.hash !== hash) history[routing ? 'replaceState' : 'pushState']({ screen }, '', `${location.pathname}${hash}`);
  if (changed) {
    releaseMixing();
    if (focus) window.scrollTo({ top: 0, behavior: 'instant' });
  }
  return changed;
}
function showPanel(panel, screen = panel === 'setup' ? setupPage : panel === 'result-panel' ? 'result' : panel === 'loading-panel' ? 'loading' : shuffled ? 'draw' : 'shuffle') {
  ['setup', 'draw-panel', 'loading-panel', 'result-panel'].forEach(id => { $(`#${id}`).hidden = id !== panel; });
  const changed = activateScreen(screen);
  if (changed) {
    const visiblePanel = panel === 'setup' ? $(`#${setupPage}-step`) : $(`#${panel}`);
    visiblePanel.classList.remove('journey-enter');
    requestAnimationFrame(() => {
      visiblePanel.classList.add('journey-enter');
      const heading = visiblePanel.querySelector('h3');
      if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
    });
  }
}
function scrollToExperience() { window.scrollTo({ top: 0, behavior: 'instant' }); }
function showSetup(page) {
  setupPage = page;
  const locked = Boolean(reading?.cards.length);
  $('#question').disabled = locked;
  document.querySelectorAll('input[name="spread"], #option-a, #option-b').forEach(input => { input.disabled = locked; });
  $('#locked-context').hidden = !locked;
  $('#question-step').hidden = page !== 'question';
  $('#spread-step').hidden = page !== 'spread';
  $('#spread-question-preview').textContent = $('#question').value.trim();
  showPanel('setup', page); step(page === 'question' ? 0 : 1);
  $('#start-button').firstChild.textContent = reading ? '回到這次的牌組 ' : '準備好了，去洗牌 ';
  saveDraft();
}
function showHome() {
  if (busy) return;
  notice(); activateScreen('home');
}
function saveDraft() {
  try { sessionStorage.setItem(draftKey, JSON.stringify({ question: $('#question').value, spreadId: document.querySelector('input[name="spread"]:checked')?.value, a: $('#option-a').value, b: $('#option-b').value })); } catch { /* 不影響流程。 */ }
}
function applyDraft(draft) {
  if (!draft) return;
  if (typeof draft.question === 'string') $('#question').value = draft.question;
  if (typeof draft.a === 'string') $('#option-a').value = draft.a;
  if (typeof draft.b === 'string') $('#option-b').value = draft.b;
  document.querySelectorAll('input[name="spread"]').forEach(input => { input.checked = input.value === draft.spreadId; });
  if (!document.querySelector('input[name="spread"]:checked')) {
    const fallback = document.querySelectorAll('input[name="spread"]')[1];
    if (fallback) fallback.checked = true;
  }
  updateComparison(); countQuestion();
}
function updateComparison() {
  const selected = spreads.find(spread => spread.id === document.querySelector('input[name="spread"]:checked')?.value);
  const compare = Boolean(selected?.requiresOptions);
  $('#comparison-options').hidden = !compare;
  $('#option-a').required = compare; $('#option-b').required = compare;
}
function routeLocation() {
  if (busy) { history.replaceState({}, '', `#${document.body.dataset.screen}`); return; }
  routing = true;
  const target = location.hash.slice(1);
  notice();
  if (!target || target === 'home') showHome();
  else if (target === 'question') showSetup('question');
  else if (target === 'spread' && $('#question').value.trim()) showSetup('spread');
  else if (reading && target === 'result' && reading.interpretation) renderResult();
  else if (reading && ['shuffle', 'draw', 'loading', 'result', 'experience'].includes(target)) {
    if (target === 'shuffle') renderDraw('shuffle');
    else if (reading.interpretation && target !== 'draw') renderResult();
    else renderDraw();
  } else showSetup('question');
  routing = false;
}
async function api(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method, headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(65000)
    });
  } catch {
    throw new Error('暫時連不上服務。你的抽牌不會改變，請稍後再試。');
  }
  let data;
  try { data = await response.json(); } catch { throw new Error('服務回應不完整，請稍後再試。'); }
  if (!response.ok) {
    const error = new Error(data.error?.message || '服務暫時忙碌，請稍後再試。');
    error.code = data.error?.code;
    error.status = response.status;
    throw error;
  }
  return data;
}
function saveSession() {
  try { sessionStorage.setItem(sessionKey, JSON.stringify({ id: reading.id, token, shuffled })); } catch { /* 儲存不可用時仍可占卜。 */ }
}
function clearSession() {
  try { sessionStorage.removeItem(sessionKey); sessionStorage.removeItem(draftKey); } catch { /* 無需阻擋操作。 */ }
}
function countQuestion() {
  const length = Array.from($('#question').value.trim()).length;
  const over = length > 100;
  $('#question-count').textContent = `${length} / 100`;
  $('#question-count').classList.toggle('error', over);
  $('#question').classList.toggle('over-limit', over);
  $('#question').setCustomValidity(over ? '問題最多 100 字，請精簡後再出發。' : '');
  $('#question').setAttribute('aria-invalid', String(over));
  $('#question-help').textContent = over ? '超過 100 字囉，請保留重點與你最想釐清的問題。' : '寫得具體一點，比「我會成功嗎？」更容易獲得有用的指引。';
  $('#question-help').classList.toggle('error', over);
}
function renderSpreads() {
  const container = $('#spread-options'); container.replaceChildren();
  spreads.forEach((spread, index) => {
    const label = node('label', 'spread-option');
    const input = node('input'); input.type = 'radio'; input.name = 'spread'; input.value = spread.id; input.checked = index === 1; input.required = true;
    const content = node('span', 'option-content');
    content.append(node('span', 'option-icon', icons[index] || '✦'));
    const copy = node('span'); copy.append(node('strong', '', spread.name), node('small', '', spread.description));
    const dot = node('span', 'radio-dot'); dot.setAttribute('aria-hidden', 'true');
    content.append(copy, dot); label.append(input, content); container.append(label);
    input.addEventListener('change', () => {
      updateComparison(); saveDraft();
    });
  });
  $('#start-button').disabled = false;
}
function imageFor(card) {
  const image = node('img', card.orientation === 'reversed' ? 'reversed' : '');
  // 圖片路徑由後端提供，只接受專案牌組路徑。
  if (/^\/cards\/rider-waite-smith\/[a-z0-9-]+\.jpg$/.test(card.image)) image.src = card.image;
  image.alt = `${card.nameZh}，${card.orientation === 'reversed' ? '逆位' : '正位'}`;
  image.loading = 'lazy';
  return image;
}
function renderDraw(view = shuffled ? 'draw' : 'shuffle') {
  if (view === 'draw' && !shuffled) view = 'shuffle';
  const drawing = view === 'draw';
  showPanel('draw-panel', view); step(drawing ? 3 : 2);
  $('#draw-question').textContent = reading.question;
  const count = reading.cards.length;
  $('#draw-title').textContent = !drawing ? shuffled ? '這副牌，已為你準備好了。' : '深呼吸，把心慢慢放輕。' : count === 3 ? '三張牌，已經與你相遇。' : `現在，選出你的第${['一', '二', '三'][count]}張牌。`;
  $('#draw-subtitle').textContent = !drawing ? shuffled ? '返回不會改變牌組，準備好就繼續這次的抽牌。' : '想著你的問題，用手勢慢慢洗牌。準備好時，再開始選牌。' : count === 3 ? '看看它們的模樣，準備好就打開這次的指引。' : `這張牌將代表「${reading.spread.positions[count].label}」，跟著直覺點選一個位置。`;
  $('#manual-shuffle').hidden = drawing;
  $('#selected-cards').hidden = !drawing;
  $('#card-selection').hidden = !drawing || count === 3;
  $('#interpret-button').hidden = !drawing || count !== 3;
  $('#continue-draw').hidden = !shuffled;
  $('#continue-draw').disabled = busy;
  $('#shuffle-button').hidden = shuffled;
  $('#shuffle-scene').setAttribute('aria-disabled', String(shuffled));
  $('#shuffle-scene').tabIndex = shuffled ? -1 : 0;
  $('#shuffle-help').textContent = shuffled ? '這副牌已完成洗牌。可以返回查看牌陣，或繼續選牌；原本的牌序與正逆位都會保留。' : '用手指，或按住觸控板／滑鼠，在牌桌上來回畫圈，把牌慢慢混開。也可以聚焦牌桌後，使用方向鍵洗牌。';
  if (shuffled) $('#shuffle-status').textContent = '牌組已固定，返回查看不會改變抽牌結果。';
  $('#draw-back').textContent = drawing ? '← 回到洗牌桌' : '← 回到牌陣';
  $('#draw-back').disabled = busy;
  const slots = $('#selected-cards'); slots.replaceChildren();
  reading.spread.positions.forEach((position, i) => {
    const slot = node('div', 'card-slot');
    const label = node('div', 'slot-label'); label.append(node('span', '', `0${i + 1}`), document.createTextNode(position.label)); slot.append(label);
    const figure = node('figure'); const imageWrap = node('div', 'card-image-wrap');
    const card = reading.cards[i];
    if (card) { imageWrap.append(imageFor(card)); figure.append(imageWrap, node('figcaption', '', card.nameZh), node('span', 'orientation', card.orientation === 'reversed' ? 'REVERSED · 逆位' : 'UPRIGHT · 正位')); }
    else { imageWrap.append(node('div', 'card-empty', '✦')); figure.append(imageWrap, node('figcaption', '', '等待你的直覺')); }
    slot.append(figure); slots.append(slot);
  });
  const grid = $('#deck-grid'); grid.replaceChildren();
  for (let position = 0; position < reading.deckSize; position++) {
    const selected = reading.selectedPositions.includes(position);
    const button = node('button', `deck-card${selected ? ' selected' : ''}`); button.type = 'button';
    button.setAttribute('aria-label', `位置 ${position + 1}${selected ? '，已抽取' : '，抽取這張牌'}`);
    button.disabled = selected || busy;
    const image = node('img'); image.src = '/assets/card-back.svg'; image.alt = '';
    button.append(image, node('span', '', String(position + 1).padStart(2, '0')));
    button.addEventListener('click', () => draw(position)); grid.append(button);
  }
  $('#interpret-button').disabled = busy;
  $('#restart-button').disabled = busy;
}
async function draw(position) {
  if (busy || reading.cards.length >= 3) return;
  busy = true; notice(); renderDraw();
  const drawIndex = reading.cards.length;
  try {
    reading = await api(`/readings/${reading.id}/draw`, { method: 'POST', body: { position, drawIndex } });
    saveSession();
  } catch (error) {
    // 請求可能已在伺服器完成；先同步，避免將同一張重抽。
    try { reading = await api(`/readings/${reading.id}`); saveSession(); } catch { /* 保留原狀可安全重試。 */ }
    notice(error.message, true);
  } finally {
    busy = false; renderDraw();
    const next = $('#deck-grid button:not(:disabled)');
    if (reading.cards.length === 3) $('#interpret-button').focus({ preventScroll: true });
    else if (next) next.focus({ preventScroll: true });
  }
}
function renderResult() {
  showPanel('result-panel'); step(4);
  const result = reading.interpretation;
  $('#result-question').textContent = reading.question;
  $('#result-summary').textContent = result.summary;
  const container = $('#result-cards'); container.replaceChildren();
  reading.cards.forEach((card, index) => {
    const article = node('article', 'result-card');
    article.append(node('div', 'slot-label', `0${index + 1} / ${card.position.label}`));
    const image = node('div', 'card-image-wrap'); image.append(imageFor(card));
    article.append(image, node('h4', '', card.nameZh), node('span', 'orientation', card.orientation === 'reversed' ? 'REVERSED · 逆位' : 'UPRIGHT · 正位'), node('p', '', result.cards[index].interpretation));
    container.append(article);
  });
  const advice = $('#result-advice'); advice.replaceChildren(...result.advice.map(item => node('li', '', item)));
  $('#result-reflection').textContent = result.reflection;
}
async function interpret() {
  if (busy) return;
  if (reading.interpretation) { renderResult(); return; }
  busy = true; notice(); showPanel('loading-panel'); step(4); scrollToExperience();
  const started = Date.now();
  $('#loading-time').textContent = '已等待 0 秒';
  timer = setInterval(() => { const seconds = Math.floor((Date.now() - started) / 1000); $('#loading-time').textContent = seconds < 15 ? `已等待 ${seconds} 秒` : `已等待 ${seconds} 秒 · 解讀仍在準備中`; }, 1000);
  try {
    reading = await api(`/readings/${reading.id}/interpretation`, { method: 'POST' });
    saveSession(); renderResult();
  } catch (error) {
    // 斷線不代表後端失敗，優先恢復可能已保存的結果。
    try { reading = await api(`/readings/${reading.id}`); } catch { /* 下次可重試。 */ }
    if (reading.interpretation) renderResult();
    else { renderDraw(); $('#interpret-button').firstChild.textContent = '再試一次，打開指引 '; notice(`${error.message} 已保留原本三張牌，不需要重新抽牌。`, true); }
  } finally { busy = false; clearInterval(timer); $('#interpret-button').disabled = false; $('#restart-button').disabled = false; $('#draw-back').disabled = false; }
}
function restart() {
  if (busy) return;
  reading = null; token = ''; shuffled = false; clearSession(); notice();
  $('#question').value = ''; $('#option-a').value = ''; $('#option-b').value = ''; countQuestion();
  showSetup('question');
  resetMixing();
}
$('#question').addEventListener('input', () => { countQuestion(); saveDraft(); });
for (const id of ['option-a', 'option-b']) $(`#${id}`).addEventListener('input', saveDraft);
$('#question-next').addEventListener('click', () => {
  if (busy) return;
  countQuestion();
  if ($('#question').reportValidity()) { notice(); showSetup('spread'); }
});
$('#question-back').addEventListener('click', showHome);
$('#spread-back').addEventListener('click', () => { if (!busy) { notice(); showSetup('question'); } });
$('#continue-draw').addEventListener('click', () => { if (!busy) renderDraw('draw'); });
$('#draw-back').addEventListener('click', () => {
  if (busy) return;
  notice();
  if (document.body.dataset.screen === 'draw') renderDraw('shuffle');
  else showSetup('spread');
});
$('#result-back').addEventListener('click', () => { if (!busy) renderDraw('draw'); });
document.querySelectorAll('a[href="#experience"]').forEach(link => link.addEventListener('click', event => {
  event.preventDefault(); if (busy) return;
  notice();
  if (reading?.interpretation) renderResult();
  else if (reading) renderDraw();
  else showSetup('question');
}));
document.querySelectorAll('a[href="/"]').forEach(link => link.addEventListener('click', event => { event.preventDefault(); showHome(); }));
window.addEventListener('popstate', routeLocation);
window.addEventListener('hashchange', routeLocation);
$('#reading-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  if (setupPage !== 'spread') { $('#question-next').click(); return; }
  countQuestion(); if (!$('#reading-form').reportValidity()) return;
  busy = true; notice(); $('#start-button').disabled = true; $('#start-button').firstChild.textContent = '正在準備你的牌組 ';
  try {
    const spreadId = document.querySelector('input[name="spread"]:checked').value;
    const body = { question: $('#question').value.trim(), spreadId };
    if (spreads.find(spread => spread.id === spreadId)?.requiresOptions) body.options = { a: $('#option-a').value.trim(), b: $('#option-b').value.trim() };
    const same = reading && reading.question === body.question && reading.spread.id === body.spreadId && JSON.stringify(reading.options ?? null) === JSON.stringify(body.options ?? null);
    if (same) { if (reading.interpretation) renderResult(); else renderDraw(); return; }
    if (reading?.cards.length) throw new Error('已開始抽牌，請保留原問題與牌陣，或重新開始一次占卜。');
    const created = await api('/readings', { method: 'POST', body }); reading = created; token = created.accessToken; shuffled = false;
    resetMixing();
    saveSession(); renderDraw(); scrollToExperience();
  } catch (error) { notice(error.message, true); }
  finally {
    busy = false; $('#start-button').disabled = false; $('#restart-button').disabled = false; $('#draw-back').disabled = false;
    $('#start-button').firstChild.textContent = reading ? '回到這次的牌組 ' : '準備好了，去洗牌 ';
    if (['draw', 'shuffle'].includes(document.body.dataset.screen)) renderDraw(document.body.dataset.screen);
  }
});
$('#shuffle-button').addEventListener('click', async () => {
  if (busy || mixRatio < 1) return;
  busy = true; $('#shuffle-button').disabled = true; $('#restart-button').disabled = true;
  $('#shuffle-button').firstChild.textContent = '正在收攏你的牌組 ';
  releaseMixing();
  try {
    // 手勢只決定視覺互動；實際牌序仍由後端安全亂數產生。
    reading = await api(`/readings/${reading.id}/shuffle`, { method: 'POST' });
    shuffled = true; saveSession();
  } catch (error) { notice(`${error.message} 牌桌仍為你保留，請再試一次。`, true); }
  finally {
    busy = false; $('#shuffle-button').disabled = mixRatio < 1;
    $('#shuffle-button').firstChild.textContent = '洗好了，開始選牌 '; renderDraw();
    if (shuffled) $('#deck-grid button:not(:disabled)')?.focus({ preventScroll: true });
  }
});

function paintMixing() {
  for (const card of mixCards) {
    card.element.style.left = `${card.x * 100}%`;
    card.element.style.top = `${card.y * 100}%`;
    card.element.style.transform = `translate(-50%, -50%) rotate(${card.angle}deg)`;
  }
}
function resetMixing() {
  releaseMixing(); mixDistance = 0; mixRatio = 0; mixCheckpoint = -1;
  const container = $('#mixing-cards'); container.replaceChildren();
  mixCards = Array.from({ length: 18 }, (_, i) => {
    const element = node('img', 'mix-card'); element.src = '/assets/card-back.svg'; element.alt = ''; element.draggable = false;
    container.append(element);
    return { element, x: .5 + Math.cos(i * 2.4) * .14, y: .5 + Math.sin(i * 2.4) * .16, angle: (i - 9) * 8 };
  });
  paintMixing(); updateMixProgress();
}
function updateMixProgress() {
  mixRatio = Math.min(1, mixDistance / 1.6);
  $('#shuffle-progress-fill').style.width = `${mixRatio * 100}%`;
  $('#shuffle-button').disabled = busy || mixRatio < 1;
  const checkpoint = Math.floor(mixRatio * 4);
  if (checkpoint === mixCheckpoint) return;
  mixCheckpoint = checkpoint;
  $('#shuffle-status').textContent = mixRatio === 1 ? '牌已經混開了！可以繼續洗，或按「洗好了」開始選牌。' : mixRatio > 0 ? `牌跟著你的手勢散開了，再混一混就好。${Math.round(mixRatio * 100)}%` : '還沒開始，試著按住牌面滑動看看。';
}
function stirCards(x, y, dx, dy) {
  const table = $('#shuffle-scene');
  const rect = table.getBoundingClientRect();
  const distance = Math.hypot(dx, dy);
  if (distance < .001) return;
  mixDistance += Math.min(distance, .15);
  for (let i = 0; i < mixCards.length; i++) {
    const card = mixCards[i];
    const proximity = Math.hypot((card.x - x) * rect.width / rect.height, card.y - y);
    const influence = Math.max(.08, 1 - proximity / .65);
    // 牌面在手勢附近跟著移動，加入方向交錯讓整副牌自然混散。
    card.x = Math.max(.12, Math.min(.88, card.x + dx * influence * 2.2 + Math.cos(i * 2.4 + mixDistance * 5) * distance * .32));
    card.y = Math.max(.2, Math.min(.8, card.y + dy * influence * 2.2 + Math.sin(i * 2.4 + mixDistance * 5) * distance * .4));
    card.angle += (dx * 120 - dy * 100) * (i % 2 ? 1 : -1) * influence;
  }
  paintMixing(); updateMixProgress();
}
function releaseMixing() {
  const table = $('#shuffle-scene');
  if (mixPointer !== null && table.hasPointerCapture(mixPointer)) table.releasePointerCapture(mixPointer);
  mixPointer = null; mixLast = null; table.classList.remove('is-mixing');
}
$('#shuffle-scene').addEventListener('pointerdown', event => {
  if (busy || shuffled || mixPointer !== null || (event.pointerType === 'mouse' && event.button !== 0)) return;
  event.preventDefault();
  const table = event.currentTarget;
  table.focus({ preventScroll: true }); table.setPointerCapture(event.pointerId);
  mixPointer = event.pointerId; mixLast = { x: event.clientX, y: event.clientY };
  table.classList.add('is-mixing');
});
$('#shuffle-scene').addEventListener('pointermove', event => {
  if (event.pointerId !== mixPointer || !mixLast || busy || shuffled) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
  const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
  stirCards(x, y, (event.clientX - mixLast.x) / rect.width, (event.clientY - mixLast.y) / rect.height);
  mixLast = { x: event.clientX, y: event.clientY };
});
for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) $('#shuffle-scene').addEventListener(type, event => {
  if (event.pointerId === mixPointer) releaseMixing();
});
$('#shuffle-scene').addEventListener('keydown', event => {
  if (busy || shuffled) return;
  const vectors = { ArrowLeft: [-.08, 0], ArrowRight: [.08, 0], ArrowUp: [0, -.08], ArrowDown: [0, .08] };
  if (!vectors[event.key]) return;
  event.preventDefault();
  const [dx, dy] = vectors[event.key]; stirCards(.5 + dx, .5 + dy, dx, dy);
});
window.addEventListener('blur', releaseMixing);
$('#interpret-button').addEventListener('click', interpret);
$('#restart-button').addEventListener('click', restart);
$('#new-reading-button').addEventListener('click', restart);
$('#print-button').addEventListener('click', () => window.print());
$('#about-button').addEventListener('click', () => $('#about-dialog').showModal());
$('#close-about').addEventListener('click', () => $('#about-dialog').close());
$('#about-done').addEventListener('click', () => $('#about-dialog').close());
$('#about-dialog').addEventListener('click', event => { if (event.target === $('#about-dialog')) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close(); } });

async function init() {
  try { spreads = (await api('/spreads')).spreads; renderSpreads(); }
  catch (error) { notice('牌陣暫時無法載入，請確認服務正常後重新整理頁面。', true); return; }
  let saved;
  try { applyDraft(JSON.parse(sessionStorage.getItem(draftKey))); } catch { /* 忽略無效草稿。 */ }
  try { saved = JSON.parse(sessionStorage.getItem(sessionKey)); } catch { clearSession(); }
  if (!saved?.id || !saved?.token) { routeLocation(); return; }
  token = saved.token;
  try {
    reading = await api(`/readings/${saved.id}`);
    applyDraft({ question: reading.question, spreadId: reading.spread.id, a: reading.options?.a ?? '', b: reading.options?.b ?? '' });
    shuffled = Boolean(saved.shuffled || reading.cards.length);
    resetMixing(); routeLocation();
    if (document.body.dataset.screen !== 'home') notice('歡迎回來，已替你保留這次的占卜進度。');
  } catch (error) {
    if (error.status === 404) { clearSession(); token = ''; }
    routeLocation();
    notice('暫時無法恢復上次進度。你可以重新整理再試，或開始新的占卜。', true);
  }
}
init();
