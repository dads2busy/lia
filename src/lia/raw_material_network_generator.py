from pydantic_graph import BaseNode,End,GraphRunContext,Graph
from typing import List,Dict,Any,Union
from dataclasses import dataclass,field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai import UsageLimitExceeded
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from pydantic import BaseModel,Field
import asyncio
import pprint
import json
from pydantic_ai.mcp import MCPServerStdio

max_recursion_depth:int = 3

mcp_servers = [
    # MCPServerStdio("apptainer", ["run","--bind",f"{self.options.storage_folder}:/data","/sfs/gpfs/tardis/home/dm8qs/filesystem_latest.sif","/data"]),
    # MCPServerStdio("apptainer", ["run","/sfs/gpfs/tardis/home/dm8qs/mcp-postgres.sif","postgresql://testuser:testpass@10.155.197.1/usgs"]),
    # MCPServerStdio('npx', ['-y', "@modelcontextprotocol/server-postgres","postgresql://testuser:testpass@10.155.197.1/usgs"])
    # MCPServerStdio('npx', ["-y", "@oevortex/ddg_search"]),
    # MCPServerStdio('npx',["-y", "@pydantic/mcp-run-python", "stdio"]),
    MCPServerStdio('python', ["-m", "mcp_server_fetch"]),
    MCPServerStdio('python', ["-m", "mcp_simple_arxiv"]),
    # MCPServerStdio('npx',args=["-y", "@modelcontextprotocol/server-puppeteer"],env={"PUPPETEER_LAUNCH_OPTIONS": '{"headless": true}'})
    # MCPServerStdio('npx', ["-y", "@gongrzhe/server-json-mcp@1.0.3"]),
    MCPServerStdio('wikipedia-mcp', ["--transport", "stdio"]),
    # MCPServerStdio('python', ["/sfs/gpfs/tardis/home/dm8qs/lia/src/lia/tools/mcp-server-duckb.py","/sfs/gpfs/tardis/home/dm8qs/lia/src/lia/tools/H6array.json"])
    MCPServerStdio('python', ["tools/mcp-server-hscode-sql.py"]),
]       

class GenerateSupplyChainNetworkOptions(BaseModel):
    model_name: str = "llama3.3"
    llm_api_url: str | None = "http://localhost:11434/v1"
    llm_api_key: str = ""
    max_network_reviews: int | None = 10
    max_base_reviews: int | None = 5
  
@dataclass
class SuggestedChanges:
    has_updates: bool = False
    recommendations: str = ""
    
@dataclass
class Material(BaseModel):
    name: str
    hscode: str
    description: str

class Node(BaseModel):
    id: str
    material: str
    stage: str = Field(default="Other", description="Mining|Refinery|Base chemical||Component|Finished product|Recycling|Other")
    description: str | None = None

    
class Link(BaseModel):
    source: str
    target: str
    process: str = Field(default="Other", description="Industrial transformation")
    
class DAG(BaseModel):
    nodes: List['Node'] =field(default_factory=list)
    links: List['Link'] =field(default_factory=list)


@dataclass
class NetworkBuilderState:
    material: str
    # raw_materials: List[str] = field(default_factory=list)
    description: str|None = None
    # base_material_suggested_changes: SuggestedChanges = field(default_factory=lambda: SuggestedChanges(has_updates=False))
    network_suggested_changes: SuggestedChanges = field(default_factory=lambda: SuggestedChanges(has_updates=False))
    network_reviews = int(0)
    # material_reviews = int(0)
    options: GenerateSupplyChainNetworkOptions = field(default_factory=GenerateSupplyChainNetworkOptions)
    network: DAG|None = None
    # base_material_history:List = field(default_factory=list)
    # base_material_reviewer_history:List = field(default_factory=list)
    network_generator_history:List = field(default_factory=list)
    network_reviewer_history:List = field(default_factory=list)

    
async def get_raw_material_network(material: str, options: GenerateSupplyChainNetworkOptions):

    # default_model = OpenAIModel(model_name=options.model_name,base_url=options.llm_api_url,api_key=options.llm_api_key) 
    provider = OpenAIProvider(base_url=options.llm_api_url,api_key=options.llm_api_key)
    default_model = OpenAIModel(options.model_name,provider=provider)
    
    network_agent_system_prompt = """
            You are a trade‑supply‑chain analyst.  When given a single material or component name as input, you must build a directed acyclic graph (DAG) of its value‑added chain using HS‑2022 6‑digit codes only (no spaces or dots).  Follow these rules exactly:

            1. If the input is a raw material (e.g. “silicon”), trace forward from raw minerals (stage = “Mined”) through refining and intermediate chemicals (stages = “Refined” and “Base Chemical”) to first‑tier end‑product families (stage = “Product”), including at least one and up to two product codes per branch.  
            2. If the input is a higher‑level component (e.g. “Photoresist Polymers”), reverse‑trace from its HS‑6 code down through its base chemicals to raw feedstocks and trace forward to its first‑tier end‑product families.  
            3. Include a maximum of 6 levels of nodes,
            4. Ensure that all middle materials are traced to their base forms.
            5. Add and trace any missing base chemicals or raw materials HS Codes that are not already in the graph and are required to support any refined, base chemicals, or products in the graph.
            6. Exclude any obsolete HS codes that are not part of HS-6 (i.e. “HS-2022”).
            7. Each **node** must be an object with:
            - **id**: the 6‑digit HS code  
            - **material**: the common name  
            - **description**: The published H6 description of **id**
            - **stage**: one of “Mined”, “Refined”, “Base Chemical”, “Product”  
            8. Each **edge** must be an object with:
            - **source**: the parent node’s HS code  
            - **target**: the child node’s HS code  
            - **process**:  <= 20 words description of the transformation or manufacturing step  
            9. Ensure no duplicate HS codes appear.  
            10. When an HS Code represents multiple materials, do not split them into separate nodes.  Use the HS-6 code brief description to determine the material name.  If sub-materials are important to a process, the sub-materials may be clarified in the process description. 
            10. Output **only** a single JSON object with two arrays:  
            11. You have the following tools available to you which you can use to help build the network:
                mcp_server_wikipedia: Search for Wikipedia articles to discover the various forms and stages of the material.
                query_hscodes: Search for H6 codes using sql.
            
            When you use query_hscodes tool, follow these rules:
                - Before calling query_hscodes, think step-by-step and write a numbered list of the queries you will need.  This should not exceed 3 queries.
                - After you produce the list, execute the queries in that order.
                - Never call `query_hscodes` more than 3 times per pass.
                
            Return JSON with this structure:

            {
                "nodes": [
                    { "id": "HS6", "material": "<concise material description>", "stage": "<Mining|Refinery|Base chemical|Component|Finished product|Recycling|Other>", "description": "<HS 2022 description>" },
                    …
                ],
                "links": [
                    { "source": "HS6_src", "target": "HS6_tgt", "process": "<industrial transformation>" },
                    …
                ]
            }

            Do not include any other text or explanations.
    """
    network_agent = Agent(model=default_model, result_type=DAG,system_prompt=network_agent_system_prompt,mcp_servers=mcp_servers,retries=5)
    
    reviewer_agent_system_prompt = """
        You are a trade‑supply‑chain network reviewer. When given a JSON DAG describing a material’s value‑added chain (with “nodes” and "links"), perform the following checks:

        1. **HS‑6 code validity**  
        - Verify each node.id is a valid 6‑digit HS‑2022 code.  
        - Flag any codes that are invalid or do not match its node.description
        - Exclude any obsolete HS codes that are not part of HS-6. If an old code and it maps to HS-6, use the new code.  If the code has been deprecated, remove it from the graph.

        2. **Completeness**  
        - Ensure all major refined products and base chemicals (first‑tier intermediates and end‑product families) are present.  
        - Identify any missing HS‑6 codes for significant product or chemical families.
        - Ensure all major refined products and base chemicals at reversed traced to all their dependencies.
        
        3. **Process accuracy**  
        - Check each link.process for specificity and technical accuracy.  
        - Recommend more precise terminology or missing steps where needed.
        - Verify source and target are in the correct order (i.e., target depends on source).  If not, reverse them.

        4. **No duplicates or extra fields**  
        - Confirm there are no duplicate HS codes.  
        - Ensure every node has exactly id, material, description, stage; every edge has source, target, process.
        - Do not recommend differentiating nodes by appending a suffix (e.g., '281000-ore' or '281000-acid'). If sub-materials are important to a process, the sub-materials may be clarified in the process description when important.

        You have the following tools available to you which you can use to help build the network:
            mcp_server_wikipedia: Search for Wikipedia articles to discover the various forms and stages of the material.
            query_hscodes: Search for H6 codes using sql.
            
        When you use query_hscodes tool, follow these rules:
            - Before calling query_hscodes, think step-by-step and write a numbered list of the queries you will need.  This should not exceed 3 queries.
            - After you produce the list, execute the queries in that order.
            - Never call `query_hscodes` more than 3 times per pass.

        Output **ONLY** SuggestedChanges object that contains the following fields:
            - has_updates: boolean indicating if there are any recommendations for the base material list. If there are no recommendations, set this to False.    
            - recommendations: string containing the recommendations for the base material list if there are any. This field must exist if has_updates is True.
    """
    reviewer_agent = Agent(model=default_model,result_type=SuggestedChanges,system_prompt=reviewer_agent_system_prompt,mcp_servers=mcp_servers,retries=5)
    
    @dataclass
    class GetMaterialNetwork(BaseNode[NetworkBuilderState]):

        async def run(self, ctx: GraphRunContext) -> 'End':
            print(f"GetMaterialNetwork...{ctx.state.material}")
            try: 
                if not ctx.state.network_suggested_changes.has_updates:
                    r = await network_agent.run(f"Perform the task for material:\n{ctx.state.material}. ",message_history=ctx.state.network_generator_history,model_settings={'temperature': .25},usage_limits=UsageLimits(request_limit=500))
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
                    print("Processing recommended changes:\n ",ctx.state.network_suggested_changes.recommendations)
                    r = await network_agent.run(prompt,message_history=ctx.state.network_generator_history, model_settings={'temperature': .5},usage_limits=UsageLimits(request_limit=200))
                    ctx.state.network_generator_history += r.new_messages()
                    print(f"Network Nodes: {len(r.data.nodes)} Edges: {len(r.data.links)}") 
                    ctx.state.network = r.data
            
            except UsageLimitExceeded as err:
                print(f"Usage limit exceeded: {err}")
                
                await asyncio.sleep(20)
                return GetMaterialNetwork()
            except Exception as err:
                if hasattr(err,'body') and err.body['code']=="rate_limit_exceeded":
                    print(f"Usage limit exceeded: {err}")
                    await asyncio.sleep(20)
                    return GetMaterialNetwork()

                print(f"Error in GetMaterialNetwork: {err}")
        
            return ReviewNetwork()  
    
    @dataclass
    class ReviewNetwork(BaseNode[NetworkBuilderState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','End']:
            if ctx.state.network_reviews < ctx.state.options.max_network_reviews:
                print(f"({ctx.state.network_reviews+1} of {ctx.state.options.max_network_reviews}) Reviewing Network.")
                ctx.state.network_reviews += 1
                              
                try: 

                    prompt = f"""
                        Perform review for network:
                        {ctx.state.network}
                    """
                    r = await reviewer_agent.run(prompt,message_history=ctx.state.network_reviewer_history,model_settings={'temperature': 1},usage_limits=UsageLimits(request_limit=200))

                    ctx.state.network_reviewer_history += r.new_messages()
                    # print(f"r.data: {r.data}")
                    ctx.state.network_suggested_changes = r.data
                    if r.data.has_updates:
                        return GetMaterialNetwork()
                except UsageLimitExceeded as err:
                    print(f"Usage limit exceeded: {err}")
                    ctx.state.network_review -= 1
                    await asyncio.sleep(10)
                    return ReviewNetwork()
                except Exception as err:
                    if hasattr(err,'body') and err.body['code']=="rate_limit_exceeded":
                        print(f"Usage limit exceeded: {err}")
                        await asyncio.sleep(20)
                        return ReviewNetwork()
                    print(f"Error in ReviewBaseMaterials: {err}")
            
            return End(ctx.state.network)

    async with network_agent.run_mcp_servers():    
            TaskGraph = Graph(nodes=(GetMaterialNetwork,ReviewNetwork))
            state = NetworkBuilderState(material,options=options)
            result = await TaskGraph.run(GetMaterialNetwork(),state=state)
            # print("GetComponentAssembly Result:")
            # print(f"\n{result}")
            return result

def serialize_material_network(network:DAG,filter_products:bool = True) -> str:
    if (filter_products):
        network.nodes = [node for node in network.nodes if node.stage != "Product"]
        network.links = [link for link in network.links if link.target not in [node.id for node in network.nodes if node.stage == "Product"]]
    # Remove duplicates
    
    return json.dumps({
        "nodes": [node.model_dump() for node in network.nodes],
        "links": [link.model_dump() for link in network.links]
    },indent=4)

async def main():
    material = 'Boron'
    print(f"Analyzing Raw Material: {material}")
    result= await get_raw_material_network(material,options=GenerateSupplyChainNetworkOptions(model_name="llama-3.3",llm_api_url="http://udc-aj37-36:11434/v1",llm_api_key="none"))
    print("Graph Run Complete.")
    # pprint.pp(result.output,indent=4)
    print(serialize_material_network(result.output))

            
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())