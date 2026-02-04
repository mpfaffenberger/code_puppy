"""Tests for ask_user_question models."""

import pytest
from pydantic import ValidationError

from code_puppy.tools.ask_user_question.models import (
    AskUserQuestionInput,
    AskUserQuestionOutput,
    Question,
    QuestionAnswer,
    QuestionOption,
)


class TestQuestionOption:
    """Tests for QuestionOption model."""

    def test_valid_option_with_description(self) -> None:
        """Valid option with label and description."""
        opt = QuestionOption(label="PostgreSQL", description="Relational DB")
        assert opt.label == "PostgreSQL"
        assert opt.description == "Relational DB"

    def test_label_only(self) -> None:
        """Description is optional."""
        opt = QuestionOption(label="PostgreSQL")
        assert opt.label == "PostgreSQL"
        assert opt.description == ""

    def test_empty_label_rejected(self) -> None:
        """Empty label should fail validation."""
        with pytest.raises(ValidationError) as exc:
            QuestionOption(label="")
        assert "label" in str(exc.value).lower()

    def test_label_too_long(self) -> None:
        """Label over 50 chars should fail."""
        with pytest.raises(ValidationError):
            QuestionOption(label="x" * 51)

    def test_description_too_long(self) -> None:
        """Description over 200 chars should fail."""
        with pytest.raises(ValidationError):
            QuestionOption(label="Valid", description="x" * 201)

    def test_whitespace_trimmed(self) -> None:
        """Leading/trailing whitespace should be trimmed."""
        opt = QuestionOption(label="  PostgreSQL  ", description="  Desc  ")
        assert opt.label == "PostgreSQL"
        assert opt.description == "Desc"

    def test_ansi_codes_stripped(self) -> None:
        """ANSI escape codes should be stripped."""
        opt = QuestionOption(label="\x1b[31mRed\x1b[0m")
        assert opt.label == "Red"
        assert "\x1b" not in opt.label


class TestQuestion:
    """Tests for Question model."""

    @pytest.fixture
    def valid_options(self) -> list[QuestionOption]:
        return [
            QuestionOption(label="Option 1", description="First option"),
            QuestionOption(label="Option 2", description="Second option"),
        ]

    def test_valid_question(self, valid_options: list[QuestionOption]) -> None:
        """Valid question with all fields."""
        q = Question(
            question="Which option?",
            header="Choices",
            multi_select=False,
            options=valid_options,
        )
        assert q.question == "Which option?"
        assert q.header == "Choices"
        assert q.multi_select is False
        assert len(q.options) == 2

    def test_multi_select_default_false(
        self, valid_options: list[QuestionOption]
    ) -> None:
        """multi_select defaults to False."""
        q = Question(
            question="Which option?",
            header="Choices",
            options=valid_options,
        )
        assert q.multi_select is False

    def test_header_too_long(self, valid_options: list[QuestionOption]) -> None:
        """Header over 12 chars should fail."""
        with pytest.raises(ValidationError):
            Question(
                question="Which option?",
                header="TooLongHeader!",  # 14 chars
                options=valid_options,
            )

    def test_too_few_options(self) -> None:
        """Must have at least 2 options."""
        with pytest.raises(ValidationError):
            Question(
                question="Which option?",
                header="Choices",
                options=[QuestionOption(label="Only one")],
            )

    def test_too_many_options(self) -> None:
        """Must have at most 6 options."""
        options = [QuestionOption(label=f"Option {i}") for i in range(7)]
        with pytest.raises(ValidationError):
            Question(
                question="Which option?",
                header="Choices",
                options=options,
            )

    def test_empty_question_text(self, valid_options: list[QuestionOption]) -> None:
        """Empty question text should fail."""
        with pytest.raises(ValidationError):
            Question(
                question="",
                header="Choices",
                options=valid_options,
            )

    def test_question_text_too_long(self, valid_options: list[QuestionOption]) -> None:
        """Question over 500 chars should fail."""
        with pytest.raises(ValidationError):
            Question(
                question="x" * 501,
                header="Choices",
                options=valid_options,
            )

    def test_duplicate_option_labels(self) -> None:
        """Duplicate option labels should fail."""
        with pytest.raises(ValidationError):
            Question(
                question="Which option?",
                header="Choices",
                options=[
                    QuestionOption(label="Same"),
                    QuestionOption(label="Same"),
                ],
            )

    def test_header_spaces_replaced_with_hyphens(
        self, valid_options: list[QuestionOption]
    ) -> None:
        """Spaces in header should be replaced with hyphens."""
        q = Question(
            question="Which option?",
            header="My Header",
            options=valid_options,
        )
        assert q.header == "My-Header"


class TestAskUserQuestionInput:
    """Tests for AskUserQuestionInput model."""

    @pytest.fixture
    def valid_question(self) -> Question:
        return Question(
            question="Which database?",
            header="Database",
            options=[
                QuestionOption(label="PostgreSQL"),
                QuestionOption(label="MySQL"),
            ],
        )

    def test_valid_single_question(self, valid_question: Question) -> None:
        """Valid input with one question."""
        inp = AskUserQuestionInput(questions=[valid_question])
        assert len(inp.questions) == 1

    def test_valid_multiple_questions(self, valid_question: Question) -> None:
        """Valid input with multiple questions."""
        q2 = Question(
            question="Which framework?",
            header="Framework",
            options=[
                QuestionOption(label="FastAPI"),
                QuestionOption(label="Flask"),
            ],
        )
        inp = AskUserQuestionInput(questions=[valid_question, q2])
        assert len(inp.questions) == 2

    def test_empty_questions_array(self) -> None:
        """Empty questions array should fail."""
        with pytest.raises(ValidationError):
            AskUserQuestionInput(questions=[])

    def test_too_many_questions(self, valid_question: Question) -> None:
        """More than 10 questions should fail."""
        questions = []
        for i in range(11):  # MAX_QUESTIONS_PER_CALL is 10
            questions.append(
                Question(
                    question=f"Question {i}?",
                    header=f"Q{i}",
                    options=[
                        QuestionOption(label="A"),
                        QuestionOption(label="B"),
                    ],
                )
            )
        with pytest.raises(ValidationError):
            AskUserQuestionInput(questions=questions)

    def test_duplicate_headers(self) -> None:
        """Duplicate question headers should fail."""
        with pytest.raises(ValidationError):
            AskUserQuestionInput(
                questions=[
                    Question(
                        question="First?",
                        header="Same",
                        options=[
                            QuestionOption(label="A"),
                            QuestionOption(label="B"),
                        ],
                    ),
                    Question(
                        question="Second?",
                        header="Same",
                        options=[
                            QuestionOption(label="C"),
                            QuestionOption(label="D"),
                        ],
                    ),
                ]
            )


class TestQuestionAnswer:
    """Tests for QuestionAnswer model."""

    def test_valid_answer(self) -> None:
        """Valid answer with selections."""
        answer = QuestionAnswer(
            question_header="Database",
            selected_options=["PostgreSQL"],
        )
        assert answer.question_header == "Database"
        assert answer.selected_options == ["PostgreSQL"]
        assert answer.other_text is None

    def test_answer_with_other_text(self) -> None:
        """Answer with other_text set."""
        answer = QuestionAnswer(
            question_header="Database",
            selected_options=["Other"],
            other_text="CockroachDB",
        )
        assert answer.other_text == "CockroachDB"

    def test_empty_selections_valid(self) -> None:
        """Empty selections are valid (for multi-select)."""
        answer = QuestionAnswer(
            question_header="Features",
            selected_options=[],
        )
        assert answer.selected_options == []

    def test_multiple_selections(self) -> None:
        """Multiple selections for multi-select."""
        answer = QuestionAnswer(
            question_header="Features",
            selected_options=["Auth", "Caching", "Logging"],
        )
        assert len(answer.selected_options) == 3

    def test_has_other_true(self) -> None:
        """has_other returns True when other_text is set."""
        answer = QuestionAnswer(
            question_header="Q", selected_options=["Other"], other_text="custom"
        )
        assert answer.has_other is True

    def test_has_other_false(self) -> None:
        """has_other returns False when other_text is None."""
        answer = QuestionAnswer(question_header="Q", selected_options=["A"])
        assert answer.has_other is False

    def test_is_empty_true(self) -> None:
        """is_empty returns True when no selections and no other_text."""
        answer = QuestionAnswer(question_header="Q", selected_options=[])
        assert answer.is_empty is True

    def test_is_empty_false_with_selection(self) -> None:
        """is_empty returns False when selections exist."""
        answer = QuestionAnswer(question_header="Q", selected_options=["A"])
        assert answer.is_empty is False

    def test_is_empty_false_with_other_text(self) -> None:
        """is_empty returns False when other_text is set."""
        answer = QuestionAnswer(
            question_header="Q", selected_options=[], other_text="custom"
        )
        assert answer.is_empty is False


class TestAskUserQuestionOutput:
    """Tests for AskUserQuestionOutput model."""

    def test_success_output(self) -> None:
        """Successful output with answers."""
        output = AskUserQuestionOutput(
            answers=[
                QuestionAnswer(
                    question_header="Database",
                    selected_options=["PostgreSQL"],
                )
            ]
        )
        assert len(output.answers) == 1
        assert output.cancelled is False
        assert output.error is None
        assert output.timed_out is False

    def test_cancelled_output(self) -> None:
        """Cancelled output."""
        output = AskUserQuestionOutput(
            answers=[],
            cancelled=True,
            error="User cancelled",
        )
        assert output.cancelled is True
        assert output.answers == []

    def test_timed_out_output(self) -> None:
        """Timed out output."""
        output = AskUserQuestionOutput(
            answers=[],
            timed_out=True,
            error="Timed out after 300 seconds",
        )
        assert output.timed_out is True

    def test_error_output(self) -> None:
        """Error output."""
        output = AskUserQuestionOutput(
            answers=[],
            error="Validation error: header too long",
        )
        assert output.error is not None
        assert "header" in output.error

    def test_success_property_true(self) -> None:
        """success property returns True for successful output."""
        output = AskUserQuestionOutput(
            answers=[QuestionAnswer(question_header="Q", selected_options=["A"])]
        )
        assert output.success is True

    def test_success_property_false_when_cancelled(self) -> None:
        """success property returns False when cancelled."""
        output = AskUserQuestionOutput(cancelled=True)
        assert output.success is False

    def test_success_property_false_when_error(self) -> None:
        """success property returns False when error."""
        output = AskUserQuestionOutput(error="Something went wrong")
        assert output.success is False

    def test_success_property_false_when_timed_out(self) -> None:
        """success property returns False when timed out."""
        output = AskUserQuestionOutput(timed_out=True)
        assert output.success is False

    def test_get_answer_found(self) -> None:
        """get_answer returns answer when header exists."""
        output = AskUserQuestionOutput(
            answers=[
                QuestionAnswer(question_header="Database", selected_options=["PG"]),
                QuestionAnswer(
                    question_header="Framework", selected_options=["FastAPI"]
                ),
            ]
        )
        answer = output.get_answer("database")  # case-insensitive
        assert answer is not None
        assert answer.question_header == "Database"
        assert answer.selected_options == ["PG"]

    def test_get_answer_not_found(self) -> None:
        """get_answer returns None when header doesn't exist."""
        output = AskUserQuestionOutput(
            answers=[
                QuestionAnswer(question_header="Database", selected_options=["PG"])
            ]
        )
        assert output.get_answer("nonexistent") is None

    def test_get_selected_found(self) -> None:
        """get_selected returns options when header exists."""
        output = AskUserQuestionOutput(
            answers=[
                QuestionAnswer(
                    question_header="Features",
                    selected_options=["Auth", "Caching"],
                )
            ]
        )
        assert output.get_selected("features") == ["Auth", "Caching"]

    def test_get_selected_not_found(self) -> None:
        """get_selected returns empty list when header doesn't exist."""
        output = AskUserQuestionOutput(answers=[])
        assert output.get_selected("nonexistent") == []

    def test_error_response_factory(self) -> None:
        """error_response creates proper error output."""
        output = AskUserQuestionOutput.error_response("Something went wrong")
        assert output.error == "Something went wrong"
        assert output.answers == []
        assert output.cancelled is False
        assert output.timed_out is False
        assert output.success is False

    def test_cancelled_response_factory(self) -> None:
        """cancelled_response creates proper cancelled output."""
        output = AskUserQuestionOutput.cancelled_response()
        assert output.cancelled is True
        assert output.error is None  # Cancellation is not an error
        assert output.answers == []
        assert output.timed_out is False
        assert output.success is False

    def test_timeout_response_factory(self) -> None:
        """timeout_response creates proper timeout output."""
        output = AskUserQuestionOutput.timeout_response(300)
        assert output.timed_out is True
        assert output.cancelled is False
        assert output.answers == []
        assert "300" in output.error  # Error message includes timeout value
        assert output.success is False
