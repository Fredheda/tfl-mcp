from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tfl_status_agent.agent import GraphHolder
from tfl_status_agent.agent_executor import TflStatusAgentExecutor


@pytest.mark.asyncio
async def test_execute_invokes_graph_and_completes_task():
    fake_graph = MagicMock()
    fake_graph.ainvoke = AsyncMock(
        return_value={"messages": [MagicMock(content="Victoria: Good Service")]}
    )
    holder = GraphHolder()
    holder.graph = fake_graph
    executor = TflStatusAgentExecutor(holder)

    context = MagicMock()
    context.current_task = MagicMock()  # task already exists -- skip enqueue path
    context.task_id = "task-1"
    context.context_id = "ctx-1"
    context.get_user_input.return_value = "victoria line status"

    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    with patch("tfl_status_agent.agent_executor.TaskUpdater") as MockUpdater:
        updater = MockUpdater.return_value
        updater.start_work = AsyncMock()
        updater.add_artifact = AsyncMock()
        updater.complete = AsyncMock()

        await executor.execute(context, event_queue)

    fake_graph.ainvoke.assert_awaited_once()
    updater.add_artifact.assert_awaited_once()
    updater.complete.assert_awaited_once()
