# bots

자동화된 분석 및 알림 봇들의 모음입니다.

## 포함된 봇들

### 1. ClickHouse Issues Summarizer (`clickhouse_issues_summarizer.py`)
ClickHouse GitHub 이슈를 주간 단위로 요약하여 텔레그램으로 전송합니다.

**실행 주기**: 매주 일요일 오전 9시 (UTC)  
**기능**: 
- 지난 일주일간 ClickHouse GitHub 이슈 수집
- 인기도별로 상위 10개 이슈 분석
- AI를 활용한 상세 기술 분석 및 운영 영향도 평가
- 텔레그램을 통한 자동 알림

### 2. HackerNews Recommender (`hn_recommender.py`)
HackerNews 추천 시스템입니다.

### 3. HD현대 합병 아비트리지 모니터 (`hd_merger_arbitrage.py`) 🆕
HD현대중공업과 HD현대미포 간의 합병 아비트리지 기회를 실시간 모니터링합니다.

**실행 주기**: 한국 주식시장 시간 (월~금 09:00-15:30) 동안 10분마다  
**기능**:
- HD현대중공업(329180.KS)과 HD현대미포(010620.KS) 실시간 주가 수집
- 합병비율(0.4059146)을 적용한 아비트리지 기회 계산
- 괴리율 2% 이상 시 텔레그램 자동 알림
- Yahoo Finance API 우선, 네이버 금융 백업 데이터 수집
- 수수료 및 슬리피지 고려한 실질 수익성 분석

**주요 지표**:
- 미포 경유 중공업 실질 매입가 계산
- 직매수 대비 괴리율 분석  
- 중공업 기준 미포 이론가(패리티) 제시
- 투자 전략 추천 (미포 매수 vs 중공업 직매수)

## 설정

### 환경 변수
```bash
# 공통 텔레그램 설정
TG_TOKEN=your_telegram_bot_token
TG_CHAT_ID=your_chat_id

# ClickHouse 요약기용
CHAT_API_KEY=your_openrouter_api_key
GITHUB_TOKEN=your_github_token
CHAT_MODEL_SMART=anthropic/claude-3.5-sonnet

# HD현대 아비트리지 모니터용 (추가 설정 불필요)
```

### GitHub Secrets 설정
Actions에서 자동 실행하려면 다음 secrets을 설정하세요:
- `TG_TOKEN`: 텔레그램 봇 토큰 (ClickHouse 요약기용)
- `TG_TOKEN_TRADEPAL`: 텔레그램 봇 토큰 (HD현대 아비트리지용)
- `TG_CHAT_ID`: 텔레그램 채팅 ID
- `CHAT_API_KEY`: Chat API 키 (ClickHouse 요약기용)
- `GITHUB_TOKEN`: GitHub API 토큰
- `CHAT_MODEL_SMART`: 사용할 AI 모델 (선택사항)

## 실행 방법

### 로컬 실행
```bash
# 의존성 설치
uv sync

# ClickHouse 이슈 요약
uv run python clickhouse_issues_summarizer.py

# HD현대 아비트리지 체크
uv run python hd_merger_arbitrage.py

# HackerNews 추천
uv run python hn_recommender.py
```

### GitHub Actions 자동 실행
- ClickHouse 요약: 매주 일요일 자동 실행
- HD현대 아비트리지: 한국 주식시장 시간 중 10분마다 자동 실행
- 수동 실행도 GitHub Actions 탭에서 가능

## 의존성

주요 라이브러리:
- `requests`: HTTP 요청
- `beautifulsoup4`: HTML 파싱 (네이버 금융 스크래핑용)
- `yfinance`: Yahoo Finance API (주가 데이터)

자세한 의존성은 `pyproject.toml` 참조.
