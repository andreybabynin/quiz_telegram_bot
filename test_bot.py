import os
import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def test_load_config_reads_bot_token_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "test_token_123")
    monkeypatch.setenv("ADMIN_ID", "42")
    from bot import load_config
    token, admin_id = load_config()
    assert token == "test_token_123"
    assert admin_id == 42


def test_load_config_raises_when_token_missing(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_ID", "42")
    from bot import load_config
    with pytest.raises((KeyError, ValueError, TypeError)):
        load_config()


def test_load_config_raises_when_admin_id_missing(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "tok")
    monkeypatch.delenv("ADMIN_ID", raising=False)
    from bot import load_config
    with pytest.raises((KeyError, ValueError, TypeError)):
        load_config()


# ---------------------------------------------------------------------------
# Questions loading
# ---------------------------------------------------------------------------

def test_load_questions_returns_dict(tmp_path):
    qfile = tmp_path / "questions.yaml"
    qfile.write_text(
        "q1:\n"
        "  text: Test?\n"
        "  options:\n"
        "    - [A, a]\n"
        "    - [B, b]\n"
        "  correct: a\n"
    )
    from bot import load_questions
    questions = load_questions(str(qfile))
    assert "q1" in questions
    assert questions["q1"]["correct"] == "a"
    assert questions["q1"]["options"] == [["A", "a"], ["B", "b"]]


def test_load_questions_raises_for_missing_file():
    from bot import load_questions
    with pytest.raises(FileNotFoundError):
        load_questions("/nonexistent/path/questions.yaml")


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def test_calculate_score_with_letter_answers():
    from bot import calculate_score
    questions = {
        "q1": {"correct": "A", "options": [], "text": ""},
        "q2": {"correct": "B", "options": [], "text": ""},
    }
    answers = {1: {"q1": "A", "q2": "B"}}
    correct, total = calculate_score(user_id=1, answers=answers, questions=questions)
    assert correct == 2
    assert total == 2


def test_calculate_score_empty():
    from bot import calculate_score
    questions = {
        "q1": {"correct": "paris", "options": [], "text": ""},
    }
    correct, total = calculate_score(user_id=1, answers={}, questions=questions)
    assert correct == 0
    assert total == 0


def test_calculate_score_all_correct():
    from bot import calculate_score
    questions = {
        "q1": {"correct": "paris", "options": [], "text": ""},
        "q2": {"correct": "six", "options": [], "text": ""},
    }
    user_answers = {1: {"q1": "paris", "q2": "six"}}
    correct, total = calculate_score(user_id=1, answers=user_answers, questions=questions)
    assert correct == 2
    assert total == 2


def test_calculate_score_partial():
    from bot import calculate_score
    questions = {
        "q1": {"correct": "paris", "options": [], "text": ""},
        "q2": {"correct": "six", "options": [], "text": ""},
    }
    user_answers = {1: {"q1": "london", "q2": "six"}}
    correct, total = calculate_score(user_id=1, answers=user_answers, questions=questions)
    assert correct == 1
    assert total == 2


def test_get_correct_answer_text():
    from bot import get_correct_answer_text
    questions = {
        "q1": {
            "correct": "paris",
            "options": [["Лондон", "london"], ["Париж", "paris"]],
            "text": "",
        }
    }
    assert get_correct_answer_text("q1", questions) == "Париж"


def test_get_correct_answer_text_q3_from_yaml():
    from bot import get_correct_answer_text, QUESTIONS
    result = get_correct_answer_text("q3", QUESTIONS)
    assert result != "N/A", f"Expected a real answer text, got N/A (correct val likely not found in options)"


def test_get_correct_answer_text_unknown_question():
    from bot import get_correct_answer_text
    assert get_correct_answer_text("q99", {}) == "N/A"


def test_is_admin_true():
    from bot import is_admin
    assert is_admin(user_id=42, admin_id=42) is True


def test_is_admin_false():
    from bot import is_admin
    assert is_admin(user_id=1, admin_id=42) is False


# ---------------------------------------------------------------------------
# handle_answer: keyboard removal and no re-answer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_answer_removes_keyboard():
    from telegram import InlineKeyboardMarkup
    import bot

    bot.current_question = "q1"
    bot.answers = {}

    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 999
    query.data = "q1:paris"

    update = MagicMock()
    update.callback_query = query

    await bot.handle_answer(update, MagicMock())

    query.edit_message_text.assert_called_once()
    kwargs = query.edit_message_text.call_args.kwargs
    assert "reply_markup" in kwargs
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
    assert kwargs["reply_markup"].inline_keyboard == ()


@pytest.mark.asyncio
async def test_handle_answer_already_answered_shows_closed():
    import bot

    bot.current_question = "q2"  # different question is now active
    bot.answers = {}

    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 999
    query.data = "q1:paris"  # user clicks old q1 button

    update = MagicMock()
    update.callback_query = query

    await bot.handle_answer(update, MagicMock())

    query.edit_message_text.assert_called_once()
    text_arg = query.edit_message_text.call_args.args[0] if query.edit_message_text.call_args.args else query.edit_message_text.call_args.kwargs.get("text", "")
    assert "закрыт" in text_arg


@pytest.mark.asyncio
async def test_handle_answer_already_answered_blocks_repeat():
    import bot

    bot.current_question = "q1"
    bot.answers = {}
    bot.current_question_respondents = {999}  # already answered this question instance

    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 999
    query.data = "q1:london"

    update = MagicMock()
    update.callback_query = query

    await bot.handle_answer(update, MagicMock())

    # Should NOT record any answer and NOT edit the message
    assert 999 not in bot.answers
    query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_answer_allows_same_question_id_in_new_session():
    import bot

    bot.current_question = "q1"
    bot.answers = {999: {"q1": "paris"}}  # answered in previous session
    bot.current_question_respondents = set()  # fresh for new question dispatch

    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 999
    query.data = "q1:london"

    update = MagicMock()
    update.callback_query = query

    await bot.handle_answer(update, MagicMock())

    # Should accept and overwrite the old answer
    assert bot.answers[999]["q1"] == "london"
    query.edit_message_text.assert_called_once()


# ---------------------------------------------------------------------------
# build_leaderboard helper
# ---------------------------------------------------------------------------

_QUESTIONS = {
    "q1": {"correct": "paris", "options": [], "text": ""},
    "q2": {"correct": "six", "options": [], "text": ""},
}


def test_build_leaderboard_sorted_by_score():
    from bot import build_leaderboard
    participants = {
        1: {"name": "Alice"},
        2: {"name": "Bob"},
    }
    answers = {
        1: {"q1": "paris", "q2": "six"},   # 2 correct
        2: {"q1": "london", "q2": "six"},  # 1 correct
    }
    result = build_leaderboard(participants, answers, _QUESTIONS)
    assert result[0][0] == "Alice"
    assert result[1][0] == "Bob"


def test_build_leaderboard_includes_participants_without_answers():
    from bot import build_leaderboard
    participants = {
        1: {"name": "Alice"},
        2: {"name": "Charlie"},  # never answered
    }
    answers = {1: {"q1": "paris"}}
    result = build_leaderboard(participants, answers, _QUESTIONS)
    names = [r[0] for r in result]
    assert "Charlie" in names


def test_build_leaderboard_limits_to_10():
    from bot import build_leaderboard
    participants = {i: {"name": f"User{i}"} for i in range(15)}
    answers = {}
    result = build_leaderboard(participants, answers, _QUESTIONS)
    assert len(result) == 10


# ---------------------------------------------------------------------------
# Admin not added to participants on /start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_does_not_add_admin_to_participants():
    import bot
    bot.ADMIN_ID = 42
    bot.participants = {}

    user = MagicMock()
    user.id = 42  # admin
    user.username = "admin"
    user.first_name = "Admin"
    user.last_name = None

    update = MagicMock()
    update.effective_user = user
    update.message.reply_text = AsyncMock()

    await bot.start(update, MagicMock())

    assert 42 not in bot.participants


@pytest.mark.asyncio
async def test_start_adds_regular_user_to_participants():
    import bot
    bot.ADMIN_ID = 42
    bot.participants = {}

    user = MagicMock()
    user.id = 999
    user.username = "alice"
    user.first_name = "Alice"
    user.last_name = None

    update = MagicMock()
    update.effective_user = user
    update.message.reply_text = AsyncMock()

    await bot.start(update, MagicMock())

    assert 999 in bot.participants


# ---------------------------------------------------------------------------
# Admin access control
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_callback_rejects_non_admin():
    import bot
    bot.ADMIN_ID = 42
    bot.quiz_active = True
    bot.answers = {"some": "data"}

    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 999  # non-admin
    query.data = "reset_confirm"

    update = MagicMock()
    update.callback_query = query

    await bot.reset_callback(update, MagicMock())

    # State must NOT have been wiped
    assert bot.quiz_active is True
    assert bot.answers == {"some": "data"}


def test_build_leaderboard_score_format():
    from bot import build_leaderboard
    participants = {1: {"name": "Alice"}}
    answers = {1: {"q1": "paris", "q2": "four"}}  # 1 correct out of 2
    result = build_leaderboard(participants, answers, _QUESTIONS)
    name, correct, total = result[0]
    assert correct == 1
    assert total == 2  # len(_QUESTIONS) == 2


def test_build_leaderboard_denominator_is_total_questions_not_answered():
    from bot import build_leaderboard
    questions = {
        "q1": {"correct": "paris", "options": [], "text": ""},
        "q2": {"correct": "six", "options": [], "text": ""},
        "q3": {"correct": "python", "options": [], "text": ""},
    }
    participants = {1: {"name": "Alice"}}
    answers = {1: {"q1": "paris"}}  # only answered 1 out of 3
    result = build_leaderboard(participants, answers, questions)
    _, correct, total = result[0]
    assert correct == 1
    assert total == 3  # total questions in quiz, not just answered


# ---------------------------------------------------------------------------
# Leaderboard broadcast to participants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_show_leaderboard_broadcasts_to_participants():
    import bot
    bot.ADMIN_ID = 42
    bot.participants = {1: {"name": "Alice"}, 2: {"name": "Bob"}}
    bot.answers = {}

    update = MagicMock()
    update.effective_user.id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await bot.show_leaderboard(update, context)

    sent_to = {c.kwargs["chat_id"] for c in context.bot.send_message.call_args_list}
    assert sent_to == {1, 2}


# ---------------------------------------------------------------------------
# Auto-show answer on close + reset clears participants
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_question_auto_shows_correct_answer():
    import bot
    bot.ADMIN_ID = 42
    bot.current_question = "q1"
    bot.current_question_respondents = set()
    bot.participants = {1: {"name": "Alice"}}

    update = MagicMock()
    update.effective_user.id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await bot.close_question(update, context)

    context.bot.send_message.assert_called_once()
    text = context.bot.send_message.call_args.kwargs["text"]
    assert text != "N/A"  # correct answer text was found in options


@pytest.mark.asyncio
async def test_reset_clears_participants():
    import bot
    bot.ADMIN_ID = 42
    bot.answers = {"x": {}}
    bot.participants = {1: {"name": "Alice"}}
    bot.current_question = "q1"
    bot.quiz_active = True

    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 42  # admin
    query.data = "reset_confirm"

    update = MagicMock()
    update.callback_query = query

    await bot.reset_callback(update, MagicMock())

    assert bot.participants == {}
    assert bot.answers == {}
