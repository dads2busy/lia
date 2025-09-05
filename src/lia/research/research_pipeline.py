from pydantic_graph import BaseNode,End,GraphRunContext,Graph
from typing import List,Dict,Any,Union
from pydantic import BaseModel,Field
from dataclasses import dataclass,field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai import UsageLimitExceeded
from pydantic_ai.models.openai import OpenAIModel,OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
import hashlib
import asyncio
import json
from pydantic_ai.mcp import MCPServerStdio,MCPServerHTTP
import asyncio
from typing import Callable, List, TypeVar, Awaitable
import os

from lia.research.research_cli import load_config
from lia.research.agents.researcher_agent import get_researcher_agent
from lia.research.agents.url_scorer_agent import get_url_scorer_agent
from lia.research.agents.material_classificaton_agent import get_material_classification_agent
from lia.research.agents.material_manufacturing_agent import get_material_manufacturing_agent
from lia.research.agents.reference_reviewer_agent import get_reference_reviewer_agent
from lia.research.agents.material_finder_agent import get_material_finder_agent
from lia.research.agents.process_merging_agent import get_process_merging_agent
from lia.research import ResearchPipelineOptions
from lia.research.config import ResearchConfig,load_config,save_config
from lia.research.research_tasks import generate_research_material,generate_material_processes,review_material_processes,expand_process_materials,purge_processes,expand_product_family_materials,review_materials,merge_duplicate_processes
from lia.util.mcp_server_manager import launch_all_mcp_servers
from lia.research.pipeline_state import ResearchPipelineState,load_state,save_state,backup_state
import sys



async def get_agents(options:ResearchPipelineOptions) -> Dict[str,Agent]:
    print("Get Agents")
    return {
        # "researcher_agent":await get_researcher_agent(options),
        "url_scorer_agent": await get_url_scorer_agent(options),
        "material_classification_agent": await get_material_classification_agent(options),
        "reference_reviewer_agent": await get_reference_reviewer_agent(options),
        "material_manufacturing_agent": await get_material_manufacturing_agent(options),
        "material_finder_agent": await get_material_finder_agent(options),
        "process_merging_agent": await get_process_merging_agent(options),
    }
    

ResearchTaskGraph = Graph(nodes=[generate_research_material,generate_material_processes,review_material_processes,expand_process_materials,purge_processes,expand_product_family_materials,review_materials,merge_duplicate_processes])

start_map = {
    "generate_materials": generate_research_material,
    "review_materials": review_materials,
    "generate_material_processes": generate_material_processes,
    "review_material_processes": review_material_processes,
    "purge_processes": purge_processes,
    "expand_process_materials": expand_process_materials,
    "expand_product_family_materials": expand_product_family_materials,
    "merge_duplicate_processes": merge_duplicate_processes,
}

async def run_research_pipeline(options: ResearchPipelineOptions):
    """
        Run the research pipeline. 
        - research_folder: Folder containing the research configuration and state
        - options: ResearchPipelineOptions containing model and API settings
    """
    research_folder = options.research_folder
    research_config = load_config(research_folder)
    #Get Agents and setup or load the initial state
    agents = await get_agents(options)   
    
    if not options.generate_materials and options.maximum_reference_reviews>1:
        print("Warning: maximum_reference_reviews is set to more than 1, but generate_materials is False. Setting maximum_reference_reviews to 1.")
        options.maximum_reference_reviews = 1
    
    backup_state(research_folder)
        
    state = ResearchPipelineState(research_config=research_config, agents=agents, options=options)
    try:
        print("Loading State...")
        state = load_state(research_folder,state)
    except FileNotFoundError:
        print("No existing state found, starting fresh.")
    except Exception as e:
        print(f"Error loading state: {e}")
        raise

    if options.debug:
        print(f"state loaded: {state.model_dump_json(indent=2)}")

    if options.start is not None and options.start not in start_map:
        raise ValueError(f"Invalid start option: {options.start}. Must be one of {list(start_map.keys())}.")

    if options.start is None:
        print("No start option provided, defaulting to generate_research_material.")
        start = generate_research_material
    else:
        print(f"Starting from: {options.start} {start_map[options.start]}")
        start = start_map[options.start]



    try:
        async with launch_all_mcp_servers(list(agents.values())):
            result = await ResearchTaskGraph.run(start(), state=state)
            # print(f"research pipeline results:\n************\n{result.output}************\n")
            print(f"Research Pipeline completed. Data can be found in {research_folder}.")
            
            if options.save_state:
                save_state(research_folder, result.output)   
            else:
                print("Skipping state save as per configuration.")
                
            return result.output

    except Exception as e:
        print(f"An error occurred in run_research_pipeline: {e}")
        raise
    
def main():
    if len(sys.argv) < 2:
        print("Usage: python research_pipeline.py <output_file>")
        sys.exit(1)

    output_file = sys.argv[1]
    ResearchTaskGraph.mermaid_save(
        output_file,start=generate_research_material,
        direction="TB",title="Research Pipeline",
    )
    print(f"Mermaid diagram saved to {output_file}")


if __name__ == "__main__":
    main()