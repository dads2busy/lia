from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import Agent,RunContext

# model_name = "gpt-4o"
# api_key = "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"
# default_model = OpenAIModel(model_name=model_name,api_key=api_key)

# default_model = OpenAIModel(model_name="llama3.2",base_url="http://localhost:11434/v1",api_key="none")                
default_model = OpenAIModel(model_name="llama3.3",base_url="http://localhost:11434/v1",api_key="none") 

@dataclass
class TeamMember():
    """ 
        Describes a team member
        name - The name of the team member
        role - Describes the exptertise of the team member
    """
    name: str 
    role: str


def create_agent(name:str,role:str,model:OpenAIModel):
    system_prompt = role + ' '.join([
        f"Engage in discussion with team members to further user's objective.  Your name is {name}.",
        "Responses from other team members should be inspected and questionsed to make sure they are accurate and complete."
    ])
    # print(f"Create Agent : {name} Prompt: {system_prompt}")
    return Agent(
        name=name,
        model=model,
        system_prompt = system_prompt
    )

def get_create_team_tool(model=default_model):
    def create_team(ctx: RunContext[str],team: list[TeamMember]) -> str:
        """
            Given a list of TeamMember objects, this tool will gather exper team members described by the TeamMember objects.
            Once the team members have been gathered, as a group they should discuss the best way to solve the user's objective.
        """
        # print(f"ctx.state {ctx}")
        # print(f"Team: {team}")

        if len(ctx.deps.team)>0:
            return "Team already exists. Work with your current team."
            
        ctx.deps.team += team
        
        for tm in ctx.deps.team:
            if tm.name not in ctx.deps.agents:
                ctx.deps.agents[tm.name] = create_agent(tm.name,tm.role,model)
                # print(f"Agent: {ctx.deps.agents[tm.name]}")
        
        return "The team has been assembled."
    
    return create_team
class ATeamAgent(Agent):
    """
    Returns an ATeam Agent
    """
    def __init__(self, model=default_model,name:str="ATeamAgent",tools=[],system_prompt=None, result_type=str,retries:int=5):
        base_prompt = ' '.join([
            "Your role is to assemble a team of experts to address the user's question or objective.",
            "Generate a list of 1-3 experts with diverse areas of expertise related to the objective.",
            "For each of these experts, generate a name and prompt describing their role as experts.",
            "You will then send the list of team members to the create_team tool to establish the team.",
            "Once a team has been gathered, you will lead the discussion for addressing the users questions.",
            "Verify "
            "If you need any clarification, you can do so by preceding the question with '@user_question'."
        ])
        if system_prompt is None:
            system_prompt = base_prompt
        else:
            system_prompt = base_prompt + system_prompt
        
        create_team = get_create_team_tool(model=model)
        
        tools = [create_team]
        
        

        
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    