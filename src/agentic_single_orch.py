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

class TravelWorkflowAgent(ChatCompletionAgent):
    def __init__(self, kernel: Kernel, name: str, instructions: str):
        super().__init__(
            name=name, 
            instructions=instructions, 
            service=azure_chat_service
        )
        # Initialize the internal orchestration with the sequential agents
        self._kernel = Kernel
        self._sequential_orchestration = SequentialOrchestration(
                                            members=get_sequential_agents(kernel),
                                            agent_response_callback=lambda msg: print(f"\n--- Sequential Agent: {msg.name} ---\n{msg.content}"),
                                            # human_response_function=lambda: ChatMessageContent(role=AuthorRole.USER, content=input("Human Input Required: "))
                                        )
        self._runtime = InProcessRuntime() # Each agent can have its own runtime, or share one

def get_sequential_agents(kernel: Kernel):
    """
    Create a list of sequential agents for the ExpertTravelAgent's internal orchestration.
    Each agent will handle a specific part of the order verification process.
    """

    # Create the Travel Agent
    travel_kernel = kernel
    travel_kernel.add_service(azure_chat_service)
    travel_agent = ChatCompletionAgent(
        kernel=travel_kernel,
        name="TravelAgent",
        instructions="You are a travel assistant. Use your general knowledge to provide travel advice, destination information, and answer travel-related questions for the user.",
    )

    # Create the Summarizer Agent
    summarizer_agent = ChatCompletionAgent(
        kernel=kernel, # No plugins needed, it relies on instructions
        service=azure_chat_service,
        name="SummarizerAgent",
        instructions="You are a summarization expert. Take the provided text and create a concise, one-sentence summary.",
    )

    # Create the Weather Agent
    weather_agent = ChatCompletionAgent(
        kernel=kernel, # No plugins needed, it relies on instructions
        service=azure_chat_service,
        name="WeatherAgent",
        instructions=(
            "You are a weather expert. Provide the current weather for the destination, if available. "
            "Current and season average temperatures should be in both Celsius and Fahrenheit, and weather advisories should be included."
        )
    )
    
    return [travel_agent, summarizer_agent, weather_agent]

def get_individual_agents():
    # --- Agent Creation ---

    # Create the Support Agent (Customer Support)
    # This agent's only job is to greet the user
    support_kernel = Kernel()
    support_kernel.add_service(azure_chat_service)
    support_agent = ChatCompletionAgent(
        kernel=support_kernel, # No plugins needed for this simple router
        name="SupportAgent",
        instructions=(
            "You are a curteous agent who greets the user and introduce the service as a hub for information related to travel information and sport trivia. "
            "You are also politely communicating with the user when his topics are neither related to travel or sport. "
        ),
    )

    # Create the Triage Agent (Router)
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
        ),
    )

    # Your custom agent that wraps the sequential orchestration
    travel_workflow_agent = TravelWorkflowAgent(
        kernel=Kernel(),
        name="TravelWorkflowAgent",
        instructions=(
            "You are a travel assistant. Use your general knowledge to provide travel advice, destination information, and answer travel-related questions for the user."
            "You will also provide a summary of your findings."
            "At the end of your message add up weather information for the destination, if available. "
        )
    )

    # Create the Sport Agent
    sport_kernel = Kernel()
    sport_kernel.add_service(azure_chat_service)
    sport_agent = ChatCompletionAgent(
        kernel=sport_kernel,
        name="SportAgent",
        instructions="You are a sports expert. Your job is to provide information, facts, and answer questions about sports to the user.",
    )
    return support_agent, triage_agent, travel_workflow_agent, sport_agent

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
                "agents": [travel_workflow_agent],
                "description": "Provide travel advice, summary and weather information based on the destinations provided in the users's query."
            },
            "SPORT": {
                "agents": [sport_agent],
                "description": "Provide sports information or answer sports-related questions."
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
            sorry_message = await get_support_message("Explain the user that you cannot handle his request.")
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
async def get_support_message(instruction: str = None):
    welcome_prompt = instruction
    welcome_history = ChatHistory(messages=[{"role": "user", "content": welcome_prompt}])
    welcome_msg = ""
    async for message in support_agent.invoke(welcome_history):
        welcome_msg += str(message.content)
    return welcome_msg

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

    # Get the agents
    support_agent,triage_agent, travel_workflow_agent, sport_agent = get_individual_agents()
    if not all([support_agent,triage_agent, travel_workflow_agent, sport_agent]):
        print("--- Error: One or more agents could not be created.")
        sys.exit(1)

    # Print the welcoming message before starting the loop
    print("--- System: Getting welcoming message from SupportAgent...")
    welcome_message = asyncio.run(get_support_message("Greet the user and explain you can help with travel or sports questions."))
    print(f"System: {welcome_message}")
    asyncio.run(main())