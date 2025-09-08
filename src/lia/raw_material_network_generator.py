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
from .system_prompts.reference_reviewer_system_prompt import reference_reviewer_system_prompt,url_scorer_system_prompt
from .system_prompts.preliminary_research_agent_prompt import preliminary_research_agent_prompt
from lia.util.url_to_markdown import fetch_url_as_markdown
import hashlib
from pydantic import BaseModel,Field
import asyncio
import json
from pydantic_ai.mcp import MCPServerStdio,MCPServerHTTP
import asyncio
from typing import Callable, List, TypeVar, Awaitable

ddg_mcp_server = MCPServerStdio('uvx', args=["duckduckgo-mcp-server"])
wikipedia_mcp_server = MCPServerStdio('wikipedia-mcp', ["--transport", "stdio", "--log-level", "INFO"])
hscode_vector_mcp_server = MCPServerHTTP(url="http://127.0.0.1:8000/mcp/")
preliminary_research_vector_mcp_server = MCPServerHTTP(url="http://127.0.0.1:8001/mcp/")

# hscode_sql_mcp_server = MCPServerStdio('python', ["tools/mcp-server-hscode-sql.py"])
# arxiv_mcp_server = MCPServerStdio('python', ["-m", "mcp_simple_arxiv"],log_level="notice")

# all of the tools available need to be in the generator as we only use its context manager instead
# starting up multiple instances of tools for different agents.
generator_mcp_servers =  [
    ddg_mcp_server,
    wikipedia_mcp_server,
    hscode_vector_mcp_server,
    preliminary_research_vector_mcp_server
]

research_mcp_servers = [
    ddg_mcp_server,
    wikipedia_mcp_server
]

reviewer_mcp_servers = [
    ddg_mcp_server,
    wikipedia_mcp_server,
    hscode_vector_mcp_server,
    preliminary_research_vector_mcp_server
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

class RemovedProcessesForReview(BaseModel):
    material: str
    process: str
    reference: str
    reason:str

class ReferenceContent(BaseModel):
    """
        A structure to hold the content of a reference URL.
        - 'url' - The URL of the reference
        - 'content' - The content of the reference as markdown
    """
    url: str
    content: str = ""
    error: str | None = None

class ProcessReference(BaseModel):
    process: str
    process_supported: bool| None = None
    precursors_supported: list[str] = field(default_factory=list)
    byproducts_supported: list[str] = field(default_factory=list)
    summary: str = ""
    
class Reference(BaseModel):
    """
        A reference to a process for a material.
        - 'material' - The name of the material being referenced
        - 'process' - The description of the process being referenced
        - 'reference' - The URL of the reference
    """
    material: str
    url: str
    score: float|None = None
    retrievable: bool|None = None
    processes: dict[str,ProcessReference] = field(default_factory=dict)
    
    
class MaterialNetworkGeneratorOptions(BaseModel):
    model_name: str = "llama3.3"
    llm_api_url: str | None = "http://localhost:11434/v1"
    llm_api_key: str = ""
    preliminary_research_only: bool = False
    preliminary_research_data: PreliminaryResearch|None = None
    preliminary_research_rounds: int | None = 1
    preliminary_research_voters: int = 3
    max_preliminary_research_rounds: int = 6
    max_network_reviews: int = 5
    max_secondary_reviews: int = 3
    reference_cache_folder: str|None = None
    debug: bool = False
    
@dataclass
class NetworkBuilderState:
    material: str
    preliminary_research: PreliminaryResearch|None = None
    preliminary_round=int(0)
    removed_references: list[RemovedProcessesForReview]|None = None
    references: dict[str, Reference] = field(default_factory=dict)
    reference_content: dict[str, ReferenceContent] = field(default_factory=dict)
    description: str|None = None
    network_suggested_changes: SuggestedChanges = field(default_factory=lambda: SuggestedChanges(has_updates=False))
    network_reviews = int(0)
    secondary_reviews = int(0)
    network_secondary_review: bool = False
    options: MaterialNetworkGeneratorOptions = field(default_factory=MaterialNetworkGeneratorOptions)
    network: DAG|None = None
    network_generator_history:List = field(default_factory=list)
    network_reviewer_history:List = field(default_factory=list)


T = TypeVar('T')

async def async_filter(
    func: Callable[[T], Awaitable[bool]],
    items: List[T]
) -> List[T]:
    results = []
    for item in items:
        if await func(item):
            results.append(item)
    return results

async def get_raw_material_network(material: str, options: MaterialNetworkGeneratorOptions,graph_only:bool=False):
    provider = OpenAIProvider(base_url=options.llm_api_url,api_key=options.llm_api_key)
    default_model = OpenAIModel(options.model_name,provider=provider)
    
    # url_scorer_mcp = MCPServerStdio('python', ["tools/mcp-server-score-url.py", "--model", options.model_name, "--llm-api-url", options.llm_api_url, "--llm-api-key", options.llm_api_key])
    # generator_mcp_servers.append(url_scorer_mcp)
    # research_mcp_servers.append(url_scorer_mcp)
    
    network_agent = Agent(model=default_model, result_type=DAG,system_prompt=network_agent_system_prompt,mcp_servers=generator_mcp_servers,retries=5)
    reviewer_agent = Agent(model=default_model,result_type=SuggestedChanges,system_prompt=reviewer_agent_system_prompt,mcp_servers=reviewer_mcp_servers,retries=5)
    preliminary_research_agent = Agent(model=default_model,result_type=PreliminaryResearch,system_prompt=preliminary_research_agent_prompt,mcp_servers=research_mcp_servers,retries=5)
    reference_review_agent = Agent(model=default_model,result_type=ValidatedReference,system_prompt=reference_reviewer_system_prompt,retries=5)
    url_scorer_agent = Agent(model=default_model,result_type=float,system_prompt=url_scorer_system_prompt,retries=5)
    clean_reviewer_agent = Agent(model=default_model,result_type=SuggestedChanges,system_prompt=reviewer_agent_system_prompt,mcp_servers=reviewer_mcp_servers,retries=5)
    
    async def fetch_content(url: str) -> ReferenceContent:
        """
        Fetch the content of a URL and return it as a ReferenceContent object.
        If the URL cannot be fetched, return an empty content with an error message.
        """
        filename = hashlib.md5(url.encode('utf-8')).hexdigest()

        try:
            if options.reference_cache_folder is not None:
                # Check if the content is already cached
                cache_file = f"{options.reference_cache_folder}/{filename}.json"
                # print(f"Checking cache for {url} at {cache_file}")
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        content = json.loads(f.read())
                        print(f"✅ Loaded cached content for {url}")
                        return ReferenceContent(**content)
                except FileNotFoundError:
                    print(f"Cache miss for {url}, fetching new content...")

            content = fetch_url_as_markdown(url, max_redirects=5, timeout=20.0)
            rc=ReferenceContent(url=url, content=content)
            
                    
        except Exception as e:
            print(f"❌ Error in fetch_content() from URL {url}: {e}")
            rc=ReferenceContent(url=url,error=f"Error fetching URL: {e}")
    

        return rc
        
    async def score_url(url: str) -> float:
        """
        Score the URL content using the provided model and return a quality score.
        """
        prompt = f"""
            Review the following URL content and assign a source quality score between 0.0 and 1.0 (inclusive):
            {url}
        """
        
        result = await url_scorer_agent.run(
            prompt,
            usage_limits=UsageLimits(request_limit=200)
        )

        return result.output

    async def evaluate_reference(material:str, content: str, process_description: str, precursors: List[str], byproducts: List[str],score: float = 0.0, num_voters: int = 3,process_reference:ProcessReference|None=None) -> ValidatedReference:
        """
        Evaluate the reference content and update the validated_reference object.
        """
        
        prompt = f"""
            Material:
            {material}

            Expected Process Description:
            {process_description}

            Expected Precursors:
            {", ".join(precursors)}

            Expected Byproducts:  
            {', '.join(byproducts)}

            Reference Content:
            ------------------
            {content}
            ------------------
            
            Evaluate the reference content and determine if it supports the expected process, precursors, and byproducts.
        """
        print(f"Evaluating reference for {material} with process: {process_description}")    
        voter_outputs = []

        for _ in range(num_voters):
            try:
                print(f"🔍 Voting on reference for {material} with process: {process_description} {_+1}/{num_voters}")
                result = await reference_review_agent.run(
                    prompt,
                    usage_limits=UsageLimits(request_limit=200)
                )

                voter_outputs.append(result.output)
            except Exception as err:
                print(f"❌ Error during voting: {err}")
                
                
        # Count per-voter valid refs
        voter_valid_flags = [process_supported for process_supported in voter_outputs if process_supported.process_supported]
        if len(voter_valid_flags) < (num_voters/2):    
            return False
            
        print(f"✔️ Valid votes: {len(voter_valid_flags)}/{num_voters} → {'VALID' if len(voter_valid_flags) >= (num_voters // 2 + 1) else 'INVALID'}")
        if process_reference is not None:
            for voter_output in voter_outputs:
                if voter_output.process_supported:
                    process_reference.precursors_supported=voter_output.precursors_supported
                    process_reference.byproducts_supported=voter_output.byproducts_supported
                    process_reference.summary = voter_output.summary
                    break
                
        return True
        

    @dataclass
    class ReviewPreliminaryResearchReferences(BaseNode[NetworkBuilderState]):

        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','DoPreliminaryResearch','End','ReviewPreliminaryResearchReferences','PruneUnsupportedProcesses']:
            if ctx.state.preliminary_research is None:
                if ctx.state.options.debug:
                    print(f"No preliminary research for {ctx.state.material}")
                return End(ctx.state)

            num_voters = ctx.state.options.preliminary_research_voters
            recommendations: list[dict] = []
            removed_references: list[dict] = []

            # Mapping of material -> set of validated process descriptions
            valid_process_map: dict[str, set[str]] = {}

            for material in ctx.state.preliminary_research.research:
                print(f"\n🔍 Reviewing reference material for {material.name}...")
                valid_processes: set[str] = set()
                for process in material.processes:
                    if ctx.state.options.debug:
                        print(f"\n🔍 Reviewing process for {material.name}: {process.description}...")
                    
                    async def _filter_reference(ref: str) -> bool:
                        """
                        Filter out invalid references that do not start with http or https.
                        """
                        
                        if ref not in ctx.state.references:
                            ctx.state.references[ref]=Reference(material=material.name,url=ref)        
                            
                        if process.description in ctx.state.references[ref].processes:
                            return ctx.state.references[ref].processes[process.description].process_supported
                    
                        processReference=ProcessReference(
                            process=process.description,
                            score=None,
                            retrievable=None,
                            process_supported=None,
                            precursors_supported=[],
                            byproducts_supported=[],
                            summary=""
                        )
                        
                        ctx.state.references[ref].processes[process.description] = processReference 
                        
                        if not ref.startswith("http"):
                            print(f"❌ Invalid reference URL: {ref} for {material.name} - {process.description}")
                            summary = f"Invalid URL format: {ref}"
                            removed_references.append({
                                'material': material.name,
                                'process': process.description,
                                'reference': ref,
                                'reason': summary
                                
                            })
                            processReference.process_supported = False
                            processReference.summary=summary
                            return False

                        try:
                            if getattr(ctx.state.reference_content,ref,None) is not None:
                                err = getattr(ctx.state.reference_content[ref],'error',None)
                                if err is None:
                                    content = ctx.state.reference_content[ref].content
                                elif err is not None:
                                    removed_references.append({
                                        'material': material.name,
                                        'process': process.description,
                                        'reference': ref,
                                        'reason': f"Error fetching URL: {err}"
                                    })
                                    return False
                            else:     
                                rcontent = await fetch_content(ref)
                                filename = hashlib.md5(ref.encode('utf-8')).hexdigest()
                                cache_file = f"{options.reference_cache_folder}/{filename}.json"
                                
                                if options.reference_cache_folder is not None:
                                    # Save the content to cache
                                    filename = hashlib.md5(ref.encode('utf-8')).hexdigest()
                                    cache_file = f"{options.reference_cache_folder}/{filename}.json"
                                        
                                    with open(cache_file, 'w', encoding='utf-8') as f:
                                        f.write(rc.model_dump_json())
                                        print(f"✅ Cached content for {url} at {cache_file}")
                                        
                                        
                                if getattr(rcontent,'error',None) is not None:
                                    removed_references.append({
                                        'material': material.name,
                                        'process': process.description,
                                        'reference': ref,
                                        'reason': f"Error fetching URL: {rcontent.error}"
                                    })
                                    if options.reference_cache_folder is not None:
                                        # Save the content to cache
                                          with open(cache_file, 'w', encoding='utf-8') as f:
                                            f.write(rc.model_dump_json())
                                            print(f"✅ Cached content for {ref} at {cache_file}")

                                    return False
                                
                                content = rcontent.content
                                ctx.state.reference_content[ref] = content   
                                ctx.state.references[ref].retrievable = True

                                
                            print(f"✅ Fetched URL: {ref} successfully")
                            print(f"Content length: {len(content)} characters")
                            
                        except Exception as e:
                            print(f"❌ Error fetching URL {ref}: {e}")
                            ctx.state.reference_content[ref] = ReferenceContent(url=ref, error=f"Error fetching URL: {e}") 
                            removed_references.append({
                                'material': material.name,
                                'process': process.description,
                                'reference': ref,
                                'reason': f"Error fetching URL: {e}"
                            })
                            if options.reference_cache_folder is not None:
                            # Save the content to cache
                                with open(cache_file, 'w', encoding='utf-8') as f:
                                    f.write(ctx.state.reference_content[ref].model_dump_json())
                                    print(f"✅ Cached content for {ref} at {cache_file}")
                                    
                            return False
                        
                        try:
                            
                            if ctx.state.references[ref].score is None:
                                score = await score_url(ref)
                                ctx.state.references[ref].score = score
                            else:
                                score = ctx.state.references[ref].score
                                
                            print(f"Reference {ref} source quality score: {score}")

                            if score <= 0.25:
                                print(f"❌ Reference {ref} scored too low: {score:.2f}")
                                removed_references.append({
                                    'material': material.name,
                                    'process': process.description,
                                    'reference': ref,
                                    'reason': f"Reference scored too low: {score:.2f}"
                                })
                                if options.reference_cache_folder is not None:
                                      # Save the content to cache
                                    with open(cache_file, 'w', encoding='utf-8') as f:
                                        f.write(ReferenceContent(url=ref,error=f"Reference scored too low: {score:.2f}").model_dump_json())
                                        print(f"✅ Cached content for {ref} at {cache_file}")
                                        
                                return False
                        
                            if options.reference_cache_folder is not None:
                                # Save the content to cache
                                with open(cache_file, 'w', encoding='utf-8') as f:
                                    f.write(ReferenceContent(url=ref,content=content).model_dump_json())
                                    print(f"✅ Cached content for {ref} at {cache_file}")
                                    
                            # print(f"Pre-evaluation: Material: {material.name}, Process: {process.description}, Reference: {ref}")
                            if processReference.process_supported is not None:
                                evaluation = processReference.process_supported
                            else:
                                evaluation = await evaluate_reference(material.name,content,process.description, process.precursors, process.byproducts,score, num_voters=num_voters,process_reference=processReference)
                                processReference.process_supported = evaluation

                            if evaluation:
                                processReference.process_supported = True
                                
                            elif not evaluation:
                                print(f"❌ Reference {ref} does not support the process: {process.description}")
                                removed_references.append({
                                    'material': material.name,
                                    'process': process.description,
                                    'reference': ref,
                                    'reason': f"Reference does not support the process: {process.description}"
                                })
                                return False
                        except Exception as e:
                            print(f"❌ Error evaluating reference {ref}: {e}")
                            removed_references.append({
                                'material': material.name,
                                'process': process.description,
                                'reference': ref,
                                'reason': f"Error evaluating reference: {e}"
                            })
                            return False

                        return True
                    

                    process.references = await async_filter(_filter_reference,process.references)
                 

            print("\n🔍 Finished reviewing all references for preliminary research.")
            ctx.state.removed_references = removed_references

            if ctx.state.options.debug and removed_references:
                print("\n🗑️ Removed References Summary:")
                for r in removed_references:
                    print(f"- {r['material']} :: {r['process']} :: {r['reference']} :: {r.get('reason', 'No reason provided')}")

            if ctx.state.removed_references is not None and len(ctx.state.removed_references) > 0:
                if ctx.state.preliminary_round < ctx.state.options.max_preliminary_research_rounds:
                    print(f"Removed references for {ctx.state.material} require another round of preliminary research.")
                    return DoPreliminaryResearch()

            return PruneUnsupportedProcesses() 
        
    @dataclass
    class PruneUnsupportedProcesses(BaseNode[NetworkBuilderState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','End']:
            print(f"Pruning unsupported processes for {ctx.state.material}...")
            try:
                if ctx.state.preliminary_research is not None:      
                    
                    for material in ctx.state.preliminary_research.research:

                        print(f"Pruning processes for material: {material}")
                        material.processes = [
                            p for p in material.processes if len(p.references) > 0
                        ]

                    

                if ctx.state.options.preliminary_research_only:
                    return End(ctx.state)

                return GetMaterialNetwork()
            except Exception as e:
                print(f"Error: {e}")
                
            return End(ctx.state)
                
    @dataclass
    class DoPreliminaryResearch(BaseNode[NetworkBuilderState]):

        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','DoPreliminaryResearch','ReviewPreliminaryResearchReferences','End', 'PruneUnsupportedProcesses']:
            if ctx.state.options.preliminary_research_rounds == 0:
                return PruneUnsupportedProcesses()
            
            if ctx.state.preliminary_round < ctx.state.options.max_preliminary_research_rounds:
                print(f"Performing Preliminary Research on {ctx.state.material} Round {ctx.state.preliminary_round+1} / {ctx.state.options.max_preliminary_research_rounds}")
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
                    
                        if ctx.state.removed_references is not None and len(ctx.state.removed_references) > 0:
                            prompt += f"""
                                Note: The following processes were removed from the previous round for insufficient support:
                                {json.dumps(ctx.state.removed_references, indent=2)}
                                
                                These URLS should not be re-used in this round of research.
                                
                                Review these processes to ensure the are correct and/or find DIFFERENT references to support them.
                            """
                    
                    r = await preliminary_research_agent.run(prompt,usage_limits=UsageLimits(request_limit=200))
                    ctx.state.preliminary_round += 1
                    ctx.state.preliminary_research = r.output
                    if ctx.state.preliminary_round < ctx.state.options.preliminary_research_rounds:
                        print(f"Preliminary Research Round {ctx.state.preliminary_round} completed for {ctx.state.material}.")
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
                    """
                    
                    prompt=""
                    
                    if ctx.state.preliminary_research is not None:
                        prompt = f"""
                            
                            Here is the preliminary research for {ctx.state.material}. Use the list of materials as nodes in the network and complete the network.
                            The preliminary research provides a list of materials, names, aliases, and primary uses, transformation processes (with precursors,byproducts, and references). 
                            Ensure that the final network represents all of the materials listed and is traced towards products for each of the use cases identified for each product.
                        
                            {json.dumps(ctx.state.preliminary_research.dict(),indent=2)}
                        """
                    prompt += f"""
                        Perform the task for material: {ctx.state.material}.
                    """
                    r = await network_agent.run(f"Perform the task for material:\n{ctx.state.material}. ",message_history=ctx.state.network_generator_history,usage_limits=UsageLimits(request_limit=500))
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
                        
                    r = await network_agent.run(prompt,message_history=ctx.state.network_generator_history,usage_limits=UsageLimits(request_limit=200))
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
                    # ctx.state.options.max_secondary_reviews += 1
                    print("Some errors are still identified with this network, but the max_secondary_reviews has been reached")
                    return End(ctx.state)

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

                    prompt = ""
                    
                    # if there is preliminary research and this is the first review, include it in the prompt
                    if ctx.state.preliminary_research is not None and ctx.state.network_reviews == 0:
                        prompt = f"""
                            
                            Here is the preliminary research for {ctx.state.material}. Use the list of materials as nodes in the network and complete the network.
                            The preliminary research provides a list of materials, names, aliases, and primary uses, transformation processes (with precursors,byproducts, and references). 
                            Ensure that the final network represents all of the materials listed and is traced towards products for each of the use cases identified for each product.
                        
                            {json.dumps(ctx.state.preliminary_research.dict(),indent=2)}
                        """

                    prompt += f"""   
                        Perform review for network:
                        {ctx.state.network}
                    """
                    if ctx.state.network_secondary_review:
                        prompt += f"The secondary reviewer also made the following recommendations: \n{ctx.state.network_suggested_changes.recommendations if ctx.state.network_suggested_changes.recommendations else ''}. Please ensure they have been addressed."
                        
                    r = await reviewer_agent.run(prompt,message_history=ctx.state.network_reviewer_history,usage_limits=UsageLimits(request_limit=200))

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
                    print(f"Error in CleanReviewNetwork: {err}")
            
            return CleanReviewNetwork()

    @dataclass
    class CleanReviewNetwork(BaseNode[NetworkBuilderState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','VerifiyNodesExist','CleanReviewNetwork']:
            
            if ctx.state.secondary_reviews < ctx.state.options.max_secondary_reviews:
                ctx.state.secondary_reviews += 1
                print(f"Secondary (clean) Review: {ctx.state.secondary_reviews} / {ctx.state.options.max_secondary_reviews}")
                
                try: 
                    prompt = ""
                    if ctx.state.preliminary_research is not None:
                        prompt = f"""
                            
                            Here is the preliminary research for {ctx.state.material}. Use the list of materials as nodes in the network and complete the network.
                            The preliminary research provides a list of materials, names, aliases, and primary uses, transformation processes (with precursors,byproducts, and references). 
                            Ensure that the final network represents all of the materials listed and is traced towards products for each of the use cases identified for each product.
                        
                            {json.dumps(ctx.state.preliminary_research.dict(),indent=2)}
                        """

                    prompt += f"""   
                        Perform review for network:
                        {ctx.state.network}
                    """
                    r = await clean_reviewer_agent.run(prompt,usage_limits=UsageLimits(request_limit=200))

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
            
            return VerifiyNodesExist()
    
    TaskGraph = Graph(nodes=(DoPreliminaryResearch,GetMaterialNetwork,ReviewNetwork,CleanReviewNetwork,VerifiyNodesExist,ReviewPreliminaryResearchReferences,PruneUnsupportedProcesses))
    if graph_only:
        return  TaskGraph
    
    async with network_agent.run_mcp_servers():    
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
    graph = await get_raw_material_network("Boron",options=MaterialNetworkGeneratorOptions(model_name="llama-3.3",llm_api_url="http://udc-aj37-36:11434/v1",llm_api_key="none"),graph_only=True)
    graph.mermaid_save("generate_raw_material_network_graph.png")
    
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())