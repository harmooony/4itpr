import subprocess

from openai import OpenAI



GROQ_API_KEY = "КЛЮЧ_ГРОК_АПИ"



client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)



def get_git_diff():
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        return result.stdout

    except Exception as e:
        print("Ошибка получения git diff:")
        print(e)

        return None



def generate_commit_message(diff):
    if not diff or not diff.strip():
        return "Нет staged changes."

    shortened_diff = diff[:12000]

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",

            messages=[
                {
                    "role": "system",
                    "content": """
Ты генерируешь git commit messages.

Используй Conventional Commits.

Примеры:
- feat(auth): add jwt login
- fix(api): handle null response
- refactor(db): simplify queries

Правила:
- одна строка
- коротко
- понятно
- без объяснений
""",
                },
                {
                    "role": "user",
                    "content": f"""
Git diff:

{shortened_diff}
""",
                },
            ],

            temperature=0.2,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Ошибка AI:\n{e}"



def main():
    print("Reading staged git diff...\n")

    diff = get_git_diff()

    commit_message = generate_commit_message(diff)

    print("Generated commit message:\n")
    print(commit_message)

    answer = input("\nCommit changes? (y/n): ")

    if answer.lower() == "y":
        subprocess.run(
            ["git", "commit", "-m", commit_message]
        )

        print("\n✅ Commit created.")


if __name__ == "__main__":
    main()