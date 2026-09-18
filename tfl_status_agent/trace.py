"""Turns LangGraph `stream_mode="updates"` chunks into human-readable trace lines.

The A2A executor streams these to the caller as task status updates while
the graph runs. Deliberately independent of graph node names: every node
update is scanned for messages, so a renamed or added node (middleware,
a second tool node) can't silently mute the trace.
"""

from langchain_core.messages import AIMessage, ToolMessage

RESULT_MAX_CHARS = 200

TraceLine = tuple[str, str]  # (kind, text)


def trace_lines(update: object) -> list[TraceLine]:
    """Returns (kind, text) pairs for every message in one graph update.

    kind is one of "reasoning", "tool_call", "tool_result", "answering".
    Non-dict updates, nodes without a `messages` key, and non-AI/tool
    messages produce nothing.
    """
    lines: list[TraceLine] = []
    for message in _messages_in(update):
        if isinstance(message, ToolMessage):
            lines.append(("tool_result", _tool_result_text(message)))
        elif isinstance(message, AIMessage):
            lines.extend(_ai_message_lines(message))
    return lines


def final_answer_text(update: object) -> str | None:
    """Text of the last AIMessage in `update` that carries no tool calls --
    i.e. the model's final answer -- or None if this update has none."""
    answer: str | None = None
    for message in _messages_in(update):
        if isinstance(message, AIMessage) and not message.tool_calls:
            answer = message.text
    return answer


def _messages_in(update: object) -> list:
    if not isinstance(update, dict):
        return []
    messages: list = []
    for node_update in update.values():
        if isinstance(node_update, dict):
            messages.extend(node_update.get("messages") or [])
    return messages


def _ai_message_lines(message: AIMessage) -> list[TraceLine]:
    lines: list[TraceLine] = [("reasoning", text) for text in _reasoning_texts(message)]
    if message.tool_calls:
        for call in message.tool_calls:
            lines.append(("tool_call", f"Calling {call['name']}({_format_args(call.get('args') or {})})"))
    else:
        lines.append(("answering", "Composing answer"))
    return lines


def _reasoning_texts(message: AIMessage) -> list[str]:
    texts: list[str] = []
    for block in message.content_blocks:
        if not isinstance(block, dict) or block.get("type") != "reasoning":
            continue
        # Normalized LangChain shape (model_provider set) puts the text
        # under "reasoning"; the raw OpenAI Responses shape nests it in
        # summary[].text. Both are seen depending on how the message was
        # constructed, so read whichever is present.
        text = block.get("reasoning") or " ".join(
            part.get("text", "")
            for part in block.get("summary") or []
            if isinstance(part, dict) and part.get("text")
        )
        if text and text.strip():
            texts.append(text.strip())
    return texts


def _format_args(args: dict) -> str:
    values: list[str] = []
    for value in args.values():
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return ", ".join(values)


def _tool_result_text(message: ToolMessage) -> str:
    content = message.text.strip()
    if len(content) > RESULT_MAX_CHARS:
        content = content[:RESULT_MAX_CHARS] + "…"
    return f"{message.name or 'tool'} → {content}"
