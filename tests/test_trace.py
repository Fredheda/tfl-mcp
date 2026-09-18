from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tfl_status_agent.trace import RESULT_MAX_CHARS, final_answer_text, trace_lines


def _tool_call_message(**extra) -> AIMessage:
    return AIMessage(
        content=extra.pop("content", ""),
        tool_calls=[
            {
                "name": "get_tfl_status",
                "args": {"lines": ["victoria", "central"]},
                "id": "call_1",
            }
        ],
        **extra,
    )


def test_reasoning_then_tool_call_in_order_normalized_shape():
    message = _tool_call_message(
        content=[{"type": "reasoning", "id": "rs_1", "reasoning": "User wants two lines."}],
        response_metadata={"model_provider": "openai", "output_version": "responses/v1"},
    )
    assert trace_lines({"model": {"messages": [message]}}) == [
        ("reasoning", "User wants two lines."),
        ("tool_call", "Calling get_tfl_status(victoria, central)"),
    ]


def test_reasoning_raw_responses_shape_is_read_from_summary():
    message = _tool_call_message(
        content=[
            {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [{"type": "summary_text", "text": "Checking both lines."}],
            }
        ],
    )
    assert trace_lines({"model": {"messages": [message]}})[0] == (
        "reasoning",
        "Checking both lines.",
    )


def test_tool_call_without_args_renders_empty_parens():
    message = AIMessage(
        content="",
        tool_calls=[{"name": "get_disrupted_lines", "args": {}, "id": "call_2"}],
    )
    assert trace_lines({"model": {"messages": [message]}}) == [
        ("tool_call", "Calling get_disrupted_lines()")
    ]


def test_tool_result_is_named_and_truncated():
    long = "x" * (RESULT_MAX_CHARS + 50)
    message = ToolMessage(content=long, tool_call_id="call_1", name="get_tfl_status")
    [(kind, text)] = trace_lines({"tools": {"messages": [message]}})
    assert kind == "tool_result"
    assert text.startswith("get_tfl_status → " + "x" * RESULT_MAX_CHARS)
    assert text.endswith("…")
    assert "x" * (RESULT_MAX_CHARS + 1) not in text


def test_final_answer_message_yields_answering():
    message = AIMessage(content="Victoria line: Good Service.")
    assert trace_lines({"model": {"messages": [message]}}) == [
        ("answering", "Composing answer")
    ]


def test_non_message_updates_and_human_messages_are_ignored():
    assert trace_lines(None) == []
    assert trace_lines({"model": None}) == []
    assert trace_lines({"model": {"messages": [HumanMessage(content="hi")]}}) == []
    assert trace_lines({"some_node": {"other_key": 1}}) == []


def test_final_answer_text_returns_text_of_last_plain_ai_message():
    plain = AIMessage(content="Victoria line: Good Service.")
    assert final_answer_text({"model": {"messages": [plain]}}) == "Victoria line: Good Service."
    assert final_answer_text({"model": {"messages": [_tool_call_message()]}}) is None
    assert final_answer_text({"tools": {"messages": [ToolMessage(content="x", tool_call_id="c")]}}) is None
    assert final_answer_text(None) is None
