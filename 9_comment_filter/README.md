# AI Comment Moderation

Веб-приложение для проверки комментариев через LLM.

## Установка зависимостей

```bash
pip install fastapi uvicorn openai

uvicorn main:app --reload

http://127.0.0.1:8000