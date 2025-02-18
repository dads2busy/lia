from pydantic_ai import RunContext, Tool
from typing import List, Optional,Union
from lia.analysis_context import AnalysisContext


def get_analysis_context(ctx: RunContext[str]) -> AnalysisContext:
     """
          returns the current analysis context.
          You can use this tool to retrieve the whole analysis context and use the properties of the analysis, such as the object, the key questions, the constraints, and the methodology or plan.
     """
     print(f"Retrieving the current analysis context...")
     return ctx.deps.analysis_context

def add_analysis_question(ctx: RunContext[str], question:str) -> AnalysisContext:
    """
     Inserts (appends, adds) a new key question related to object to the analysis context.
    """
    print(f"Using add question tool: {question}")
    question.replace('"','')
    if question in ctx.deps.analysis_context.key_questions:
        print(f"Question already exists in the analysis context: {question}")
        return ctx.deps.analysis_context
    ctx.deps.analysis_context.key_questions.append(question)
    return ctx.deps.analysis_context

def update_analysis_question(ctx: RunContext[str], updated_question:str,position:int) -> AnalysisContext:
     """
          Updates a question in the analysis context given the position in the list (an integer starting at 0)
     """
     print(f"Using update question tool: {position} -> {updated_question}")
     ctx.deps.analysis_context.key_questions[position] = updated_question
     return ctx.deps.analysis_context

def delete_analysis_question(ctx: RunContext[str], position:int) -> AnalysisContext:
     """
          Deletes (removes) a key question in the analysis context given the position in the list (an integer starting at 0)
     """
     print(f"Using delete question tool: {position} current size: {len(ctx.deps.analysis_context.keyquestions)}")
     ctx.deps.analysis_context.key_questions.pop(position)
     print(f"Updated Context Count {len(ctx.deps.analysis_context.keyquestions)}")
     return ctx.deps.analysis_context

def add_analysis_constraint(ctx: RunContext[str], constraint:str) -> AnalysisContext:
    """
     Adds a new 'constraint' to be added to the analysis context.
    """
    print(f"Using add constraint tool: {constraint}")
    ctx.deps.analysis_context.constraints.append(constraint)
    return ctx.deps.analysis_context   

def update_analysis_constraint(ctx: RunContext[str], updated_constraint:str, position:int) -> AnalysisContext:
     """
          Updates a constraint in the analysis context given the position in the list (an integer starting at 0)
          The constraint position 'position' will be set to 'updated_constraint'.
     """
     print(f"Using update constraint tool: {position} -> {updated_constraint}")
     ctx.deps.analysis_context.constraints[position] = updated_constraint
     return ctx.deps.analysis_context
def delete_analysis_constraint(ctx: RunContext[str], position:int) -> AnalysisContext:
     """
          Deletes (removes) a constraint in the analysis context given the position of the question in the list (an integer starting at 0)
          The constraint position 'position' will be deleted.
     """
     print(f"Using delete constraint tool: {position}")
     ctx.deps.analysis_context.constraints.pop(position)
     return ctx.deps.analysis_context


def set_analysis_objective(ctx: RunContext[str], objective:str) -> AnalysisContext:
   """
   Sets or updates the objective on the analysis context.
   Must only be used when the user specifically instructs you to update the objective.
   """
   print(f"Using set objective tool: {objective}")
   ctx.deps.analysis_context.objective = objective
   return ctx.deps.analysis_context

def preliminary_analysis_tool(ctx: RunContext[str]) -> str:
    """
    Returns a preliminary analysis of the context.
    """
    print(f"Using preliminary analysis tool")
    return ctx.deps.analysis_context
