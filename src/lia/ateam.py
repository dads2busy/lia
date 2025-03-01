# src/ATeam/ateam.py
import asyncio
import pprint
import inspect
from prompt_toolkit import PromptSession
from lia.analysis_context import AnalysisContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages, UnexpectedModelBehavior, Agent,AgentRunError
from lia.agent import load_agent, list_agents
from dataclasses import dataclass
from lia.agent.message_routing_agent.message_routing_agent import MessageRoutingAgent,AgentMessage,RoutingDeps
from lia.agent.ateam_agent.ateam_agent import RegisteredAgent,TeamMember,ATeamDeps,ATeamAgent


class ATeam:
    prompt = "(ATeam) > "
    
    def __init__(self,options):
        self.options = options
        self.stop_queue = False
        self.team = []
        self.agents = {}
        self.message_history = []
        self.team_introduced_to_problem = False
        
        self.default_model = OpenAIModel(
            model_name=self.options.model_name,
            base_url=self.options.llm_api_url,
            api_key=self.options.llm_api_key
        )
  
        self.default_agent = ATeamAgent(model=self.default_model)
        if self.default_agent.name is not None and options.agent is not None:
            self.prompt = f"({self.default_agent.name}) > "

        self.message_routing_agent = load_agent('message_routing_agent', model=self.default_model)
        if options.debug:
            pprint.pprint(self.default_agent, indent=2)
    
    async def run_cli(self):
        session = PromptSession(self.prompt)
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
        await self.resume_reasoning()
        asyncio.create_task(self.send_to_agent(user_input,"leader","user"))
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
        self.agents[agent.name.lower()] = RegisteredAgent(agent,[])
        
    async def send_to_agent(self, message: str, target:str, sender: str):
        # print(f"Send to agent {sender} -> {target}")
        # print(f"Send to agent msg: {message}")
        target = target.lower()
        if target=="leader":
            agent=self.default_agent
            # if len(self.team)>0:
            message_history = self.message_history
            # else:
                # message_history = []
            temperature = 0.4
        elif target in self.agents:
            agent=self.agents[target].agent
            message_history = self.agents[target].messages
            temperature=0.5
        
        else:
            print(f"Invalid agent target: {target}. Dropping Message")
            return
            
        message_preamble = f"\n[From {sender}]:\n"
        msg = f"{message_preamble}{message}"
        if self.options.reasoning and sender!="user":
            print(f"\n[{sender} -> {target}]: {message}\n")
        else:
            print(f"\n[{sender} -> {target}]")
        
        try:
            # print("send msg")
            # print(f"team: {self.team}")
            # print(f"agents: {self.agents}")
            # print(f"team_introduced: {self.team_introduced_to_problem}")
            # print(f"Message_history: {message_history}")
            deps = ATeamDeps(team=self.team,agents=self.agents,team_introduced_to_problem=self.team_introduced_to_problem)
    
            response = await agent.run(
                msg,
                message_history=message_history,
                result_type=str,
                deps=deps,
                model_settings={'temperature': temperature,"num_ctx": 131072},
            )
            
            newmsgs = response.new_messages()
            if self.options.debug:
                print(f"New Messages from {agent.name}")
                pprint.pp(newmsgs,indent=3)

            if target=="leader":
                self.message_history += newmsgs
            elif target in self.agents:
                self.agents[target].messages += newmsgs

            for kw in ["**objective met**","**raise question**"]:
                if kw in response.data.lower() and sender == "leader":
                    self.stop_reasoning=True            

            if "**no action**" not in response.data:
                asyncio.create_task(self.route_response(response.data,target,default_route=sender))
                
        except AgentRunError as err:
            if self.options.debug:
                print(f"Got AgentRunError from {agent.name}: \n{err}")
            if self.options.reasoning: 
                print(f"Got AgentRunError from {agent.name}")        
        
                
        except Exception as err:
            print(f"Error in send_to_agent response: {err}")
            
    async def deliver_messages_from_dict(self,message_dict):
        # print(f"message_dict: {message_dict}")
        md = message_dict["messages"]
        source = message_dict["source"]
        for target in md:
            # print(f"\tDeliver Target: {target}")
            msg = []
            if target in ["all","team"]:
                continue
            
            if 'all' in md:
                msg += md["all"]
                
            if target=="user" and "user" in md:
                msg += md['user']
            
            if target in self.agents.keys() and target in md:
                if "team" in md and target!=source:
                    msg += md['team']
                if target != source:
                    msg += md[target]

            jmsg = ' '.join(msg)
            
            if self.stop_reasoning and target=="user":
                print(f"\n[{source} -> {target}]:{jmsg} ")
            else:
                if target != "user":
                    wait = self.stop_reasoning 
    
                    while wait:
                        print("Still waiting")
                        await asyncio.sleep(2)   
                    await self.send_to_agent(jmsg,target,source)
                    
    async def resume_reasoning(self):
        self.stop_reasoning=False

    async def route_response(self,message,source:str, default_route:str|None=None):
        print(f"Route Response from {source}: \n{message}")
        if len(self.team)>0:
            try:
                response = await self.message_routing_agent.run(message,deps=RoutingDeps(team=self.team),result_type=list[AgentMessage])
                md = {}
                if self.options.debug:
                    print("Message Routing Agent Response: ")
                    pprint.pp(response.data)
                # print(f"Route Response Data: {response.data}") 
                for msg in response.data:
                    target = msg.target.lower()
                    if target == source:
                        continue
                    
                    if target not in md:
                        md[target]=[]
                    
                    md[target].append(msg.message) 
            except UnexpectedModelBehavior as err:
                print(f"Message router had unexpected behavior: {err}")
                if default_route is not None:
                    md[default_route] = [message]
        elif source=="leader":
            md={"user": [message]}
        else:
            md={"leader": [message]}
            
        await self.deliver_messages_from_dict({"messages": md, "source": source})

    