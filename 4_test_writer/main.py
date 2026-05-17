import ast
import subprocess
import sys
from pathlib import Path

from openai import OpenAI


API_KEY = "КЛЮЧ_ГРОК_АПИ"
MODEL_ID = "llama-3.3-70b-versatile"
API_ENDPOINT = "https://api.groq.com/openai/v1"


ai = OpenAI(
    api_key=API_KEY,
    base_url=API_ENDPOINT
)


class PythonFileInspector:
    def __init__(self, filename: str):
        self.filepath = Path(filename)
        self.source_code = self.filepath.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source_code)

    def collect_functions(self):
        result = []

        for item in self.tree.body:
            if isinstance(item, ast.FunctionDef):
                result.append({
                    "function_name": item.name,
                    "parameters": [arg.arg for arg in item.args.args],
                    "code": ast.get_source_segment(self.source_code, item)
                })

        return result


class PytestGenerator:
    def __init__(self, module_name: str):
        self.module_name = module_name

    def build_prompt(self, functions_data: list):
        prepared_code = "\n\n".join(
            function["code"] for function in functions_data
        )

        return f"""
ты пишешь unit-тесты на pytest. cгенерируй тесты для функций ниже.

требования:
- импортируй функции из модуля: {self.module_name}
- покрой happy path, edge cases (пустые значения, None, ноль, отрицательные числа)
- покрой обработку ошибок (если функция должна выбрасывать исключения)
- каждый тест - отдельная функция test_*
- используй параметризацию pytest.mark.parametrize где уместно
- не пиши пояснения, только код
- не оборачивай код в markdown (никаких ```python)

функции:
{prepared_code}

тесты:
"""

    def generate(self, functions_data: list):
        response = ai.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": self.build_prompt(functions_data)
                }
            ],
            temperature=0.25,
            max_tokens=1800
        )

        generated = response.choices[0].message.content.strip()

        if generated.startswith("```"):
            generated = "\n".join(generated.splitlines()[1:-1])

        return generated


class TestValidator:
    @staticmethod
    def validate_python_syntax(filepath: Path):
        try:
            ast.parse(filepath.read_text(encoding="utf-8"))
            return True

        except SyntaxError as exc:
            print(f"ошибка синтаксиса: {exc}")
            return False

    @staticmethod
    def validate_pytest_collection(filepath: Path):
        try:
            execution = subprocess.run(
                ["pytest", "--collect-only", str(filepath)],
                capture_output=True,
                text=True,
                timeout=20
            )

            return execution.returncode == 0

        except Exception as exc:
            print(f"ошибка проверки pytest: {exc}")
            return False


class Application:
    def __init__(self, source_path: str):
        self.source_path = source_path
        self.module_name = Path(source_path).stem

    def start(self):
        print(f"обрабатываю файл: {self.source_path}")

        parser = PythonFileInspector(self.source_path)
        functions = parser.collect_functions()

        if len(functions) == 0:
            print("функции не найдены")
            return

        print(f"найдено функций: {len(functions)}")

        for function in functions:
            args = ", ".join(function["parameters"])
            print(f" - {function['function_name']}({args})")

        generator = PytestGenerator(self.module_name)
        generated_tests = generator.generate(functions)

        target_file = Path(f"test_{self.module_name}.py")
        target_file.write_text(generated_tests, encoding="utf-8")

        print(f"тесты сохранены: {target_file.name}")

        syntax_ok = TestValidator.validate_python_syntax(target_file)

        if syntax_ok:
            print("синтаксис корректный")

        collected = TestValidator.validate_pytest_collection(target_file)

        if collected:
            print("pytest успешно собрал тесты")
        else:
            print("pytest не смог собрать тесты")


def main():
    if len(sys.argv) < 2:
        print("использование: python main.py file.py")
        sys.exit(1)

    source = sys.argv[1]

    if not Path(source).exists():
        print("файл не существует")
        sys.exit(1)

    app = Application(source)
    app.start()


if __name__ == "__main__":
    main()