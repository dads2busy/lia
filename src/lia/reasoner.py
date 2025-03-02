# src/lia/ateam.py
import asyncio
import pprint
import inspect
from prompt_toolkit import PromptSession
from lia.analysis_context import AnalysisContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages, UnexpectedModelBehavior, Agent,AgentRunError
from lia.agent import load_agent, list_agents
from dataclasses import dataclass
from lia.agent.reasoning_agent.reasoning_agent import create_python_executor_tool,AgentPythonExecutionError
from lia.agent.message_routing_agent.message_routing_agent import AgentMessage,RoutingDeps
from lia.agent.ateam_agent.ateam_agent import TeamMember,ATeamDeps
from lia.agent.python_developer_agent.python_developer_agent import PythonDeveloperAgent
import re



class Reasoner:
    prompt = "(Reasoner) > "
    
    def __init__(self,options):
        self.options = options
        self.stop_reasoning=False
        self.stopped_message = None
        self.isFirstMessage=True
        self.message_history = []
        self.team_introduced_to_problem=False
        self.agent_message_history = {"lefty": [], "righty":[]}
        
        print(f"Model:\n\t{self.options.model_name}\n\t{self.options.llm_api_url}\n\t{self.options.llm_api_key}")
        self.default_model = OpenAIModel(
            model_name=self.options.model_name,
            base_url=self.options.llm_api_url,
            api_key=self.options.llm_api_key
        )
        
        self.default_agent = load_agent('reasoning_agent', model=self.default_model)
        if self.default_agent.name is not None and options.agent is not None:
            self.prompt = f"({self.default_agent.name}) > "
  
        self.message_routing_agent = load_agent('message_routing_agent', model=self.default_model)
        
        self.debugger_agent = load_agent("python_developer_agent", model=self.default_model)
        
        self.create_hemispheres(self.default_model)
        if options.debug:
            pprint.pp(self.default_agent, indent=2)
            pprint.pp(self.lefty, indent=2)
            pprint.pp(self.righty, indent=2)
    
    def create_hemispheres(self,model):
        self.lefty = Agent(model,name="Lefty",
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
        )
        self.righty = Agent(model,name="Righty",
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

    async def send_to_agent(self, message: str, target:str, sender: str):
        target = target.lower()
        if target=="leader":
            agent=self.default_agent
            message_history = self.message_history
            temperature = 0.5
        elif target=="lefty":
            agent=self.lefty
            message_history = self.agent_message_history["lefty"]
            temperature = 0.1
        elif target=="righty":
            agent=self.righty
            message_history = self.agent_message_history["righty"]
            temperature = 0.9
        elif target=="debugger":
            agent=self.debugger_agent
            message_history = []
            temperature=0.5

        else:
            print("Invalid agent target: {target}. Dropping Message")
            return
            
        if target == "debugger":
            message_preamble = ""
        else:
            message_preamble = f"[From {sender}]:\n"
            
        msg = f"{message_preamble}: {message}"
        
        if self.options.reasoning and sender!="user":
            print(f"\n[{sender} -> {target}]:\n{message}\n")
        else:
            print(f"\n[{sender} -> {target}]")
        
        try:
            deps = ATeamDeps(team=self.getTeam(),agents={},team_introduced_to_problem=self.team_introduced_to_problem)
            response = await agent.run(
                msg,
                message_history=message_history,
                result_type=str,
                deps=deps,
                model_settings={'temperature': temperature,"num_ctx": 131072,"keep_alive":-1},
            )
            newmsgs = response.new_messages()
            if self.options.debug:
                print(f"New Messages from {agent.name}")
                pprint.pp(newmsgs,indent=3)

            if target=="leader":
                self.message_history += newmsgs
            elif target!="debugger":
                self.agent_message_history[target] += newmsgs

            for kw in ["**objective met**","**raise question**"]:
                if kw in response.data.lower() and sender == "leader":
                    self.stop_reasoning=True            

            if target == "debugger":
                asyncio.create_task(self.send_to_agent(message=response.data,target=sender,sender="debugger"))
            elif "**no action**" not in response.data.lower():
                asyncio.create_task(self.route_response(response.data,target,default_route=sender))
                
        except AgentPythonExecutionError as err:
            if self.options.debug:
                print(f"\nGot PythonError from {agent.name}: \n{err}")
                
            if self.options.reasoning: 
                print(f"\nGot Python error from {agent.name}")        
            
            asyncio.create_task(self.send_to_agent(
                message=f"I had an issue executing my python: {err}",
                target="leader",
                sender=target
            ))   
                
        except AgentRunError as err:
            if self.options.debug:
                print(f"\nGot AgentRunError frin {agent.name}: \n{err}")
            if self.options.reasoning: 
                print(f"\nGot AgentRunError from {agent.name}")        
                
        except Exception as err:
            print(f"Error in send_to_agent response: {err}")
            
    async def deliver_messages_from_dict(self,message_dict):
        md = message_dict["messages"]
        source = message_dict["source"]
        for target in md:
            # print("\tTarget: {target}")
            msg = []
            if target in ["all","team"]:
                continue
            
            if 'all' in md:
                msg += md["all"]
                
            if target=="user" and "user" in md:
                msg += md["user"]
            
            if target in ["lefty","righty","leader"] and target in md:
                if "team" in md and target!=source:
                    msg += md["team"]
                if target != source:
                    msg += md[target]

            jmsg = ' '.join(msg)
            
            if self.stop_reasoning and target=="user":
                print(f"\n[{source} -> {target}]:{jmsg} ")
            else:
                if target != "user":
                    wait = self.stop_reasoning
                    while wait:
                        await asyncio.sleep(2)
                        wait = self.stop_reasoning
                    await self.send_to_agent(jmsg,target,source)
                    
    async def resume_reasoning(self):
        self.stop_reasoning=False

    def getTeam(self):
        return [
            TeamMember(name="lefty",role=''),
            TeamMember(name="righty",role='')
        ]
                        
    async def route_response(self,message,source:str, default_route:str|None=None):
        if self.options.debug:
            print(f"\nRoute Response from {source}: \n{message}")
            
        md = {}
        try:
            deps = RoutingDeps(team=self.getTeam())
            # print(f"Routing Deps: {deps}")
            response = await self.message_routing_agent.run(message,deps=deps,  model_settings={'temperature': .1,"num_ctx": 131072,"keep_alive":-1}, result_type=list[AgentMessage])
            if self.options.debug:
                print("Message Routing Agent Response: ")
                pprint.pp(response.data)
                
            for msg in response.data:
                target = msg.target.lower()
                if target not in md:
                    md[target]=[]
                
                md[target].append(msg.message) 
            
            await self.deliver_messages_from_dict({"messages": md, "source": source})
                            
        except UnexpectedModelBehavior as err:
            print(f"Message router had unexpected behavior: {err}")
            if default_route is not None:
                print(f"Using default route ({default_route}) for response.")
                md[default_route] = [message]
        
                
        await self.deliver_messages_from_dict({"messages": md, "source": source})

