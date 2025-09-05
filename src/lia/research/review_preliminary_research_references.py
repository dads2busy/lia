from pydantic_graph import BaseNode,End,GraphRunContext,Graph
from typing import List,Dict,Any,Union
from dataclasses import dataclass,field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai import UsageLimitExceeded
from pydantic_ai.models.openai import OpenAIModel,OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from lia.system_prompts.network_agent_system_prompt import network_agent_system_prompt
from lia.system_prompts.reviewer_agent_system_prompt import reviewer_agent_system_prompt
from lia.system_prompts.reference_reviewer_system_prompt import reference_reviewer_system_prompt,url_scorer_system_prompt
from lia.system_prompts.preliminary_research_agent_prompt import preliminary_research_agent_prompt
from lia.util.url_to_markdown import fetch_url_as_markdown
import hashlib
from pydantic import BaseModel,Field
import asyncio
from lia.research import Reference,ReferenceContent,ProcessReference
from lia.research.research_pipeline import NetworkBuilderState
from lia.util.fetch_reference_content import fetch_content

# @dataclass
# class ReviewPreliminaryResearchReferences(BaseNode[NetworkBuilderState]):

#     async def run(self, ctx: GraphRunContext) -> Union['GetMaterialNetwork','DoPreliminaryResearch','End','ReviewPreliminaryResearchReferences','PruneUnsupportedProcesses']:
#         options = ctx.state.options
        
#         if ctx.state.preliminary_research is None:
#             if ctx.state.options.debug:
#                 print(f"No preliminary research for {ctx.state.material}")
#             return End(ctx.state)

#         num_voters = ctx.state.options.preliminary_research_voters
#         recommendations: list[dict] = []
#         removed_references: list[dict] = []

#         # Mapping of material -> set of validated process descriptions
#         valid_process_map: dict[str, set[str]] = {}

#         for material in ctx.state.preliminary_research.research:
#             print(f"\n🔍 Reviewing reference material for {material.name}...")
#             valid_processes: set[str] = set()
#             for process in material.processes:
#                 if ctx.state.options.debug:
#                     print(f"\n🔍 Reviewing process for {material.name}: {process.description}...")
                
#                 async def _filter_reference(ref: str) -> bool:
#                     """
#                     Filter out invalid references that do not start with http or https.
#                     """
                    
#                     if ref not in ctx.state.references:
#                         ctx.state.references[ref]=Reference(material=material.name,url=ref)        
                        
#                     if process.description in ctx.state.references[ref].processes:
#                         return ctx.state.references[ref].processes[process.description].process_supported
                
#                     processReference=ProcessReference(
#                         process=process.description,
#                         score=None,
#                         retrievable=None,
#                         process_supported=None,
#                         precursors_supported=[],
#                         byproducts_supported=[],
#                         summary=""
#                     )
                    
#                     ctx.state.references[ref].processes[process.description] = processReference 
                    
#                     if not ref.startswith("http"):
#                         print(f"❌ Invalid reference URL: {ref} for {material.name} - {process.description}")
#                         summary = f"Invalid URL format: {ref}"
#                         removed_references.append({
#                             'material': material.name,
#                             'process': process.description,
#                             'reference': ref,
#                             'reason': summary
                            
#                         })
#                         processReference.process_supported = False
#                         processReference.summary=summary
#                         return False

#                     try:
#                         if getattr(ctx.state.reference_content,ref,None) is not None:
#                             err = getattr(ctx.state.reference_content[ref],'error',None)
#                             if err is None:
#                                 content = ctx.state.reference_content[ref].content
#                             elif err is not None:
#                                 removed_references.append({
#                                     'material': material.name,
#                                     'process': process.description,
#                                     'reference': ref,
#                                     'reason': f"Error fetching URL: {err}"
#                                 })
#                                 return False
#                         else:     
#                             rcontent = await fetch_content(ref)
#                             filename = hashlib.md5(ref.encode('utf-8')).hexdigest()
#                             cache_file = f"{options.reference_cache_folder}/{filename}.json"
                            
#                             if options.reference_cache_folder is not None:
#                                 # Save the content to cache
#                                 filename = hashlib.md5(ref.encode('utf-8')).hexdigest()
#                                 cache_file = f"{options.reference_cache_folder}/{filename}.json"
                                    
#                                 with open(cache_file, 'w', encoding='utf-8') as f:
#                                     f.write(rc.model_dump_json())
#                                     print(f"✅ Cached content for {url} at {cache_file}")
                                    
                                    
#                             if getattr(rcontent,'error',None) is not None:
#                                 removed_references.append({
#                                     'material': material.name,
#                                     'process': process.description,
#                                     'reference': ref,
#                                     'reason': f"Error fetching URL: {rcontent.error}"
#                                 })
#                                 if options.reference_cache_folder is not None:
#                                     # Save the content to cache
#                                         with open(cache_file, 'w', encoding='utf-8') as f:
#                                         f.write(rc.model_dump_json())
#                                         print(f"✅ Cached content for {ref} at {cache_file}")

#                                 return False
                            
#                             content = rcontent.content
#                             ctx.state.reference_content[ref] = content   
#                             ctx.state.references[ref].retrievable = True

                            
#                         print(f"✅ Fetched URL: {ref} successfully")
#                         print(f"Content length: {len(content)} characters")
                        
#                     except Exception as e:
#                         print(f"❌ Error fetching URL {ref}: {e}")
#                         ctx.state.reference_content[ref] = ReferenceContent(url=ref, error=f"Error fetching URL: {e}") 
#                         removed_references.append({
#                             'material': material.name,
#                             'process': process.description,
#                             'reference': ref,
#                             'reason': f"Error fetching URL: {e}"
#                         })
#                         if options.reference_cache_folder is not None:
#                         # Save the content to cache
#                             with open(cache_file, 'w', encoding='utf-8') as f:
#                                 f.write(ctx.state.reference_content[ref].model_dump_json())
#                                 print(f"✅ Cached content for {ref} at {cache_file}")
                                
#                         return False
                    
#                     try:
                        
#                         if ctx.state.references[ref].score is None:
#                             score = await score_url(ref)
#                             ctx.state.references[ref].score = score
#                         else:
#                             score = ctx.state.references[ref].score
                            
#                         print(f"Reference {ref} source quality score: {score}")

#                         if score <= 0.25:
#                             print(f"❌ Reference {ref} scored too low: {score:.2f}")
#                             removed_references.append({
#                                 'material': material.name,
#                                 'process': process.description,
#                                 'reference': ref,
#                                 'reason': f"Reference scored too low: {score:.2f}"
#                             })
#                             if options.reference_cache_folder is not None:
#                                     # Save the content to cache
#                                 with open(cache_file, 'w', encoding='utf-8') as f:
#                                     f.write(ReferenceContent(url=ref,error=f"Reference scored too low: {score:.2f}").model_dump_json())
#                                     print(f"✅ Cached content for {ref} at {cache_file}")
                                    
#                             return False
                    
#                         if options.reference_cache_folder is not None:
#                             # Save the content to cache
#                             with open(cache_file, 'w', encoding='utf-8') as f:
#                                 f.write(ReferenceContent(url=ref,content=content).model_dump_json())
#                                 print(f"✅ Cached content for {ref} at {cache_file}")
                                
#                         # print(f"Pre-evaluation: Material: {material.name}, Process: {process.description}, Reference: {ref}")
#                         if processReference.process_supported is not None:
#                             evaluation = processReference.process_supported
#                         else:
#                             evaluation = await evaluate_reference(material.name,content,process.description, process.precursors, process.byproducts,score, num_voters=num_voters,process_reference=processReference)
#                             processReference.process_supported = evaluation

#                         if evaluation:
#                             processReference.process_supported = True
                            
#                         elif not evaluation:
#                             print(f"❌ Reference {ref} does not support the process: {process.description}")
#                             removed_references.append({
#                                 'material': material.name,
#                                 'process': process.description,
#                                 'reference': ref,
#                                 'reason': f"Reference does not support the process: {process.description}"
#                             })
#                             return False
#                     except Exception as e:
#                         print(f"❌ Error evaluating reference {ref}: {e}")
#                         removed_references.append({
#                             'material': material.name,
#                             'process': process.description,
#                             'reference': ref,
#                             'reason': f"Error evaluating reference: {e}"
#                         })
#                         return False

#                     return True
                

#                 process.references = await async_filter(_filter_reference,process.references)
                

#         print("\n🔍 Finished reviewing all references for preliminary research.")
#         ctx.state.removed_references = removed_references

#         if ctx.state.options.debug and removed_references:
#             print("\n🗑️ Removed References Summary:")
#             for r in removed_references:
#                 print(f"- {r['material']} :: {r['process']} :: {r['reference']} :: {r.get('reason', 'No reason provided')}")

#         if ctx.state.removed_references is not None and len(ctx.state.removed_references) > 0:
#             if ctx.state.preliminary_round < ctx.state.options.max_preliminary_research_rounds:
#                 print(f"Removed references for {ctx.state.material} require another round of preliminary research.")
#                 return DoPreliminaryResearch()

#         return PruneUnsupportedProcesses() 