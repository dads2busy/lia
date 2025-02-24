from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import Agent,RunContext

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
    
@dataclass
class RegisteredAgent:
    agent: Agent
    messages: list
    
def create_agent(name:str,role:str,model:OpenAIModel):
    system_prompt = f"""
        Perform tasks and engage with team members to further user's objective.  Your name is {name}.
        Please provide a detailed, evidence-based response. Avoid using clichés, vague generalizations, or platitudes.
        Instead, focus on specific examples, concrete reasoning, and direct, nuanced language that clearly supports your answer.
    """
    # print(f"Create Agent : {name} Prompt: {system_prompt}")
    return Agent(
        name=name,
        model=model,
        system_prompt = system_prompt
    )

def get_create_team_tool(model=default_model):
    def create_team(ctx: RunContext[str],team: list[TeamMember],retries=5) -> str:
        """
            Given a list of TeamMember objects, this tool will create expert team members described by the TeamMember objects.
            Once the team has been created, as a group they should self organize to discuss the best way to solve the user's objective.
        """
        print(f"Calling all experts....")
        if len(ctx.deps.team)>0:
            return "Team already exists. Work with your current team."
        else:  
            ctx.deps.team += team
            
        for tm in ctx.deps.team:
            if tm.name not in ctx.deps.agents:
                ctx.deps.agents[tm.name] = RegisteredAgent(agent=create_agent(tm.name,tm.role,model), messages=[])
        
        return "The team has been assembled." 

    return create_team
   
class ATeamAgent(Agent):
    """
    Returns an ATeam Agent
    """
    def __init__(self, model=default_model,name:str="ATeamAgent",tools=[],system_prompt=None, result_type=str,retries:int=1):

        base_prompt=f"""
                Role:
                You are an expert analyst. 
                You lead a dynamic team of experts.  
                
                Objective:
                Your objective is to generate the team of experts and then lead the discussion amongst the team and the user.
                The team's job is to analyze the objective, request clarification from the user, develop and refine an execution plan,
                and then finally to execute the plan. 

                Constraints:
                Please provide a detailed, evidence-based response. Avoid using clichés, vague generalizations, or platitudes.
                Instead, focus on specific examples, concrete reasoning, and direct, nuanced language that clearly supports your answer.
                
                Tasks:
                1. Obtain objective from the user.
                2. Generate a list of 1-2 team members with diverse areas of expertise related to the user's objective.
                3. Describe the objective to the team and the initial tasks to team members to begin the discussion.
                4. Once the objectives have been met, tell the team to stop and present the output to the user.
                
                Once the discussions have begun.  It is your job to route messages between team members and the user as needed.  

        """  


        if system_prompt is None:
            system_prompt = base_prompt
        else:
            system_prompt = base_prompt + system_prompt
        
        create_team = get_create_team_tool(model=model)
        
        tools = [create_team]

        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    

