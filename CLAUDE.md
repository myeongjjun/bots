# Claude Code Instructions

## Git Configuration Rules

When making commits to this repository:

### Author Settings
- **Name**: `myeongjjun`
- **Email**: `myeongjjun@users.noreply.github.com`

### Auto-Configuration Commands
Before making any commits, always run:
```bash
git config user.name "myeongjjun"
git config user.email "myeongjjun@users.noreply.github.com"
```

### Commit Message Format
Follow conventional commits format:
- Use descriptive commit messages
- Include the Claude Code footer:
  ```
  🤖 Generated with [Claude Code](https://claude.ai/code)
  
  Co-Authored-By: Claude <noreply@anthropic.com>
  ```

## Project Structure

This repository contains:
- `hn_recommender.py` - Hacker News recommendation bot
- `clickhouse_issues_summarizer.py` - ClickHouse GitHub issues summarizer
- GitHub Actions workflows in `.github/workflows/`

## Environment Variables

Both scripts use:
- `CHAT_API_KEY` - API key for LLM completions
- `TG_TOKEN` - Telegram bot token
- `TG_CHAT_ID` - Telegram chat ID
- `GITHUB_TOKEN` - GitHub API token (optional)

## Development Commands

- **Run tests**: `pytest` (if tests exist)
- **Lint code**: Check for linting commands in pyproject.toml
- **Run scripts**: Use `uv run python <script_name>.py`