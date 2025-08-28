#!/usr/bin/env python3
"""
HD현대 합병 아비트리지 모니터링 봇

HD현대중공업과 HD현대미포 간의 합병 아비트리지 기회를 모니터링하고 
텔레그램으로 알림을 보내는 스크립트입니다.
"""

import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime

import requests
from bs4 import BeautifulSoup

try:
    import yfinance as yf
except ImportError:
    yf = None

# --- 설정 ---
TICKER_HEAVY = "329180.KS"   # HD현대중공업
TICKER_MIPO  = "010620.KS"   # HD현대미포
MERGE_RATIO  = 0.4059146     # 미포 1주 -> 중공업 0.4059146주 (공시/리포트 기준)

# 네이버 금융 코드(백업용 스크랩): 329180, 010620
NAVER_CODES = {"329180.KS": "329180", "010620.KS": "010620"}

# 알림 임계값 (절댓값 기준)
ALERT_THRESHOLD_PCT = 2.0  # 2% 이상 차이날 때 알림

MAX_TELEGRAM_LEN = 4000  # 4096 is limit; keep some buffer for Markdown issues


def _telegram_post(text, telegram_token, telegram_chat_id):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": telegram_chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "Markdown"  # 마크다운 지원
    })
    if resp.status_code != 200:
        print("❌ 텔레그램 전송 실패:", resp.status_code, resp.text)
        return False
    else:
        print("✅ 텔레그램 전송 성공 (message length =", len(text), ")")
        return True


def send_to_telegram(message: str, telegram_token: str, telegram_chat_id: str):
    """
    Send a potentially long message to Telegram by splitting it into
    chunks that respect the 4096‑character limit (we use 4000 for safety).
    """
    if len(message) <= MAX_TELEGRAM_LEN:
        return _telegram_post(message, telegram_token, telegram_chat_id)

    print("ℹ️ 메시지가 길어 여러 개로 분할 전송합니다. 총 길이:", len(message))
    lines = message.split('\n')
    chunk = ""
    all_success = True
    
    for line in lines:
        # +1 for newline that will be re-added
        if len(chunk) + len(line) + 1 > MAX_TELEGRAM_LEN:
            success = _telegram_post(chunk, telegram_token, telegram_chat_id)
            all_success = all_success and success
            chunk = ""
            time.sleep(1)  # Rate limiting
        chunk += line + "\n"
    
    if chunk:
        success = _telegram_post(chunk, telegram_token, telegram_chat_id)
        all_success = all_success and success
    
    return all_success


# --- 가격 가져오기 ---
def get_price_yf(ticker: str) -> Optional[float]:
    """Yahoo Finance에서 주가 가져오기"""
    if yf is None:
        return None
    try:
        data = yf.Ticker(ticker).fast_info
        price = float(data["last_price"])
        return price if price > 0 else None
    except Exception:
        try:
            # fallback within yfinance
            hist = yf.download(ticker, period="1d", interval="1m", progress=False)
            if not hist.empty:
                return float(hist["Close"][-1])
        except Exception:
            pass
    return None


def get_price_naver(ticker: str) -> Optional[float]:
    """간단 백업: 네이버 금융 현재가 스크랩"""
    code = NAVER_CODES.get(ticker)
    if not code:
        return None
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers, timeout=5).text
        soup = BeautifulSoup(html, "html.parser")
        # 현재가 (js masking 있을 수 있어 백업 선택자 2개 시도)
        now = soup.select_one("p.no_today .blind")
        if now:
            # 쉼표 제거
            return float(now.text.replace(",", ""))
        # 대체 선택자
        alt = soup.select_one("#chart_area div.rate_info div.today span.blind")
        if alt:
            return float(alt.text.replace(",", ""))
    except Exception as e:
        print(f"네이버 금융 스크랩 실패 ({ticker}): {e}")
        return None
    return None


def get_price(ticker: str) -> Optional[float]:
    """주가 가져오기 (Yahoo Finance 우선, 네이버 금융 백업)"""
    p = get_price_yf(ticker)
    if p is None:
        p = get_price_naver(ticker)
    return p


# --- 계산 로직 ---
@dataclass
class Decision:
    heavy_price: float
    mipo_price: float
    ratio: float
    effective_heavy_via_mipo: float
    discount_pct: float
    parity_mipo_given_heavy: float
    better: str  # "MIPO" or "HEAVY" or "SAME"


def decide(heavy_price: float, mipo_price: float, ratio: float = MERGE_RATIO) -> Decision:
    """아비트리지 기회 계산"""
    # 미포 1주를 합병 후 중공업으로 환산한 가치
    effective_heavy_via_mipo = mipo_price / ratio
    # 어느 쪽이 더 싼지: (미포 경유 가격 - 직매수 가격) / 직매수 가격
    discount_pct = (effective_heavy_via_mipo - heavy_price) / heavy_price * 100.0
    # 중공업 현재가 대비 '이론상 미포 적정가' (패리티)
    parity_mipo = heavy_price * ratio

    if abs(discount_pct) < 1e-6:
        better = "SAME"
    elif discount_pct < 0:
        # effective 가격이 더 낮으면 미포가 유리(즉, 미포 경유가 할인)
        better = "MIPO"
    else:
        better = "HEAVY"

    return Decision(
        heavy_price=heavy_price,
        mipo_price=mipo_price,
        ratio=ratio,
        effective_heavy_via_mipo=effective_heavy_via_mipo,
        discount_pct=discount_pct,
        parity_mipo_given_heavy=parity_mipo,
        better=better,
    )


def format_arbitrage_message(decision: Decision, timestamp: str) -> str:
    """아비트리지 분석 결과를 텔레그램 메시지로 포맷"""
    
    # 기본 정보
    msg = f"🔍 *HD현대 합병 아비트리지 분석*\n"
    msg += f"📅 {timestamp}\n\n"
    
    msg += f"📊 *현재가*\n"
    msg += f"• HD현대중공업: `{decision.heavy_price:,.0f}원`\n"
    msg += f"• HD현대미포: `{decision.mipo_price:,.0f}원`\n"
    msg += f"• 합병비율: `{decision.ratio:.6f}`\n\n"
    
    msg += f"📈 *분석 결과*\n"
    msg += f"• 미포→중공업 환산가: `{decision.effective_heavy_via_mipo:,.0f}원`\n"
    msg += f"• 괴리율: `{decision.discount_pct:+.2f}%`\n"
    msg += f"• 미포 이론가(패리티): `{decision.parity_mipo_given_heavy:,.0f}원`\n\n"
    
    # 결론 및 추천
    if decision.better == "MIPO":
        msg += f"💡 *투자 전략*\n"
        msg += f"🟢 **미포 매수 → 합병 신주 수령**이 유리\n"
        msg += f"• 예상 수익: `{abs(decision.discount_pct):.2f}%`\n"
        if abs(decision.discount_pct) >= ALERT_THRESHOLD_PCT:
            msg += f"⚠️ **주목**: 괴리율이 {ALERT_THRESHOLD_PCT}% 이상입니다!"
    elif decision.better == "HEAVY":
        msg += f"💡 *투자 전략*\n"
        msg += f"🔵 **중공업 직접 매수**가 유리\n"
        msg += f"• 미포 대비 할인: `{abs(decision.discount_pct):.2f}%`\n"
        if abs(decision.discount_pct) >= ALERT_THRESHOLD_PCT:
            msg += f"⚠️ **주목**: 괴리율이 {ALERT_THRESHOLD_PCT}% 이상입니다!"
    else:
        msg += f"💡 *투자 전략*\n"
        msg += f"🟡 **두 선택이 거의 동일**합니다\n"
        msg += f"• 괴리율: `{abs(decision.discount_pct):.2f}%`\n"
    
    # 수수료 고려사항
    fee_bp = 15  # 왕복 0.15% 가정
    msg += f"\n📋 *참고사항*\n"
    if abs(decision.discount_pct) <= fee_bp * 2 / 100:
        msg += f"⚠️ 추정 수수료({fee_bp*2/100:.2f}%) 고려 시 실질 이득 미미\n"
    else:
        msg += f"✅ 추정 수수료({fee_bp*2/100:.2f}%) 고려해도 수익 가능성 있음\n"
    
    msg += f"• 실제 거래 시 슬리피지 및 수수료 추가 고려 필요\n"
    msg += f"• 합병 완료 시점까지의 시간 위험 존재\n"
    
    return msg


class HDArbitrageMonitor:
    """HD현대 합병 아비트리지 모니터링 클래스"""
    
    def __init__(self, telegram_token: str = None, telegram_chat_id: str = None):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
    
    def check_arbitrage(self) -> Optional[Decision]:
        """현재 아비트리지 기회 확인"""
        print("가격 정보 수집 중...")
        
        heavy_price = get_price(TICKER_HEAVY)
        mipo_price = get_price(TICKER_MIPO)
        
        if heavy_price is None or mipo_price is None:
            print(f"가격 조회 실패: heavy={heavy_price}, mipo={mipo_price}")
            return None
        
        print(f"가격 수집 완료: 중공업={heavy_price:,.0f}원, 미포={mipo_price:,.0f}원")
        
        decision = decide(heavy_price, mipo_price, MERGE_RATIO)
        return decision
    
    def should_send_alert(self, decision: Decision) -> bool:
        """알림을 보낼지 여부 결정"""
        return abs(decision.discount_pct) >= ALERT_THRESHOLD_PCT
    
    def send_notification(self, decision: Decision, is_alert: bool = False) -> bool:
        """텔레그램 알림 전송"""
        if not self.telegram_token or not self.telegram_chat_id:
            print("텔레그램 설정이 없어 메시지를 전송하지 않습니다.")
            return False
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = format_arbitrage_message(decision, timestamp)
        
        if is_alert:
            message = f"🚨 *아비트리지 기회 감지!* 🚨\n\n{message}"
        
        return send_to_telegram(message, self.telegram_token, self.telegram_chat_id)
    
    def run_check(self, send_always: bool = False) -> None:
        """아비트리지 체크 실행"""
        try:
            decision = self.check_arbitrage()
            if decision is None:
                error_msg = "❌ 가격 정보를 가져올 수 없습니다."
                print(error_msg)
                if self.telegram_token and self.telegram_chat_id:
                    send_to_telegram(error_msg, self.telegram_token, self.telegram_chat_id)
                return
            
            # 콘솔 출력
            print("\n[HD현대 합병 아비트리지 체크]")
            print(f"- HD현대중공업(HEAVY) 현재가: {decision.heavy_price:,.0f}원")
            print(f"- HD현대미포(MIPO)  현재가:  {decision.mipo_price:,.0f}원")
            print(f"- 합병비율(MIPO→HEAVY): {decision.ratio}")
            print(f"■ 미포 경유 중공업 1주 실질 매입가 = {decision.effective_heavy_via_mipo:,.0f}원")
            print(f"■ 직매수 대비 괴리율 = {decision.discount_pct:.2f}%")
            print(f"■ 중공업 기준 미포 패리티 = {decision.parity_mipo_given_heavy:,.0f}원")
            
            if decision.better == "MIPO":
                print("▶ 결론: **미포 매수 → 합병 신주 수령**이 더 유리합니다.")
            elif decision.better == "HEAVY":
                print("▶ 결론: **중공업 본주를 직접 매수**하는 게 더 유리합니다.")
            else:
                print("▶ 결론: **두 선택이 거의 동일**합니다.")
            
            # 알림 전송 여부 결정
            should_alert = self.should_send_alert(decision)
            
            if send_always or should_alert:
                success = self.send_notification(decision, is_alert=should_alert)
                if success:
                    if should_alert:
                        print(f"🚨 알림 전송 완료 (괴리율: {decision.discount_pct:.2f}%)")
                    else:
                        print("📱 정기 리포트 전송 완료")
                else:
                    print("❌ 텔레그램 전송 실패")
            else:
                print(f"ℹ️ 괴리율({abs(decision.discount_pct):.2f}%)이 임계값({ALERT_THRESHOLD_PCT}%) 미만이므로 알림 전송 안함")
                
        except Exception as e:
            error_msg = f"❌ 아비트리지 체크 중 오류 발생: {str(e)}"
            print(error_msg)
            if self.telegram_token and self.telegram_chat_id:
                send_to_telegram(error_msg, self.telegram_token, self.telegram_chat_id)


def main():
    """메인 함수"""
    # 환경 변수에서 텔레그램 설정 가져오기
    telegram_token = os.getenv("TG_TOKEN")
    telegram_chat_id = os.getenv("TG_CHAT_ID")
    
    if not telegram_token or not telegram_chat_id:
        print("경고: 텔레그램 설정이 없습니다. 콘솔에만 출력됩니다.")
        print("텔레그램 알림을 원하면 TG_TOKEN과 TG_CHAT_ID를 환경변수에 설정하세요.")
        print()
    
    # 아비트리지 모니터 초기화 및 실행
    monitor = HDArbitrageMonitor(
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id
    )
    
    # GitHub Actions에서 실행되는 경우 항상 보고서 전송
    # 로컬에서 실행되는 경우에는 임계값 초과시에만 알림
    send_always = os.getenv("GITHUB_ACTIONS") == "true"
    
    monitor.run_check(send_always=send_always)


if __name__ == "__main__":
    main()