from unittest.mock import AsyncMock, MagicMock, patch

from a2a.types import TaskState
from langchain_core.messages import AIMessage, ToolMessage

from tfl_status_agent.agent import GraphHolder
from tfl_status_agent.agent_executor import TflStatusAgentExecutor


def _executor_with_updates(updates: list[dict]) -> tuple[TflStatusAgentExecutor, dict]:
    seen: dict = {}

    async def fake_astream(*_args, **kwargs):
        seen["kwargs"] = kwargs
        for update in updates:
            yield update

    fake_graph = MagicMock()
    fake_graph.astream = fake_astream
    holder = GraphHolder()
    holder.graph = fake_graph
    return TflStatusAgentExecutor(holder), seen


def _context() -> MagicMock:
    context = MagicMock()
    context.current_task = MagicMock()  # task already exists -- skip enqueue path
    context.task_id = "task-1"
    context.context_id = "ctx-1"
    context.get_user_input.return_value = "victoria line status"
    return context


def _patched_updater():
    patcher = patch("tfl_status_agent.agent_executor.TaskUpdater")
    mock_cls = patcher.start()
    updater = mock_cls.return_value
    updater.start_work = AsyncMock()
    updater.update_status = AsyncMock()
    updater.add_artifact = AsyncMock()
    updater.complete = AsyncMock()
    updater.new_agent_message = MagicMock(side_effect=lambda parts, metadata=None: ("msg", parts))
    return patcher, updater


async def test_execute_streams_trace_lines_then_artifact_then_complete():
    executor, seen = _executor_with_updates(
        [
            {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {"name": "get_tfl_status", "args": {"lines": ["victoria"]}, "id": "c1"}
                            ],
                        )
                    ]
                }
            },
            {
                "tools": {
                    "messages": [
                        ToolMessage(content="Victoria: Good Service", tool_call_id="c1", name="get_tfl_status")
                    ]
                }
            },
            {"model": {"messages": [AIMessage(content="Victoria line: Good Service.")]}},
        ]
    )
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()
    patcher, updater = _patched_updater()
    try:
        await executor.execute(_context(), event_queue)
    finally:
        patcher.stop()

    assert seen["kwargs"]["stream_mode"] == "updates"
    assert seen["kwargs"]["config"] == {"configurable": {"thread_id": "ctx-1"}}

    kinds = [call.kwargs["metadata"]["kind"] for call in updater.update_status.await_args_list]
    assert kinds == ["tool_call", "tool_result", "answering"]
    for call in updater.update_status.await_args_list:
        assert call.args[0] == TaskState.TASK_STATE_WORKING
        assert call.kwargs["message"][0] == "msg"  # built via updater.new_agent_message

    updater.add_artifact.assert_awaited_once()
    artifact_parts = updater.add_artifact.await_args.args[0]
    assert artifact_parts[0].text == "Victoria line: Good Service."
    assert updater.add_artifact.await_args.kwargs["name"] == "tfl_status"
    updater.complete.assert_awaited_once()

    # Order: start_work, updates..., artifact, complete
    order = [name for name, *_ in updater.mock_calls if name in {"start_work", "update_status", "add_artifact", "complete"}]
    assert order == ["start_work", "update_status", "update_status", "update_status", "add_artifact", "complete"]


async def test_execute_enqueues_task_when_none_exists():
    executor, _ = _executor_with_updates(
        [{"model": {"messages": [AIMessage(content="No tools loaded.")]}}]
    )
    context = _context()
    context.current_task = None
    context.message = MagicMock()
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()
    patcher, updater = _patched_updater()
    try:
        with patch("tfl_status_agent.agent_executor.new_task_from_user_message", return_value="new-task") as new_task:
            await executor.execute(context, event_queue)
    finally:
        patcher.stop()

    new_task.assert_called_once_with(context.message)
    event_queue.enqueue_event.assert_awaited_once_with("new-task")
    updater.add_artifact.assert_awaited_once()
