# src/lia/ateam.py
import asyncio
import inspect
from prompt_toolkit import PromptSession
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages, Agent
from lia.agent import load_agent, list_agents
from dataclasses import dataclass
from lia.agent_swarm import AgentSwarm
from lia.tools.python_execution_tool import create_python_executor_tool,AgentPythonExecutionError

@dataclass
class SwarmDeps:
    team: list[str]

class Reasoner:
    prompt = "(Reasoner) > "
    
    def __init__(self,options):
        self.options = options

        print(f"Model:\n\t{self.options.model_name}\n\t{self.options.llm_api_url}\n\t{self.options.llm_api_key}")
        self.default_model = OpenAIModel(
            model_name=self.options.model_name,
            base_url=self.options.llm_api_url,
            api_key=self.options.llm_api_key 
        )
        
        leader = load_agent('reasoning_agent', model=self.default_model,deps_type=SwarmDeps)
        self.swarm = AgentSwarm(leader=leader,model=self.default_model,deps_type=SwarmDeps,getDeps=self.getDeps,show_agent_messages=self.options.reasoning,debug=self.options.debug)
    
        agents = self.create_hemispheres(self.default_model)
    
    def getDeps(self,agent_name:str):
        deps = SwarmDeps(team=self.swarm.get_agent_names())
        return deps
    
    def create_hemispheres(self,model):
    
        self.swarm.register_agent(
            agent = Agent(model,name="Lefty",
                deps_type=SwarmDeps,
                tools=[create_python_executor_tool(container_path=self.options.python_tool_container,storage_folder=self.options.storage_folder,agent_name="Lefty")],
                system_prompt = 
                    """
                        You represent the left hemisphere brain of a reasoning agent. Your name is "Lefty".
                        Given a problem or objective you discuss with Righty and Leader to determine the best course of action. 
                        If you believe you are done, the object has been met, or you don't have any additional insight,  say "**no action**".  Never address questions directly to user.
                        Your messages should be structured in section for the intended audience (righty or leader).  Precede each message section with '@' and the target's name.
                        For example:
                        
                            @righty:
                                Please collected the details about product x.
                            @leader:
                                Here are the results from my task.
                        
                    """                    
            ),
            role="agent",
            model_options={"temperature": .1}
        )
        
        self.swarm.register_agent(   
            agent=Agent(model,name="Righty",
                deps_type=SwarmDeps,
                tools=[create_python_executor_tool(container_path=self.options.python_tool_container,storage_folder=self.options.storage_folder,agent_name="Righty")],
                system_prompt = 
                    """
                        You represent the right hemisphere brain of a reasoning agent. Your name is 'Righty'. 
                        Given a problem or objective you discuss with Lefty and Leader to determine the best course of action. Never address questions directly to user.
                        If you believe you are done, the object has been met, or you don't have any additional insight, say "**no action**"
                        Your messages should be structured in section for the intended audience (lefty or leader).  Precede each message section with '@' and the target's name.
                        For example:
                        
                            @lefty:
                                Please collected the details about product x.
                            @leader:
                                Here are the results from my task.
                    """                    
            ),
            role="agent",
            model_options={"temperature": .9}
        )
    async def run_cli(self):
        session = PromptSession(self.prompt)
        # Start background task to process the message queue.
        print("Starting interactive chat with Reasoner.\nType '/help' for commands or '/exit' to quit.\n")
        
        while True:
            try:
                # prompt_async lets you use prompt_toolkit in an async loop.
                line = await session.prompt_async(self.prompt)
            except (EOFError, KeyboardInterrupt):
                # When ctrl-d (or ctrl-c) is pressed, treat the input as the EOF command.
                line = "EOF"
            line = line.strip()
            if not line:
                continue
            # If the line is exactly "EOF", handle it as a command.
            if line == "EOF":
                command_line = "EOF"
            elif line.startswith('/'):
                command_line = line[1:]
            else:
                # Otherwise, prepend the "send" command.
                command_line = "send " + line
            # Process the command.
            should_exit = await self.handle_command(command_line)
            if should_exit:
                break

    
    async def handle_command(self, line: str) -> bool:
        # Split the line into command and argument.
        parts = line.split(" ", 1)
        command = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        # Map the command to a method (e.g. "send" maps to do_send).
        method_name = f"do_{command}"
        method = getattr(self, method_name, None)
        if method is None:
            print(f"Unknown command: {command}")
            return False
        if inspect.iscoroutinefunction(method):
            return await method(arg)
        else:
            return method(arg)
    
    # Command methods:
    async def do_send(self, user_input):
        """Send a message to the main agent."""
        asyncio.create_task(self.swarm.send(user_input))
        return False
    
    def do_help(self, command):
        if command == '':
            print("Commands:")
            for attr in dir(self):
                if attr.startswith("do_") and attr not in ("do_EOF",):
                    print(f"\t{attr[3:]}")
            print("Prefix a command with '/' (for example, '/help').")
        else:
            print("No additional help available for this command.")
        return False
    
    def do_EOF(self, inp):
        """Exit the chat."""
        print("Bye")
        return True
    
    def do_exit(self, inp):
        """Exit the chat."""
        return self.do_EOF(inp)
