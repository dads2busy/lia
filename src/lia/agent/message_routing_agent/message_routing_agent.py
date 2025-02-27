from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import Agent,RunContext,ModelRetry

from lia.agent.ateam_agent.ateam_agent import TeamMember

default_model = OpenAIModel(model_name="llama3.3",base_url="http://localhost:11434/v1",api_key="none") 

class AgentMessage(BaseModel):
    """
    This object contains a response from an agent.
    'message' is the content of the message.
    'target': is the intended recipient of the message.  
    """
    target: str
    message: str

class MessageRoutingAgent(Agent):
    """
    Returns an ATeam Agent
    """
    def __init__(self, model=default_model,name:str="MessageRoutingAgent",deps_type=list[TeamMember],tools=[],system_prompt=None, result_type=list[AgentMessage],retries:int=15):

        system_prompt=f"""
            You are a message routing agent. 
            You will be provided text of a generated message. 
            For each of the available targets, extract:
                - the target (addressee) with the '@' stripped off. Use only canonical name for target.  For example, do not shorten 'Mr. Larry Bird' to 'Mr. Bird'.
                - the portion of the message meant for the target or '' if there is no message for the target.  Do not change the text any more than necessary. 
                
            @user should never be used in a message to @team or to @all.
 
            For example, if the team members are 'lefty' and 'righty', then the available targets are:
                @user - Send to the user
                @[team member name]  - send to specific team member (e.g, @lefty, @righty)
             
           Generate a complete list of messages containing all available targets. Output should be JSON
        """

        tools = []



        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    
        @self.system_prompt(dynamic=True)
        async def add_team_to_system_prompt(ctx: RunContext[list[TeamMember]]) -> str:
            # For instance, concatenate team details into the prompt.
            print("Adding team to system prompt")
            if len(ctx.deps)<0:
                return "There are currently no team members.  Only route between user and leader."
            else:
                team_info = ", ".join(member.name for member in ctx.deps)
                return f"Team members: {team_info}"
        
