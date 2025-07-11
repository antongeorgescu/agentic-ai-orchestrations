import asyncio
import os, sys
from typing import Annotated

from semantic_kernel.agents import Agent, ChatCompletionAgent, SequentialOrchestration, HandoffOrchestration, OrchestrationHandoffs, GroupChatOrchestration
from semantic_kernel.agents.orchestration.group_chat import BooleanResult, RoundRobinGroupChatManager,AIManager
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion # or OpenAIChatCompletion
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.contents import ChatHistory
from semantic_kernel.agents import AgentGroupChat # for group chat
from semantic_kernel.contents import ChatMessageContent, AuthorRole, FunctionCallContent, FunctionResultContent
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function # for custom agent's skill

# Ensure compatibility with Python 3.12+ for the override decorator
if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover

class CustomRoundRobinGroupChatManager(RoundRobinGroupChatManager):
    """Custom round robin group chat manager to enable user input."""

    @override
    async def should_request_user_input(self, chat_history: ChatHistory) -> BooleanResult:
        """Override the default behavior to request user input after the reviewer's message.

        The manager will check if input from human is needed after each agent message.
        """
        if len(chat_history.messages) == 0:
            return BooleanResult(
                result=False,
                reason="No agents have spoken yet.",
            )
        last_message = chat_history.messages[-1]
        # Request user input after the SupportAgent's message to ensure the user gets a turn
        if last_message.name == "SupportAgent":
            print("CustomRoundRobinGroupChatManager: Requesting user input after SupportAgent.")
            return BooleanResult(
                result=True,
                reason="User input is needed after the SupportAgent's initial greeting.",
            )
        # Request user input after any specialist agent's message
        elif last_message.name in ["WeatherSpecialist", "SportSpecialist", "FlightSpecialist"]:
             print(f"CustomRoundRobinGroupChatManager: Requesting user input after {last_message.name}.")
             return BooleanResult(
                 result=True,
                 reason=f"User input is needed after {last_message.name}'s response.",
             )


        print(f"CustomRoundRobinGroupChatManager: Not requesting user input after {last_message.name}.")
        return BooleanResult(
                result=False,
                reason="User input is not needed if the last message is not from a recognized agent.",
            )
        

def get_groupchat_agents(service):
    # --- Agent Creation ---

    # Create the Support Agent (Customer Support)
    # This agent's only job is to greet the user
    support_kernel = Kernel()
    support_kernel.add_service(service)
    support_agent = ChatCompletionAgent(
        kernel=support_kernel, # No plugins needed for this simple router
        name="SupportAgent",
        description="Welcomes the user and asks them about their interest.",
        instructions=(
            "You are a specialized agent in customer support. "
            "Greet the user and ask them about their travel interests, including destination, preferred season, and any specific activities like sports events or flight booking needs. "
            "Once the user provides their initial request, yield the turn to the appropriate specialist agent (WeatherSpecialist, SportSpecialist, or FlightSpecialist) based on the user's stated interests. "
            "Do not try to answer questions related to weather, sports, or flights yourself."
        ),
    )

    # Create the Weather Agent
    weather_kernel = Kernel()
    weather_kernel.add_service(service)
    weather_agent = ChatCompletionAgent(
        kernel=weather_kernel, # No plugins needed, it relies on instructions
        service=service,
        name="WeatherSpecialist",
        description="Provides current weather information including temperature and advisories.",
        instructions=(
            "You are a weather expert. Provide the current weather for the destination, if available. "
            "Current and season average temperatures should be in both Celsius and Fahrenheit, and weather advisories should be included. "
            "Only respond to queries specifically about weather. For any other queries do not output any weather information. "
            "If the user query is about flights, flight booking, explicitly state that you cannot help with that and yield the turn to the FlightSpecialist explaining the user that you transfer to a flight agent. "
            "If the user query is about sports events or sports-related topics, explicitly state that you cannot help with that and yield the turn to the SportSpecialist. "
            "If the user query is not related to sports, weather, or flights, send a polite message back to the user and yield the turn to the SupportAgent."
        )
    )

    # Create the Sport Agent
    sport_kernel = Kernel()
    sport_kernel.add_service(service)
    sport_agent = ChatCompletionAgent(
        kernel=sport_kernel,
        name="SportSpecialist",
        description="Provides information and answers questions about sports.",
        instructions=(
            "You are a sports expert. Your job is to provide information, facts, and answer questions about sport events related to the travel destination. "
            "Only respond to queries specifically about sports events or sports-related topics. "
            "If the user query is about flights, flight booking, or travel arrangements, explicitly state that you cannot help with that and  yield the turn to the FlightSpecialist. "
            "If the user query is about weather, explicitly state that you cannot help with that and yield the turn to the WeatherSpecialist. "
            "If the user query is not related to sports, weather, or flights, send a polite message back to the user and yield the turn to the SupportAgent."
        ),
        service=service
    )

    # Create the Flight Agent
    flight_kernel = Kernel()
    flight_kernel.add_service(service)
    flight_agent = ChatCompletionAgent(
        kernel=flight_kernel,
        name="FlightSpecialist",
        description="Provides details about available flights to a destination.",
        instructions=(
            "You are a flights expert. Your job is to provide full details about flights available to the travel destination."
            "If user did not provide the departure location, ask for it. "
            "Only respond to queries specifically about flights or flight booking. "
            "If the user query is about weather, explicitly state that you cannot help with that and yield the turn to the WeatherSpecialist. "
            "If the user query is about sports events or sports-related topics, explicitly state that you cannot help with that and yield the turn to the SportSpecialist. "
            "If the user query is not related to flights, weather, or sports, send back a polite message to the user and yield the turn to the SupportAgent."
        ),
        service=service
    )

    return support_agent, weather_agent, sport_agent, flight_agent

def agent_response_callback(message: ChatMessageContent) -> None:
    """Observer function to print the messages from the agents."""
    # print(f"**{message.name}**\n{message.content}")
    """Observer function to print the messages from the agents.

    Please note that this function is called whenever the agent generates a response,
    including the internal processing messages (such as tool calls) that are not visible
    to other agents in the orchestration.
    """
    print(f"{message.name}: {message.content}")
    for item in message.items:
        if isinstance(item, FunctionCallContent):
            print(f"Calling '{item.name}' with arguments '{item.arguments}'")
        if isinstance(item, FunctionResultContent):
            print(f"Result from '{item.name}' is '{item.result}'")


async def human_response_function(chat_histoy: ChatHistory) -> ChatMessageContent:
    """Function to get user input."""
    user_input = input("User: ")
    return ChatMessageContent(role=AuthorRole.USER, content=user_input)


async def run_groupchat_orchestration(service):
    """Function to run a GroupChat orchestration with SupportAgent, WeatherSpecialist, SportSpecialist and FlightSpecialist."""
    
    # 1. Create a group chat orchestration with a round robin manager
    support_agent, weather_agent, sport_agent, flight_agent = get_groupchat_agents(service)
    group_chat_orchestration = GroupChatOrchestration(
        members=[support_agent, flight_agent],
        manager=CustomRoundRobinGroupChatManager(
            # max_rounds=9,
            max_rounds_per_agent=9,
            human_response_function=human_response_function,
        ),
        agent_response_callback=agent_response_callback,
    )

    # 2. Create a runtime and start it
    runtime = InProcessRuntime()
    runtime.start()

    # 3. Invoke the orchestration with a task and the runtime
    orchestration_result = await group_chat_orchestration.invoke(
        # task="A user wants to travel to a destination, during the warm season to watch a few sport events. He also looks to book a flight and needs support with the booking process.",
        task="A user wants to travel to a destination and book a flight.",
        runtime=runtime,
    )

    # 4. Wait for the results
    final_response = await orchestration_result.get()
    print(f"\n***** Final GroupChat Response *****\n{final_response}")

    # 5. Stop the runtime after the invocation is complete
    print("--- Stopping GroupChat Orchestration...")
    await runtime.stop_when_idle()
    print("--- GroupChat Orchestration ended.")

if __name__ == "__main__":
    # --- Azure OpenAI Configuration ---
    azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    azure_deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

    # --- Kernel and Service Setup ---
    azure_chat_service = AzureChatCompletion(
        service_id="chat-gpt",
        api_key=azure_api_key,
        endpoint=azure_endpoint,
        deployment_name=azure_deployment_name,
    )

    if not all([azure_api_key, azure_endpoint, azure_deployment_name]):
        print("Error: Azure OpenAI environment variables not set.")
        sys.exit(1)

    # Run the group chat orchestration
    print("--- Starting GroupChat Orchestration with WeatherSpecialist, SportSpecialist and FlightSpecialist ---")
    asyncio.run(run_groupchat_orchestration(azure_chat_service))

"""
Sample Queries for Testing the Agents
These queries can be used to test the agents in the orchestration.

I would like to visit Romania in summer and watch some football matches.
What is the weather like in Romania in summer?
Can you tell me about the sports events in Romania during summer?
What flights are available from London to Romania in summer?
"""
# End of file