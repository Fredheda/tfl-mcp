"""A2A AgentExecutor wrapping the tfl-status LangGraph graph.

Takes a GraphHolder (tfl_status_agent.agent.GraphHolder) via its
constructor and reads `.graph` at call time, rather than importing a bound
`graph` name -- the graph is built asynchronously at FastAPI startup
(server.py's lifespan), after this module is first imported, so a
bound-name import would capture `None` permanently.
"""

from a2a.helpers import new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater

from tfl_status_agent.agent import GraphHolder


class TflStatusAgentExecutor(AgentExecutor):
    def __init__(self, graph_holder: GraphHolder) -> None:
        self.graph_holder = graph_holder

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        if context.current_task is None:
            # The framework requires an actual Task to be enqueued before any
            # TaskStatusUpdateEvent/TaskArtifactUpdateEvent for a new task.
            await event_queue.enqueue_event(
                new_task_from_user_message(context.message)
            )

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()

        user_input = context.get_user_input() or "What's the tube status?"
        result = await self.graph_holder.graph.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": context.context_id}},
        )
        answer = result["messages"][-1].content

        await updater.add_artifact([new_text_part(answer)], name="tfl_status")
        await updater.complete()

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()
