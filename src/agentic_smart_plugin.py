import asyncio
import os, sys
from typing import Annotated

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion # or OpenAIChatCompletion
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents import ChatMessageContent, AuthorRole, FunctionCallContent, FunctionResultContent
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function # for custom agent's skill
from serpapi import GoogleSearch


class FlightSearch:
    @kernel_function(
        description="Searches for flights based on departure, destination, and date.",
        name="search_flights",
    )
    def search_flights(
        self,
        departure: Annotated[str, "The departure airport or city."],
        destination: Annotated[str, "The destination airport or city."],
        date: Annotated[str, "The date of travel (YYYY-MM-DD)."]
    ) -> Annotated[str, "A JSON string containing flight information."]:
        """
        Searches for flights using the SerpApi Google Flights API.
        """
        params = {
            "engine": "google_flights",
            "departure_id": departure,
            "arrival_id": destination,
            "outbound_date": date,
            "api_key": os.environ.get("SERPAPI_API_KEY") # Make sure to set SERPAPI_API_KEY in your environment variables
        }

        search = GoogleSearch(params)
        results = search.get_dict()

        # You can process the results further if needed
        return str(results)


def get_travel_agent(service):
    """
    Create the Travel Agent.
    """
    travel_kernel = Kernel()
    travel_kernel.add_service(service)
    travel_agent = ChatCompletionAgent(
        kernel=travel_kernel,
        name="TravelAgent",
        instructions="You are a travel assistant. Use your general knowledge to provide travel advice, destination information, and answer travel-related questions for the user. You have access to a flight search tool.",
        service=service
    )
    # Add the FlightSearch plugin to the TravelAgent's kernel
    travel_agent.kernel.add_plugin(FlightSearch(), plugin_name="FlightSearchPlugin")

    return travel_agent


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

# Modified function to run the single TravelAgent
async def run_single_agent(service):
    """Main function to run the single TravelAgent."""

    # 1. Get the Travel Agent
    travel_agent = get_travel_agent(service)

    # 2. Create a runtime and start it
    runtime = InProcessRuntime()
    runtime.start()

    print("--- Starting Single Travel Agent ---")

    # 3. Start a chat session with the agent
    chat_history = ChatHistory()
    chat_history.add_user_message("Hello, I need some assistance with travel.")

    # 4. Get the initial response from the agent
    initial_response = await travel_agent.get_response(chat_history)
    print(f"\n{initial_response.name}: {initial_response.content}")
    # Ensure the response is a ChatMessageContent with a role before adding to history
    if isinstance(initial_response, ChatMessageContent) and initial_response.role:
         chat_history.add_message(initial_response)
    else:
         # If the response is not a ChatMessageContent or lacks a role, create one
         chat_history.add_message(ChatMessageContent(role=AuthorRole.ASSISTANT, content=str(initial_response.content)))


    # 5. Continue the conversation (optional loop for interactive chat)
    print("\n--- Start interactive chat with Travel Agent (type 'quit' to exit) ---")
    while True:
        user_input = input("User: ")
        if user_input.lower() == 'quit':
            break
        chat_history.add_user_message(user_input)
        response = await travel_agent.get_response(chat_history)
        print(f"\n{response.name}: {response.content}")
        # Ensure the response is a ChatMessageContent with a role before adding to history
        if isinstance(response, ChatMessageContent) and response.role:
             chat_history.add_message(response)
        else:
             # If the response is not a ChatMessageContent or lacks a role, create one
             chat_history.add_message(ChatMessageContent(role=AuthorRole.ASSISTANT, content=str(response.content)))


    # 6. Stop the runtime after the invocation is complete
    print("--- Stopping Single Travel Agent...")
    await runtime.stop_when_idle()
    print("--- Single Travel Agent ended.")


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

    # Run the single support agent
    print("--- Starting Single Travel Agent with Azure OpenAI Service ---")
    asyncio.run(run_single_agent(azure_chat_service))

"""
Sample Queries for Testing the Agents
These queries can be used to test the agents in the orchestration.

I'd like to know which national team won the highest number of World Cups and when.
What is fusion and how can be used for producing cheap energy?
I would like to travel to Romania in December 2025. What kind of objectives I can see?
Is it safe to visit Kenia on your own as a North-American tourist?
"""