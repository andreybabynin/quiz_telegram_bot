# Quiz Bot

Telegram bot for running multiple-choice quizzes: one admin sends questions to all participants; answers are collected via inline buttons and scored automatically.

## Setup

1. **Environment**
   ```bash
   cp .env.example .env
   # Edit .env: set BOT_TOKEN (from @BotFather) and ADMIN_ID (your Telegram user ID).
   ```

2. **Questions**
   ```bash
   cp questions.yaml.example questions.yaml
   # Edit questions.yaml with your questions (see example format).
   ```

3. **Run**
   ```bash
   pip install -r requirements.txt
   python bot.py
   ```

## Main functionality

- **Participants:** Send `/start` to register. They receive questions as the admin sends them and answer with inline buttons (one answer per question).
- **Admin:** Same `/start` identifies you as admin; you do not appear in the participant list.
- **Quiz flow:** Admin runs `/start_quiz`, then sends questions with `/q1`, `/q2`, … (one command per question ID in `questions.yaml`). Use `/close` to close the current question and broadcast the correct answer to everyone. `/stop_quiz` stops accepting new answers.
- **Leaderboard:** `/leaderboard` shows top 10 by score (admin only); it can be broadcast to all participants.
- **Export:** `/export` (admin) downloads a CSV of all answers and totals.
- **Reset:** `/reset` (admin, with confirmation) clears participants and answers for a new run.

## Tests

```bash
pytest test_bot.py -v
```

(Use the project `venv` if you have one: `venv/bin/pytest test_bot.py -v`.)
