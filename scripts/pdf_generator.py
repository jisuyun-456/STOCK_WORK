"""
PDF 생성 모듈 — WeasyPrint + Jinja2
templates/pdf_report.html → A4 PDF
"""
import sys
import os
from pathlib import Path
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
DOCS_DIR = Path(__file__).parent.parent / "docs" / "reports"


def get_pdf_path(report_date: str) -> str:
    """docs/reports/YYYY-MM-DD-report.pdf"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    return str(DOCS_DIR / f"{report_date}-report.pdf")


def generate_pdf(context: dict, output_path: str) -> str:
    """
    context → templates/pdf_report.html 렌더링 → WeasyPrint → PDF 저장
    반환: 저장된 PDF 파일 경로 (실패 시 None)
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError as e:
        print(f"  [pdf_generator] ImportError: {e}", file=sys.stderr)
        return None

    try:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
        )
        # Jinja2 필터 추가
        env.filters["format"] = lambda v, fmt: (v % fmt) if fmt is not None else "N/A"

        template = env.get_template("pdf_report.html")
        html_content = template.render(**context)

        font_config = FontConfiguration()
        html_obj = HTML(string=html_content, base_url=str(TEMPLATES_DIR))
        html_obj.write_pdf(output_path, font_config=font_config)

        size_kb = os.path.getsize(output_path) / 1024
        print(f"  [pdf_generator] PDF 저장 완료: {output_path} ({size_kb:.0f}KB)", file=sys.stderr)
        return output_path

    except Exception as e:
        print(f"  [pdf_generator] PDF 생성 실패: {e}", file=sys.stderr)
        return None


def generate_html_preview(context: dict, output_path: str) -> str:
    """
    PDF 생성이 불가한 환경(Windows 로컬)에서 HTML 미리보기 저장
    반환: 저장된 HTML 파일 경로
    """
    try:
        from jinja2 import Environment, FileSystemLoader

        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
        )
        env.filters["format"] = lambda v, fmt: (v % fmt) if fmt is not None else "N/A"

        template = env.get_template("pdf_report.html")
        html_content = template.render(**context)

        Path(output_path).write_text(html_content, encoding="utf-8")
        print(f"  [pdf_generator] HTML 미리보기 저장: {output_path}", file=sys.stderr)
        return output_path

    except Exception as e:
        import traceback
        print(f"  [pdf_generator] HTML 미리보기 실패: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None
