from pydantic import BaseModel,Field
import tempfile,os
import subprocess

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