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

### Security Review Process
Before committing any changes, always verify:
- No API keys, tokens, or secrets in code or files
- No internal company information or references
- No personal email addresses (use GitHub noreply email)
- No internal URLs or system details
- Configuration files contain only public information

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

Model configuration (optional):
- `CHAT_MODEL_FAST` - Fast/cost-effective model for simple tasks (default: google/gemini-2.0-flash-001)
- `CHAT_MODEL_SMART` - High-performance model for complex analysis (default: anthropic/claude-3.5-sonnet)

## Code Quality Rules

### API Safety
- Always set timeout for external API calls
- Implement proper error handling and response validation
- Consider rate limiting for API requests

### GitHub Actions Guidelines
- Validate workflow syntax locally before committing
- Use minimum required permissions for secrets
- Fix and re-run failed workflows immediately

### Code Standards
- Extract hardcoded values to environment variables or constants
- Follow single responsibility principle for functions
- Include specific error messages in exception handling

### Telegram Bot Specific
- Check message length limits (4096 characters)
- Handle markdown escaping properly
- Validate bot token before use

### Dependency Management
- Always commit uv.lock file with dependency changes
- Review security implications of new packages
- Separate dependency updates into dedicated commits

## Development Commands

- **Run tests**: `pytest` (if tests exist)
- **Lint code**: Check for linting commands in pyproject.toml
- **Run scripts**: Use `uv run python <script_name>.py`