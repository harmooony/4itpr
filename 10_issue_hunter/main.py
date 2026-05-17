import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from openai import OpenAI


API_KEY = "КЛЮЧ_ГРОК_АПИ"

GITHUB_TOKEN = "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"

MODEL_NAME = "llama-3.3-70b-versatile"

GITHUB_URL = "https://api.github.com"

CACHE_FOLDER = Path("github_cache")

CACHE_FOLDER.mkdir(exist_ok=True)

CACHE_LIFETIME = 6


client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


class CacheManager:
    @staticmethod
    def build_path(key: str):
        filename = hashlib.md5(
            key.encode()
        ).hexdigest()

        return CACHE_FOLDER / f"{filename}.json"

    @staticmethod
    def load(key: str):
        path = CacheManager.build_path(key)

        if not path.exists():
            return None

        age = (
            time.time() - path.stat().st_mtime
        ) / 3600

        if age > CACHE_LIFETIME:
            return None

        try:
            return json.loads(
                path.read_text(encoding="utf-8")
            )

        except Exception:
            return None

    @staticmethod
    def save(key: str, data):
        path = CacheManager.build_path(key)

        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8"
        )


class GithubApi:
    @staticmethod
    def headers():
        headers = {
            "Accept": "application/vnd.github+json"
        }

        if GITHUB_TOKEN:
            headers["Authorization"] = (
                f"Bearer {GITHUB_TOKEN}"
            )

        return headers

    @staticmethod
    def get_user_languages(username: str):
        cache_key = f"languages:{username}"

        cached = CacheManager.load(cache_key)

        if cached:
            print("языки загружены из кэша")

            return cached

        url = (
            f"{GITHUB_URL}/users/"
            f"{username}/repos"
        )

        response = requests.get(
            url,
            headers=GithubApi.headers(),
            params={
                "per_page": 30,
                "sort": "updated"
            },
            timeout=15
        )

        if response.status_code == 404:
            print("пользователь не найден")

            return []

        response.raise_for_status()

        repositories = response.json()

        if not repositories:
            print("репозитории отсутствуют")

            return []

        counter = Counter()

        for repository in repositories:
            language = repository.get("language")

            if language:
                counter[language] += 1

        top_languages = [
            item[0]
            for item in counter.most_common(5)
        ]

        CacheManager.save(
            cache_key,
            top_languages
        )

        return top_languages

    @staticmethod
    def search_issues(language: str, limit: int):
        cache_key = (
            f"issues:{language}:{limit}"
        )

        cached = CacheManager.load(cache_key)

        if cached:
            print(
                f"{language}: "
                f"{len(cached)} issues из кэша"
            )

            return cached

        query = (
            'is:issue is:open '
            'label:"good first issue" '
            f'language:{language}'
        )

        response = requests.get(
            f"{GITHUB_URL}/search/issues",
            headers=GithubApi.headers(),
            params={
                "q": query,
                "sort": "comments",
                "order": "desc",
                "per_page": limit
            },
            timeout=20
        )

        if response.status_code != 200:
            print(
                f"ошибка github api: "
                f"{response.status_code}"
            )

            return []

        items = response.json().get(
            "items",
            []
        )

        issues = []

        for item in items:
            repository_url = item.get(
                "repository_url",
                ""
            )

            repository_name = "/".join(
                repository_url.split("/")[-2:]
            )

            issues.append({
                "title": item["title"],
                "url": item["html_url"],
                "repo": repository_name,
                "comments": item.get(
                    "comments",
                    0
                ),
                "labels": [
                    label["name"]
                    for label in item.get(
                        "labels",
                        []
                    )
                ],
                "body": (
                    item.get("body") or ""
                )[:400]
            })

        CacheManager.save(
            cache_key,
            issues
        )

        return issues


class IssueRanker:
    @staticmethod
    def select_best(
        issues: list,
        languages: list,
        count: int = 10
    ):
        prepared = []

        for index, issue in enumerate(issues):
            prepared.append({
                "index": index,
                "repo": issue["repo"],
                "title": issue["title"],
                "labels": issue["labels"],
                "preview": issue["body"][:150]
            })

        prompt = f"""
ты помогаешь разработчику искать beginner-friendly задачи на github.

языки разработчика:
{", ".join(languages)}

выбери {count} самых подходящих задач.

верни json:
{{
  "selected": [
    {{
      "index": 0,
      "reason": "краткое объяснение"
    }}
  ]
}}

issues:
{json.dumps(prepared, ensure_ascii=False)}

верни только json.
"""

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            response_format={
                "type": "json_object"
            }
        )

        result = json.loads(
            response.choices[0].message.content
        )

        selected = result.get(
            "selected",
            []
        )

        final = []

        for item in selected:
            index = item.get("index")

            if (
                isinstance(index, int)
                and 0 <= index < len(issues)
            ):
                issue = issues[index].copy()

                issue["reason"] = item.get(
                    "reason",
                    ""
                )

                final.append(issue)

        return final[:count]


class Application:
    def __init__(self, username: str):
        self.username = username

    def start(self):
        if not GITHUB_TOKEN:
            print(
                "github token не указан, "
                "лимиты api будут ниже"
            )

        print(
            f"анализ github-профиля: "
            f"{self.username}"
        )

        languages = GithubApi.get_user_languages(
            self.username
        )

        if not languages:
            print(
                "не удалось получить языки"
            )

            return

        print(
            f"основные языки: "
            f"{', '.join(languages)}"
        )

        all_issues = []

        for language in languages[:3]:
            print(
                f"\nпоиск задач для "
                f"{language}"
            )

            found = GithubApi.search_issues(
                language,
                limit=15
            )

            all_issues.extend(found)

        if not all_issues:
            print("issues не найдены")

            return

        print(
            f"\nвсего найдено задач: "
            f"{len(all_issues)}"
        )

        print("выбираю лучшие варианты")

        top = IssueRanker.select_best(
            all_issues,
            languages,
            count=10
        )

        print("\n" + "=" * 60)

        print(
            f"лучшие задачи для "
            f"@{self.username}"
        )

        print("=" * 60)

        for number, issue in enumerate(top, 1):
            print(
                f"\n{number}. "
                f"{issue['title']}"
            )

            print(
                f"репозиторий: "
                f"{issue['repo']}"
            )

            print(
                f"комментарии: "
                f"{issue['comments']}"
            )

            print(
                f"ссылка: "
                f"{issue['url']}"
            )

            print(
                f"почему подходит: "
                f"{issue['reason']}"
            )


def main():
    if len(sys.argv) < 2:
        print(
            "использование:"
        )

        print(
            "python main.py github_username"
        )

        sys.exit(1)

    username = sys.argv[1]

    app = Application(username)

    app.start()


if __name__ == "__main__":
    main()