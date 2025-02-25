from dataclasses import dataclass
from pydantic import BaseModel,Field
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import Agent,RunContext
import tempfile,os
import subprocess

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
    
class ExecuteScriptOutput(BaseModel):
    output: str = Field(..., description="Standard output produced by the script execution")

def create_python_executor_tool(container_path:str="/home/dmachi/lia/src/lia/tool_image/python_executor.sif"):
    def execute_script_in_container(python_script: str) -> ExecuteScriptOutput:
        """
            Executes a provided Python script.
        """
        # Write the script to a temporary file
        print("[execute_script_in_container] Executing python script")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp_file:
            temp_file.write(python_script)
            temp_script_path = temp_file.name

        try:
            # Build the command to run the script inside the container
            command = [
                "apptainer", "exec",
                container_path,
                "python",
                temp_script_path
            ]
            print(f"Execute script {command}")
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode == 0:
                return ExecuteScriptOutput(output=result.stdout)
            else:
                # Raise an error with the stderr output for debugging if execution fails.
                # raise RuntimeError(f"Error executing script: {result.stderr}")
                print(f"Error executing script: {result.stderr}")
        finally:
            # Ensure that the temporary file is removed after execution
            os.remove(temp_script_path)
        
            
    return execute_script_in_container
   
class ReasoningAgent(Agent):
    """
    Returns a Reasoning Agent
    """
    def __init__(self, model=default_model,name:str="ReasoningAgent",tools=[],system_prompt=None, result_type=str,retries:int=1):

        base_prompt=f"""
                Role:
                You are an expert analyst. 
                
                Objective:
                Your objective is to reason about the objective and then execute.
                You will communicate with the left and right half of your brain (lefty and righty) to analyze the objective, request clarification from the user, develop and refine an execution plan,
                and then finally to execute the plan. 

                Constraints:
                Please provide a detailed, evidence-based response. Avoid using clichés, vague generalizations, or platitudes.
                Instead, focus on specific examples, concrete reasoning, and direct, nuanced language that clearly supports your answer.
                
                You should ask the user for clarifications or additional context by proceeding the question with "@user" when needed by you, lefty, or righty.
                
                When you think the objective has been met, ask the user to see whether to continue or not.
        """  


        if system_prompt is None:
            system_prompt = base_prompt
        else:
            system_prompt = base_prompt + system_prompt
        
        tools=[create_python_executor_tool()]

        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    

