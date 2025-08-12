import requests
from bs4 import BeautifulSoup
import os

MAX_TELEGRAM_LEN = 4000  # 4096 is limit; keep some buffer for Markdown issues

TELEGRAM_TOKEN = os.environ["TG_TOKEN"]          # GitHub secret TG_TOKEN
TELEGRAM_CHAT_ID = os.environ["TG_CHAT_ID"]      # GitHub secret TG_CHAT_ID
CHAT_API_KEY = os.environ["CHAT_API_KEY"]  # GitHub secret CHAT_API_KEY
CHAT_MODEL = os.environ.get("CHAT_MODEL_FAST", "google/gemini-2.0-flash-001")  # GitHub secret CHAT_MODEL_FAST (optional)

def md_escape(text: str) -> str:
    return text  # No escaping needed for plain text

def _telegram_post(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    })
    if resp.status_code != 200:
        print("❌ 텔레그램 전송 실패:", resp.status_code, resp.text)
    else:
        print("✅ 텔레그램 전송 성공 (chunk length =", len(text), ")")

def send_to_telegram(message: str):
    """
    Send a potentially long message to Telegram by splitting it into
    chunks that respect the 4096‑character limit (we use 4000 for safety).
    """
    if len(message) <= MAX_TELEGRAM_LEN:
        _telegram_post(message)
        return

    print("ℹ️ 메시지가 길어 여러 개로 분할 전송합니다. 총 길이:", len(message))
    lines = message.split('\n')
    chunk = ""
    for line in lines:
        # +1 for newline that will be re-added
        if len(chunk) + len(line) + 1 > MAX_TELEGRAM_LEN:
            _telegram_post(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        _telegram_post(chunk)

def fetch_hn_titles():
    res = requests.get("https://news.ycombinator.com/")
    soup = BeautifulSoup(res.text, "html.parser")
    titles = []
    for a in soup.select(".athing"):
        title_tag = a.select_one(".titleline > a")
        if title_tag:
            title = title_tag.get_text()
            href = title_tag.get("href")
            titles.append((title, href))
    return titles

def translate_titles_with_openrouter(top5, rest):
    # Summarize and recommend 5 articles from the rest, with Korean translation and explanation, and also translate Top 5
    prompt = "다음은 Hacker News 상위 페이지의 기사 제목 목록입니다.\n\n1. 상위 5개 헤드라인을 한국어로 자연스럽게 번역해 주세요.\n2. 그 외 나머지 기사 중에서 한국 독자가 기술적으로 흥미로울 만한 5개를 골라 추천해 주세요. 추천된 항목마다 번역된 제목과 간단한 이유를 함께 제공해 주세요.\n\n[상위 5개 헤드라인 목록]:\n"
    for title, link in top5:
        prompt += f"- {title}\n"
    prompt += "\n[나머지 기사 목록]:\n"
    for title, link in rest:
        prompt += f"- {title}\n"

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {CHAT_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": "너는 영어 기술 뉴스 제목을 한국어로 자연스럽게 번역하고, 한국 개발자에게 흥미로운 기사를 선별해서 추천하는 AI야. 결과를 마크다운 링크, 굵은 글씨 등 어떤 마크다운 문법도 사용하지 말고, 순수 텍스트로만 출력해."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print("❌ OpenRouter 응답 실패:", e)
        return "⚠️ 번역 요청 중 오류가 발생했습니다."


def main():
    titles = fetch_hn_titles()
    top5 = titles[:5]
    rest = titles[5:]

    message_lines = ["🧠 Hacker News 헤드라인 요약", ""]
    message_lines.append("🔥 Top 5 헤드라인")
    for title, _ in top5:
        message_lines.append(f"• {title}")
    message_lines.append("")
    message_lines.append("✨ 추천 기사 (LLM 선정)")
    translated = translate_titles_with_openrouter(top5, rest)
    message_lines.append(translated.strip())

    message = "\n".join(message_lines)
    print(f"📏 최종 메시지 길이: {len(message)}자")
    send_to_telegram(message)
    print("✅ 메시지 전송 완료")

if __name__ == "__main__":
    main()