import asyncio
import os
from typing import Annotated

from semantic_kernel.agents import Agent, ChatCompletionAgent, SequentialOrchestration, HandoffOrchestration, OrchestrationHandoffs
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion # or OpenAIChatCompletion
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.contents import ChatHistory
from semantic_kernel.agents import AgentGroupChat # for group chat
from semantic_kernel.contents import ChatMessageContent, AuthorRole, FunctionCallContent, FunctionResultContent
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function # for custom agent's skill

def get_agents():
    # --- Azure OpenAI Configuration ---
    azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    azure_deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

    if not all([azure_api_key, azure_endpoint, azure_deployment_name]):
        print("Error: Azure OpenAI environment variables not set.")
        return

    # --- Kernel and Service Setup ---
    azure_chat_service = AzureChatCompletion(
        service_id="chat-gpt",
        api_key=azure_api_key,
        endpoint=azure_endpoint,
        deployment_name=azure_deployment_name,
    )

    # --- Agent Creation ---

    # 1. Create the Welcome Agent (Introducer)
    # This agent's only job is to greet the user
    welcome_kernel = Kernel()
    welcome_kernel.add_service(azure_chat_service)
    welcome_kernel = ChatCompletionAgent(
        kernel=welcome_kernel, # No plugins needed for this simple router
        name="WelcomeAgent",
        instructions=(
            "You are a curteous agent who greets the user and introduce the service as a hub for information related to travel information and sport trivia. "
            "You are also politely communicating with the user when his topics are neither related to travel or sport. "
        ),
    )

    # 2. Create the Triage Agent (Router)
    # This agent's only job is to classify the user's intent.
    triage_kernel = Kernel()
    triage_kernel.add_service(azure_chat_service)
    triage_agent = ChatCompletionAgent(
        kernel=triage_kernel, # No plugins needed for this simple router
        name="TriageAgent",
        instructions=(
            "You are a request router. Analyze the user's query and extract his intent: "
            " - if user query is about travel information, destination, tips and budgets, respond with the single word 'TRAVEL'. "
            " - if user query is about sport topics, events, trivia, respond with the single word 'SPORT'. "
            " - if user query is about flights and flight booking, respond with the single word 'FLIGHT'. "
        ),
    )

    # 3. Create the Travel Agent
    travel_kernel = Kernel()
    travel_kernel.add_service(azure_chat_service)
    travel_agent = ChatCompletionAgent(
        kernel=travel_kernel,
        name="TravelAgent",
        instructions="You are a travel assistant. Use your general knowledge to provide travel advice, destination information, and answer travel-related questions for the user.",
    )

    # 4. Create the Summarizer Agent
    summarizer_agent = ChatCompletionAgent(
        kernel=Kernel(), # No plugins needed, it relies on instructions
        service=azure_chat_service,
        name="SummarizerAgent",
        instructions="You are a summarization expert. Take the provided text and create a concise, one-sentence summary.",
    )

    # 5. Create the Sport Agent
    sport_kernel = Kernel()
    sport_kernel.add_service(azure_chat_service)
    sport_agent = ChatCompletionAgent(
        kernel=sport_kernel,
        name="SportAgent",
        instructions="You are a sports expert. Your job is to provide information, facts, and answer questions about sports to the user.",
    )

    # 6. Create the Flight Agent
    flight_agent = ChatCompletionAgent(
        kernel=Kernel(),
        service=azure_chat_service,
        name="FlightSpecialist",
        instructions=(
            "You are a flights expert. Your job is to provide full details about flights available to the travel destination."
            "If user did not provide the departure location, ask for it. "
            "Only respond to queries specifically about flights or flight booking. "
            "If the user asks about travel or sport topics, politely redirect them to the appropriate agent."
            "If the user asks about flights, you can also provide a summary of the flight details"
        ),
    )  
    return welcome_kernel, triage_agent, travel_agent, summarizer_agent, sport_agent, flight_agent

async def main():
    """
    Main function to run the agent handoff example with a welcoming/routing agent.
    """
    # --- Orchestration Logic ---
    async def run_orchestration(user_query: str):
        print(f"--- User Query > {user_query}\n")

        # Step 1: Invoke the Triage Agent to classify the user's intent
        print("--- Orchestrator > Invoking TriageAgent to classify request...")
        routing_history = ChatHistory(messages=[{"role": "user", "content": user_query}])
        route = ""
        async for message in triage_agent.invoke(routing_history):
            route += str(message.content).strip().upper()
        print(f"--- TriageAgent classified as > {route}\n")

        # Step 2: Semantic intent-based orchestration
        workflows = {
            "TRAVEL": {
                "agents": [travel_agent, summarizer_agent],
                "description": "Provide travel advice and summarize the user's query."
            },
            "SPORT": {
                "agents": [sport_agent],
                "description": "Provide sports information or answer sports-related questions."
            },
             "FLIGHT": {
                "agents": [flight_agent],
                "description": "Provide flight and flight booking information or answer flight-related questions."
            }
            # Add more intent-agent mappings here as needed
        }

        if route in workflows:
            print(f"--- Orchestrator > Starting '{route}' workflow: {workflows[route]['description']}")
            current_input = user_query
            for agent in workflows[route]["agents"]:
                print(f"--- Orchestrator > Invoking {agent.name}...")
                history = ChatHistory(messages=[{"role": "user", "content": current_input}])
                output = ""
                async for message in agent.invoke(history):
                    output += str(message.content)
                print(f"{agent.name} output:\n{output}\n")
                current_input = output  # Pass output to next agent if any
            if len(workflows[route]["agents"]) > 1:
                print(f"Final output:\n{current_input}")
        else:
            # print("Orchestrator > Sorry, I'm not sure how to handle that request.")
            sorry_message = await get_welcome_message("Explain the user that you cannot handle his request.")
            print(f"System: {sorry_message}")


    print("--- Starting looped conversation. Type 'exit' to quit.")
    while True:
        user_input = input("User: ")
        if user_input.lower() == 'exit':
            break

        try:
            # --- Run Examples ---
            await run_orchestration(user_input)
        
        except Exception as e:
            print(f"--- An error occurred: {e}")
            break

# --- Welcoming Message ---
async def get_welcome_message(instruction: str = None):
    welcome_prompt = instruction
    welcome_history = ChatHistory(messages=[{"role": "user", "content": welcome_prompt}])
    welcome_msg = ""
    async for message in welcome_kernel.invoke(welcome_history):
        welcome_msg += str(message.content)
    return welcome_msg

if __name__ == "__main__":
    # Get the agents
    welcome_kernel,triage_agent, travel_agent, summarizer_agent, sport_agent, flight_agent = get_agents()
    if not all([triage_agent, travel_agent, summarizer_agent, sport_agent, flight_agent]):
        print("--- Error: One or more agents could not be created.")
        import sys
        sys.exit(1)

    # Print the welcoming message before starting the loop
    print("--- System: Getting welcoming message from TriageAgent...")
    welcome_message = asyncio.run(get_welcome_message("Greet the user and explain you can help with travel or sports questions."))
    print(f"System: {welcome_message}")
    asyncio.run(main())