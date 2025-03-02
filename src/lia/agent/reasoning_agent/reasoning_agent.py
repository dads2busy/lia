from dataclasses import dataclass
from pydantic import BaseModel,Field
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai import Agent,RunContext,AgentRunError
import tempfile,os
import subprocess

default_model = OpenAIModel(model_name="llama3.3",base_url="http://localhost:11434/v1",api_key="none") 

    
class ExecuteScriptOutput(BaseModel):
    output: str = Field(..., description="Standard output produced by the script execution")
    
class AgentPythonExecutionError(Exception):
    pass
    
def create_python_executor_tool(container_path:str="/sfs/gpfs/tardis/home/dm8qs/lia/src/lia/tool_image/python_executor.sif", storage_folder:str|None=None, agent_name:str = 'Agent'):
    def execute_script_in_container(python_script: str) -> ExecuteScriptOutput:
        """
            Executes a provided Python3 script.
            
            The execute_script_in_container is available to execute any python3 code you generate 
            for searching the web or performing other analysis.  It has libraries such as pandas,
            scipy,duckdb,requests,and matplotlib availabe for your use.
            
            Your code can check to see if a /workdir folder exists.  If /workdir exists, file output can be stored there.
        """
        # Write the script to a temporary file
        print(f"\n** {agent_name} is executing a python script. **")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp_file:
            temp_file.write(python_script)
            temp_script_path = temp_file.name

        try:
            # Build the command to run the script inside the container
            command = ["apptainer", "exec"]
            if storage_folder:
                command += ["--bind", f"{storage_folder}:/workdir", "--cwd","/workdir"]
    
            command += [   
                container_path,
                "python",
                temp_script_path
            ]
            
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"\n** {agent_name}'s script executed successfully. **")
                return ExecuteScriptOutput(output=result.stdout)
            else:
                # Raise an error with the stderr output for debugging if execution fails.
                print(f"\n** {agent_name}'s script failed. **")
                err_out = f"There was an error executing my script.  Here is the script:\n{python_script}\nHere is the error: {result.stderr}\n."
                raise AgentPythonExecutionError(err_out)
                # print(f"Error executing script: {result.stderr}")
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
                You are an expert analyst. Your name is @Leader.
                
                Objective:
                Your objective is to reason about the objective, create a analysis plan with your team, and then execute the plan.
               
                Constraints:
                Please provide a detailed, evidence-based response. Avoid using clichés, vague generalizations, or platitudes.
                Instead, focus on specific examples, concrete reasoning, and direct, nuanced language that clearly supports your answer.
                
                Tasks:
                1. Determine objective and generate initial tasks for @lefty and @righty.
                2. Examine responses from @lefty and @righty to identify mistakes and improvements.  Continue the discussion towards achieving the user's objective.
                
                When the user's objective has been met, say "**Objective Met**"

                If there is a need for clarification or action required by the user and work needs to stop until that answer is provided, say "**raise question**" at the end of the response followed by a specific question or action required.
                
                Your messages should be structured in sections for the intended audience (righty,lefty, or user).  Precede each message section with '@' and the target's name.
                    For example:
                    
                        @righty:
                            Please collected the details about product x.
                        @lefty:
                            Here is the results to task 2: 'foobar'.
                        @user:
                            I have righty working on collecting the details of product x.  Lefty has the results to task2: 'foobar'
                            
                    Second Example:
                        @righty:
                            Please collected the details about product x.
                        @lefty:
                            I need more detail about the type of product y to complete my analysis.
                        @user:
                            I have Righty working on collecting the details of product x. 
                    
                    **raise question**
                    Can you please provide more details about product y?        
                
        """  


        if system_prompt is None:
            system_prompt = base_prompt
        else:
            system_prompt = base_prompt + system_prompt
        
        # tools=[create_python_executor_tool()]

        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    

