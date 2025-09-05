from pydantic_graph import BaseNode,End,GraphRunContext
from typing import List,Dict,Any,Union
from dataclasses import dataclass,field
from pydantic_ai.usage import UsageLimits
from pydantic_ai import UsageLimitExceeded,Agent
import asyncio
import re
import hashlib
from lia.research import ResearchPipelineOptions,ResearchPipelineState,ResearchMaterial,ReviewedReference
from lia.research.agents.researcher_agent import ResearchAgentDependencies
from lia.util.fetch_reference_content import fetch_content,ReferenceContentOptions,ReferenceContent

def _normalize_string(s: str) -> str:
    # Remove parenthesis and their contents, then strip and lowercase
    return re.sub(r"\s*\([^)]*\)", "", s).strip().lower()

def normalize_research_material(material: ResearchMaterial) -> ResearchMaterial:
    # Normalize top-level fields
    material.name = _normalize_string(material.name)
    material.aliases = [_normalize_string(alias) for alias in material.aliases]

    # Normalize each transformation process
    for process in material.processes:
        process.precursors = [_normalize_string(p) for p in process.precursors]
        process.byproducts = [_normalize_string(b) for b in process.byproducts]

    return material

def material_exists(state: ResearchPipelineState, material: str) -> bool:
    material_lower = material.lower()

    if material_lower in ["none","null","undefined","","steam","water","water vapor","clay","treated water","air","liquid air","gas","electricity","heat","seawater","sea water","salt water"]:
        # These are considered common materials that do not require research
        return True

    # Check unresearched list (case-insensitive)
    if any(m.lower() == material_lower for m in state.unresearched):
        return True

    # Check materials dict: by key or alias match (case-insensitive)
    for name_key, material_obj in state.materials.items():
        if name_key.lower() == material_lower:
            return True
        if any(alias.lower() == material_lower for alias in material_obj.aliases):
            return True

    return False

    
async def score_url(url: str, agent:Agent) -> float:
    """
    Score the URL content using the provided model and return a quality score.
    """
    prompt = f"""
        Review the following URL content and assign a source quality score between 0.0 and 1.0 (inclusive):
        {url}
    """
    
    result = await agent.run(
        prompt,
        usage_limits=UsageLimits(request_limit=200)
    )

    return result.output


@dataclass
class expand_config(BaseNode[ResearchPipelineState]):
    async def run(self, ctx: GraphRunContext) -> Union[End,'do_preliminary_research']:
        if not ctx.state.options.expand_config:
            return do_preliminary_research()
        
        prompt = f"""
            The primary material is '{ctx.state.research_config.material}'.
          
            The currently known forms and products of {ctx.state.research_config.material} are:
            - Forms: {', '.join(ctx.state.research_config.forms + ctx.state.research_config.expanded_forms)}
        """
        if len(ctx.state.research_config.products) > 0:
            prompt += f"""
            - Products: {', '.join(ctx.state.research_config.products)}
            """
        
        if len(ctx.state.research_config.references) > 0:
            prompt += f"""
            - References: {', '.join(ctx.state.research_config.references)}
            """
        
        prompt += f"""
            Please identify any additional forms or compounds of {ctx.state.research_config.material} that are not already in the provided list.
            Use tools to retrieve references and information about the material and its forms.
        """ 
        
        print(f"Prompt: {prompt}")
        try: 
            result = await ctx.state.agents['material_classification_agent'].run(
                prompt, 
                usage_limits=UsageLimits(request_limit=200)
            )
            
            # print(f"ctx.state.materials: {ctx.state.materials}")
            
            ctx.state.research_config.expanded_forms = result.output
            ctx.state.updated_config = True
            
            print(f"Expanded Research Config: {ctx.state.research_config.expanded_forms}")
            return End(ctx.state)
        
        except UsageLimitExceeded as err:
            print(f"DoPreliminaryResearch: Usage limit exceeded: {err}")
            await asyncio.sleep(20)
            return expand_config()
        except Exception as err:
            print(f"Error in do_preliminary_research: {err}")
            if getattr(err,'body',{}) and 'code' in err.body and err.body['code']=="rate_limit_exceeded":
                print(f"Usage limit exceeded: {err}")
                await asyncio.sleep(20)
                return expand_config()

@dataclass
class do_preliminary_research(BaseNode[ResearchPipelineState]):
    async def run(self, ctx: GraphRunContext) -> Union[End,'review_references']:

        print(f"Performing preliminary research for '{ctx.state.research_config.material}'")
        seed_materials = [ctx.state.research_config.material] + ctx.state.research_config.forms + ctx.state.research_config.expanded_forms

        for material in seed_materials:
            m = material.lower()
            if not material_exists(ctx.state, m):
                ctx.state.unresearched.append(m)        
        
        if len(ctx.state.unresearched)>0:
            material = ctx.state.unresearched.pop(0)
            print(f"\t researching: {material} Remaining: {len(ctx.state.unresearched)}")
            prompt = f"""
                Please generate a material profile for "{material}".
            """
            # print(f"Prompt:{prompt}")
            try: 
                result = await ctx.state.agents['researcher_agent'].run(
                    prompt, 
                    usage_limits=UsageLimits(request_limit=200),
                    deps=ResearchAgentDependencies(material=material,research_config=ctx.state.research_config)
                )
                
              
                # print(f"ctx.state.materials: {ctx.state.materials}")
                mprofile = result.output
                # ctx.state.materials[material.lower()] = normalize_research_material(mprofile)
                ctx.state.current_material = normalize_research_material(mprofile)
                for process in ctx.state.current_material.processes:
                    process_supported = False
                
                # if mprofile.category != "mined" and len(mprofile.processes)>0:
                #     for process in mprofile.processes:
                #         for m in process.precursors:
                #             if not material_exists(ctx.state,m):
                #                 print(f"\t Adding material: {m}")
                #                 ctx.state.unresearched.append(m)
                #         for m in process.byproducts:
                #             if not material_exists(ctx.state,m):
                #                 print(f"\t Adding material: {m}")
                #                 ctx.state.unresearched.append(m)
                
                return review_references()
                
            except UsageLimitExceeded as err:
                print(f"DoPreliminaryResearch: Usage limit exceeded: {err}")
                await asyncio.sleep(20)
                return do_preliminary_research()
            except Exception as err:
                print(f"Error in do_preliminary_research: {err}")
                if getattr(err,'body',{}) and 'code' in err.body and err.body['code']=="rate_limit_exceeded":
                    print(f"Usage limit exceeded: {err}")
                    await asyncio.sleep(20)
                    return do_preliminary_research()

        else:
            ctx.state.current_material = None
            return review_references()
@dataclass
class review_references(BaseNode[ResearchPipelineState]):
    async def run(self, ctx: GraphRunContext) -> Union[End,'do_preliminary_research']:
        if ctx.state.current_material is None:
            print("No current material to review references for.")
            return End(ctx.state)

        print(f"Reviewing material: {ctx.state.current_material.name}")
        if len(ctx.state.current_material.processes)>0:
            for process in ctx.state.current_material.processes:
                print(f"Reviewing process: {process.description}")
                if not process.references:
                    print(f"No references found for process: {process.description}")
                    continue
                
                refReplacements=[]
                for ref in process.references:
                    print(f"Reviewing reference: {ref}")
                    reviewedRef = ReviewedReference(url=ref)
                    reviewedRef.source_quality_score = await score_url(ref,ctx.state.agents['url_scorer_agent'])
                    
                    rc = await fetch_content(ref, options=ReferenceContentOptions(reference_cache_folder=ctx.state.options.reference_cache_folder, save=True, refresh=False))
                    
                    if rc.error is None:
                        reviewedRef.retrievable = True
                        
                    if not reviewedRef.retrievable:
                        print(f"Reference {ref} is not retrievable or not reviewed yet.")
                        continue
                    
                    refReplacements.append(reviewedRef)
                    
                process.references = refReplacements
                    # Process the reference content, validate, etc.
                    # This is where you would add your logic to handle the reference
        ctx.state.materials[ctx.state.current_material.name.lower()] = ctx.state.current_material
        print(f"Completed review for material: {ctx.state.current_material}")
        ctx.state.current_material = None
        return do_preliminary_research()
    
@dataclass
class review_materials(BaseNode[ResearchPipelineState]):
    async def run(self, ctx: GraphRunContext) -> End:
        for material_name, material in ctx.state.materials.items():
            print(f"Reviewing material: {material_name}")
            if len(material.processes) == 0:
                print(f"No processes found for material: {material_name}")
                continue
            
            for process in material.processes:
                print(f"Reviewing process: {process.description}")
                if not process.references:
                    print(f"No references found for process: {process.description}")
                    continue
                
                refReplacements=[]
                for ref in process.references:
                    sqs = None
                    if isinstance(ref,ReviewedReference):
                        sqs = ref.source_quality_score
                        ref = ref.url              
                           
                    print(f"Reviewing reference: {ref}")
                    reviewedRef = ReviewedReference(url=ref)
                    if sqs is not None:
                        reviewedRef.source_quality_score = sqs
                    else:
                        reviewedRef.source_quality_score = await score_url(ref,ctx.state.agents['url_scorer_agent'])
                    
                    rc = await fetch_content(ref, options=ReferenceContentOptions(reference_cache_folder=ctx.state.options.reference_cache_folder, save=True, refresh=False))
                    
                    if rc.error is None:
                        reviewedRef.retrievable = True
                        
                    if not reviewedRef.retrievable:
                        print(f"Reference {ref} is not retrievable or not reviewed yet.")
                        continue
                    
                    prompt = f"""
#### Process Description for {material.name} ####:
{process.description}

Precursors: {', '.join(process.precursors)}
Byproducts: {', '.join(process.byproducts)} 

#### Content for Review ####
{rc.content}                      
########  
Evaluate the provided content to determine support for the described process?
                    """
                    # print(f"Prompt for reference review: {prompt}")
                    result = await ctx.state.agents['reference_reviewer_agent'].run(
                        prompt,
                        usage_limits=UsageLimits(request_limit=200)
                    )
                    review_results = result.output
                    reviewedRef.content_quality_score = review_results.score
                    reviewedRef.summary = review_results.reason
                    # print(f"RESULT MESSAGES:\n{result.new_messages()}")
                    print(f"*****REVIEW RESULTS********\n{reviewedRef}\n**************************")
                    refReplacements.append(reviewedRef)
                
                pscore = 0.0
                all_reviewed = True
                reviewed_refs = [
                    ref for ref in process.references if isinstance(ref, ReviewedReference)
                ]
                
                if len(reviewed_refs) > 2:
                    # Sort references by combined score (content_quality_score * source_quality_score)
                    reviewed_refs.sort(
                        key=lambda ref: ref.content_quality_score * ref.source_quality_score,
                        reverse=True
                    )
                    # Use only the top two references for scoring
                    top_refs = reviewed_refs[:2]
                else:
                    top_refs = reviewed_refs
                
                for ref in top_refs:
                    pscore += ref.content_quality_score * ref.source_quality_score
                
                all_reviewed = all_reviewed and len(reviewed_refs) == len(process.references)
                
                if all_reviewed and len(top_refs) > 0:
                    process.process_score = pscore / len(top_refs)
                    if process.process_score >= 0.4:
                        process.process_supported = True
                    else:
                        process.process_supported = False
                else:
                    process.process_score = None
                    
                process.references = refReplacements
      

        return End(ctx.state)