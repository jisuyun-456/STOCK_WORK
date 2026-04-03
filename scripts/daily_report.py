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
from report_formatter import to_markdown, to_html, save_report


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
    commodities = fetch_commodities()

    print("  → 매크로 지표 수집 중...", file=sys.stderr)
    macro = fetch_macro()

    print("  → 섹터 등락 수집 중...", file=sys.stderr)
    sectors_daily = fetch_sector_performance()

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

    # 4. 컨텍스트 조립
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
    }

    return context


def send_email(html_content: str, report_date: str):
    """Gmail SMTP로 리포트 이메일 발송"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_user = os.environ.get("GMAIL_ADDRESS", "").strip()
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    to_email = os.environ.get("REPORT_EMAIL_TO", "").strip()

    if not all([smtp_user, smtp_pass, to_email]):
        print("  ⚠️ 이메일 설정 누락 (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, REPORT_EMAIL_TO)", file=sys.stderr)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 일일 투자 리포트 — {report_date}"
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"  ✅ 이메일 발송 완료 → {to_email}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  ❌ 이메일 발송 실패: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="일일 투자 리포트 생성")
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto")
    parser.add_argument("--format", choices=["all", "md", "html"], default="all")
    parser.add_argument("--send", action="store_true", help="이메일 발송")
    args = parser.parse_args()

    # 리포트 데이터 생성
    context = generate_report(mode=args.mode)

    # Markdown 상세본
    if args.format in ("all", "md"):
        md_content = to_markdown(context)
        filepath = save_report(md_content, context["report_date"])
        print(f"  ✅ Markdown 저장: {filepath}", file=sys.stderr)

    # HTML 이메일본
    html_content = None
    if args.format in ("all", "html"):
        html_content = to_html(context)
        if not args.send:
            print(html_content)
        print(f"  ✅ HTML 생성 완료", file=sys.stderr)

    # 이메일 발송
    if args.send and html_content:
        send_email(html_content, context["report_date"])

    print(f"\n[완료] 리포트 생성 성공 — {context['report_date']}", file=sys.stderr)


if __name__ == "__main__":
    main()
