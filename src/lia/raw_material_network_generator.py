from pydantic_graph import BaseNode,End,GraphRunContext,Graph
from typing import List,Dict,Any,Union
from dataclasses import dataclass,field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai import UsageLimitExceeded
from pydantic_ai.models.openai import OpenAIModel,OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from .system_prompts.network_agent_system_prompt import network_agent_system_prompt
from .system_prompts.reviewer_agent_system_prompt import reviewer_agent_system_prompt
from .system_prompts.preliminary_research_agent_prompt import preliminary_research_agent_prompt

from pydantic import BaseModel,Field
import asyncio
import pprint
import json
from pydantic_ai.mcp import MCPServerStdio,MCPServerHTTP

import asyncio
import socket

research_mcp_servers = [
    MCPServerStdio('uvx', ["duckduckgo-mcp-server"]),
    # MCPServerStdio('python', ["-m", "mcp_simple_arxiv"]),
    MCPServerStdio('wikipedia-mcp', ["--transport", "stdio"]),
]

generator_mcp_servers = [
    MCPServerStdio('uvx', ["duckduckgo-mcp-server"]),
    # MCPServerStdio('python', ["-m", "mcp_simple_arxiv"]),
    MCPServerStdio('wikipedia-mcp', ["--transport", "stdio"]),
    # MCPServerStdio('python', ["tools/mcp-server-hscode-sql.py"]),
    MCPServerHTTP(url="http://127.0.0.1:8000/mcp")
]       

reviewer_mcp_servers = [
    MCPServerStdio('uvx', ["duckduckgo-mcp-server"]),
    # MCPServerStdio('python', ["-m", "mcp_simple_arxiv"]),
    MCPServerStdio('wikipedia-mcp', ["--transport", "stdio"]),
    # MCPServerStdio('python', ["tools/mcp-server-hscode-sql.py"]),
    MCPServerHTTP(url="http://127.0.0.1:8000/mcp")
]       

class SuggestedChanges(BaseModel):
    has_updates: bool = False
    recommendations: str = ""
    
class Material(BaseModel):
    name: str
    hscode: str
    description: str

class Node(BaseModel):
    id: str
    material: str
    stage: str = Field(default="Other", description="mined|intermediate|product|assembly|recycled|other")
    description: str | None = None

    
class Link(BaseModel):
    source: list[str] = Field(default_factory=list, description="HS6 codes of parent nodes")
    target: str = Field(default_factory=list, description="HS6 codes of child node")
    references: list[str] = Field(default_factory=list, description="URLs to sources describing the process")      
    process: str = Field(default="Other", description="Industrial transformation")
    
class DAG(BaseModel):
    nodes: List['Node'] =field(default_factory=list)
    links: List['Link'] =field(default_factory=list)

class ValidatedReference(BaseModel):
    """
        A structure describing a valid (or invalid) reference
        - 'url' - The URL in question
        - 'reachable' - Whether the url can be retrieved properly
        - 'source_quality_score' - A ranking of trustworthiness of the target url (value between 0 and 1 inclusive)
        - 'process_supported' - Whether or not the URL's content supports the process in question
        - 'precursors_supported' - List precursors supported by the reference
        - 'byproducts_supported' - List of byproducts supported by the reference
        - 'summary' - Summary of the validity
    """
    url: str
    reachable: bool
    process_supported: bool
    source_quality_score: float = 0.0
    precursors_supported: list[str]= field(default_factory=list)
    byproducts_supported: list[str]= field(default_factory=list)
    summary: str

class ValidatedTransformationProcesses(BaseModel):
    """
        A process to perform a material transformation.
        - 'description' - Description of the process
        - 'validated' - Whether or not this process appears to be supported by the references
        - 'reason' - Reasoning behind the 'validated' decision
        - 'references' - list of ValidatedReference Objects which contain Validation and scoring of each process/reference.
    """
    description: str
    validated: bool
    reason: str
    references: List[ValidatedReference] = field(default_factory=list)

class ValidatedMaterial(BaseModel):
    """
        Information about a particular material gathered through preliminary research
        - 'name' - Canonical name of the material
        - 'processes' - A list of TransformationProcesses that are used in order mine,refine, or otherwise produce material
    """
    name: str
    processes: List[ValidatedTransformationProcesses] = field(default_factory=list)

class ValidatedResearch(BaseModel):
    """
        Preliminary Research data about a material to be used in downstream production of networks.
        - 'material' - The name of the material being researched
        - 'research' - A list of PreliminaryResearchMaterial contained other forms and compounds of the material being researched.
    """
    material: str
    research: List[ValidatedMaterial] = field(default_factory=list)
    
class TransformationProcesses(BaseModel):
    """
        A process to perform a material transformation.
        - 'description' - Description of the process
        - 'precursors' - List of materials that are required for this process
        - 'byproducts' - Output, other than the primary output this transformation is describing, from this process
        - 'references' - URLs to websites / papers describing the process in detail
    """
    description: str
    precursors: List[str] = field(default_factory=list)
    byproducts: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    
class PreliminaryResearchMaterial(BaseModel):
    """
        Information about a particular material gathered through preliminary research
        - 'name' - Canonical name of the material
        - 'category' - 'mined' | 'intermediate' | 'other'
        - 'aliases' - List of other names the material is known by. Includes common names and industry specific names
        - 'primary_uses' - The primary downstream uses of the material
        - 'processes' - A list of TransformationProcesses that are used in order mine,refine, or otherwise produce material
    """
    name: str
    category: str
    aliases: List[str] = field(default_factory=list)
    primary_uses: List[str] = field(default_factory=list)
    processes: List[TransformationProcesses] = field(default_factory=list)

class PreliminaryResearch(BaseModel):
    """
        Preliminary Research data about a material to be used in downstream production of networks.
        - 'material' - The name of the material being researched
        - 'research' - A list of PreliminaryResearchMaterial contained other forms and compounds of the material being researched.
    """
    material: str
    research: List[PreliminaryResearchMaterial] = field(default_factory=list)

class GenerateSupplyChainNetworkOptions(BaseModel):
    model_name: str = "llama3.3"
    llm_api_url: str | None = "http://localhost:11434/v1"
    llm_api_key: str = ""
    preliminary_research_only: bool = False
    preliminary_research_data: PreliminaryResearch|None = None
    preliminary_research_rounds: int | None = 1
    max_network_reviews: int | None = 5
    max_secondary_reviews: int | None = 2
    
@dataclass
class NetworkBuilderState:
    material: str
    preliminary_research: PreliminaryResearch|None = None
    preliminary_round=int(0)
    validated_research: ValidatedResearch|None = None
    description: str|None = None
    network_suggested_changes: SuggestedChanges = field(default_factory=lambda: SuggestedChanges(has_updates=False))
    network_reviews = int(0)
    secondary_reviews = int(0)
    network_secondary_review: bool = False
    options: GenerateSupplyChainNetworkOptions = field(default_factory=GenerateSupplyChainNetworkOptions)
    network: DAG|None = None
    network_generator_history:List = field(default_factory=list)
    network_reviewer_history:List = field(default_factory=list)

async def get_raw_material_network(material: str, options: GenerateSupplyChainNetworkOptions,graph_only:bool=False):
    provider = OpenAIProvider(base_url=options.llm_api_url,api_key=options.llm_api_key)
    default_model = OpenAIModel(options.model_name,provider=provider)
    network_agent = Agent(model=default_model, result_type=DAG,system_prompt=network_agent_system_prompt,mcp_servers=generator_mcp_servers,retries=5)
    reviewer_agent = Agent(model=default_model,result_type=SuggestedChanges,system_prompt=reviewer_agent_system_prompt,mcp_servers=reviewer_mcp_servers,retries=5)
    preliminary_research_agent = Agent(model=default_model,result_type=PreliminaryResearch,system_prompt=preliminary_research_agent_prompt,mcp_servers=research_mcp_servers,retries=5)
    reference_review_agent = Agent(model=default_model,result_type=ValidatedTransformationProcesses,system_prompt=preliminary_research_agent_prompt,mcp_servers=research_mcp_servers,retries=5)
    clean_reviewer_agent = Agent(model=default_model,result_type=SuggestedChanges,system_prompt=reviewer_agent_system_prompt,mcp_servers=reviewer_mcp_servers,retries=5)
    
    
    @dataclass
    class ReviewPreliminaryResearchReferences(BaseNode[NetworkBuilderState]):

        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','DoPreliminaryResearch','End','ReviewPreliminaryResearchReferences']:
            
            if ctx.state.preliminary_research is None:
                print(f"There is currently no preliminary research for {ctx.state.material}")
                return End(ctx.state)
            
            print("Creating validated research object")
            validated_research = ValidatedResearch(material=ctx.state.material,research=[])
            print(f"ValidatedResearch: {validated_research}")
            for material in ctx.state.preliminary_research.research:
                validated_material = ValidatedMaterial(name=material.name,processes=[])
                print(f"Validating references for {material.name}....")
                for process in material.processes:
                    try: 
                        prompt = f"""
Material:
{material.name}

Process Description:
{process.description}

Precursors:
{", ".join(process.precursors)}
                                            
Byproducts:  
{', '.join(process.byproducts)}

References:
 
                        """
                        prompt += '\n'.join(process.references)
                        print(f"Review Prompt: \n{prompt} {process}")
                        r = await reference_review_agent.run(prompt, model_settings={'temperature': 1},usage_limits=UsageLimits(request_limit=200))

                        # print(f"Preliminary Research: {ctx.state.preliminary_research}")
                        print(f"Result: {r.output}")
                        validated_material.processes.append(r.output)
                
                    except Exception as err:
                        print(f"Error in DoPreliminaryResearch: {err}")
                        if getattr(err,'body',{}) and 'code' in err.body and err.body['code']=="rate_limit_exceeded":
                            print(f"Usage limit exceeded: {err}")
                            await asyncio.sleep(20)
                            return ReviewPreliminaryResearchReferences()
                        
                validated_research.research.append(validated_material)
                    
            ctx.state.validated_research=validated_research
            
            if ctx.state.options.preliminary_research_only:
                return End(ctx.state)
            
            return GetMaterialNetwork()  
    
    
    @dataclass
    class DoPreliminaryResearch(BaseNode[NetworkBuilderState]):

        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','DoPreliminaryResearch','ReviewPreliminaryResearchReferences','End']:
            if ctx.state.preliminary_round < ctx.state.options.preliminary_research_rounds:
                print(f"Performing Preliminary Research on {ctx.state.material} Round {ctx.state.preliminary_round+1} / {ctx.state.options.preliminary_research_rounds}")
                try: 
                    if ctx.state.preliminary_round == 0 and ctx.state.preliminary_research is None:
                        prompt = f"""
                            Please research: {ctx.state.material}.
                        """
                    else:
                        if ctx.state.preliminary_research is not None:
                            print(f"\tExtending pre-existing preliminary research. len(materials): {len(ctx.state.preliminary_research.research)}")
                            
                        prompt = f"""
                            Perform another round of research on {ctx.state.material}.
                                                                                
                            The current list is:
                            {json.dumps(ctx.state.preliminary_research.dict(),indent=2)}
    
                            Review and expand the network: 
                            - Identify additional forms of the material 
                            - Consolidate duplicate materials,uses, and/or processes
                            - Verify that process references are accessible and contain information about the process, precursors, and byproducts being defined.
                            - Ensure accuracy of information that already exists in the list
                            
                        """
                    
                    r = await preliminary_research_agent.run(prompt, model_settings={'temperature': 1},usage_limits=UsageLimits(request_limit=200))
                    ctx.state.preliminary_round += 1
                    ctx.state.preliminary_research = r.output
                    # print(f"Preliminary Research: {ctx.state.preliminary_research}")
                    return DoPreliminaryResearch()
                except UsageLimitExceeded as err:
                    print(f"DoPreliminaryResearch: Usage limit exceeded: {err}")
                    await asyncio.sleep(20)
                    return DoPreliminaryResearch()
                except Exception as err:
                    print(f"Error in DoPreliminaryResearch: {err}")
                    if getattr(err,'body',{}) and 'code' in err.body and err.body['code']=="rate_limit_exceeded":
                        print(f"Usage limit exceeded: {err}")
                        await asyncio.sleep(20)
                        return DoPreliminaryResearch()
            # if ctx.state.options.preliminary_research_only:
            #     return ReviewPreliminaryResearchReferences(ctx.state)
            
            return ReviewPreliminaryResearchReferences()
    
    
    @dataclass
    class GetMaterialNetwork(BaseNode[NetworkBuilderState]):

        async def run(self, ctx: GraphRunContext) -> Union['ReviewNetwork','GetMaterialNetwork']:
            print(f"GetMaterialNetwork...{ctx.state.material}")
            try: 
                if not ctx.state.network_suggested_changes.has_updates:
                    prompt = f"""
                        
                        Here is the preliminary research for {ctx.state.material}. Use the list of materials as nodes in the network and complete the network.
                        The preliminary research provides a list of materials, names, aliases, and primary uses, transformation processes (with precursors,byproducts, and references). 
                        Ensure that the final network represents all of the materials listed and is traced towards products for each of the use cases identified for each product.
                        
                        {json.dumps(ctx.state.preliminary_research.dict(),indent=2)}
                        
                        Perform the task for material: {ctx.state.material}.
                    """
                    r = await network_agent.run(f"Perform the task for material:\n{ctx.state.material}. ",message_history=ctx.state.network_generator_history,model_settings={'temperature': .5},usage_limits=UsageLimits(request_limit=500))
                    ctx.state.network_generator_history += r.new_messages()
                    ctx.state.network = r.data

                else:
                    prompt = f"""
                        Review the network for material: {ctx.state.material}.
                    
                        Current network:
                        {serialize_material_network(ctx.state.network)}
                        
                        {ctx.state.network_suggested_changes.recommendations if ctx.state.network_suggested_changes.recommendations else ""}
                        Please review and update network to reflect the suggested changes.  Do not use any suggestionst that would violate the rules above.
                        Return the updated network JSON.  
                    """
                    if ctx.state.network_secondary_review:
                        print(f"Processing recommended changes from secondary reviewer:\n{ctx.state.network_suggested_changes.recommendations}")
                    else:
                        print(f"Processing recommended changes:\n{ctx.state.network_suggested_changes.recommendations}")
                        
                    r = await network_agent.run(prompt,message_history=ctx.state.network_generator_history, model_settings={'temperature': .75},usage_limits=UsageLimits(request_limit=200))
                    ctx.state.network_generator_history += r.new_messages()
                    print(f"Generator Pass Completed. Network Nodes: {len(r.data.nodes)} Edges: {len(r.data.links)}") 
                    ctx.state.network = r.data
            
            except UsageLimitExceeded as err:
                print(f"Usage limit exceeded: {err}")
                
                await asyncio.sleep(20)
                return GetMaterialNetwork()
            except Exception as err:
                print(f"Error in GetMaterialNetwork: {err}")
                if getattr(err,'body',{}) and 'code' in err.body and err.body['code']=="rate_limit_exceeded":
                    print(f"Usage limit exceeded: {err}")
                    await asyncio.sleep(20)
                    return GetMaterialNetwork()

            return ReviewNetwork()  

    def verify_source_nodes_exist(network: DAG):
        """
        Verifies that all source nodes in the network's links exist in the node list
        and that all nodes have at least one edge.

        Parameters:
            network (DAG): A DAG object with 'nodes' and 'links' attributes.

        Returns:
            True if all source and target nodes exist and all nodes have at least one edge.
            Otherwise, returns a list of tuples (missing_type, missing_id, process_description).
        """
        node_ids = {node.id for node in network.nodes}
        missing = []

        # Verify source and target nodes exist
        for link in network.links:
            source_ids = link.source
            for source_id in source_ids:
                if source_id not in node_ids:
                    process = link.process or "UNKNOWN PROCESS"
                    missing.append(("Missing Node", source_id, process))
            
            target_id = link.target
            if target_id and target_id not in node_ids:
                process = link.process or "UNKNOWN PROCESS"
                missing.append(("Missing Node", target_id, process))

        # Verify all nodes have at least one edge
        nodes_with_edges = {node_id for link in network.links for node_id in link.source + [link.target]}
        for node in network.nodes:
            if node.id not in nodes_with_edges:
                missing.append(("Missing Edge", node.id, "No edges associated with this node"))

        return False if not missing else missing
    
    @dataclass 
    class VerifiyNodesExist(BaseNode[NetworkBuilderState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','End']:
            print(f"Verifying all edge source and target nodes exist and all nodes have at least one edge...")
            errors = verify_source_nodes_exist(ctx.state.network)
            if not errors:
                return End(ctx.state)
            else:
                suggestions = "\n".join([
                    f"{error_type}: {missing_id} - {process_description}" 
                    for error_type, missing_id, process_description in errors
                ])
                ctx.state.network_suggested_changes.has_updates = True
                ctx.state.network_suggested_changes.recommendations = f"Missing source and/or target nodes in network:\n{suggestions}\n Please ensure they are added to the network."
                ctx.state.network_secondary_review = True
                if ctx.state.secondary_reviews >= ctx.state.options.max_secondary_reviews:
                    ctx.state.options.max_secondary_reviews += 1
                    
                return GetMaterialNetwork()
            
    @dataclass
    class ReviewNetwork(BaseNode[NetworkBuilderState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','ReviewNetwork','VerifiyNodesExist']:
            if ctx.state.network_reviews < ctx.state.options.max_network_reviews:
                print(f"({ctx.state.network_reviews+1} of {ctx.state.options.max_network_reviews}) Reviewing Network.")

                
                #make sure there is at least one secondary review after the normal reviews
                if ctx.state.secondary_reviews >= ctx.state.options.max_secondary_reviews:
                    ctx.state.options.max_secondary_reviews += 1
                    
                try: 

                    prompt = f"""
                        Here is the preliminary research collected to begin construction of the network.
                        The preliminary research provides a list of materials, names, aliases, and primary uses, transformation processes (with precursors,byproducts, and references). 
                        Ensure that, at a minimum, the final network represents all of the materials listed (including precursors and byproducts) and is traced towards products for each of the use cases identified for each material.
                        
                        {json.dumps(ctx.state.preliminary_research.dict(),indent=2)}
                        
                        Perform review for network:
                        {ctx.state.network}
                    """
                    if ctx.state.network_secondary_review:
                        prompt += f"The secondary reviewer also made the following recommendations: \n{ctx.state.network_suggested_changes.recommendations if ctx.state.network_suggested_changes.recommendations else ''}. Please ensure they have been addressed."
                        
                    r = await reviewer_agent.run(prompt,message_history=ctx.state.network_reviewer_history,model_settings={'temperature': 1},usage_limits=UsageLimits(request_limit=200))

                    ctx.state.network_reviewer_history += r.new_messages()
                    # print(f"r.data: {r.data}")
                    ctx.state.network_reviews += 1
                    ctx.state.network_suggested_changes = r.data
                    if r.data.has_updates:
                        ctx.state.network_secondary_review = False
                        return GetMaterialNetwork()
                except UsageLimitExceeded as err:
                    print(f"Usage limit exceeded: {err}")
                    await asyncio.sleep(10)
                    return ReviewNetwork()
                except Exception as err:
                    if hasattr(err,'body') and err.body['code']=="rate_limit_exceeded":
                        print(f"Usage limit exceeded: {err}")
                        await asyncio.sleep(20)
                        return ReviewNetwork()
                    print(f"Error in ReviewBaseMaterials: {err}")
            
            return CleanReviewNetwork()

    @dataclass
    class CleanReviewNetwork(BaseNode[NetworkBuilderState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','VerifiyNodesExist','CleanReviewNetwork']:
            
            if ctx.state.secondary_reviews < ctx.state.options.max_secondary_reviews:
                ctx.state.secondary_reviews += 1
                print(f"Secondary (clean) Review: {ctx.state.secondary_reviews} / {ctx.state.options.max_secondary_reviews}")
                
                try: 
                    prompt = f"""
                        Here is the preliminary research collected to begin construction of the network.
                        The preliminary research provides a list of materials, names, aliases, and primary uses, transformation processes (with precursors,byproducts, and references). 
                        Ensure that, at a minimum, the final network represents all of the materials listed (including precursors and byproducts) and is traced towards products for each of the use cases identified for each material.
                        
                        {json.dumps(ctx.state.preliminary_research.dict(),indent=2)}
                    
                        Perform review for network:
                        {ctx.state.network}
                    """
                    r = await clean_reviewer_agent.run(prompt,model_settings={'temperature': 1},usage_limits=UsageLimits(request_limit=200))

                    ctx.state.network_suggested_changes = r.output
                    ctx.state.network_secondary_review = True
                    if r.output.has_updates:
                        return GetMaterialNetwork()
                except UsageLimitExceeded as err:
                    print(f"Usage limit exceeded: {err}")
                    await asyncio.sleep(60)
                    if ctx.state.network_reviews < ctx.state.options.max_network_reviews:
                        ctx.state.network_review -= 1
                    return CleanReviewNetwork()
                except Exception as err:
                    if hasattr(err,'body') and err.body['code']=="rate_limit_exceeded":
                        print(f"Usage limit exceeded: {err}")
                        await asyncio.sleep(60)
                        if ctx.state.network_reviews < ctx.state.options.max_network_reviews:
                            ctx.state.network_review -= 1
                        return CleanReviewNetwork()
                    print(f"Error in ReviewBaseMaterials: {err}")
            
            print("Return VerifyNodes from Clean Review")
            return VerifiyNodesExist()
    if graph_only:
        return  Graph(nodes=(GetMaterialNetwork,ReviewNetwork,CleanReviewNetwork,VerifiyNodesExist,DoPreliminaryResearch,ReviewPreliminaryResearchReferences))
    
    async with preliminary_research_agent.run_mcp_servers():
        async with network_agent.run_mcp_servers():    
            async with reviewer_agent.run_mcp_servers():   
                TaskGraph = Graph(nodes=(DoPreliminaryResearch,GetMaterialNetwork,ReviewNetwork,CleanReviewNetwork,VerifiyNodesExist,ReviewPreliminaryResearchReferences))
                state = NetworkBuilderState(material,options=options)
                if options.preliminary_research_data:
                    state.preliminary_research = options.preliminary_research_data
                result = await TaskGraph.run(DoPreliminaryResearch(),state=state)
                # print("GetComponentAssembly Result:")
                # print(f"\n{result}")
                return result

def serialize_material_network(network:DAG) -> str:
    return json.dumps({
        "nodes": [node.model_dump() for node in network.nodes],
        "links": [link.model_dump() for link in network.links]
    },indent=4)

async def main():
    graph = await get_raw_material_network("Boron",options=GenerateSupplyChainNetworkOptions(model_name="llama-3.3",llm_api_url="http://udc-aj37-36:11434/v1",llm_api_key="none"),graph_only=True)
    graph.mermaid_save("generate_raw_material_network_graph.png")
    
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())