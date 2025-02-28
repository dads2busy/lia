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
    team_introduced_to_problem: bool = False

@dataclass
class RegisteredAgent:
    agent: Agent
    messages: list
    
def create_agent(name:str,role:str,model:OpenAIModel):
    system_prompt = f"""
        Perform tasks and engage with team members to further user's objective.  Your name is {name}.
        {role}
        Please provide a detailed, evidence-based response. Avoid using clichés, vague generalizations, or platitudes.
        Instead, focus on specific examples, concrete reasoning, and direct, nuanced language that clearly supports your answer.
        
        Response message should be split up into sections to for the target team member or Leader.
        Precede each message portion with '@' and the target team member's users name.        
    """
    print(f"Create Agent : {name} Prompt: {system_prompt}")
    agent = Agent(
        name=name.lower(),
        model=model,
        deps_type=ATeamDeps,
        system_prompt = system_prompt
    )
    
    @agent.system_prompt(dynamic=True)
    async def add_team_to_system_prompt(ctx: RunContext[ATeamDeps]) -> str:
        p = ["Team Members:\n"]
        
        for member in ctx.deps.team:
            p.append(f"{member.name}: {member.role}")
    
        # print(f"Teams for team member prompt: {p}")
        return ' '.join(p)

    return agent

def get_create_team_tool(model=default_model):
    def create_team(ctx: RunContext[str],team: list[TeamMember],retries=5) -> list[TeamMember]:
        """
            Given a list of TeamMember objects, this tool will create expert team members described by the TeamMember objects.
            Once the team has been created, as a group they should self organize to discuss the best way to solve the user's objective.
            Team members must not be named Leader or User.
        """
        print(f"[call team tool in use...]")
        # print(f"Team Call: {team}")
        
        if len(ctx.deps.team)>0:
            return "Team already exists. Work with your current team."
        else:  
            ctx.deps.team += team
            
        for tm in ctx.deps.team:
            if tm.name not in ctx.deps.agents:
                ctx.deps.agents[tm.name.lower()] = RegisteredAgent(agent=create_agent(tm.name,tm.role,model), messages=[])
        
        return ctx.deps.team

    return create_team
   
class ATeamAgent(Agent):
    """
    Returns an ATeam Agent
    """
    def __init__(self, model=default_model,name:str="ATeamAgent",tools=[],deps_type=ATeamDeps,result_type=str,retries:int=1):

        system_prompt=f"""
                Role:
                You are an expert analyst. Your name is 'Leader'.
        """     

        create_team = get_create_team_tool(model=model)
        
        tools = [create_team]

        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=deps_type, result_type=result_type, tools=tools,retries=retries)
        
        @self.system_prompt(dynamic=True)
        async def team_system_prompt(ctx: RunContext[ATeamDeps]) -> str:
            # print(f"Generate Team System Prompt: {ctx.deps.team}")
            
            shared_portion = """
            
            """
            
            team = ctx.deps.team
            if len(team)<1:
                p = """
                    Your current objective is to assemble a team and respond with an introductory message for the individual team members containing their initial tasks.
                    
                    Tasks:
                        1. Obtain objective from the user.
                        2. Generate team of researchers with diverse expertise to consult on the user's objective.
                           Each team member is composed of a TeamMember object with a generated human name and a generated role appropraite for the objective.
                           Do not use 'Leader' or 'User' as the name. 
                           Send the generated team to the create_team tool.
                        3. Generate an introduction to the objective and and an initial set of instructions for each team member.
                        4. Respond with messages for all team members. 
                        
                        Response message should be split up into sections to for the target team member.
                        Precede each message portion with '@' and the target team member's users name.
                         
                        Message for the user should state that the team has been created an you are beginning your initial deliberations with the team.
                        Be sure each message is for one of the new team members or user.
                """
            else:
                teamout = []
                team_names = []
                for tm in ctx.deps.team:
                    teamout.append(f"{tm.name} : {tm.role}\n")
                    team_names.append(tm.name)
                    
                teamout = ' '.join(teamout)
                p = f"""
                    The current team is: 
                        {teamout}

                    Further the discussion with the team members. Point out mistakes that team members make.  Keep the team on the objective.
                    Once the objectives have been met, tell the team to stop and present the output to the user.
                    
                    When the user's objective has been met, say "**Objective Met**"  
                    You should ask team members or the user question by proceeding the target of the question with '@'.  For example, @user,@{',@'.join(team_names)}.
                    If there is a question or action required by the user and work needs to stop until that answer is provided, say "**raise question**" at the end of the response followed by a specific set of questions.
                    
                    Your messages should be structured in sections for the intended audience (a team member or user).  Precede each message section with '@' and the target's name.
                        For example:
                        
                            @{team_names[0]}:
                                Please collected the details about product x.
                            @{team_names[1]}:
                                Here is the results to task 2: 'foobar'.
                            @user:
                                I have righty working on collecting the details of product x. 
                                
                        Second Example:
                            @{team_names[0]}:
                                Please collected the details about product x.
                            @{team_names[1]}:
                                I need more detail about the type of product y to complete my analysis.
                            @user:
                                I have Righty working on collecting the details of product x. 
                        
                        **raise question**
                        Can you please provide more details about product y?    
                    
                    
                """
            # print(f"Ateam agent team system prompt: {p}")
            return p

