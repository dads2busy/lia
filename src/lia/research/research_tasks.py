from pydantic_graph import BaseNode,End,GraphRunContext,Edge
from typing import List,Dict,Any,Union,Annotated
from dataclasses import dataclass,field
from pydantic_ai.usage import UsageLimits
from pydantic_ai import UsageLimitExceeded,Agent
import asyncio
import re
import hashlib
from lia.research import ResearchMaterial,ResearchPipelineOptions,ReviewedReference,ContentReviewResult,MaterialProcess,MaterialReference,SuggestedMaterialReference,AddProcessInstruction,AddMaterialToProcessInstruction,AddReferenceToProcessInstruction,SetProcessInstruction,RemoveMaterialFromProcessInstruction,RemoveProcessInstruction
from lia.research.pipeline_state import ResearchPipelineState
from lia.research.agents.material_manufacturing_agent import MaterialManufacturingAgentDependencies
from lia.research.agents.material_finder_agent import MaterialFinderAgentDeps
from lia.research.agents.material_classificaton_agent import MaterialClassificatonAgentDeps
from lia.util.fetch_reference_content import fetch_content,ReferenceContentOptions,ReferenceContent
from lia.research.pipeline_state import save_state

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
        process.products = [_normalize_string(b) for b in process.products]

    return material

def normalize_precursors_and_products(material: ResearchMaterial) -> ResearchMaterial:
    """
    Normalize the precursors and products of each process in a material.
    Ensures that all precursors and products are lowercased and split correctly
    when "or" or "and" are present, except when they are within parentheses.
    """
    for process_id, process in material.processes.items():
        # Normalize and split precursors
        updated_precursors = []
        for precursor in process.precursors:
            if isinstance(precursor, MaterialReference):
                updated_precursors.append(precursor)  # Keep MaterialReference objects as is
            else:
                precursor = precursor.lower()
                if " or " in precursor or " and " in precursor:
                    # Handle splitting while respecting parentheses
                    # Check if " and " or " or " are outside of parentheses
                    in_parentheses = any(
                        " and " in match or " or " in match
                        for match in re.findall(r'\([^)]*\)', precursor)
                    )
                    if not in_parentheses:
                        parts = re.split(r'\s+(?:or|and)\s+', precursor)
                        updated_precursors.extend(part.strip() for part in parts)
                    else:
                        updated_precursors.append(precursor.strip())
                else:
                    updated_precursors.append(precursor.strip())
        process.precursors = updated_precursors

        # Normalize and split products
        updated_products = []
        for byproduct in process.products:
            if isinstance(byproduct, MaterialReference):
                updated_products.append(byproduct)  # Keep MaterialReference objects as is
            else:
                byproduct = byproduct.lower()
                if " or " in byproduct or " and " in byproduct:
                    # Handle splitting while respecting parentheses
                    in_parentheses = any(
                        " and " in match or " or " in match
                        for match in re.findall(r'\([^)]*\)', byproduct)
                    )
                    if not in_parentheses:
                        parts = re.split(r'\s+(?:or|and)\s+', byproduct)
                        updated_products.extend(part.strip() for part in parts)
                    else:
                        updated_products.append(byproduct.strip())
                else:
                    updated_products.append(byproduct.strip())
        process.products = updated_products

    return material

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

async def review_reference_content(content: str, process: MaterialProcess, agent: Agent) -> ContentReviewResult:
    """
    Review the content of a URL against a process description and return a ReviewedReference.
    """
    prompt = f"""
#### Process Description ####
{process.description}

This process creates the following products/materials:
"""
    for p in process.products:
        prompt += f"- {process}\n"

    prompt += f"\nThis process requires the following precursors/materials:\n"
    for p in process.precursors:
        prompt += f"- {p}\n"

    prompt += f"""
#### Content for Review ####
{content}                      
########  
Evaluate the provided content to determine support for the described process?
"""
    try: 
        result = await agent.run(
            prompt,
            usage_limits=UsageLimits(request_limit=200)
        )
        
        return result.output
    except Exception as e:
        print(f"Exception while reviewing content: {e}")
        return None

def evaluate_references(references, minimum_process_references, distinct_domains_required=2):
    """
    Evaluate a list of references to determine the top references, 
    whether all references have been reviewed, if there are enough distinct domains,
    and the number of unreviewed references.

    Args:
        references (list): List of references to evaluate.
        minimum_process_references (int): Minimum number of references required.
        distinct_domains_required (int): Minimum number of distinct domains required.

    Returns:
        tuple: (top_references, all_reviewed, found_required_distinct_domains, unreviewed_count)
    """
    all_reviewed = True
    unreviewed_count = 0
    reviewed_refs = []
    
    for ref in references:
        if isinstance(ref, ReviewedReference) and ref.content_quality_score is not None and ref.source_quality_score is not None:
            reviewed_refs.append(ref)
        else:
            all_reviewed = False
            unreviewed_count += 1

    print(f"   - Total Reviewed References: {len(reviewed_refs)}")
    print(f"   - Total Unreviewed References: {unreviewed_count}")
    found_required_distinct_domains = False
    top_refs = []

    if len(reviewed_refs) >= minimum_process_references:
        # Sort references by their combined score
        reviewed_refs.sort(
            key=lambda ref: ref.content_quality_score * min(ref.source_quality_score * 2, 1.0),
            reverse=True
        )

        # Populate top_refs with the required number of distinct domains
        used_domains = set()
        for ref in reviewed_refs:
            domain = re.match(r"https?://([^/]+)", ref.url).group(1)
            if len(top_refs) < distinct_domains_required and domain not in used_domains:
                top_refs.append(ref)
                used_domains.add(domain)
            elif len(top_refs) >= distinct_domains_required:
                break

        if len(top_refs) >= distinct_domains_required:
            # Fill the remaining slots with top scorers from any domain
            for ref in reviewed_refs:
                if len(top_refs) >= minimum_process_references:
                    break
                if ref not in top_refs:
                    top_refs.append(ref)
            found_required_distinct_domains = True
        else:
            found_required_distinct_domains = False
    else:
        top_refs = reviewed_refs
        # Verify there are enough distinct domains in the references
        distinct_domains = set()
        for ref in reviewed_refs:
            match = re.match(r"https?://([^/]+)", ref.url)
            if match:
                distinct_domains.add(match.group(1))

        if len(distinct_domains) < distinct_domains_required:
            found_required_distinct_domains = False
        else:
            found_required_distinct_domains = True
            
    return top_refs, all_reviewed, found_required_distinct_domains, unreviewed_count

def create_process_string(process: MaterialProcess):
    """output a string representation of the process for printing"""
    
    out = f"\nProcess ID: {process.id}\n"
    out += f"Description: {process.description}\n"
    
    out += "\nProducts:\n"
    for product in process.products:
        if isinstance(product, MaterialReference):
            out+=f"  - {product.name} (HS {product.hs_code})\n"
        else:
            out+=f"  - {product}\n"
    
    out += "\n\nPrecursors:\n"
    for precursor in process.precursors:
        if isinstance(precursor, MaterialReference):
            out += f"  - {precursor.name} (HS {precursor.hs_code})\n"
        else:
            out += f"  - {precursor}"
            
    out += "\n\nReferences:\n"
    for ref in process.references:
        if isinstance(ref, ReviewedReference):
            out+=f"  - {ref.url}\n"
        else:
            out+=f"  - {ref}\n"
   
    out += f"\n\n**** End {process.id} ****\n"
    return out

def process_instruction(instruction:Union[AddProcessInstruction,RemoveProcessInstruction,AddMaterialToProcessInstruction,RemoveMaterialFromProcessInstruction,SetProcessInstruction,AddReferenceToProcessInstruction],state:ResearchPipelineState):
    """
    Process a MaterialProcessInstruction and apply it to the ResearchPipelineState.
    """
    
    try:
        if isinstance(instruction, AddProcessInstruction):
            newp = MaterialProcess(
                description=instruction.process.description,
                precursors=instruction.process.precursors,
                products=instruction.process.products,
                references=instruction.process.references,
                scale=instruction.process.scale
            )   
            state.add_process(newp)
            return
        
        if isinstance(instruction, RemoveProcessInstruction):
            if instruction.process_id in state.processes:
                print(f"Removing process with ID: {instruction.process_id}")
                state.remove_process(instruction.process_id)
            else:
                print(f"Process with ID {instruction.process_id} not found.")
            return
        
        if isinstance(instruction, AddMaterialToProcessInstruction):
            addition_type = instruction.addition_type
            if addition_type == "precursor":
                print(f"Adding precursor: {instruction.material.name} ({instruction.material.hs_code}) to process {instruction.process_id}")
                state.add_precursor(instruction.process_id, instruction.material) 
            elif addition_type == "product":
                print(f"Adding product: {instruction.material.name} ({instruction.material.hs_code}) to process {instruction.process_id}")
                state.add_product(instruction.process_id, instruction.material) 
                
            return
        
        if isinstance(instruction, RemoveMaterialFromProcessInstruction):
            removal_type = instruction.removal_type
            if removal_type == "precursor":
                print(f"Removing precursor: {instruction.material.name} ({instruction.material.hs_code}) from process {instruction.process_id}")
                state.remove_precursor(instruction.process_id, instruction.material)
            elif removal_type == "product":
                print(f"Removing product: {instruction.material.name} ({instruction.material.hs_code}) from process {instruction.process_id}")
                state.remove_product(instruction.process_id, instruction.material)
                
            return
    
        if isinstance(instruction, SetProcessInstruction):
            if instruction.description is not None:
                print(f"Setting description for process {instruction.process_id} to: {instruction.description}")
                state.processes[instruction.process_id].description = instruction.description
            if instruction.scale is not None:
                print(f"Setting scale for process {instruction.process_id} to: {instruction.scale}")
                state.processes[instruction.process_id].scale = instruction.scale
            return
            
        if isinstance(instruction, AddReferenceToProcessInstruction):
            for ref in instruction.references:
                print(f"Adding reference: {ref} to process {instruction.process_id}")
                state.add_reference(instruction.process_id, ref)
            return
       
        print (f"Unknown instruction type: {type(instruction)}")
    except Exception as e:
        print(f"Error processing instruction {instruction}: {e}")
                
@dataclass
class generate_research_material(BaseNode[ResearchPipelineState]):
    """Generate Basic Research Materials based on the research configuration and options."""
    async def run(self, ctx: GraphRunContext) -> Annotated[End, Edge(label="solo")] | 'review_materials' | Annotated['generate_material_processes',Edge(label="skip material generation")]:
        print("[generate_research_material] start")
        opts = ctx.state.options
        
        if not opts.generate_materials or ctx.state.material_generation_passes >= opts.material_generation_rounds:
            print("\t[generate_research_material] Skipping material generation.")
            
            if opts.solo:
                return End(ctx.state)
            return generate_material_processes()
        
        agent = ctx.state.agents.get("material_classification_agent")
        
        print(f"\t[generate_research_material] Generating materials for {ctx.state.research_config.material} Round {ctx.state.material_generation_passes + 1}/{opts.material_generation_rounds}")
                          
        prompt = f"""
Please proceed with the following set of materials: 
- {ctx.state.research_config.material}\n"""
        
        for m in ctx.state.research_config.materials:
            prompt += f"  - {m}\n"
        
        
        if len(ctx.state.materials) > 0:
            prompt += "\nPreviously identified materials:\n"
            for mat in ctx.state.materials.values():
                prompt += f"  - {mat.name} [HS {mat.hs_code}]\n"
                
            prompt += """
Ensure that you do not duplicate HS Codes in your response.
Do not duplicate HS codes.
            """
            
        try :
            result = await agent.run(
                prompt,
                deps=MaterialClassificatonAgentDeps(
                    materials=ctx.state.materials
                ),  
                usage_limits=UsageLimits(request_limit=200)
            )
            
            new_materials = result.output
            for mat in new_materials:
                if ctx.state.materials.get(mat.hs_code,None) is None:
                    print(f"\t[generate_research_material] Adding new material: {mat.name} ({mat.hs_code})")
                    ctx.state.add_material(mat)
                else:
                    print(f"\t[generate_research_material] Material already exists: {mat.name} ({mat.hs_code})")
                    existing = ctx.state.materials[mat.hs_code]
                    for alias in mat.aliases:
                        if alias not in existing.aliases:
                            print(f"\t\t[generate_research_material] Adding alias: {alias}")
                            existing.aliases.append(alias)
                    if mat.name not in existing.aliases:
                        print(f"\t\t[generate_research_material] Adding alias: {mat.name}")
                        existing.aliases.append(mat.name)
                        
                    print(f"\t[generate_research_material] Material already exists: {mat.name} ({mat.hs_code})")
                    
        except UsageLimitExceeded as e:
            print(f"\t[generate_research_material] Usage limit exceeded while generating materials: {e}")
        except Exception as e:
            print(f"\t[generate_research_material] Error generating materials with material_classification_agent: {e}")
            
        if ctx.state.options.save_state:    
            save_state(ctx.state.options.research_folder,ctx.state,silent=True)  

        if opts.solo:
            return End(ctx.state)
        
        return review_materials()

@dataclass
class review_materials(BaseNode[ResearchPipelineState]):
    """Review and validate the generated research materials to ensure their hs codes, aliases, and primary uses are accurate and non duplicative."""
    async def run(self, ctx: GraphRunContext) -> Union[End,'generate_material_processes','generate_research_material']:
        print("[review_materials] start")
        opts = ctx.state.options
        
        if not opts.generate_materials:
            print("\t[review_materials] Skipping material review as requested.")
            if opts.solo:
                return End(ctx.state)
            
            return generate_material_processes()
        
        agent = ctx.state.agents.get("material_finder_agent")
        
        print(f"\t[review_materials] TODO: Review material")
        ### TODO: add in material review.  Check for validity of HS Codes, duplication of materials, aliases, primary uses, etc
        for hscode,material in ctx.state.materials.items():
            print(f"TODO: Review material")
            pass
    
        if opts.generate_materials and ctx.state.material_generation_passes < opts.material_generation_rounds:
            print(f"\t[review_materials] Completed Material Generation and Review Pass {ctx.state.material_generation_passes + 1}/{opts.material_generation_rounds}")
            ctx.state.material_generation_passes += 1
            if not opts.solo:
                return generate_research_material()
        
        if opts.solo:
            return End(ctx.state)
    
        return generate_material_processes()
       
@dataclass
class generate_material_processes(BaseNode[ResearchPipelineState]):
    """Research and identify the processes that are required to produce the materials. Performed on a material-by-material basis."""
    async def run(self, ctx: GraphRunContext) -> Union[End,'merge_duplicate_processes']:
        opts = ctx.state.options
        
        print("[generate_material_processes] start")
        if not opts.generate_processess:
            print("\t[generate_material_processes] Skipping process research as requested.")
            if opts.solo:
                return End(ctx.state)
            return merge_duplicate_processes()
        
        for hscode,material in ctx.state.materials.items():
            mode="create"
            print(f"\t[generate_material_processes] Researching processes for material: {material.name} ({hscode})")
            agent = ctx.state.agents.get("material_manufacturing_agent")
            prompt = f"""
Please identify the key processes, precursors, and products for manufacturing the material "{material.name}" (HS Code: {hscode}). 

The material is also known by the following aliases:
"""
            for alias in material.aliases:
                prompt += f"  - {alias}\n"
        
            prompt += "\n"
            material_processes = ctx.state.get_processes_for_material(hscode)    
            print(f"\t[generate_material_processes] Material Processes: {material_processes}")
            
            all_scored=True
            print(f"\t[generate_material_processes] Checking {hscode} for processes to see if they have all been scored")
            if len(material_processes) > 0:
                for p in material_processes:
                    pid= p.id
                    print(f"{pid} {p.process_score}")
                    if p.process_score is None:
                        all_scored = False
                        break

            print(f"\t[generate_material_processes] Material has {len(material_processes)} existing processes.  All scored: {all_scored}")
            if len(material_processes)>0 and all_scored:
                print(f"\t[generate_material_processes] Skipping process generation for {material.name} ({hscode}) as there is at least one process and all processes have been scored.")
                continue

            if len(material_processes)>0:
                mode="edit"
                print("\t[generate_material_processes] Found existing processes for material, switching to edit mode.")
                for process in material_processes:
                    top_refs, all_reviewed, found_required_distinct_domains,unreviewed_count = evaluate_references(
                        references=process.references,
                        minimum_process_references=ctx.state.options.minimum_process_references,
                        distinct_domains_required=ctx.state.options.distinct_domains_required
                    )
 
                    
                    process_id = process.id
                    labeled=False
                    if process.process_score is not None and process.process_score >= ctx.state.options.process_score_threshold:
                        if not labeled:
                            prompt += f"\n\n**************************************************\nThese processes have been previously reviewed and do not require changes :\n**************************************************\n"
                            labeled = True
                            
                        prompt += create_process_string(process)
                    
                        # if not found_required_distinct_domains:
                        #     prompt += f"\n** Process {process.id}  does not have enough distinct internet domains in the references. Identify new high quality references from different internet domains. **\n"


                    if process.process_score is None:
                        for process in material_processes:
                            labeled=False
                            top_refs, all_reviewed, found_required_distinct_domains,unreviewed_count = evaluate_references(
                                references=process.references,
                                minimum_process_references=ctx.state.options.minimum_process_references,
                                distinct_domains_required=ctx.state.options.distinct_domains_required
                            )
                            process_id = process.id
                            if process.process_score is None:
                                if not labeled:
                                    prompt += f"\n\n**************************************************\nThese processes have been previously identified, but not yet completely reviewed:\n**************************************************\n"
                                    labeled = True
        
                                prompt += create_process_string(process)
                                    
                            if all_reviewed and len(top_refs) < ctx.state.options.minimum_process_references:
                                prompt += f"\n** Process {process.id} needs additional references to be reviewed and scored **\n"
                                if not found_required_distinct_domains:
                                    prompt += f"\n** Process {process.id}  does not have enough distinct internet domains in the references. Identify new high quality references from different internet domains. **\n"    
                            
                            elif not all_reviewed and len(process.references) < ctx.state.options.minimum_process_references:
                                prompt += f"\n** Process {process.id}  needs additional references to be reviewed and scored **\n"
                            else:        
                                prompt += f"\n** Process {process.id}  has not been reviewed and scored.  No changes required at this time. **\n"
                                
                    
                labeled=False
                for process in material_processes:
                    process_id = process.id
                    if process.process_score is not None and process.process_score <= ctx.state.options.process_score_threshold:
                        if not labeled:
                            prompt += "\n\n**************************************************\nThe following processes have been previously identified, but require additional quality references or refinement:\n**************************************************\n"
                        prompt += create_process_string(process)

   
                prompt += "For all processes, please ensure that the suggested precursors and products using the correct HS Codes for the form of the material required for the specific process.\n"
                prompt += "Verify that the representation of the process scale is accurate and that the process description is clear and complete.\n"
                prompt += "Do not reuse existing references, but instead identify new high quality references from different internet domains.\n"
                prompt += "Verify that precursors and products represented in the references FOR THIS SPECIFIC PROCESS are accurate and complete.\n"
                prompt += "Address actions identfied in notes in the form ** Process <process id> ... **"
            else:
                print("No existing processes found for material, switching to create mode.")
                prompt += "No existing processes found for this material. Please identify the key processes, precursors, and products for manufacturing the material.\n"
                prompt += "Ensure that the suggested precursors and products using the correct HS Codes for the form of the material required for the specific process.\n"
                prompt += "Verify that the representation of the process scale is accurate and that the process description is clear and complete.\n"
                mode= "create"
            try:
                print("\t[generate_material_processes] Prompting LLM for material processes...")
                # print(f"\t[generate_material_processes] Prompt for Generating/Editing Material Processes:\n{prompt}")
                result = await agent.run(
                    prompt,
                    usage_limits=UsageLimits(request_limit=200),
                    deps=MaterialManufacturingAgentDependencies(mode=mode)
                )
                mod_instructions = result.output

                print(f"\t[generate_material_processes] Processing {len(mod_instructions)} modification instructions for material {material.name} ({hscode})")
                
                for instruction in mod_instructions:
                    process_instruction(instruction, ctx.state)
                    
                    if ctx.state.options.save_state:    
                        save_state(ctx.state.options.research_folder,ctx.state, silent=True)  
                        
            except UsageLimitExceeded as e:
                print(f"\t[generate_material_processes] Usage limit exceeded while researching processes for material {material.name} ({hscode}): {e}")
                continue
            except Exception as e:
                print(f"\t[generate_material_processes] Error generating/researching the processes for material {material.name} ({hscode}): {e}")  
                continue
                    
            if ctx.state.options.save_state:    
                save_state(ctx.state.options.research_folder,ctx.state, silent=True)  
        
        print(f"\t[generate_material_processes] Purging processes below scale threshold ({opts.purge_scale_threshold}).")
        ctx.state.purge_for_scale(scale_threshold=opts.purge_scale_threshold, dry_run=opts.purge_dry_run)

                                
        if opts.solo:
            return End(ctx.state)
        
        return merge_duplicate_processes()

@dataclass
class merge_duplicate_processes(BaseNode[ResearchPipelineState]):
    """
    Merge duplicate materials based on their HS Codes, aliases, and names.
    This will ensure that materials with the same HS Code or similar names are merged into a single material entry.
    """
    async def run(self, ctx: GraphRunContext) -> Union[End,'review_material_processes']:
        print("[merge_duplicate_processes] start")
        opts = ctx.state.options
        agent = ctx.state.agents.get("process_merging_agent")
        if not opts.merge_duplicate_processes:
            print("\t[merge_duplicate_processes] Skipping duplicate merging as requested.")
            if opts.solo:
                return End(ctx.state)
            
            return review_material_processes()
        
        print(f"\t[merge_duplicate_processes] Merging duplicates for {len(ctx.state.materials)} materials")
        duplicates = ctx.state.identify_duplicate_processes()
        print(f"\t[merge_duplicate_processes] Found {len(duplicates)} sets of duplicate processes to merge.")
        for index,dupset in enumerate(duplicates):
            print(f"\t[merge_duplicate_processes] Set {index+1} ")
                
            prompt = "The following processes are duplicates. Please merge them into a single process, ensuring that quality references are combined and the process description is clear and complete.\n"
            for index,dup in enumerate(dupset):
                prompt += "Process #{index+1}:\n"
                prompt += create_process_string(dup)
                prompt += "\n" 
                            
            try:
                result = await agent.run(
                    prompt,
                    usage_limits=UsageLimits(request_limit=200),
                )
                print(f"\t[merge_duplicate_processes] Adding merged process: {result.output}")
                newp = MaterialProcess(
                    description=result.output.description,
                    precursors=result.output.precursors,
                    products=result.output.products,
                    references=result.output.references,
                    scale=result.output.scale
                )
                ctx.state.add_process(newp)
                for dup in dupset:
                    print(f"\t[merge_duplicate_processes] Removing the duplicate process {dup.id}")
                    ctx.state.remove_process(dup.id)
            except Exception as e:
                print(f"\t[merge_duplicate_processes] Error merging duplicate processes: {e}")
                continue
                
        if opts.solo:
            return End(ctx.state)
        
        return review_material_processes()

@dataclass
class review_material_processes(BaseNode[ResearchPipelineState]):
    """
    Review and validate the processes for each material, ensuring that all references are reviewed and scored appropriately.
    If enough references are available and reviewed, the process score is calculated.
    If there are any process wihtout enough references or a score below the defined threshold, AND we have not yet reached the maximum number of review passes, we will return to this task for another review pass.
    If we have reached the maximum number of review passes, we will proceed to purge processes that do not meet the criteria.
    """
    async def run(self, ctx: GraphRunContext) -> Union[End,'generate_material_processes','purge_processes']:
        opts = ctx.state.options
        print("[review_material_processes] start")
        if ctx.state.review_passes >= opts.maximum_reference_reviews:
            if opts.solo:
                return End(ctx.state)
            
            return purge_processes()
        
        print(f"\t[review_material_processes] Review Research Material {ctx.state.review_passes+1} / {ctx.state.options.maximum_reference_reviews}") 
        requires_additional_research = False

        print(f"\t[review_material_processes]Processes to review: {len(ctx.state.processes)}")

        for process_id, process in ctx.state.processes.items():
            print(f"\t[review_material_processes]Reviewing process: {process_id}")

            if not process.references:
                print(f"\t[review_material_processes]No references found for process: {process.description}")
                requires_additional_research = True
                continue

            refReplacements = []
            for ref in process.references:
                original_ref = ref
                if isinstance(ref, ReviewedReference):
                    if ctx.state.options.force_reference_review \
                        or ref.source_quality_score is None \
                        or ref.content_quality_score is None \
                        or (isinstance(ref.content_quality_score, float) and ref.content_quality_score == 0.0 and ref.content_quality_reason is None):
                        reviewedRef = ReviewedReference(url=ref.url)
                    else:
                        reviewedRef = ref
                else:
                    reviewedRef = ReviewedReference(url=ref)

                if reviewedRef.source_quality_score is None:
                    reviewedRef.source_quality_score = await score_url(reviewedRef.url, ctx.state.agents['url_scorer_agent'])

                if reviewedRef.content_quality_score is None:
                    print(f"\t\t[review_material_processes] Fetching content for reference: {reviewedRef.url}")
                    try:
                        rc = await fetch_content(
                            reviewedRef.url,
                            options=ReferenceContentOptions(
                                reference_cache_folder=ctx.state.options.reference_cache_folder,
                                save=True,
                                refresh=False
                            )
                        )

                        if rc.error is not None:
                            reviewedRef.content_quality_score = 0.0
                            reviewedRef.content_quality_reason = rc.error
                        else:
                            review_results = await review_reference_content(
                            content=rc.content,
                            process=process,
                            agent=ctx.state.agents['reference_reviewer_agent']
                            )
                            if review_results is None:
                                print(f"\t\t[review_material_processes]Error reviewing content for reference {ref}. Skipping.")
                                refReplacements.append(original_ref)
                                continue

                            print(f"\t\t[review_material_processes] Review Results: {review_results}")
                            reviewedRef.content_quality_score = review_results.score
                            reviewedRef.content_quality_reason = review_results.reason
                    except Exception as e:
                        print(f"\t\t[review_material_processes]Error fetching or reviewing content for reference {ref}: {e}")
                        reviewedRef.content_quality_score = None
                        reviewedRef.content_quality_reason = str(e)
                        refReplacements.append(original_ref)
                        continue

                refReplacements.append(reviewedRef)

            distinct_domains_required=2
            top_refs, all_reviewed, found_required_distinct_domains,unreviewed_count = evaluate_references(
                references=refReplacements,
                minimum_process_references=ctx.state.options.minimum_process_references,
                distinct_domains_required=distinct_domains_required
            )
            pscore = 0.0
            for ref in top_refs:
                pscore += ref.content_quality_score * min(ref.source_quality_score * 2, 1.0)

            if all_reviewed and len(top_refs) >= ctx.state.options.minimum_process_references and found_required_distinct_domains:
                process.process_score = pscore / len(top_refs)
                print(f"\t[review_material_processes]   - Top References: {len(top_refs)}")
                print(f"   - Process Score: {process.process_score}")
            elif not found_required_distinct_domains:
                print(f"\t[review_material_processes]   * Not enough distinct domains ({distinct_domains_required}) for process references.")
                process.process_score = None
            else:
                print("\t[review_material_processes]   * Not all references reviewed or not enough references for process.")
                process.process_score = None

            if process.process_score is None or process.process_score < ctx.state.options.process_score_threshold:
                print(f"\t[review_material_processes]  * Process with score {process.process_score} does not meet the score threshold of {ctx.state.options.process_score_threshold}.")
                requires_additional_research = True

            process.references = refReplacements

            if ctx.state.options.save_state:
                save_state(ctx.state.options.research_folder, ctx.state, silent=True)

        print(f"\t[generate_material_processes] Purging processes with low quality references (content score < .3).")
        ctx.state.purge_low_content_quality_references(minimum_content_score=.3,dry_run=opts.purge_dry_run)

        if ctx.state.options.save_state:
            save_state(ctx.state.options.research_folder, ctx.state, silent=True)

        ctx.state.review_passes += 1
        print(f"\t[review_material_processes]Review pass {ctx.state.review_passes}/{ctx.state.options.maximum_reference_reviews} Completed")
        if requires_additional_research and ctx.state.options.generate_processess:
            print("\t[review_material_processes]Some processes require additional research. Continuing to research processes...")
            if opts.solo:
                return End(ctx.state)

            return generate_material_processes()

        if opts.solo:
            return End(ctx.state)

        return purge_processes()

@dataclass
class expand_process_materials(BaseNode[ResearchPipelineState]):
    async def run(self, ctx: GraphRunContext) -> Union[End,'generate_material_processes','expand_product_family_materials']:
    
        print("[expand_process_materials] start")
        agent = ctx.state.agents["material_finder_agent"]
        opts = ctx.state.options
        if not opts.expand_process_materials or ctx.state.expansion_passes >= opts.maximum_material_expansion_rounds:
            if opts.solo:
                return End(ctx.state)
            
            return expand_product_family_materials()
        
        current_keys = set(ctx.state.materials.keys())
        
        for process_id, process in ctx.state.processes.items():
            print(f"\t[expand_process_materials] Processing: {process_id}")
            
            prompt = f"Process:\n{process.description}\nThis process is used for the production of:\n"
            
            for product in process.products:
                if isinstance(product, SuggestedMaterialReference):
                    prompt += f"  - {product.name} (Suggested HS Code: {product.hs_code})\n"
                elif isinstance(product, MaterialReference):
                    prompt += f"  - {product.name} ( HS Code: {product.hs_code})\n"
                else:
                    prompt += f"  - {product}\n"
            
            for precursor in process.precursors:
                if isinstance(precursor, SuggestedMaterialReference):
                    prompt += f"  - {precursor.name} (Suggested HS Code: {precursor.hs_code})\n"
                elif isinstance(precursor, MaterialReference):
                    prompt += f"  - {precursor.name} ( HS Code: {precursor.hs_code})\n"
                else:
                    prompt += f"  - {precursor}\n"
            
            
            replacement_precursors = []
            for precursor in process.precursors:
                if isinstance(precursor, SuggestedMaterialReference):
                    print(f"\t\t[expand_process_materials] Precursor is already a MaterialReference: {precursor.name}")

                    if precursor.hs_code not in ctx.state.materials:
                        if opts.expansion_filter is not None and precursor.hs_code in opts.expansion_filter:
                            print(f"\t\t[expand_process_materials] Precursor {precursor.name} ({precursor.hs_code}) not found in materials. Generating new material.")
                            prompt += f"\n\nPlease generate a ResearchMaterial object for the precursor '{precursor.name}' with suggested HS Code {precursor.hs_code}.\nThis is ONLY a suggested HS Code, so if you know of a more appropriate HS Code for this material, please use that instead.\n"                        
                            result = await agent.run(
                                prompt,
                                deps=MaterialFinderAgentDeps(
                                    materials=ctx.state.materials
                                ),
                                usage_limits=UsageLimits(request_limit=200)
                            )  
                            if not isinstance(result.output, ResearchMaterial):
                                print(f"\t\t[expand_process_materials] Expected ResearchMaterial, got {type(result.output)}. Skipping.")
                            else:                                  
                                print(f"\t\t[expand_process_materials] Adding new material to state: {result.output.name} ({result.output.hs_code})")
                                ctx.state.add_material(result.output) 
                                replacement_precursors.append(MaterialReference(hs_code=result.output.hs_code,name=result.output.name))
                        else:
                            print(f"\t\t[expand_process_materials] Precursor {precursor.name} ({precursor.hs_code}) not found in materials. Skipping as it is not in the expansion filter.")
                            replacement_precursors.append(MaterialReference(hs_code=precursor.hs_code,name=precursor.name))
                    else:
                        replacement_precursors.append(precursor)       
                elif isinstance(precursor, MaterialReference):                
                    prompt += f"  - {precursor.name} (HS Code: {precursor.hs_code})\n"
                    replacement_precursors.append(precursor)
        
                else:
                    print(f"\t\t[expand_process_materials] Precursor is not a MaterialReference or SuggestedMaterialReference: {precursor}")
                    prompt += f"  - {precursor}\n"
                    replacement_precursors.append(precursor)    

            replacement_products = []
            for product in process.products:
                if isinstance(product, SuggestedMaterialReference):
                    print(f"\t\t[expand_process_materials] Product is already a MaterialReference: {product.name}")

                    if product.hs_code not in ctx.state.materials:
                        if opts.expansion_filter is not None and product.hs_code in opts.expansion_filter:
                            print(f"\t\t[expand_process_materials] Product {product.name} ({product.hs_code}) not found in materials. Generating new material.")
                            prompt += f"Please generate a ResearchMaterial object for the product {product.name} with suggested HS Code {product.hs_code}.\n"                        
                            result = await agent.run(
                                prompt,
                                deps=MaterialFinderAgentDeps(
                                    materials=ctx.state.materials
                                ),
                                usage_limits=UsageLimits(request_limit=200)
                            )  
                            if not isinstance(result.output, ResearchMaterial):
                                print(f"\t\t[expand_process_materials] Expected ResearchMaterial, got {type(result.output)}. Skipping.")
                                replacement_products.append(product)
                                continue    
                            else:
                                print(f"\t\t[expand_process_materials] Adding new material to state: {result.output.name} ({result.output.hs_code})")
                                ctx.state.add_material(result.output) 
                                replacement_products.append(MaterialReference(hs_code=result.output.hs_code,name=result.output.name))
                        else:
                            print(f"\t\t[expand_process_materials] Product {product.name} ({product.hs_code}) not found in materials. Skipping as it is not in the expansion filter.")
                            replacement_products.append(product)
                    else:
                        replacement_products.append(MaterialReference(hs_code=product.hs_code,name=product.name))
                elif isinstance(product, MaterialReference):                
                    prompt += f"  - {product.name} (HS Code: {product.hs_code})\n"
                    replacement_products.append(product)
        
                else:
                    print(f"\t\t[expand_process_materials] Product is not a MaterialReference or SuggestedMaterialReference: {product}")
                    prompt += f"  - {product}\n"
                    replacement_products.append(product)    

            print(f"\t[expand_process_materials] Updated precursors for process. len {len(replacement_precursors)} orig: {len(process.precursors)} ")
            print(f"\t[expand_process_materials] Updated products for process. len {len(replacement_products)} orig: {len(process.products)} ")
            if len(replacement_precursors) == len(process.precursors):
                process.precursors = replacement_precursors 
            else:
                raise Exception("Mismatch in precursor lengths")
            
            if len(replacement_products) == len(process.products):
                process.products = replacement_products
            else:
                raise Exception("Mismatch in product lengths")
            
            if opts.save_state:
                save_state(ctx.state.options.research_folder, ctx.state, silent=True)   
            
        
        if opts.solo:
            return End(ctx.state)   
        
        return expand_product_family_materials()
@dataclass

class expand_product_family_materials(BaseNode[ResearchPipelineState]):
    async def run(self, ctx: GraphRunContext) -> Union[End,'generate_material_processes']:
        opts = ctx.state.options 
        print("[expand_product_family_materials] start")
        if not opts.expand_product_family_materials or ctx.state.expansion_passes >= opts.maximum_material_expansion_rounds:
            print("Skipping product family material expansion")
            return End(ctx.state)
        
        print(f"\t[expand_product_family_materials] Generating Product Family Materials")  
        
        if opts.generate_processess:
            ctx.state.expansion_passes += 1
            if opts.reset_reference_reviews_on_material_expansion:
                print("\t[expand_product_family_materials]Resetting reference reviews on material expansion.")
                ctx.state.review_passes = 0
            if not opts.solo:
                print("\t[expand_product_family_materials] Continuing to generate material processes after expanding product family materials.")
                return generate_material_processes()
    
        return End(ctx.state)    
        
@dataclass
class purge_processes(BaseNode[ResearchPipelineState]):
    async def run(self, ctx: GraphRunContext) -> Union[End,'expand_process_materials']:
        print("[purge_processes] start")
        opts= ctx.state.options
        if not opts.purge_processes:
            print("\t[purge_processes] Skipping process purging as requested.")
            if opts.solo:
                return End(ctx.state)
            return expand_process_materials()
        
        if ctx.state.options.purge_dry_run:
            print("\t[purge_processes] Dry run of purge processes. No changes will be made.")
        else:
            print("\t[purge_processes] Purging processes from research state.")

        # Remove unsupported processes
        unsupported_processes = []
        for pid, process in ctx.state.processes.items():
            print(f"\t[purge_processes] Checking process {pid} for support")
            reasons = []
            
            if process.process_score is None:
                if all(isinstance(ref, ReviewedReference) and ref.content_quality_score is not None and ref.source_quality_score is not None for ref in process.references):
                    reasons.append(f"too few reviewed references.  Process scale: {process.scale}")
                elif len(process.references) < 0:
                    reasons.append(f"no references.  Process scale: {process.scale}")    
                
            if process.process_score is not None and process.process_score < ctx.state.options.process_score_threshold:
                reasons.append(f"score of {process.process_score} below threshold {ctx.state.options.process_score_threshold}.  Process scale: {process.scale}")
                
            if process.scale is not None and process.scale < ctx.state.options.purge_scale_threshold:
                reasons.append(f"scale of {process.scale} below threshold {ctx.state.options.purge_scale_threshold}")
                
            if reasons:
                print("\t[purge_processes] Unsupported process found:", pid, "due to", ", ".join(reasons))
                unsupported_processes.append((pid, reasons))
        
        if unsupported_processes and ctx.state.options.purge_processes:
            print(f"\t[purge_processes] Unsupported processes found  {len(unsupported_processes)}")
            for pid, reasons in unsupported_processes:
                reason_str = " and ".join(reasons)
                if ctx.state.options.purge_dry_run:
                    print(f"\t[purge_processes] [Dry Run] Remove process {pid} due to {reason_str}")
                else:
                    del ctx.state.processes[pid]
                    print(f"\t[purge_processes] Removed process {pid} due to {reason_str}")
         
        
        if ctx.state.options.save_state and not ctx.state.options.purge_dry_run:
            save_state(ctx.state.options.research_folder, ctx.state)
        
        if ctx.state.options.purge_dry_run or opts.solo:
            return End(ctx.state)

        return expand_process_materials()
        