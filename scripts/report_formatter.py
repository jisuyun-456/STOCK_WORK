"""
리포트 포맷터 — Jinja2 기반 Markdown/HTML 렌더링 + 파일 저장
"""
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# 프로젝트 루트 기준 templates 경로
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
REPORTS_DIR = PROJECT_ROOT / "docs" / "reports"
SIMULATION_DIR = PROJECT_ROOT / "docs" / "simulation"


def _get_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def to_markdown(data: dict) -> str:
    """Jinja2 → Markdown (daily_report.md.j2)"""
    env = _get_env()
    template = env.get_template("daily_report.md.j2")
    return template.render(**data)


def to_html(data: dict) -> str:
    """Jinja2 → HTML (email_template.html)"""
    env = _get_env()
    template = env.get_template("email_template.html")
    return template.render(**data)


def save_report(content: str, date: str) -> str:
    """docs/reports/YYYY-MM-DD-daily.md 저장"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = REPORTS_DIR / f"{date}-daily.md"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def to_simulation_md(data: dict) -> str:
    """Jinja2 → 시뮬레이션 상세 Markdown (simulation_section.md.j2)"""
    env = _get_env()
    template = env.get_template("simulation_section.md.j2")
    return template.render(**data)


def save_simulation_report(content: str, date: str) -> str:
    """docs/simulation/YYYY-MM-DD-simulation.md 저장"""
    SIMULATION_DIR.mkdir(parents=True, exist_ok=True)
    filepath = SIMULATION_DIR / f"{date}-simulation.md"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)
