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
    def __init__(self, kernel: Kernel, name: str, instructions: str, service):
        super().__init__(
            name=name, 
            instructions=instructions, 
            service=service
        )
        # Initialize the internal orchestration with the sequential agents
        self._kernel = Kernel
        self._sequential_orchestration = SequentialOrchestration(
                                            members=get_sequential_agents(kernel,service),
                                            agent_response_callback=lambda msg: print(f"\n--- Sequential Agent: {msg.name} ---\n{msg.content}"),
                                            # human_response_function=lambda: ChatMessageContent(role=AuthorRole.USER, content=input("Human Input Required: "))
                                        )
        self.service = service  # Use the Azure service for this agent
        self._runtime = InProcessRuntime() # Each agent can have its own runtime, or share one

def get_sequential_agents(kernel: Kernel,service):
    """
    Create a list of sequential agents for the ExpertTravelAgent's internal orchestration.
    Each agent will handle a specific part of the order verification process.
    """

    # Create the Travel Agent
    travel_agent = ChatCompletionAgent(
        kernel=kernel,
        name="TravelSpecialist",
        instructions="You are a travel assistant. Use your general knowledge to provide travel advice, destination information, and answer travel-related questions for the user.",
    )
    
    # Create the Weather Agent
    weather_agent = ChatCompletionAgent(
        kernel=kernel, # No plugins needed, it relies on instructions
        service=service,
        name="WeatherSpecialist",
        instructions=(
            "You are a weather expert. Provide the current weather for the destination, if available. "
            "Current and season average temperatures should be in both Celsius and Fahrenheit, and weather advisories should be included."
        )
    )

    # Create the Enetrtainment Agent
    entertainment_agent = ChatCompletionAgent(
        kernel=kernel, # No plugins needed, it relies on instructions
        service=service,
        name="EntertainmentSpecialist",
        instructions=(
            "You are an expert in entertainment related activities and events."
            "Mention the most popular events, festivals, and cultural activities that a tourist should not miss, all related to the travel destination."
        )
    )

    # Create the Summarizer Agent
    summarizer_agent = ChatCompletionAgent(
        kernel=kernel, # No plugins needed, it relies on instructions
        service=service,
        name="SynopsisSpecialist",
        instructions="You are a summarization expert. Take the provided text and create a concise, one-sentence summary.",
    )

    
    return [travel_agent, weather_agent,entertainment_agent, summarizer_agent]

def get_handoff_agents(service):
    # --- Agent Creation ---

    # Create the Support Agent (Customer Support)
    # This agent's only job is to greet the user
    support_kernel = Kernel()
    support_kernel.add_service(service)
    support_agent = ChatCompletionAgent(
        kernel=support_kernel, # No plugins needed for this simple router
        name="SupportAgent",
        instructions=(
            "If user intent is travel information or flights route the user query to the appropriate agent. "
            # "You will also greet the user and explain that you can help with travel or sports questions. "
            "Otherwise, explain that you cannot handle the request. "
        ),
    )

    # Create the Triage Agent (Router)
    # This agent's only job is to classify the user's intent.
    triage_kernel = Kernel()
    triage_kernel.add_service(service)
    triage_agent = ChatCompletionAgent(
        kernel=triage_kernel, # No plugins needed for this simple router
        name="TripAdvisor",
        instructions=(
            "You are a request router. Analyze the user's query and extract his intent: "
            " - if user query is about travel information, destination, tips and budgets, transfer the user query to travel_workflow_agent. "
            " = do not transfer to travel_workflow_agent if the user query is about flights, as this is handled by flight_agent. "
            " - if user query is about sport topics, events, trivia, transfer the user query to sport_agent. "
            " - if user query is about flights to the travel destination, transfer the user query to flight_agent. "
            "For any other intent, transfer the user query to support_agent with a polite message explaining that you cannot handle the request."
        ),
        service=service
    )

    # Your custom agent that wraps the sequential orchestration
    travel_workflow_kernel = Kernel()
    travel_workflow_kernel.add_service(service)
    travel_workflow_agent = TravelWorkflowAgent(
        kernel=travel_workflow_kernel,
        name="TravelInfoCoordinator",
        instructions=(
            "You are a travel assistant. Use your general knowledge to provide travel advice, destination information, and answer travel-related questions for the user."
            "You will also provide a summary of your findings."
            "At the end of your message add up weather information for the destination, if available. "
            "Do not provide any information unless it is strictly related to travel destinations, tips, or budgets."
            "If the user query is not related to travel, route the query to support_agent."
        ),
        service=service
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

    # Define handoff relationships
    handoffs = (
        OrchestrationHandoffs()
        .add_many(
            source_agent=support_agent.name,
            target_agents={
                triage_agent.name: "Transfer to this agent for analyzing user intent",
                travel_workflow_agent.name: "Transfer to this agent if the user requires travel assistance",
                sport_agent.name: "Transfer to this agent if the user requires sports assistance",
            },
        )
        .add(
            source_agent=triage_agent.name,
            target_agent=support_agent.name,
            description="Transfer to this agent if the user query is not related to travel or sport",
        )
        .add(
            source_agent=travel_workflow_agent.name,
            target_agent=support_agent.name,
            description="Transfer to this agent if the user query is not related to travel assistance",
        )
        .add(
            source_agent=sport_agent.name,
            target_agent=support_agent.name,
            description="Transfer to this agent if the user query is not related to sports assistance",
        )
        .add(
            source_agent=flight_agent.name,
            target_agent=support_agent.name,
            description="Transfer to this agent if the user query is not related to flights assistance",
        )
    )

    return [support_agent, triage_agent, travel_workflow_agent, sport_agent, flight_agent], handoffs

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

async def run_handoff_orchestration(service):
    """Main function to run the agents."""
        
    # 1. Create a handoff orchestration with multiple agents# 1. Get the handoff agents and handoffs
    # This function should return the agents and handoffs defined in get_handoff_agents()
    handoff_agents, handoffs = get_handoff_agents(service)
    handoff_orchestration = HandoffOrchestration(
        members=handoff_agents,
        handoffs=handoffs,
        agent_response_callback=agent_response_callback,
        # Optional: If you want to observe the agent responses, you can use this callback
        # agent_response_callback=lambda msg: print(f"\n--- Handoff Agent: {msg.name} ---\n{msg.content}"),
        human_response_function=human_response_function,
        # For HandoffOrchestration, you often need a human_response_function
        # if the agents might need to ask the user clarifying questions.
        # For this example, we'll keep it simple and assume no direct human input after initial prompt.
        # If an agent explicitly requests human input, it might hang without this.
        # human_response_function=lambda: ChatMessageContent(role=AuthorRole.USER, content=input("Human Input Required: "))
    )

    # 2. Create a runtime and start it
    runtime = InProcessRuntime()
    runtime.start()

    # 3. Invoke the orchestration with a task and the runtime
    orchestration_result = await handoff_orchestration.invoke(
        task="Greet the customer who is reaching out for support.",
        runtime=runtime,
    )

    # 4. Wait for the results
    final_response = await orchestration_result.get() # Increased timeout for nested orchestration
    print(f"\n***** Final Handoff Response *****\n{final_response}")

     # 5. Stop the runtime after the invocation is complete
    print("--- Stopping Handoff Orchestration...")
    await runtime.stop_when_idle()
    print("--- Handoff Orchestration ended.")

async def run_groupchat_orchestration(service):
    """Function to run a GroupChat orchestration with SupportAgent and FlightAgent."""
    # Get the handoff agents (reuse the creation logic)
    handoff_agents, _ = get_handoff_agents(service)
    # Extract support_agent and flight_agent by name
    support_agent = next(agent for agent in handoff_agents if agent.name == "SupportAgent")
    flight_agent = next(agent for agent in handoff_agents if agent.name == "FlightSpecialist")

    # Create the group chat orchestration
    groupchat = AgentGroupChat(
        members=[support_agent, flight_agent],
        agent_response_callback=agent_response_callback,
        human_response_function=human_response_function,
    )

    runtime = InProcessRuntime()
    runtime.start()

    # Example task for the group chat
    orchestration_result = await groupchat.invoke(
        task="A user wants to book a flight and needs support with the booking process.",
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

    # Run the handoff orchestration
    print("--- Starting Handoff Orchestration with Azure OpenAI Service ---")
    asyncio.run(run_handoff_orchestration(azure_chat_service))

    # Run the group chat orchestration
    print("--- Starting GroupChat Orchestration with SupportAgent and FlightAgent ---")
    asyncio.run(run_groupchat_orchestration(azure_chat_service))

""" 
Sample Queries for Testing the Agents
These queries can be used to test the agents in the orchestration.

I am working at a historical essay about big social movements, and I need to know who was the French king killed during 1789 French Revolution.
I'd like to know which national team won the highest number of World Cups and when.
What is fusion and how can be used for producing cheap energy?
I would like to travel to Romania in December 2025. What kind of objectives I can see?
I would like to know which team has scored the highest number of goals ever in English Premier League (EPL) and during which season.
Is it safe to visit Kenia on your own as a North-American tourist?
"""
# End of file