const panelEl = document.getElementById("panel");
const pinyinEl = document.getElementById("pinyin");
const resultEl = document.getElementById("result");

const LINE_HEIGHT = 20;
const PANEL_V_PAD = 8;

function applyPanelLayout(mode, maxLines) {
  panelEl.dataset.mode = mode;
  resultEl.style.webkitLineClamp = String(maxLines);
}

function preferredPanelHeight(mode, maxLines) {
  applyPanelLayout(mode, maxLines);

  const width = resultEl.getBoundingClientRect().width;
  if (width <= 0) {
    return LINE_HEIGHT + PANEL_V_PAD;
  }

  const probe = resultEl.cloneNode(true);
  Object.assign(probe.style, {
    position: "fixed",
    left: "-10000px",
    top: "0",
    width: `${width}px`,
    height: "auto",
    maxHeight: "none",
    visibility: "hidden",
    overflow: "visible",
    display: "block",
    webkitLineClamp: "unset",
  });
  document.body.appendChild(probe);

  const style = getComputedStyle(probe);
  const lineHeight = parseFloat(style.lineHeight) || LINE_HEIGHT;
  const lines = Math.max(1, Math.ceil(probe.scrollHeight / lineHeight));
  probe.remove();

  const clamped = Math.min(lines, maxLines);
  return clamped * lineHeight + PANEL_V_PAD;
}

function showComposing(pinyin, mode, maxLines) {
  pinyinEl.textContent = pinyin;
  if (!resultEl.classList.contains("error") && resultEl.dataset.ready !== "1") {
    resultEl.textContent = "…";
    resultEl.classList.add("loading");
  }
  return preferredPanelHeight(mode, maxLines);
}

function setLoading(pinyin, mode, maxLines) {
  pinyinEl.textContent = pinyin;
  resultEl.textContent = "…";
  resultEl.dataset.ready = "0";
  resultEl.classList.add("loading");
  resultEl.classList.remove("error");
  return preferredPanelHeight(mode, maxLines);
}

function updatePanel(pinyin, result, mode, maxLines) {
  pinyinEl.textContent = pinyin;

  const isError =
    result.startsWith("请求失败") ||
    result.startsWith("请配置") ||
    result.startsWith("未读到");

  resultEl.textContent = result;
  resultEl.dataset.ready = "1";
  resultEl.classList.remove("loading");
  resultEl.classList.toggle("error", isError);
  return preferredPanelHeight(mode, maxLines);
}

function resetPanel(mode, maxLines) {
  pinyinEl.textContent = "—";
  resultEl.textContent = "…";
  resultEl.dataset.ready = "0";
  resultEl.classList.remove("loading", "error");
  return preferredPanelHeight(mode, maxLines);
}

window.showComposing = showComposing;
window.setLoading = setLoading;
window.updatePanel = updatePanel;
window.resetPanel = resetPanel;
