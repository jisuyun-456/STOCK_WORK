"""
일일 투자 리포트 메인 오케스트레이터
CLI: python3 scripts/daily_report.py [--mode auto|manual]
"""
import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Windows cp949 인코딩 문제 방지
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# .env 로드 (dotenv 없이 직접 파싱)
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from data_fetcher import (
    fetch_us_indices,
    fetch_kr_indices,
    fetch_commodities,
    fetch_macro,
    fetch_sector_performance,
)
from market_screener import volume_surge, new_highs, sector_momentum
from macro_analyzer import current_cycle, favored_sectors, recommend_stocks
from report_formatter import to_markdown, to_html, save_report, to_simulation_md, save_simulation_report
from simulation_tracker import run_daily_update
from stock_analyzer import analyze_portfolio
from market_commentator import generate_market_commentary
from pdf_generator import generate_pdf, generate_html_preview, get_pdf_path
from dashboard_generator import generate_dashboard

SIMULATION_SYMBOLS = ["PLTR", "RKLB", "HIMS", "APLD", "IONQ"]


def generate_report(mode: str = "auto") -> dict:
    """전체 리포트 데이터 수집 + 분석"""
    now = datetime.now()
    report_date = now.strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%d %H:%M")

    print(f"[{generated_at}] 리포트 생성 시작 (mode={mode})", file=sys.stderr)

    # 1. 데이터 수집
    print("  → 미국 지수 수집 중...", file=sys.stderr)
    us_indices = fetch_us_indices()

    print("  → 한국 시장 수집 중...", file=sys.stderr)
    kr_indices = fetch_kr_indices()

    print("  → 원자재/금리 수집 중...", file=sys.stderr)
    commodities_raw = fetch_commodities()
    # fetch_commodities()에 change 키 없음 → 역산 추가
    commodities = {}
    for k, v in commodities_raw.items():
        if v.get("error"):
            commodities[k] = v
        else:
            pct = v["change_pct"]
            close = v["close"]
            change = round(close * (pct / 100) / (1 + pct / 100), 2)
            commodities[k] = {**v, "change": change}

    print("  → 매크로 지표 수집 중...", file=sys.stderr)
    macro_raw = fetch_macro()
    # fetch_macro()는 float 직접 반환 → {"value": float} dict로 정규화
    macro = {k: {"value": v} for k, v in macro_raw.items()} if macro_raw else {}

    print("  → 섹터 등락 수집 중...", file=sys.stderr)
    sectors_daily_raw = fetch_sector_performance()
    # fetch_sector_performance()는 {"Technology": 1.23} (float) 반환
    # market_commentator.py / pdf_report.html은 {"change_pct": float} dict 형식 기대
    # 정규화 + 내림차순 정렬 (daily_report.md.j2 dictsort 대체)
    sectors_daily = dict(sorted(
        {k: {"change_pct": float(v), "change": None} for k, v in sectors_daily_raw.items() if v is not None}.items(),
        key=lambda x: x[1]["change_pct"],
        reverse=True,
    ))

    # 2. 스크리닝
    print("  → 거래량 급등 스크리닝...", file=sys.stderr)
    vol_surge = volume_surge(top_n=10)

    print("  → 52주 신고가 스크리닝...", file=sys.stderr)
    highs = new_highs()

    print("  → 섹터 모멘텀 분석...", file=sys.stderr)
    sec_momentum = sector_momentum()

    # 3. 매크로 분석
    cycle = current_cycle(macro)
    cycle_info = favored_sectors(cycle)
    picks = recommend_stocks(cycle_info["sectors"], top_n=5)

    # 4. 시뮬레이션 포트폴리오 업데이트
    print("  → 시뮬레이션 포트폴리오 업데이트...", file=sys.stderr)
    sim_summary = run_daily_update()

    print("  → 종목 심층 분석 중...", file=sys.stderr)
    sim_stocks = analyze_portfolio(SIMULATION_SYMBOLS)

    # 5. 시황 코멘트 생성
    print("  → 시황 코멘트 생성 중...", file=sys.stderr)
    market_commentary = generate_market_commentary(
        us_indices=us_indices,
        kr_indices=kr_indices,
        commodities=commodities,
        sectors_daily=sectors_daily,
        macro=macro,
        volume_surge=vol_surge,
    )

    # 6. 컨텍스트 조립
    context = {
        "report_date": report_date,
        "generated_at": generated_at,
        "us_indices": us_indices,
        "kr_indices": kr_indices,
        "commodities": commodities,
        "macro": macro,
        "sectors_daily": sectors_daily,
        "volume_surge": vol_surge,
        "new_highs": highs,
        "sector_momentum": sec_momentum,
        "cycle_info": cycle_info,
        "recommended_stocks": picks,
        "sim_summary": sim_summary,
        "sim_stocks": sim_stocks,
        "market_commentary": market_commentary,
    }

    return context


def send_email(html_content: str, report_date: str, pdf_path: str = None):
    """Gmail SMTP로 리포트 이메일 발송 (PDF 첨부 옵션)"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    smtp_user = os.environ.get("GMAIL_ADDRESS", "").strip()
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    to_email = os.environ.get("REPORT_EMAIL_TO", "").strip()

    if not all([smtp_user, smtp_pass, to_email]):
        print("  [email] 설정 누락 (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, REPORT_EMAIL_TO)", file=sys.stderr)
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"[Daily Brief] {report_date} Investment Report"
    msg["From"] = smtp_user
    msg["To"] = to_email

    # HTML 본문 (1페이지 요약)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # PDF 첨부
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_part = MIMEApplication(f.read(), _subtype="pdf")
            filename = f"{report_date}-investment-report.pdf"
            pdf_part["Content-Disposition"] = f'attachment; filename="{filename}"'
            msg.attach(pdf_part)
        size_kb = os.path.getsize(pdf_path) / 1024
        print(f"  [email] PDF 첨부: {filename} ({size_kb:.0f}KB)", file=sys.stderr)
    else:
        print("  [email] PDF 없음 — 본문만 발송", file=sys.stderr)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"  [email] 발송 완료 → {to_email}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  [email] 발송 실패: {e}", file=sys.stderr)
        return False


def _render_email_summary(context: dict) -> str:
    """email_summary.html 렌더링 (1페이지 요약)"""
    try:
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        def _safe_fmt(v, fmt):
            try:
                return v % fmt
            except Exception:
                return "N/A"
        env.filters["format"] = _safe_fmt
        template = env.get_template("email_summary.html")
        return template.render(**context)
    except Exception as e:
        print(f"  [email_summary] 렌더링 실패: {e} — 기존 템플릿 사용", file=sys.stderr)
        return to_html(context)


def main():
    parser = argparse.ArgumentParser(description="일일 투자 리포트 생성")
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto")
    parser.add_argument("--format", choices=["all", "md", "html", "pdf"], default="all")
    parser.add_argument("--send", action="store_true", help="이메일 발송")
    args = parser.parse_args()

    # 리포트 데이터 생성
    context = generate_report(mode=args.mode)
    report_date = context["report_date"]

    # Markdown 상세본
    if args.format in ("all", "md"):
        md_content = to_markdown(context)
        filepath = save_report(md_content, report_date)
        print(f"  [md] Markdown 저장: {filepath}", file=sys.stderr)

    # 시뮬레이션 상세 리포트
    if args.format in ("all", "md") and context.get("sim_summary"):
        sim_md = to_simulation_md(context)
        sim_filepath = save_simulation_report(sim_md, report_date)
        print(f"  [md] 시뮬레이션 리포트 저장: {sim_filepath}", file=sys.stderr)

    # PDF 생성
    pdf_path = None
    if args.format in ("all", "pdf"):
        pdf_path = get_pdf_path(report_date)
        result = generate_pdf(context, pdf_path)
        if not result:
            # PDF 실패 시 HTML 미리보기 저장 (로컬 디버깅용)
            html_preview_path = pdf_path.replace(".pdf", "-preview.html")
            generate_html_preview(context, html_preview_path)
            pdf_path = None

    # 이메일 HTML 본문 (email_summary.html)
    html_content = None
    if args.format in ("all", "html", "pdf") or args.send:
        html_content = _render_email_summary(context)
        if not args.send and args.format in ("html",):
            print(html_content)
        print(f"  [html] 이메일 요약 생성 완료", file=sys.stderr)

    # 이메일 발송 (PDF 첨부)
    if args.send and html_content:
        send_email(html_content, report_date, pdf_path=pdf_path)

    # 트레이딩 대시보드 HTML 생성
    dashboard_path = Path(__file__).parent.parent / "docs" / "dashboard.html"
    generate_dashboard(context, str(dashboard_path))

    print(f"\n[완료] 리포트 생성 성공 — {report_date}", file=sys.stderr)


if __name__ == "__main__":
    main()
