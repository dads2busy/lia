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
from lia.agent.python_developer_agent.python_developer_agent import PythonDeveloperAgent
from lia.tools.python_execution_tool import create_python_executor_tool,AgentPythonExecutionError
from lia.agent.ateam_agent.ateam_agent import RegisteredAgent,TeamMember,ATeamDeps,ATeamAgent
from pydantic import BaseModel
from typing import Callable, Optional, List, Type, Any
import re


class AgentExistsException(Exception):
    pass

class RegisteredAgent():
    def __init__(self,agent:Agent, model_options:dict|None=None):
        self.agent = agent
        self.queue = asyncio.Queue()
        self.message_history=[]
        self.model_options = model_options
    def __str__(self):
        return f"Registered Agent ({self.agent.name}) : Model Options ({self.model_options})"
    
class AgentSwarm:   
    def __init__(self,
            leader: Agent|None = None,
            agents: list[Agent] = [],
            model: OpenAIModel|None = None,
            message_router: Agent|None = None,
            debugger: Agent|None = None,
            getDeps: Optional[Callable] = None,
            deps_type: Optional[Type] = None,
            debug: Optional[bool] = False,
            show_agent_messages: Optional[bool] = False
        ):
        
        self.agents={}
        self.continue_processing=True
        self.turns = 0
        self._processor_running=False
        self._getDeps = getDeps
        self.deps_type = deps_type
        self.debug = debug
        self.show_agent_messages = show_agent_messages
        self.suspended_loop_count = 0
        self.is_first_response = True
        self.model = model
        self.user_stop_messages=[]
        
        if (leader is None or message_router is None) and self.model is None:
            raise Exception("When not providing a leader or message router agent, model is required.")
        
        if leader is None:
            self.register_agent(self.create_leader(), role="leader")
        else:
            self.register_agent(leader, role="leader")
        
        if message_router is None:
            self.register_agent(self.create_message_router(), role="message_router")
        else:
            self.register_agent(leader, role="message_router")

        if debugger is None:
            self.register_agent(self.create_debugger(), role="debugger")
        else:
            self.register_agent(leader, role="debugger")
    
        for a in agents:
            self.register_agent(agent=a,role="agent")    
            

    def register_agent(self,agent:Agent,role:str="agent",model_options:dict|None=None):
        agent_name = agent.name.lower()
        if agent_name in self.agents:
            raise AgentExistsException()
    
        if role=="leader":
            self.leader = RegisteredAgent(agent=agent,model_options=model_options)
        elif role=="message_router":
            self.message_router = RegisteredAgent(agent=agent,model_options=model_options)
        elif role=="debugger":
            self.debugger = RegisteredAgent(agent=agent,model_options=model_options)
        else:
            print(f"Registering Agent {agent.name} with options: {model_options}")
            self.agents[agent_name] = RegisteredAgent(agent=agent,model_options=model_options)

    def create_leader(self):
        pass
    
    def create_message_router(self):
        return MessageRoutingAgent(model=self.model)
    
    def create_debugger(self):
        return PythonDeveloperAgent(model=self.model)
    
    def get_agent_names(self):
        return list(self.agents.keys())
        
    async def send(self,msg: str):
        if not self._processor_running:
            asyncio.create_task(self.process_agent_queues())
            
        if not self.continue_processing:
            self.continue_processing=True
            self.suspended_loop_count = 0
            self.user_stop_messages = []
            
        return await self.send_to_agent(msg,"leader","user")    
     
        
    async def send_to_agent(self,msg: str, target: str, source: str):
        if target == source:
            print(f"target == source, drop message")
            return
        
        if target=="leader":
            agent = self.leader
        elif target in self.agents:
            agent = self.agents[target]
        else:
            print(f"Invalid Agent Route: {target}. Dropping Message")
            print(f"Agents are: {self.agents.keys()}")
            return
        m = {"message": msg, "source": source}
        if self.debug:
            print(f"Adding message for {target} from {source}")
            
        await agent.queue.put(m)
        
    async def create_agent_message(self,agent):
        queue = agent.queue
        
        if queue.empty():
            return None
        
        msg = []
        while not queue.empty():
            mdata = queue.get_nowait()
            msg.append(f"\n[From {mdata['source']}]:\n{mdata['message']}\n")
            queue.task_done()
       
        # print(f"Create Agent Message: {msg}")
        return ' '.join(msg)
    
    def getDeps(self,agent_name:str):
        if self._getDeps is not None:
            return self._getDeps(agent_name)
        
    def split_message_into_chunks(self,text):
        # Use multiline mode to match targets at the start of each line.
        pattern = r'(?m)^\s*(@\w+):'
        matches = list(re.finditer(pattern, text))
        chunks = []

        for i, match in enumerate(matches):
            target = match.group(1)
            # The content starts after the current match's colon.
            start_index = match.end()
            # If there is another target, end at the start of the next match.
            if i < len(matches) - 1:
                end_index = matches[i + 1].start()
            else:
                end_index = len(text)
            content = text[start_index:end_index].strip()
            chunks.append(AgentMessage(target=target[1:], message=content))
        
        return chunks
    async def route_response(self,message:str,source:str):
        try:
            messages = self.split_message_into_chunks(message)

            for msg in messages:
                target = msg.target.lower()
                if target=="user":
                    m = f"\n[From {source}]:\n {msg.message}\n"
                    if self.continue_processing:
                        print(m)
                    else:
                        self.user_stop_messages.append(m)
                elif msg.message != '' and target!=source:
                    await self.send_to_agent(msg.message,target,source=source)
        except UnexpectedModelBehavior:
            print(f"Unable to generate route response for message: {message}. Message dropped.")
    
    async def deliver_message(self,message:str,agent_name:str):
        if self.show_agent_messages:
            print(f"\nMessage for {agent_name}:\n{message}")
        else:
            print(f"Delivering messages for {agent_name}")
            
        if agent_name=="leader":
            agent = self.leader
        else:
            agent = self.agents[agent_name]
            
        llm = agent.agent
        
        # print(f"Agent: {agent}")
        if agent.model_options is None:
            model_settings={}
        else:
            model_settings=agent.model_options
      
        # print(f"Model Settings: {model_settings}")
        try:

            response = await llm.run(
                message,
                message_history=agent.message_history,
                result_type=str,
                deps=self.getDeps(agent_name),
                model_settings=model_settings
            )  
            
            newmsgs = response.new_messages()
            agent.message_history += newmsgs
            
            for kw in ["**objective met**","**raise question**"]:
                if kw in response.data.lower() and agent_name == "leader":
                    if self.debug:
                        print(f"Found Stop Word: {kw}.  Pause message passing loop.")
                    self.continue_processing=False    
                    if "@user" not in response.data.lower():
                        self.user_stop_messages.append(f"\n[From leader]:\n{response.data}\n")
                        
            asyncio.create_task(self.route_response(response.data,agent_name))
        
        except AgentPythonExecutionError as err:
            if self.debug or self.show_agent_messages:
                print(f"\nGot PythonError from {llm.name}.")
                      
                if self.debug:
                    print(err)
                      
        except AgentRunError as err:
            if self.debug or self.show_agent_messages:
                print(f"\nGot AgentRunError from {llm.name}.")
                      
                if self.debug:
                    print(err)    
                
        except Exception as err:
            print(f"Error in send_to_agent response: {err}")         
            
    async def process_agent_queues(self):
        self._processor_running=True
        while True:
            # print(f"Continue Processing: {self.continue_processing}")
            if self.continue_processing:
                to_process = ["leader"] + list(self.agents.keys())
                
                for agent_name in to_process:
                    if self.debug:
                        print(f"Checking {agent_name} for messages...")
                        
                    if agent_name=="leader":
                        agent = self.leader
                    else:
                        agent = self.agents[agent_name]
                        
                    message = await self.create_agent_message(agent)
                
                    if message is not None:
                        response = await self.deliver_message(message,agent_name)
            else:
                if self.suspended_loop_count < 1:
                    if len(self.user_stop_messages)>0:
                        print(' '.join(self.user_stop_messages))
                    else:
                        print("Waiting for user input.")
                self.suspended_loop_count += 1
                
            await asyncio.sleep(10)