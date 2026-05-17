import os
import re
import sys
from pathlib import Path
from collections import Counter
from math import sqrt

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

API_TOKEN = "КЛЮЧ_ГРОК_АПИ"
BASE_API_URL = "https://api.groq.com/openai/v1"
SIMILAR_LIMIT = 0.15
VECTOR_SIZE = 4096


COMMON_WORDS = {
    "и", "в", "на", "с", "по", "из", "у", "под", "для", "как",
    "или", "но", "не", "это", "that", "with", "from", "this",
    "the", "a", "an", "of", "in", "to", "is", "are"
}


client = OpenAI(
    api_key=API_TOKEN,
    base_url=BASE_API_URL
)


class MarkdownKnowledgeBase:
    def __init__(self, root_folder: str):
        self.root = Path(root_folder)
        self.notes = []

    def scan_notes(self):
        if not self.root.exists():
            raise FileNotFoundError(f"директория не существует: {self.root}")

        markdown_files = list(self.root.rglob("*.md"))

        for file_path in markdown_files:
            try:
                text = file_path.read_text(encoding="utf-8")
                self.notes.append({
                    "title": file_path.stem,
                    "filepath": file_path,
                    "body": text
                })
            except Exception as err:
                print(f"ошибка чтения {file_path.name}: {err}")

    @staticmethod
    def tokenize(text: str):
        return re.findall(r"[a-zA-Zа-яА-Я0-9]+", text.lower())

    def build_vector(self, text: str):
        vector = [0.0] * VECTOR_SIZE
        words = self.tokenize(text)
        frequencies = Counter(words)

        for word, amount in frequencies.items():
            if word in COMMON_WORDS or len(word) < 2:
                continue

            idx = abs(hash(word)) % VECTOR_SIZE
            vector[idx] += float(amount)

        return vector

    @staticmethod
    def similarity_score(vec_a, vec_b):
        numerator = sum(x * y for x, y in zip(vec_a, vec_b))

        left = sqrt(sum(x * x for x in vec_a))
        right = sqrt(sum(y * y for y in vec_b))

        if left == 0 or right == 0:
            return 0.0

        return numerator / (left * right)

    def process_embeddings(self):
        print("обработка markdown-заметок...")

        for note in self.notes:
            note["vector"] = self.build_vector(note["body"])
            print(f"готово: {note['title']}")

    def detect_connections(self):
        results = []

        for current_index, current_note in enumerate(self.notes):
            for next_note in self.notes[current_index + 1:]:
                score = self.similarity_score(
                    current_note["vector"],
                    next_note["vector"]
                )

                if score >= SIMILAR_LIMIT:
                    results.append({
                        "left": current_note,
                        "right": next_note,
                        "score": score
                    })

        return sorted(results, key=lambda item: item["score"], reverse=True)


class SummaryGenerator:
    MODEL_NAME = "llama-3.3-70b-versatile"

    @staticmethod
    def ask_llm(note_text: str):
        shortened = note_text[:3500]

        request_text = f"""
Создай короткое описание markdown-заметки.

Требования:
- максимум 1 предложение
- без кавычек
- не больше 100 символов

Текст:
{shortened}
"""

        answer = client.chat.completions.create(
            model=SummaryGenerator.MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": request_text
                }
            ],
            temperature=0.4,
            max_tokens=70
        )

        return answer.choices[0].message.content.strip()

    @staticmethod
    def inject_summary(note_path: Path, summary_text: str):
        source = note_path.read_text(encoding="utf-8")

        if source.startswith("---"):
            boundary = source.find("---", 3)

            if boundary != -1:
                metadata = source[3:boundary]
                content = source[boundary + 3:]

                if "summary:" in metadata:
                    return

                metadata += f'\nsummary: "{summary_text}"\n'
                updated = f"---{metadata}---{content}"
                note_path.write_text(updated, encoding="utf-8")
                return

        rebuilt = (
            f"---\nsummary: \"{summary_text}\"\n---\n\n{source}"
        )

        note_path.write_text(rebuilt, encoding="utf-8")


def print_connections(connection_list):
    print("\nсовпадения между заметками:\n")

    if not connection_list:
        print("ничего похожего не найдено")
        return

    for item in connection_list[:20]:
        left_name = item["left"]["title"]
        right_name = item["right"]["title"]
        percent = round(item["score"] * 100, 1)

        print(f"[{percent}%] {left_name} ↔ {right_name}")


def generate_frontmatter(notes_collection):
    user_choice = input(
        "\nдобавить llm-summary во все markdown-файлы? (y/n): "
    ).strip().lower()

    if user_choice != "y":
        return

    for note in notes_collection:
        try:
            summary = SummaryGenerator.ask_llm(note["body"])
            SummaryGenerator.inject_summary(note["filepath"], summary)
            print(f"summary обновлен: {note['title']}")
        except Exception as err:
            print(f"ошибка при обработке {note['title']}: {err}")


def run():
    if len(sys.argv) < 2:
        print("пример запуска: python main.py ./notes")
        sys.exit(1)

    target_folder = sys.argv[1]

    storage = MarkdownKnowledgeBase(target_folder)
    storage.scan_notes()

    print(f"найдено markdown-файлов: {len(storage.notes)}")

    if len(storage.notes) < 2:
        print("для анализа нужно минимум две заметки")
        return

    storage.process_embeddings()

    matches = storage.detect_connections()

    print_connections(matches)

    generate_frontmatter(storage.notes)

    print("\nработа завершена")


if __name__ == "__main__":
    run()


