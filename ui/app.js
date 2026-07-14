const pinyinEl = document.getElementById("pinyin");
const resultEl = document.getElementById("result");

function preferredPanelHeight() {
  const width = resultEl.getBoundingClientRect().width;
  if (width <= 0) {
    return 40;
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
  const lineHeight = parseFloat(style.lineHeight) || 20;
  const lines = Math.max(1, Math.ceil(probe.scrollHeight / lineHeight));
  probe.remove();

  return Math.min(lines, 3) * 40;
}

function showComposing(pinyin) {
  pinyinEl.textContent = pinyin;
  if (!resultEl.classList.contains("error") && resultEl.dataset.ready !== "1") {
    resultEl.textContent = "…";
    resultEl.classList.add("loading");
  }
  return preferredPanelHeight();
}

function setLoading(pinyin) {
  pinyinEl.textContent = pinyin;
  resultEl.textContent = "…";
  resultEl.dataset.ready = "0";
  resultEl.classList.add("loading");
  resultEl.classList.remove("error");
  return preferredPanelHeight();
}

function updatePanel(pinyin, result) {
  pinyinEl.textContent = pinyin;

  const isError =
    result.startsWith("请求失败") ||
    result.startsWith("请配置");

  resultEl.textContent = result;
  resultEl.dataset.ready = "1";
  resultEl.classList.remove("loading");
  resultEl.classList.toggle("error", isError);
  return preferredPanelHeight();
}

function resetPanel() {
  pinyinEl.textContent = "—";
  resultEl.textContent = "…";
  resultEl.dataset.ready = "0";
  resultEl.classList.remove("loading", "error");
  return preferredPanelHeight();
}

window.showComposing = showComposing;
window.setLoading = setLoading;
window.updatePanel = updatePanel;
window.resetPanel = resetPanel;
