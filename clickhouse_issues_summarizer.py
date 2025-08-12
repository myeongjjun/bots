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
    def __init__(self, chat_api_key: str, github_token: str = None, telegram_token: str = None, telegram_chat_id: str = None, chat_model: str = None):
        self.chat_api_key = chat_api_key
        self.github_token = github_token
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.chat_model = chat_model or "anthropic/claude-3.5-sonnet"
        self.github_headers = {}
        
        if github_token:
            self.github_headers["Authorization"] = f"token {github_token}"
        self.github_headers["Accept"] = "application/vnd.github.v3+json"
        
        self.openrouter_headers = {
            "Authorization": f"Bearer {chat_api_key}",
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
            
            # total_count가 있으면 우선 사용
            if isinstance(reactions, dict) and "total_count" in reactions:
                reaction_sum = reactions.get("total_count", 0)
            elif isinstance(reactions, dict):
                # reactions 값 중 숫자만 합산 (문자열은 제외)
                reaction_sum = sum(v for v in reactions.values() if isinstance(v, int))
            else:
                reaction_sum = 0
            
            return comments + reaction_sum
        
        sorted_issues = sorted(issues, key=get_popularity_score, reverse=True)
        
        # 상위 10개 인기 이슈만 LLM에 전달 (토큰 절약 및 품질 향상)
        top_issues = sorted_issues[:10]
        
        # 전체 통계 정보는 유지
        issues_text = f"ClickHouse 지난 일주일 이슈 통계:\n"
        issues_text += f"- 전체 이슈: {len(issues)}개\n"
        issues_text += f"- 분석 대상: 상위 인기 이슈 {len(top_issues)}개\n\n"
        issues_text += "상위 인기 이슈 목록 (인기도순):\n\n"
        
        for issue in top_issues:
            created_at = datetime.strptime(issue["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = created_at.strftime("%Y-%m-%d")
            
            # 인기도 계산 (test_fetch.py와 동일한 방식)
            comments_count = issue.get("comments", 0)
            reactions = issue.get("reactions", {})
            if isinstance(reactions, dict) and "total_count" in reactions:
                total_reactions = reactions.get("total_count", 0)
            elif isinstance(reactions, dict):
                total_reactions = sum(v for v in reactions.values() if isinstance(v, int))
            else:
                total_reactions = 0
            
            engagement_score = comments_count + total_reactions
            
            issues_text += f"#{issue['number']} - {issue['title']}\n"
            issues_text += f"작성일: {formatted_date}\n"
            issues_text += f"상태: {issue['state']}\n"
            issues_text += f"인기도: 코멘트 {comments_count}개, 반응 {total_reactions}개, 점수 {engagement_score}\n"
            
            if issue.get("labels"):
                labels = [label["name"] for label in issue["labels"]]
                issues_text += f"라벨: {', '.join(labels)}\n"
            
            issues_text += f"URL: {issue['html_url']}\n"
            
            if issue["body"] and len(issue["body"]) > 0:
                # 이슈 본문 전체 포함 (상위 10개만 분석하므로 토큰 사용량 관리 가능)
                issues_text += f"설명: {issue['body']}\n"
            
            issues_text += "\n" + "-"*50 + "\n\n"
            
        return issues_text

    def generate_summary(self, issues_text: str) -> str:
        """Chat Completions API를 사용해 이슈들을 요약합니다."""
        prompt = f"""Analyze top 10 most popular ClickHouse GitHub issues from the past week for DevOps team operating ClickHouse in Kubernetes environment. Provide detailed, comprehensive analysis in Korean.

**Context:**
- OpenTelemetry-based Log/Metric/Trace data processing
- Tables: Replicated, Materialized Views, Null Engines
- Self-hosted Kubernetes with ClickHouse Operator
- Issues are pre-sorted by popularity (comments + reactions)

**Analysis Requirements:**
Provide in-depth analysis for each of the 10 issues. DO NOT just summarize - analyze each issue's technical details, root causes, and operational implications.

**Detailed Summary Structure:**

1. 📊 **Issue Statistics Overview**
   - Total issues vs analyzed top 10
   - Status distribution and engagement metrics

2. 🔥 **Individual Issue Deep Analysis** 
   For EACH of the top 10 issues, provide:
   - Issue title, number, and GitHub link
   - Technical problem description and root cause analysis
   - Potential impact on our Kubernetes/OpenTelemetry environment
   - Urgency level (Critical/High/Medium/Low) with reasoning
   - Specific recommendations for our setup
   - Related components (Replicated tables, Materialized Views, etc.)

3. 🎯 **Operational Impact Assessment**
   Group issues by operational impact:
   - **CRITICAL**: Immediate action required (data loss, cluster instability)
   - **HIGH**: Performance/reliability concerns for production
   - **MEDIUM**: Operational improvements and monitoring
   - **LOW**: Future considerations and feature requests

4. ⚠️ **Action Plan for DevOps Team**
   - Immediate response items (next 24-48 hours)
   - Short-term monitoring and mitigation (this week)
   - Long-term improvements and upgrades (next month)
   - Preventive measures to implement

5. 🛠️ **Technical Deep Dive**
   - Issues affecting Kubernetes deployments and ClickHouse Operator
   - OpenTelemetry data ingestion and processing concerns
   - Replicated table and Materialized View specific problems
   - Performance optimization opportunities

6. 💡 **Strategic Insights**
   - Patterns in community concerns
   - Version-specific issues to watch
   - Recommendations for cluster configuration
   - Monitoring and alerting improvements needed

**Important**: Analyze each issue individually with technical depth. Don't just list issues - explain WHY each is important for our specific environment and WHAT we should do about it.

Issues:
{issues_text}"""

        payload = {
            "model": self.chat_model,
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
            "max_tokens": 8000,
            "temperature": 0.5
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=self.openrouter_headers,
            json=payload
        )
        
        if response.status_code != 200:
            return f"Chat API 요청 실패: {response.status_code} - {response.text}"
        
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
    chat_api_key = os.getenv("CHAT_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")  # 선택사항
    telegram_token = os.getenv("TG_TOKEN")  # 선택사항
    telegram_chat_id = os.getenv("TG_CHAT_ID")  # 선택사항
    chat_model = os.getenv("CHAT_MODEL_SMART")  # 선택사항
    
    if not chat_api_key:
        print("오류: CHAT_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("GitHub Secrets에 CHAT_API_KEY를 설정하세요.")
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
        chat_api_key=chat_api_key,
        github_token=github_token,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        chat_model=chat_model
    )
    summarizer.run()


if __name__ == "__main__":
    main()