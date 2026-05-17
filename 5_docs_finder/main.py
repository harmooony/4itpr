import sys
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from openai import OpenAI
from pypdf import PdfReader


API_KEY = "КЛЮЧ_ГРОК_АПИ"

MODEL_NAME = "llama-3.3-70b-versatile"
API_URL = "https://api.groq.com/openai/v1"

DATABASE_NAME = "rag_storage"

PART_SIZE = 700
PART_OVERLAP = 120


client = OpenAI(
    api_key=API_KEY,
    base_url=API_URL
)

vector_db = chromadb.PersistentClient(path="./vector_database")

embedding_model = SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


class FileReader:
    @staticmethod
    def load_text(path: Path):
        if path.suffix == ".md":
            return path.read_text(encoding="utf-8")

        if path.suffix == ".pdf":
            try:
                pdf = PdfReader(str(path))

                content = ""

                for page in pdf.pages:
                    content += page.extract_text() + "\n"

                return content

            except Exception as error:
                print(f"ошибка чтения pdf: {error}")
                return ""

        return ""


class ChunkSplitter:
    @staticmethod
    def split(text: str):
        result = []

        current = 0

        while current < len(text):
            next_position = current + PART_SIZE

            piece = text[current:next_position]

            if piece.strip():
                result.append(piece)

            current += PART_SIZE - PART_OVERLAP

        return result


class VectorIndexer:
    def __init__(self, folder: str):
        self.folder = Path(folder)

    def create_index(self):
        if not self.folder.exists():
            print("папка не найдена")
            return

        try:
            vector_db.delete_collection(DATABASE_NAME)
        except Exception:
            pass

        collection = vector_db.create_collection(
            name=DATABASE_NAME,
            embedding_function=embedding_model
        )

        documents = list(self.folder.rglob("*.md"))
        documents += list(self.folder.rglob("*.pdf"))

        print(f"найдено файлов: {len(documents)}")

        texts = []
        metadata = []
        identifiers = []

        for document in documents:
            print(f"обрабатываю: {document.name}")

            content = FileReader.load_text(document)

            if not content:
                continue

            chunks = ChunkSplitter.split(content)

            for index, chunk in enumerate(chunks):
                texts.append(chunk)

                metadata.append({
                    "file": str(document),
                    "part": index
                })

                identifiers.append(
                    f"{document.stem}_{index}"
                )

        if len(texts) == 0:
            print("не найден текст для индексации")
            return

        step = 100

        for position in range(0, len(texts), step):
            collection.add(
                documents=texts[position:position + step],
                metadatas=metadata[position:position + step],
                ids=identifiers[position:position + step]
            )

        print(f"добавлено чанков: {len(texts)}")


class RagAssistant:
    @staticmethod
    def ask(question: str, limit: int = 4):
        try:
            collection = vector_db.get_collection(
                name=DATABASE_NAME,
                embedding_function=embedding_model
            )

        except Exception:
            print("база не найдена, сначала выполните index")
            return

        search_result = collection.query(
            query_texts=[question],
            n_results=limit
        )

        documents = search_result["documents"][0]
        metadata = search_result["metadatas"][0]

        if len(documents) == 0:
            print("ничего не найдено")
            return

        context = []
        used_files = []

        for text, meta in zip(documents, metadata):
            filename = Path(meta["file"]).name

            context.append(
                f"[файл: {filename}]\n{text}"
            )

            if filename not in used_files:
                used_files.append(filename)

        final_context = "\n\n---\n\n".join(context)

        prompt = f"""
ответь на вопрос пользователя только по информации из контекста.

если ответа нет - так и напиши.
не придумывай информацию.

контекст:
{final_context}

вопрос:
{question}

ответ:
"""

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        print("\nответ:\n")
        print(response.choices[0].message.content)

        print("\nисточники:")

        for file in used_files:
            print(f"- {file}")


def main():
    if len(sys.argv) < 2:
        print("команды:")
        print("python main.py index <папка>")
        print("python main.py ask \"вопрос\"")
        sys.exit(1)

    command = sys.argv[1]

    if command == "index":
        if len(sys.argv) < 3:
            print("укажи папку")
            sys.exit(1)

        VectorIndexer(sys.argv[2]).create_index()

    elif command == "ask":
        if len(sys.argv) < 3:
            print("укажи вопрос")
            sys.exit(1)

        RagAssistant.ask(sys.argv[2])

    else:
        print("неизвестная команда")


if __name__ == "__main__":
    main()