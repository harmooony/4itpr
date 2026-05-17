import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel


API_KEY = "КЛЮЧ_ГРОК_АПИ"

DATABASE_FILE = "comments.db"

MODEL_NAME = "llama-3.3-70b-versatile"

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


LABELS = [
    "ok",
    "spam",
    "toxic",
    "needs_review"
]


class DatabaseManager:
    @staticmethod
    def create_tables():
        connection = sqlite3.connect(DATABASE_FILE)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS comments_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                label TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            )
        """)

        connection.commit()
        connection.close()

    @staticmethod
    def save_result(text: str, label: str, reason: str):
        connection = sqlite3.connect(DATABASE_FILE)

        connection.execute(
            """
            INSERT INTO comments_history (text, label, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                text,
                label,
                reason,
                datetime.now().isoformat()
            )
        )

        connection.commit()
        connection.close()

    @staticmethod
    def get_last_records(limit: int):
        connection = sqlite3.connect(DATABASE_FILE)

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT * FROM comments_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        connection.close()

        return [dict(item) for item in rows]


class AiModerator:
    @staticmethod
    def moderate(text: str):
        prompt = f"""
ты проверяешь комментарии пользователей.

варианты меток:
- ok
- spam
- toxic
- needs_review

верни json-ответ:
{{"label": "...", "reason": "..."}}

комментарий:
{text}
"""

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            response_format={
                "type": "json_object"
            }
        )

        result = json.loads(
            response.choices[0].message.content
        )

        if result.get("label") not in LABELS:
            return {
                "label": "needs_review",
                "reason": "неизвестная категория"
            }

        return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    DatabaseManager.create_tables()
    yield


app = FastAPI(
    title="comment_moderator",
    lifespan=lifespan
)


class CommentData(BaseModel):
    text: str


class ModerationResult(BaseModel):
    label: str
    reason: str


@app.post(
    "/check",
    response_model=ModerationResult
)
def check_comment(data: CommentData):
    if not data.text.strip():
        raise HTTPException(
            status_code=400,
            detail="пустой комментарий"
        )

    if len(data.text) > 5000:
        raise HTTPException(
            status_code=400,
            detail="слишком большой текст"
        )

    try:
        result = AiModerator.moderate(data.text)

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"ошибка модели: {error}"
        )

    DatabaseManager.save_result(
        data.text,
        result["label"],
        result["reason"]
    )

    return ModerationResult(
        label=result["label"],
        reason=result["reason"]
    )


@app.get("/logs")
def logs(limit: int = 20):
    return DatabaseManager.get_last_records(limit)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>moderation service</title>

    <style>
        body {
            font-family: Arial;
            max-width: 750px;
            margin: 40px auto;
            padding: 20px;
        }

        textarea {
            width: 100%;
            height: 120px;
            padding: 10px;
            font-size: 14px;
        }

        button {
            margin-top: 10px;
            padding: 10px 18px;
            cursor: pointer;
        }

        .result {
            margin-top: 20px;
            padding: 12px;
            border-radius: 8px;
        }

        .ok {
            background: #d4edda;
        }

        .spam {
            background: #fff3cd;
        }

        .toxic {
            background: #f8d7da;
        }

        .needs_review {
            background: #e2e3e5;
        }

        .history {
            margin-top: 30px;
        }

        .item {
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }
    </style>
</head>

<body>

<h1>comment moderation</h1>

<textarea id="text"></textarea>

<br>

<button onclick="sendComment()">
    Проверить
</button>

<button onclick="loadLogs()">
    История
</button>

<div id="result"></div>

<div id="history" class="history"></div>

<script>
    async function sendComment() {
        const text = document.getElementById("text").value;

        const response = await fetch("/check", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({text})
        });

        const data = await response.json();

        const block = document.getElementById("result");

        if (data.label) {
            block.className = "result " + data.label;

            block.innerHTML =
                "<b>" +
                data.label +
                "</b><br>" +
                data.reason;
        }

        else {
            block.innerHTML =
                JSON.stringify(data);
        }
    }

    async function loadLogs() {
        const response =
            await fetch("/logs");

        const data =
            await response.json();

        const block =
            document.getElementById("history");

        block.innerHTML =
            "<h3>последние проверки</h3>" +
            data.map(item =>
                `
                <div class="item ${item.label}">
                    <b>${item.label}</b><br>
                    ${item.text}<br>
                    <i>${item.reason}</i>
                </div>
                `
            ).join("");
    }
</script>

</body>
</html>
"""