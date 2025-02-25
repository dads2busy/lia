# src/Reasoner/ateam.py
import asyncio
import pprint
import inspect
from prompt_toolkit import PromptSession
from lia.analysis_context import AnalysisContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages, UnexpectedModelBehavior, Agent
from lia.agent import load_agent, list_agents
from dataclasses import dataclass
from lia.agent.reasoning_agent.reasoning_agent import create_python_executor_tool
import re

class Reasoner:
    prompt = "(Reasoner) > "
    
    def __init__(self, file: str | None, options):
        self.file = file
        self.options = options
        self.stop_queue = False
        self.pause_message = []
        self.team = []
        self.agents = {}
        self.queue = asyncio.Queue()
        self.message_history = []
        self.default_model = OpenAIModel(
            model_name=self.options.model_name,
            base_url=self.options.model_base_url,
            api_key=self.options.model_api_key
        )
        self.default_agent = load_agent('reasoning_agent', model=self.default_model)
        if self.default_agent.name is not None and options.agent is not None:
            self.prompt = f"({self.default_agent.name}) > "
  
        self.create_hemispheres(self.default_model)

        if options.debug:
            pprint.pp(self.default_agent, indent=2)
            pprint.pp(self.left, indent=2)
            pprint.pp(self.right, indent=2)
    
    def create_hemispheres(self,model):
        self.left = Agent(model,
            tools=[create_python_executor_tool()],
            system_prompt = 
                """
                    You represent the left hemisphere brain of a reasoning agent. Your name is "Lefty".
                    The create_python_executor_tool is available to execute any python code you generate 
                    for searching the web or performing other analysis.  It has libraries such as pandas,
                    scipy,duckdb availabe for your use.
                    Given a problem or objective you discuss with the right hemisphere to determine the best course of action.
                """                    
        )
        
        self.right = Agent(model,
            tools=[create_python_executor_tool()],
            system_prompt = 
                """
                    You represent the right hemisphere brain of a reasoning agent. Your name is 'Righty'. 
                    The create_python_executor_tool is available to execute any python code you generate 
                    for searching the web or performing other analysis.  It has libraries such as pandas,
                    scipy,duckdb availabe for your use.
                    Given a problem or objective you discuss with the left hemisphere to determine the best course of action.
                """                    
        )
        
    
    async def run_cli(self):
        session = PromptSession(self.prompt)
        # Start background task to process the message queue.
        self.queue_task = asyncio.create_task(self.process_message_queue())
        print("Starting interactive chat with Reasoner.\nType '/help' for commands or '/exit' to quit.\n")
        try:
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
        finally:
            self.queue_task.cancel()
    
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
        self.stop_queue=False
        self.add_to_queue(user_input, "@user")
        
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


    async def send_to_leader(self, message: str, sender: str):
        
        if self.options.reasoning and sender!="@user":
            print(f"[{sender} -> Leader]: {message}\n")
        else:
            print(f"[{sender} -> Leader]")
            
        response = await self.default_agent.run(
            message,
            message_history=self.message_history,
            result_type=str,
            model_settings={'temperature': 0.5,"num_ctx": 8192},
        )
        
        newmsgs = response.new_messages()
        if self.options.debug:
            pprint.pp(newmsgs,indent=3)
        self.message_history += newmsgs

        if self.options.reasoning and sender!="@user":
            print(f"[{sender} -> Leader]: {response.data}\n")
        else:
            print(f"[Leader]: {response.data}\n")
            
        if re.search("@user", response.data, re.IGNORECASE):
            print("**************\nGOT USER QUESTION\n*****************")
            self.stop_queue = True
            self.pause_message.append(response.data)
        else:
            if len(self.pause_message)>0:
                self.add_to_queue(' '.join(self.pause_message + [response.data]), "reasoner")
                self.pause_message=[]
            else:
                print("Add Leader response to queue for reasoner")
                self.add_to_queue(response.data,"reasoner")

        return False
    
    async def send_to_reasoner(self, message: str, sender: str, hemisphere:str, temperature:float=0.5):
        # print("Send to Agents()")
        
        if self.options.reasoning:
            print(f"[{sender} -> {hemisphere}]: {message}\n")
        else:
            print(f"[{sender} -> {hemisphere}]\n")
 
        agent = getattr(self,"left",None)
        if agent is None:
            raise Exception("Unexpected missing brain hemisphere!")
        
        if sender is None or agent.name != sender:
            response = await agent.run(
                message,
                message_history=self.message_history,
                model_settings={'temperature': temperature,"num_ctx": 4096}
            )
            newmsgs = response.new_messages()

            self.message_history += newmsgs
            if self.options.reasoning:
                print(f"[{hemisphere} -> Leader]: {message}\n")
            else:
                print(f"[{hemisphere} -> Leader]\n")
                
            self.add_to_queue(response.data, "leader")
                
        return False

            
    async def send_to_agents(self, message: str, sender: str):
        asyncio.create_task(self.send_to_reasoner(message, sender,"left",0.1))
        asyncio.create_task(self.send_to_reasoner(message, sender,"right",0.9))
        
        return False
    
    async def process_message_queue(self):
        while True:
            if not self.stop_queue:
                try:
                    qitem = await self.queue.get()
                    if self.options.debug:
                        print(f"qitem: {qitem}")
                        
                    if qitem['sender'] == "@user":
                        await self.send_to_leader(qitem['message'], qitem['sender'])
                    else:
                        await self.send_to_agents(qitem['message'], qitem['sender'])
                        
                    self.queue.task_done()
                except Exception as err:
                    print(f"Error processing queue: {err}")
            else:
                await asyncio.sleep(1)
    
    def add_to_queue(self, msg, sender):
        self.queue.put_nowait({"sender": sender, "message": msg})
