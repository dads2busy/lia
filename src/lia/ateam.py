# src/ATeam/ateam.py
import asyncio
import pprint
import inspect
from prompt_toolkit import PromptSession
from lia.analysis_context import AnalysisContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages, UnexpectedModelBehavior, Agent
from lia.agent import load_agent, list_agents
from dataclasses import dataclass
from lia.agent.message_routing_agent.message_routing_agent import MessageRoutingAgent,AgentMessage
from lia.agent.ateam_agent.ateam_agent import RegisteredAgent
@dataclass
class ATeamDeps:
    team: list
    agents: dict


class ATeam:
    prompt = "(ATeam) > "
    
    def __init__(self, file: str | None, options):
        self.file = file
        self.options = options
        self.stop_queue = False
        self.team = []
        self.agents = {}
        self.queue = asyncio.Queue()
        self.message_history = []
        self.default_model = OpenAIModel(
            model_name=self.options.model_name,
            base_url=self.options.llm_api_url,
            api_key=self.options.llm_api_key
        )
        
        if options.agent is not None:
            self.default_agent = load_agent(options.agent, model=self.default_model)
        else:
            self.default_agent = load_agent('ateam_agent', model=self.default_model)
        if self.default_agent.name is not None and options.agent is not None:
            self.prompt = f"({self.default_agent.name}) > "
  
        self.message_routing_agent = load_agent('message_routing_agent', model=self.default_model)
        if options.debug:
            pprint.pprint(self.default_agent, indent=2)
    
    async def run_cli(self):
        session = PromptSession(self.prompt)
        # Start background task to process the message queue.
        self.queue_task = asyncio.create_task(self.process_message_queue())
        print("Starting interactive chat with ATeam.\nType '/help' for commands or '/exit' to quit.\n")
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
        self.add_to_queue(user_input, "leader", "@user")
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
    
    def do_listAgents(self, param):
        """List the individual agents in the system."""
        print("Agents:")
        for agent in self.agents:
            print(f"  {agent}")
        return False
    
    def do_team(self, param):
        """List the current team members."""
        if len(self.team) < 1:
            print("No team has been assembled yet.")
        else:
            print("Team Members:")
            for tm in self.team:
                print(f"  {tm.name} - {tm.role}")
        return False
    
    def register_agent(self, agent):
        self.agents[agent.name] = RegisteredAgent(agent,[])
        
    async def message_route_planner(self,message):
        response = await self.message_routing_agent.run(
            message,
            deps=ATeamDeps(team=self.team,agents=self.agents),
            result_type=list[AgentMessage]
        )
        
        if self.options.debug:
            print(f"Message Route Planner Debug Data:\n{response.new_messages()}")
            print(f"Response Data Type: {type(response.data)}")
        
        if isinstance(response.data,list):
            return response.data
        else:
            print(f"Invalid Response Data from route planner:\n{response.data}")
            raise Exception("Invalid RoutePlanResponse")
        
    async def send_to_leader(self, message: str, sender: str):
        
        if self.options.reasoning and sender!="@user":
            print(f"[{sender} -> Leader]: {message}\n")
            
        response = await self.default_agent.run(
            message,
            message_history=self.message_history,
            deps=ATeamDeps(team=self.team,agents=self.agents),
            result_type=str,
            model_settings={'temperature': 0.5},
        )
        newmsgs = response.new_messages()
        if self.options.debug:
            pprint.pp(newmsgs,indent=3)
        self.message_history += newmsgs

        messages = await self.message_route_planner(response.data)
        # print(f"Route Plan: {messages}")
        joined_messages = {}
        for msg in messages:
            if msg.message=='':
                return
            # print(f"aResponseMSG: {msg}")
            
            if msg.target not in joined_messages:
                joined_messages[msg.target] = []
            
            if msg.target == "@user" or msg.target == "@all":
                print(f"[Leader]: {msg.message}\n")
            
            if msg.target != "@user":    
                joined_messages[msg.target].append(msg.message)
                # self.add_to_queue(msg.message, "@team", "leader")

        if "@team" in joined_messages:
            for tm in self.team:
                if tm.name not in joined_messages:
                    joined_messages[tm.name] = []
                joined_messages[tm.name] += joined_messages["@team"]
            del joined_messages["@team"]

        if "@all" in joined_messages:
            for tm in self.team:
                if tm.name not in joined_messages:
                    joined_messages[tm.name] = []
                joined_messages[tm.name] += joined_messages["@all"]
            del joined_messages["@all"]


        # print(f"Joined Messages: \n{joined_messages}")
        for target in joined_messages:
            if len(joined_messages[target])>0:
                self.add_to_queue(' '.join(joined_messages[target]), target, "leader")



        return False
    
    async def send_to_agent(self, message: str, to: str, sender: str):
        # print("Send to Agents()")
        
        if self.options.reasoning:
            print(f"[{sender} -> {to}]: {message}\n")
        
        if to == "leader" and sender != "leader":
            await self.send_to_leader(message, sender)
        else:    
            agent = self.agents[to].agent
            if sender is None or agent.name != sender:
                response = await agent.run(
                    message,
                    message_history=self.agents[to].messages,
                    model_settings={'temperature': 0.8}
                )
                newmsgs = response.new_messages()

                self.agents[to].messages += newmsgs
                if self.options.reasoning:
                    print(f"[{agent.name} -> Leader]: {message}\n")
                self.add_to_queue(response.data, "leader", agent.name)
                
        return False
    
    async def send_to_agents(self, message: str, sender: str):
        print("Send to Agents()")
        if sender != "leader":
            await self.send_to_leader(message, sender)
            
        for registered_agent in self.agents:
            await self.send_to_agent(message, registered_agent.agent.name, sender)
        return False
    
    async def process_message_queue(self):
        while True:
            try:
                qitem = await self.queue.get()
                if self.options.debug:
                    print(f"qitem: {qitem}")
                if qitem['sender'] == "@user":
                    await self.send_to_leader(qitem['message'], qitem['sender'])
                else:
                    if qitem["to"] == "@user": 
                        print(f"[{qitem['sender']}]: {qitem['message']}")
                    if qitem['to'] == "@team" or qitem['to'] == '@all':
                        await self.send_to_agents(qitem['message'], qitem['sender'])
                    else:
                        await self.send_to_agent(qitem['message'], qitem['to'], qitem['sender'])
                    
                self.queue.task_done()
            except Exception as err:
                print(f"Error processing queue: {err}")
    
    def add_to_queue(self, msg, to, sender):
        self.queue.put_nowait({"sender": sender, "to": to, "message": msg})
