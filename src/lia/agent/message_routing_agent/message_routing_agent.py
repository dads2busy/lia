from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import Agent,RunContext,ModelRetry

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
    def __init__(self, model=default_model,name:str="MessageRoutingAgent",tools=[],system_prompt=None, result_type=list[AgentMessage],retries:int=5):

        system_prompt=f"""
        
            You are a message routing agent. 
            You will be provided text of a generated message. 
            For each of the available targets, extract:
                - the target (addressee)
                - the portion of the message meant for the target or '' if there is no message for the target
            
            The name should always be the canonical name of the target, not a shortened form ('Mr. Larry Bird' should not be shortened to 'Mr. Bird')
            
            Available targets:
                @team - Send to all team members
                @user - Send to the user
                @all - Send to the user and team members
                team member name  - send to specific team member
             
           Generate a complete list of messages containing all available targets. Output should be JSON

        """

        tools = []

        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    

