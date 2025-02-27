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
class ATeamDeps:
    team: list
    agents: dict

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
    print(f"Create Agent : {name} Prompt: {system_prompt}")
    return Agent(
        name=name.lower(),
        model=model,
        deps_type=ATeamDeps,
        system_prompt = system_prompt
    )

def get_create_team_tool(model=default_model):
    def create_team(ctx: RunContext[str],team: list[TeamMember],retries=5) -> str:
        """
            Given a list of TeamMember objects, this tool will create expert team members described by the TeamMember objects.
            Once the team has been created, as a group they should self organize to discuss the best way to solve the user's objective.
        """
        print(f"Calling all experts....")
        print(f"Team Call: {team}")
        
        if len(ctx.deps.team)>0:
            return "Team already exists. Work with your current team."
        else:  
            ctx.deps.team += team
            
        for tm in ctx.deps.team:
            if tm.name not in ctx.deps.agents:
                ctx.deps.agents[tm.name.lower()] = RegisteredAgent(agent=create_agent(tm.name,tm.role,model), messages=[])
        
        return "The team has been assembled." 

    return create_team
   
class ATeamAgent(Agent):
    """
    Returns an ATeam Agent
    """
    def __init__(self, model=default_model,name:str="ATeamAgent",tools=[],deps_type=ATeamDeps,result_type=str,retries:int=1):

        system_prompt=f"""
                Role:
                You are an expert analyst. Your name is Leader.
                You lead a dynamic team of experts.  
        """     

        create_team = get_create_team_tool(model=model)
        
        tools = [create_team]

        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=deps_type, result_type=result_type, tools=tools,retries=retries)
        
        @self.system_prompt(dynamic=True)
        async def team_system_prompt(ctx: RunContext[ATeamDeps]) -> str:
            team = ctx.deps.team
            if len(team)<0:
                return """
                    Your task is to obtain an objective from the user.  
                    generate a team of experts with diverse expertise to consult on the objective.
                    Use the 'create_team' tool with the generated team.
                    When the create team tool has been run, generate an introduction including the user's objectives to seed each team member.
                """
            else:
                teamout = []
                for tm in ctx.deps.team:
                    teamout.append(f"{tm.name} : {tm.role}\n")
                teamout = ' '.join(teamout)
                return f"""
                    The current team is: 
                        {teamout}

                    Further the discussion with the team members. Point out mistakes that team members make.  Keep the team on the objective.
                    Once the objectives have been met, tell the team to stop and present the output to the user.
                    
                    When the user's objective has been met, say "**Objective Met**"  
                    You should ask team members or the user question by proceeding the target of the question with '@'.  For example, @user, @larry or @martha.
                    If there is a question or action required by the user and work needs to stop until that answer is provided, say "**raise question**" at the end of the response followed by a specific set of questions.
                    
                    Your messages should be structured in sections for the intended audience (a team member or user).  Precede each message section with '@' and the target's name.
                        For example:
                        
                            @larry:
                                Please collected the details about product x.
                            @martha:
                                Here is the results to task 2: 'foobar'.
                            @user:
                                I have righty working on collecting the details of product x. 
                                
                        Second Example:
                            @larry:
                                Please collected the details about product x.
                            @martha:
                                I need more detail about the type of product y to complete my analysis.
                            @user:
                                I have Righty working on collecting the details of product x. 
                        
                        **raise question**
                        Can you please provide more details about product y?    
                    
                    
                """
    

