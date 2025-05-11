from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIModel
from .context_tools import add_analysis_question, set_analysis_objective, update_analysis_question,delete_analysis_question
from .context_tools import add_analysis_constraint, update_analysis_constraint, delete_analysis_constraint,get_analysis_context
from lia.analysis_context import AnalysisContext
from dataclasses import dataclass
from typing import Union
import json

@dataclass
class AgentDeps:
   analysis_context: AnalysisContext

class ContextManagerAgent(Agent):
    def __init__(self, model,retries:int=1):
        
        name = "ContextManagerAgent"
                
        system_prompt = (
            "You are an expert analyst\n"
            "Your job is to help the user modify the analysis context.\n"
            "Only generate updates to the analysis context when told to.\n"
            "You may be asked to generate questions or constraints. Do not add them to the context unless told to do so.\n"
            "Show information about the analyis context as requested.\n"
            "Retrieve the analysis context before displaying or updating any data.\n"
            "Aks for confirmation before deleting or updating the context.\n"
            "If you are asked a question unrelated to the analysis context, try to answer it.\n"
            "To update the whole analysis context is a multi-tool process: 1.  Get the current context.  2.  Update the objective.  3.  Iterate through each key question and update them."
        )  
    
        tools = [
            get_analysis_context,
            add_analysis_question,
            set_analysis_objective,
            update_analysis_question,
            delete_analysis_question,
            add_analysis_constraint, 
            update_analysis_constraint, 
            delete_analysis_constraint
        ]

        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=AgentDeps, result_type=str, tools=tools,retries=retries)

        async def get_system_prompt(ctx: RunContext[AgentDeps]) -> str: 
            print("Add current analysis context to system prompt") 
            return f'Current Analysis Context: {json.dumps(ctx.deps.analysis_context.__dict__, default=lambda o: o.__dict__, indent=4)}'

    # agent = Agent(
    #     model,
    #     name = 'context_manager_agent', 
    #     tools=tools,
    #     system_prompt=system_prompt, 
    #     deps_type=AgentDeps,
    #     result_type=str,
    #     retries=3
    # )	
    
    # @agent.system_prompt  
    # async def get_system_prompt(ctx: RunContext[AgentDeps]) -> str: 
    #     print("Add current analysis context to system prompt") 
    #     return f'Current Analysis Context: {json.dumps(ctx.deps.analysis_context.__dict__, default=lambda o: o.__dict__, indent=4)}'
    
    # @agent.result_validator
    # async def validate_result(ctx: RunContext[AgentDeps], result: Response) -> Response:
    #     print(f"Validate Results for:\nresult:{result}\n")
    #     print(f"Result Type: {type(result)}")
    #     # if isinstance(result.data, AnalysisContext):
    #     #     return result
    #     return result
    
    # return agent