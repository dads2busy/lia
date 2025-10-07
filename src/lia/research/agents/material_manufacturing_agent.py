from pydantic_ai import Agent,RunContext
from pydantic import BaseModel,Field
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.mcp import MCPServerStdio,MCPServerStreamableHTTP
from typing import List,Union,Dict,Any

from lia.research.config import ResearchConfig
from lia.research import ResearchPipelineOptions,MaterialProcess,ResearchMaterial,RemoveProcessInstruction,AddMaterialToProcessInstruction,AddProcessInstruction,RemoveMaterialFromProcessInstruction,SetProcessInstruction,AddReferenceToProcessInstruction


class MaterialManufacturingAgentDependencies(BaseModel):
    """
    Dependencies for the Material Manufacturing Agent.
    """
    mode: str

async def get_material_manufacturing_agent(options: ResearchPipelineOptions, mcp_servers: list|None = None):
    provider = OpenAIProvider(base_url=options.llm_api_url, api_key=options.llm_api_key)
    llm_model = OpenAIModel(options.model_name, provider=provider)
    
    if mcp_servers is None:
      mcp_servers = [
        MCPServerStreamableHTTP(url="http://127.0.0.1:8000/mcp/"), # HS Code semantic search (H6 rollup)
        MCPServerStreamableHTTP(url="http://127.0.0.1:8001/mcp/"), # Research Content Semantic Search
        MCPServerStdio('wikipedia-mcp', ["--transport", "stdio", "--log-level", "INFO", "--enable-cache"] + (["--access-token", options.wikimedia_access_token] if options.wikimedia_access_token is not None else [])),
        MCPServerStdio('uvx', args=["mcp-google-cse"], env={"API_KEY": options.google_api_key, "ENGINE_ID": options.google_custom_search_engine_id,"RESULT_NUM":"200"}),
        MCPServerStdio('uvx', ["mcp-server-fetch"]),
      ]

    instructions = """
  You are a materials engineer and manufacturing expert.  Your goal is to identify the key processes, precursors, products, and references for manufacturing a given set of materials.
  You will be given a a material, its aliases and information about known processes for the material if they have already been identified.
  Based on this information, you must generate a list of instructions that describe how to manage the processes for each material.
  
  Each instruction must be one of the following types:
    - AddMaterialToProcessInstruction
      * Add a new material to an existing process
      * 'additon_type' field defines whether or not the material is a precursor or a product
      * 'material' field with a SuggestedMaterialReference or a string for minor materials
    - AddProcessInstruction
      * Add a new process to the material, 
      * requires a 'process' field with a MaterialProcess object
    - RemoveProcessInstruction
      * Remove an existing process from the material
      * requires a 'process_id' field with the ID of the process to remove
    - RemoveMaterialFromProcessInstruction
      * Remove a material from an existing process
      * 'removal_type' field defines whether or not the material is a precursor or a product
      * 'material' field with a SuggestedMaterialReference (with matching HS Code for the material to remove) or a string that is ane exact match for the name you want to remove    
    - SetProcessInstruction
      * Set the description and/or scale of an existing process
      * 'process_id' field with the ID of the process to update
      * 'description' field with the new description of the process, None if no change
      * 'scale' field with the new scale of the process, None if no change
    - AddReferenceToProcessInstruction
      * Add a reference to an existing process
      * 'process_id' field with the ID of the process to add the reference to
      * 'references' field with a list of URLs that describe the process in detail. References should be from diverse sources (e.g. Wikipedia, scientific papers, patents, etc.) and internet domains and should not include any '#' or fragment identifiers.
  
  Examples:
  ** Add a new process (AddProcessInstruction)
  ```
  {
    "process": {
      "description": "Reduction of boric acid with magnesium to produce elemental boron",
      "scale": 0.8,
      "precursors": [
        {"suggested": True, "name": "Boric Acid", "hs_code": "281000"},
        {"suggested": True, "name": "Magnesium", "hs_code": "810410"}
      ],
      "products": [
        {"suggested": True, "name": "Elemental Boron", "hs_code": "280470"},
        "Minor byproduct discarded as waste"
      ],
      "references": ["https://example.com/boron_reduction_process"]
    }
  }
  ```
  ** Add a new material to an existing process (AddMaterialToProcessInstruction)
  ```
  {
    "addition_type": "precursor",  # or "product"
    "material": {
      "suggested": True,
      "name": "Boric Acid",
      "hs_code": "281000"
    },
    "process_id": "9930ae9e-6c59-4069-bb51-9aed715c7582"  # ID of the process to add the material to
  }
  ```
  ** Remove a material from an existing process (RemoveMaterialFromProcessInstruction)
  ```
  {
    "removal_type": "precursor",  # or "product"
    "material": {"hs_code": "281000", name: "Boric Acid"},  # MaterialReference with matching HS Code 
    "process_id": "9930ae9e-6c59-4069-bb51-9aed715c7582"  # ID of the process to remove the material from
  }
  ```
  or
  ```
  { 
    "removal_type": "precursor",  # or "product"
    "material": "Boric Acid",  # String for minor material without HS Code
    "process_id": "9930ae9e-6c59-4069-bb51-9aed715c7582"  # ID of the process to remove the material
  }
  ```
  ** Set the description and/or scale of an existing process (SetProcessInstruction)
  ```
  {
    "process_id": "9930ae9e-6c59-4069-bb51-9aed715c7582",  # ID of the process to update
    "description": "New description of the process",  # New description, None if no change
    "scale": 0.8  # New scale, None if no change
  }
  ```
  ** Add a reference to an existing process (AddReferenceToProcessInstruction)
  ```
  {
    "process_id": "9930ae9e-6c59-4069-bb51-9aed715c7582",  # ID of the process to add the reference to
    "references": ["https://example.com/boron_reduction_process"]  # List of URLs that describe the process in detail
  }
  ``` 
  
  Rules:
- Do not include any additional fields in the JSON process objects.
- Do not add duplicate processes. If a process with the same description already exists, you should either update it or skip adding it.
- There MUST be no duplicate materials in the precursors or products lists of a process.
- A material can only be a precursor OR a product in a process, not both. 
- A process should be specific to a material and set of precursors.  If necessary, split processes into multiple entries if they apply to different materials or precursor sets.
  For example, this process:
  'Reduction of boric acid or boron oxides with magnesium or aluminium to produce elemental boron'
  should be split into two processes:
  - One for magnesium as a precursor 
  - One for aluminium as a precursor
- References MUST be the URL string only.  Reference should not include a '#' or any fragment identifier.
- Precursors are ONLY materials of the form that are directly required for the process.  Products are ONLY the form of materials that are produced as a result of the process.

Do not include any additional fields in the JSON process objects.
  """
    
    agent = Agent(model=llm_model, output_type=list[Union[AddMaterialToProcessInstruction,AddProcessInstruction,RemoveProcessInstruction,RemoveMaterialFromProcessInstruction,SetProcessInstruction,AddReferenceToProcessInstruction]],instructions=instructions, deps_type=MaterialManufacturingAgentDependencies, retries=5, mcp_servers=mcp_servers) 
    
    @agent.instructions
    async def create_mode_instructions(ctx:RunContext[MaterialManufacturingAgentDependencies])-> str:
        """
        Generate instructions based on the mode and material.
        """
        if ctx.deps.mode == "create":
            return """
Given a material and its aliases, you must generate a list of industrial or commericial processes that are used to produce the material.  For each process, you must identify:
- A description of the process
- A list of precursor materials that are required for the process in SuggestedMaterialReference format. 
  If the precursor material is of minor significance, do not include it.  If it is important but does not have a specific HS Code, include it as a a string instead of a SuggestedMaterialReference.
- A list of products that are produced as a result of the process in SuggestedMaterialReference format. If the material in question is waste or will otherwise be discarded, use a simple string.
- A list of references (URLs) that describe the process in detail. References should be from diverse sources (e.g. Wikipedia, scientific papers, patents, etc.) and internet domains and should not include any '#' or fragment identifiers.
- The scalability in terms of capacity and commercial viability of the process from 0.0 to 1.0, where 0.0 is possible in a laboratory setting but not commercially viable, and 1.0 is a process that is in commercial use with market adoption.

If the HS Code is Unknown, use a string instead of a SuggestedMaterialReference

You must return a list of `AddProcessInstruction` to add new processes to the material.

Do not include any additional fields in the JSON process objects.
"""

    @agent.instructions
    async def edit_mode_instructions(ctx:RunContext[MaterialManufacturingAgentDependencies])-> str:
        """
        Generate instructions based on the mode and material.
        """
        if ctx.deps.mode == "edit":
            return """
You will be given a a material and known processes for creating the material.
You must review the existing processes and generate a list of instructions that describe modifications that are required to improve the accuracy and completeness of the processes for the material.

If there are missing processes, you must generate an `AddProcessInstruction` to add a new process to the material.
If there are duplicates processes, you may remove them using a `RemoveProcessInstruction` if the process is not needed.
If there are existing processes that need to be updated, you must generate a `SetProcessInstruction` to update the description or scale of the process.
If there are existing processes that need to have materials (precursors or products) added or removed, you must generate `AddMaterialToProcessInstruction` or `RemoveMaterialFromProcessInstruction` to add or remove materials from the process.
Do not allow duplicate materials in the precursors or products lists of a process. A material can only be a precursor OR a product in a process, not both.
To move a process from a precursor to a product (or visa versa), you must remove the material from the process and then add it back in the correct role. (two separate instructions)
If there are additional references that need to be added to the process, you must generate an `AddReferenceToProcessInstruction` to add the reference to the process. Strive for diversity in the references, including scientific papers, patents, and other authoritative sources.  References should be from diverse sources (e.g. Wikipedia, scientific papers, patents, etc.) and internet domains and should not include any '#' or fragment identifiers.

You must return a list of instructions (AddProcessInstruction, SetProcessInstruction, AddMaterialToProcessInstruction, RemoveMaterialFromProcessInstruction, AddReferenceToProcessInstruction) to modify the existing processes for the material.
Do not include any additional fields in the JSON process objects.

"""

    return agent
  
  
