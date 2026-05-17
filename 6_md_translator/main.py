import re
import sys
from pathlib import Path

from openai import OpenAI


API_KEY = "КЛЮЧ_ГРОК_АПИ"

MODEL_NAME = "llama-3.3-70b-versatile"
BASE_URL = "https://api.groq.com/openai/v1"


client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)


AVAILABLE_LANGUAGES = {
    "en": "English",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "es": "Spanish"
}


class MarkdownParser:
    @staticmethod
    def extract_blocks(text: str):
        blocks = []

        patterns = [
            (r"^---\n.*?\n---\n", re.DOTALL | re.MULTILINE),
            (r"```[\s\S]*?```", 0),
            (r"<[a-zA-Z][^>]*>[\s\S]*?</[a-zA-Z]+>", 0)
        ]

        protected = []

        for pattern, flags in patterns:
            for match in re.finditer(pattern, text, flags):
                protected.append(
                    (match.start(), match.end())
                )

        protected.sort()

        merged = []

        for start, end in protected:
            if merged and start < merged[-1][1]:
                continue

            merged.append((start, end))

        current = 0

        for start, end in merged:
            if start > current:
                blocks.append({
                    "mode": "translate",
                    "text": text[current:start]
                })

            blocks.append({
                "mode": "keep",
                "text": text[start:end]
            })

            current = end

        if current < len(text):
            blocks.append({
                "mode": "translate",
                "text": text[current:]
            })

        return blocks


class TranslationCleaner:
    @staticmethod
    def clean(text: str):
        result = text.strip()

        if result.startswith("```"):
            lines = result.splitlines()
            result = "\n".join(lines[1:-1])

        forbidden = (
            "translation:",
            "перевод:",
            "translated text:",
            "вот перевод:",
            "here is the translation"
        )

        rows = result.splitlines()

        while rows and rows[0].strip().lower().startswith(forbidden):
            rows.pop(0)

        return "\n".join(rows).strip()

    @staticmethod
    def restore_spacing(original: str, translated: str):
        if original.startswith("\n") and not translated.startswith("\n"):
            translated = "\n" + translated

        if original.endswith("\n") and not translated.endswith("\n"):
            translated += "\n"

        return translated


class MarkdownTranslator:
    def __init__(self, target_language: str):
        self.language = AVAILABLE_LANGUAGES[target_language]

    def build_prompt(self, fragment: str):
        return f"""
переведи markdown-фрагмент на язык {self.language}.

правила:
- верни только перевод
- не добавляй комментарии
- не трогай markdown-разметку
- не меняй ссылки и url
- не меняй inline-код в `
- не изменяй кодовые блоки

текст:
{fragment}
"""

    def translate(self, fragment: str):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": self.build_prompt(fragment)
                }
            ],
            temperature=0.1
        )

        translated = response.choices[0].message.content

        translated = TranslationCleaner.clean(translated)

        return TranslationCleaner.restore_spacing(
            fragment,
            translated
        )


class FileTranslator:
    def __init__(self, source: str, target: str, language: str):
        self.source = Path(source)
        self.target = Path(target)
        self.language = language

    def process(self):
        text = self.source.read_text(encoding="utf-8")

        parser = MarkdownParser()

        blocks = parser.extract_blocks(text)

        print(f"найдено блоков: {len(blocks)}")

        translator = MarkdownTranslator(self.language)

        result = []

        for index, block in enumerate(blocks):
            if block["mode"] == "keep":
                print(f"[{index + 1}] пропуск блока")

                result.append(block["text"])

                continue

            if not block["text"].strip():
                result.append(block["text"])
                continue

            print(f"[{index + 1}] перевод текста")

            try:
                translated = translator.translate(
                    block["text"]
                )

                result.append(translated)

            except Exception as error:
                print(f"ошибка: {error}")

                result.append(block["text"])

        final_text = "".join(result)

        self.target.write_text(
            final_text,
            encoding="utf-8"
        )

        print(f"\nсохранено: {self.target}")


def main():
    if len(sys.argv) < 4:
        print("использование:")
        print("python main.py input.md output.md язык")
        sys.exit(1)

    source_file = sys.argv[1]
    output_file = sys.argv[2]
    language = sys.argv[3]

    if language not in AVAILABLE_LANGUAGES:
        print("язык не поддерживается")
        print(
            f"доступные языки: {', '.join(AVAILABLE_LANGUAGES.keys())}"
        )

        sys.exit(1)

    if not Path(source_file).exists():
        print("файл не найден")
        sys.exit(1)

    app = FileTranslator(
        source_file,
        output_file,
        language
    )

    app.process()


if __name__ == "__main__":
    main()