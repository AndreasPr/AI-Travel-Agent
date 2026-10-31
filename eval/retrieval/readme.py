"""Update only the delimited retrieval summary from the recorded JSON."""
import json
from pathlib import Path

from eval.retrieval.report import render_report

ROOT = Path(__file__).resolve().parents[2]
START = "<!-- RETRIEVAL:START -->"
END = "<!-- RETRIEVAL:END -->"


def update_readme(readme: Path, results: Path) -> None:
    text = readme.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("README must contain exactly one pair of retrieval markers")
    before, remainder = text.split(START)
    _, after = remainder.split(END)
    report = render_report(json.loads(results.read_text(encoding="utf-8")))
    readme.write_text(before + START + "\n\n" + report + "\n" + END + after, encoding="utf-8")


if __name__ == "__main__":
    update_readme(ROOT / "README.md", ROOT / "eval/results/retrieval.json")
