import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

CACHE_PATH = Path(__file__).parent / ".cache" / "translations.json"
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
        cached = self._cache.get(pinyin)
        if cached:
            return cached

        if not self.api_key:
            return "请配置 DEEPSEEK_API_KEY"

        try:
            result = self._call_api(pinyin)
        except Exception as exc:
            return f"请求失败：{exc}"

        if not result:
            return "翻译为空，请重试"

        self._cache[pinyin] = result
        self._save_cache()
        return result

    def _call_api(self, pinyin: str) -> str:
        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "user", "content": PROMPT.format(pinyin=pinyin)},
            ],
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": 64,
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
