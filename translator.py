import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

CACHE_PATH = Path(__file__).parent / ".cache" / "translations.json"
SELECTION_CACHE_PREFIX = "sel:"
MAX_SELECTION_CHARS = 500

PROMPT = """You are an English learning assistant. The user is typing Chinese using a Pinyin input method. The current Pinyin string is: {pinyin}

Step 1: Reconstruct the most likely Chinese text from the Pinyin.
Step 2: Determine whether it is a single word, a phrase, or a full sentence — then translate accordingly:
  - Single word → give the best English word (e.g. "apple")
  - Phrase → give a natural English phrase (e.g. "improve English proficiency")
  - Full sentence → give a natural, complete English sentence (e.g. "The weather is really nice today.")
Step 3: If the English can be expressed more naturally or correctly, use the better version.

Return exactly one line in this format: English translation（中文原文）
Examples:
  apple（苹果）
  significantly improve English proficiency（英语能力巨大提升）
  The weather is really nice today.（今天天气真好）

Rules:
- Match the granularity: word→word, phrase→phrase, sentence→sentence.
- The Chinese part is the reconstructed original for reference only.
- Output only this one line. No explanations, no extra punctuation."""

SELECTION_PROMPT = """You are an English learning assistant. The user selected this text:

{text}

Help them learn English:
- If the text is primarily Chinese (or mixed with Chinese), translate it into natural English.
- If the text is already English, keep a natural English phrasing (lightly polish if needed) and still show the Chinese meaning.
- Match granularity: word→word, phrase→phrase, sentence→sentence.

Return exactly one line in this format: English（中文）
Examples:
  apple（苹果）
  significantly improve English proficiency（显著提升英语能力）
  The weather is really nice today.（今天天气真好）

Output only this one line. No explanations."""


class Translator:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self._cache: dict[str, str] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if CACHE_PATH.exists():
            try:
                raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
                self._cache = {k: v for k, v in raw.items() if v}
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self) -> None:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def translate(self, pinyin: str) -> str:
        return self._translate_cached(
            cache_key=pinyin,
            prompt=PROMPT.format(pinyin=pinyin),
            max_tokens=64,
        )

    def translate_selection(self, text: str) -> str:
        text = " ".join(text.split())
        if not text:
            return "未读到选中文案"
        if len(text) > MAX_SELECTION_CHARS:
            text = text[:MAX_SELECTION_CHARS].rstrip() + "…"
        return self._translate_cached(
            cache_key=f"{SELECTION_CACHE_PREFIX}{text}",
            prompt=SELECTION_PROMPT.format(text=text),
            max_tokens=120,
        )

    def _translate_cached(self, *, cache_key: str, prompt: str, max_tokens: int) -> str:
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        if not self.api_key:
            return "请配置 DEEPSEEK_API_KEY"

        try:
            result = self._call_api(prompt, max_tokens=max_tokens)
        except Exception as exc:
            return f"请求失败：{exc}"

        if not result:
            return "翻译为空，请重试"

        self._cache[cache_key] = result
        self._save_cache()
        return result

    def _call_api(self, prompt: str, *, max_tokens: int) -> str:
        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = (data["choices"][0]["message"].get("content") or "").strip()
        return content.split("\n")[0].strip()
