#!/usr/bin/env python3
"""
ClickHouse GitHub Issues Weekly Summary Bot

This script fetches ClickHouse GitHub issues from the past week and generates
a summary using OpenRouter API.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any

MAX_TELEGRAM_LEN = 4000  # 4096 is limit; keep some buffer for Markdown issues


def _telegram_post(text, telegram_token, telegram_chat_id):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": telegram_chat_id,
        "text": text,
        "disable_web_page_preview": True
    })
    if resp.status_code != 200:
        print("❌ 텔레그램 전송 실패:", resp.status_code, resp.text)
    else:
        print("✅ 텔레그램 전송 성공 (chunk length =", len(text), ")")

def send_to_telegram(message: str, telegram_token: str, telegram_chat_id: str):
    """
    Send a potentially long message to Telegram by splitting it into
    chunks that respect the 4096‑character limit (we use 4000 for safety).
    """
    if len(message) <= MAX_TELEGRAM_LEN:
        _telegram_post(message, telegram_token, telegram_chat_id)
        return

    print("ℹ️ 메시지가 길어 여러 개로 분할 전송합니다. 총 길이:", len(message))
    lines = message.split('\n')
    chunk = ""
    for line in lines:
        # +1 for newline that will be re-added
        if len(chunk) + len(line) + 1 > MAX_TELEGRAM_LEN:
            _telegram_post(chunk, telegram_token, telegram_chat_id)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        _telegram_post(chunk, telegram_token, telegram_chat_id)


class ClickHouseIssuesSummarizer:
    def __init__(self, openrouter_api_key: str, github_token: str = None, telegram_token: str = None, telegram_chat_id: str = None):
        self.openrouter_api_key = openrouter_api_key
        self.github_token = github_token
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.github_headers = {}
        
        if github_token:
            self.github_headers["Authorization"] = f"token {github_token}"
        self.github_headers["Accept"] = "application/vnd.github.v3+json"
        
        self.openrouter_headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json"
        }

    def get_weekly_issues(self) -> List[Dict[str, Any]]:
        """GitHub API를 사용해 지난 일주일간의 ClickHouse 이슈를 가져옵니다."""
        one_week_ago = datetime.now() - timedelta(days=7)
        since_date = one_week_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        url = "https://api.github.com/repos/ClickHouse/ClickHouse/issues"
        params = {
            "since": since_date,
            "state": "all",
            "per_page": 100,
            "sort": "created"
        }
        
        all_issues = []
        page = 1
        
        while True:
            params["page"] = page
            response = requests.get(url, headers=self.github_headers, params=params)
            
            if response.status_code != 200:
                print(f"GitHub API 요청 실패: {response.status_code}")
                break
                
            issues = response.json()
            if not issues:
                break
                
            # Pull Request는 제외 (GitHub에서 PR도 issues로 분류됨)
            filtered_issues = [issue for issue in issues if "pull_request" not in issue]
            all_issues.extend(filtered_issues)
            
            # API 응답에 더 이상 이슈가 없으면 중단
            if len(issues) < params["per_page"]:
                break
                
            page += 1
            
        return all_issues

    def prepare_issues_for_summary(self, issues: List[Dict[str, Any]]) -> str:
        """이슈 목록을 요약을 위한 텍스트로 변환합니다."""
        if not issues:
            return "지난 일주일간 새로운 이슈가 없습니다."
        
        # 이슈를 인기도(코멘트 수 + 반응 수)로 정렬
        def get_popularity_score(issue):
            comments = issue.get("comments", 0)
            reactions = issue.get("reactions", {})
            if isinstance(reactions, dict):
                # reactions 값 중 숫자만 합산 (문자열은 제외)
                reaction_sum = sum(v for v in reactions.values() if isinstance(v, int))
            else:
                reaction_sum = 0
            return comments + reaction_sum
        
        sorted_issues = sorted(issues, key=get_popularity_score, reverse=True)
        
        issues_text = f"ClickHouse 지난 일주일 이슈 목록 ({len(issues)}개, 인기도순 정렬):\n\n"
        
        for issue in sorted_issues:
            created_at = datetime.strptime(issue["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = created_at.strftime("%Y-%m-%d")
            
            # 인기도 계산
            comments_count = issue.get("comments", 0)
            reactions = issue.get("reactions", {})
            if isinstance(reactions, dict):
                total_reactions = sum(v for v in reactions.values() if isinstance(v, int))
            else:
                total_reactions = 0
            
            issues_text += f"#{issue['number']} - {issue['title']}\n"
            issues_text += f"작성일: {formatted_date}\n"
            issues_text += f"상태: {issue['state']}\n"
            issues_text += f"인기도: 코멘트 {comments_count}개, 반응 {total_reactions}개\n"
            
            if issue.get("labels"):
                labels = [label["name"] for label in issue["labels"]]
                issues_text += f"라벨: {', '.join(labels)}\n"
            
            issues_text += f"URL: {issue['html_url']}\n"
            
            if issue["body"] and len(issue["body"]) > 0:
                # 본문이 너무 길면 처음 300자만 포함 (더 많은 컨텍스트 제공)
                body_preview = issue["body"][:300] + "..." if len(issue["body"]) > 300 else issue["body"]
                issues_text += f"설명: {body_preview}\n"
            
            issues_text += "\n" + "-"*50 + "\n\n"
            
        return issues_text

    def generate_summary(self, issues_text: str) -> str:
        """OpenRouter API를 사용해 이슈들을 요약합니다."""
        prompt = f"""Analyze ClickHouse GitHub issues from the past week for DevOps team operating ClickHouse in Kubernetes environment. Provide comprehensive summary in Korean.

**Context:**
- OpenTelemetry-based Log/Metric/Trace data processing
- Tables: Replicated, Materialized Views, Null Engines
- Self-hosted Kubernetes with ClickHouse Operator

**Summary Structure:**
1. 📊 Total issues count and status distribution

2. 🔥 Critical/Popular issues (by comments, labels)
   - Include GitHub links
   - Assess operational impact

3. 🎯 Operational categories:
   - Performance optimization
   - Operational stability
   - Kubernetes/Operator related
   - OpenTelemetry/Observability
   - Replicated/Materialized Views
   - Others (bugs, features, docs)

4. ⚠️ Key issues for ops team:
   - Critical issues requiring immediate action
   - Performance degradation risks
   - Data integrity concerns

5. 📈 Trends and patterns:
   - Recurring issue types
   - Version-specific trends
   - Community interest changes

Include GitHub links and prioritize by operational impact.

Issues:
{issues_text}"""

        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": [
                {
                    "role": "system", 
                    "content": "You are a ClickHouse operations expert. Analyze GitHub issues for DevOps teams running ClickHouse clusters in Kubernetes with OpenTelemetry data processing. Provide technical insights with operational impact assessment. Always respond in Korean."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 3000,
            "temperature": 0.5
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=self.openrouter_headers,
            json=payload
        )
        
        if response.status_code != 200:
            return f"OpenRouter API 요청 실패: {response.status_code} - {response.text}"
        
        try:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            return f"응답 파싱 오류: {e}"

    def save_summary(self, summary: str, issues_count: int) -> str:
        """요약을 파일로 저장합니다."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clickhouse_weekly_summary_{timestamp}.md"
        
        content = f"""# ClickHouse 주간 이슈 요약

**생성일**: {datetime.now().strftime("%Y년 %m월 %d일 %H:%M")}
**이슈 개수**: {issues_count}개

## 요약

{summary}

---
*이 요약은 자동으로 생성되었습니다.*
"""
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
            
        return filename

    def run(self) -> None:
        """전체 워크플로우를 실행합니다."""
        print("ClickHouse 이슈 수집 중...")
        issues = self.get_weekly_issues()
        
        print(f"수집된 이슈: {len(issues)}개")
        
        if not issues:
            message = "지난 일주일간 ClickHouse에 새로운 이슈가 없습니다."
            print(message)
            if self.telegram_token and self.telegram_chat_id:
                send_to_telegram(message, self.telegram_token, self.telegram_chat_id)
            return
        
        print("이슈 요약 생성 중...")
        issues_text = self.prepare_issues_for_summary(issues)
        summary = self.generate_summary(issues_text)
        
        # 텔레그램으로 전송
        if self.telegram_token and self.telegram_chat_id:
            telegram_message = f"🔧 ClickHouse 주간 이슈 요약\n\n{summary}"
            print("텔레그램으로 전송 중...")
            send_to_telegram(telegram_message, self.telegram_token, self.telegram_chat_id)
        
        print("요약 파일 저장 중...")
        filename = self.save_summary(summary, len(issues))
        
        print(f"요약 완료! 파일: {filename}")
        print("\n" + "="*50)
        print(summary)


def main():
    """메인 함수"""
    # 환경 변수에서 API 키를 가져옵니다
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")  # 선택사항
    telegram_token = os.getenv("TG_TOKEN")  # 선택사항
    telegram_chat_id = os.getenv("TG_CHAT_ID")  # 선택사항
    
    if not openrouter_api_key:
        print("오류: OPENROUTER_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("GitHub Secrets에 OPENROUTER_API_KEY를 설정하세요.")
        return
    
    if not github_token:
        print("경고: GITHUB_TOKEN이 설정되지 않았습니다. API 호출 제한이 있을 수 있습니다.")
        print("GitHub Secrets에 GITHUB_TOKEN을 설정하는 것을 권장합니다.")
        print()
    
    if not telegram_token or not telegram_chat_id:
        print("경고: 텔레그램 설정이 없습니다. 콘솔에만 출력됩니다.")
        print("텔레그램 전송을 원하면 TG_TOKEN과 TG_CHAT_ID를 GitHub Secrets에 설정하세요.")
        print()
    
    summarizer = ClickHouseIssuesSummarizer(
        openrouter_api_key=openrouter_api_key,
        github_token=github_token,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id
    )
    summarizer.run()


if __name__ == "__main__":
    main()