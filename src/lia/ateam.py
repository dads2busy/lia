# src/ATeam/cmd_app.py
from .acmd import ACmd
from lia.analysis_context import AnalysisContext
from typing import Union
from dataclasses import dataclass
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import capture_run_messages,UnexpectedModelBehavior,Agent
from lia.agent import load_agent,list_agents
from lia.agent.ateam_agent.ateam_agent import TeamMember
import asyncio
import pprint
import threading
import inspect

@dataclass
class ATeamDeps():
    agents: dict[Agent]
    team: list[TeamMember]

class ATeam(ACmd):
    """
    intro = 'Welcome to ATeam interactive shell. Type help or ? to list commands.\n'
    prompt = '(ATeam) '
    """
    # identchars="do_"
    message_history=[]
    prompt = '(ATeam) > '
    def __init__(self,file:Union[str|None],options):
        super().__init__()
        self.file = file
        self.options = options
        self.stop_queue = False
        self.team = []
        self.agents = {}
        self.queue = asyncio.Queue()
        self.default_model = OpenAIModel(model_name=self.options.model_name,base_url=self.options.model_base_url,api_key=self.options.model_api_key)

        
        # self.model_name = "gpt-4o"
        # self.api_key = "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"
        # self.model = OpenAIModel(model_name=self.model_name,api_key=self.api_key)

        # self.default_agent = getContextManagerAgent(model=self.model)
        if options.agent is not None:
            self.default_agent = load_agent(options.agent,model=self.default_model)
        else:
            self.default_agent = load_agent('ateam_agent', model=self.default_model)

        if self.default_agent.name is not None and options.agent is not None:
            self.prompt = f"({self.default_agent.name}) >"
 
        if options.debug:
            pprint.pp(self.default_agent,indent=2)
            
    async def cmdloop(self, intro=None):
        if intro is not None:
            self.intro = intro
        if self.intro:
            self.stdout.write(str(self.intro) + "\n")
    
        self.queue_task = asyncio.create_task(self.process_message_queue())
        try:
            stop = False
            while not stop:
                try:
                    line = await self.async_input(self.prompt)
                except EOFError:
                    line = "EOF"
                resp = self.precmd(line)
                if inspect.isawaitable(resp):
                    line = await resp
                else:
                    line = resp
                resp = self.onecmd(line)
                if inspect.isawaitable(resp):
                    stop = await resp
                else:
                    stop = resp
                resp = self.postcmd(stop, line)
                if inspect.isawaitable(resp):
                    stop = await resp
                else:
                    stop = resp
            return stop
        finally:
            self.queue_task.cancel()
    
    def precmd(self, line):
        if line.startswith('/'):
            return line[1:]
        elif line=="help":
            return line
        elif line=="EOF":
            return line
        else:
            return f"send {line}"
    
    def do_EOF(self, inp):
        '''
            Exits the chat.
        '''
        print("Bye")
        return True    

    def do_help(self,command):
        if command == '':
            print("Commands:")
            for name in dir(self):
                if name.startswith("do_") and name!="do_EOF":
                    print(f"\t{name.replace("do_","")}")
            print("To execute a command proceed it with a '/'.  For example '/help'")
        else:
            ACmd.do_help(self,command)     
            
    def emptyline(self):
        self.prompt
    
    def do_listAgents(self,param):
        """List the individual agents in the system"""
        print(f"Agents:")
        for agent in self.agents:
            print(f"  {agent}")
            
    def do_team(self,param):
        """List the current team members"""
        if len(self.team)<1:
            print("No team has been assembled yet.")
            return
        print(f"Team Members:")
        for tm in self.team:
            print(f"  {tm.name} - {tm.role}")
            
    def register_agent(self,agent):
        self.agents[agent.name] = agent
        
    async def send_to_leader(self, user_input):
        # print(f"send to leader: {user_input}")
        # print(f"self.default agent: {self.default_agent}")
        # Call run() without awaiting immediately.
        response = await self.default_agent.run(
            user_input,
            message_history=self.message_history,
            deps=ATeamDeps(team=self.team, agents=self.agents),
            model_settings={'temperature': .5}
        )
        newmsgs = response.new_messages()
        if self.options.debug:
            print("***************\nNew Messages:")
            pprint.pp(newmsgs, indent=2)
            print("***************\n")
        self.message_history += newmsgs
        print(response.data)
        self.add_to_queue(response.data, "leader")
        return True

    async def send_to_agents(self, message: str, from_agent: str | None = None):
        for agent_name in self.agents:
            agent = self.agents[agent_name]
            if from_agent is None or agent.name != from_agent:
                response = await agent.run(
                    message,
                    message_history=self.message_history,
                    model_settings={'temperature': .8}
                )

                newmsgs = response.new_messages()
                if self.options.debug:
                    print("***************\nNew Messages:")
                    pprint.pp(newmsgs, indent=2)
                    print("***************\n")
                self.message_history += newmsgs
                print(f"{agent.name} : {response.data}")
                self.add_to_queue(response.data, agent.name)
        return True

    async def process_message_queue(self):
        while True:
            if not self.stop_queue:
                try:
                    qitem = await self.queue.get()
                    if qitem['sender'] == "@user":
                        await self.send_to_leader(qitem['message'])
                    elif qitem['sender'] == "leader":
                        await self.send_to_agents(qitem['message'])
                
                    self.queue.task_done()
                except Exception as err:
                    print(f"Error processing queue: {err}")
            else:
                await asyncio.sleep(5)
            
    def add_to_queue(self, msg, sender):   
        self.queue.put_nowait({"sender": sender, "message": msg})
        
    def do_send(self, user_input):
        """Send a message to the main agent"""
        self.add_to_queue(user_input, "@user")

   
