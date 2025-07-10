import asyncio
import os, sys
from typing import Annotated

from semantic_kernel.agents import Agent, ChatCompletionAgent, SequentialOrchestration, HandoffOrchestration, OrchestrationHandoffs
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion # or OpenAIChatCompletion
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.contents import ChatHistory
from semantic_kernel.agents import AgentGroupChat # for group chat
from semantic_kernel.contents import ChatMessageContent, AuthorRole, FunctionCallContent, FunctionResultContent
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function # for custom agent's skill
from semantic_kernel.agents import GroupChatOrchestration, RoundRobinGroupChatManager


def get_groupchat_agents(service):
    # --- Agent Creation ---

    # Create the Weather Agent
    weather_kernel = Kernel()
    weather_kernel.add_service(service)
    weather_agent = ChatCompletionAgent(
        kernel=weather_kernel, # No plugins needed, it relies on instructions
        service=service,
        name="WeatherSpecialist",
        instructions=(
            "You are a weather expert. Provide the current weather for the destination, if available. "
            "Current and season average temperatures should be in both Celsius and Fahrenheit, and weather advisories should be included."
        )
    )

    # Create the Sport Agent
    sport_kernel = Kernel()
    sport_kernel.add_service(service)
    sport_agent = ChatCompletionAgent(
        kernel=sport_kernel,
        name="SportSpecialist",
        instructions=(
            "You are a sports expert. Your job is to provide information, facts, and answer questions about sports to the user."
            "Do not provide any information unless it is strictly related to sports topics, events, or trivia."
            "If the user query is not related to sports, route the query to support_agent."
        ),
        service=service
    )

    # Create the Flight Agent
    flight_kernel = Kernel()
    flight_kernel.add_service(service)
    flight_agent = ChatCompletionAgent(
        kernel=flight_kernel,
        name="FlightSpecialist",
        instructions=(
            "You are a flights expert. Your job is to provide full details about flights available to the travel destination."
            "Do not provide any flights information that is not related to the travel destination."
            "If the user query is not related to flights, route the query to support_agent."
        ),
        service=service
    )

    return weather_agent, sport_agent, flight_agent

def agent_response_callback(message: ChatMessageContent) -> None:
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


def human_response_function() -> ChatMessageContent:
    """Observer function to print the messages from the agents."""
    user_input = input("User: ")
    return ChatMessageContent(role=AuthorRole.USER, content=user_input)

async def run_groupchat_orchestration(service):
    """Function to run a GroupChat orchestration with WeatherSpecialist, SportSpecialist and FlightSpecialist."""
    # Get the group chat agents
    weather_agent, sport_agent, flight_agent = get_groupchat_agents(service)
    
    # Create the group chat orchestration
    group_chat_orchestration = GroupChatOrchestration(
        members=[weather_agent, sport_agent, flight_agent],
        manager=RoundRobinGroupChatManager(max_rounds=5),  # Odd number so writer gets the last word
        agent_response_callback=agent_response_callback,
    )

    
    # groupchat = AgentGroupChat(
    #     members=[weather_agent, flight_agent, sport_agent],
    #     agent_response_callback=agent_response_callback,
    #     human_response_function=human_response_function,
    # )
    # groupchat.set_instructions(
    #     "You are a group of specialized agents. "
    #     "You will work together to answer the user's questions. "
    #     "If a question is not related to your expertise, let the user know in a polite way."
    # )

    runtime = InProcessRuntime()
    runtime.start()

    # Example task for the group chat
    orchestration_result = await group_chat_orchestration.invoke(
        task="A user wants travel to a destination, get the weather report, watch a few soccer games, and get information about available flights.",
        runtime=runtime,
    )

    final_response = await orchestration_result.get()
    print(f"\n***** Final GroupChat Response *****\n{final_response}")

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
    print("--- Starting GroupChat Orchestration with SupportAgent and FlightAgent ---")
    asyncio.run(run_groupchat_orchestration(azure_chat_service))

""" 
Sample Queries for Testing the Agents
These queries can be used to test the agents in the orchestration.

I'd like to travel to Romania in summer and watch some soccer games. Can you help me with that?
I need to know the typical weather in Bucharest during the month of July.
I want to book a flight from Toronto to Bucharest end of July or beginning of August. Can you assist me with that?
"""
# End of file