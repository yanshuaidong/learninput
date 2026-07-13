const pinyinEl = document.getElementById("pinyin");
const resultEl = document.getElementById("result");

function showComposing(pinyin) {
  pinyinEl.textContent = pinyin;
  if (!resultEl.classList.contains("error") && resultEl.dataset.ready !== "1") {
    resultEl.textContent = "…";
    resultEl.classList.add("loading");
  }
}

function setLoading(pinyin) {
  pinyinEl.textContent = pinyin;
  resultEl.textContent = "…";
  resultEl.dataset.ready = "0";
  resultEl.classList.add("loading");
  resultEl.classList.remove("error");
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
}

function resetPanel() {
  pinyinEl.textContent = "—";
  resultEl.textContent = "…";
  resultEl.dataset.ready = "0";
  resultEl.classList.remove("loading", "error");
}

window.showComposing = showComposing;
window.setLoading = setLoading;
window.updatePanel = updatePanel;
window.resetPanel = resetPanel;
