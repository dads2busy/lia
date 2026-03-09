import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Union

import networkx as nx
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from lia.research.config import ResearchConfig


class ReviewedReference(BaseModel):
    """
    A reference that has been reviewed and scored for quality.
    - 'url' - The URL of the reference
    - 'source_quality_score' - A score from 0 to 1 indicating the quality of the source
    - 'content_quality_score' - A score from 0 to 1 indicating the quality of the content
    - 'content_quality_reason' - A brief summary reason for the scores
    """

    url: str
    source_quality_score: Union[float, None] = None
    content_quality_score: Union[float, None] = None
    content_quality_reason: Union[str, None] = None


class ContentReviewResult(BaseModel):
    """
    Result of a content review
    - 'score' - A score from 0 to 1 indicating the quality of the content in relation to a described process
    - 'reason' - A brief summary reason for the score
    """

    score: float
    reason: str


class MaterialReference(BaseModel):
    hs_code: str
    name: str

    def __hash__(self):
        return hash(self.hs_code)

    def __eq__(self, other):
        if not isinstance(other, MaterialReference):
            return NotImplemented
        return self.hs_code == other.hs_code

    def __str__(self):
        return f"MaterialReference(name={self.name}, hs_code={self.hs_code})"


class SuggestedMaterialReference(MaterialReference):
    """
    A suggested material reference that may not have been fully verified.
    - 'name' - The name of the material
    - 'hs_code' - The Harmonized System code for the material
    - 'suggested' - True if this is a suggested material, False if it is a verified material
    """

    name: str
    hs_code: str
    suggested: bool = True


class MaterialProcess(BaseModel):
    """
    A process to perform a material transformation.
    - 'id' - Unique identifier for the process, typically {material_hscode}-{index}
    - 'description' - Description of the process
    - 'precursors' - List of materials that are required for this process
    - 'products' - Output, other than the primary output this transformation is describing, from this process
    - 'references' - URLs to websites / papers describing the process in detail
    - 'scale' - The scale of the process, e.g. 'industrial', 'commercial', 'laboratory'
    - 'process_score' - A score from 0 to 1 indicating the quality of supporting references for this process. None if not all references have been reviewed.
    """

    description: str
    scale: float
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    precursors: list[Union[str, MaterialReference, SuggestedMaterialReference]] = Field(
        default_factory=list
    )
    products: list[Union[str, MaterialReference, SuggestedMaterialReference]] = Field(
        default_factory=list
    )
    references: list[str | ReviewedReference] = Field(default_factory=list)
    process_score: Union[float, None] = None

    def __eq__(self, other):
        if not isinstance(other, MaterialProcess):
            return NotImplemented
        return hash(self) == hash(other)

    def __hash__(self):
        def get_sorted_hs_codes(materials):
            return sorted(
                material.hs_code
                for material in materials
                if isinstance(material, (MaterialReference, SuggestedMaterialReference))
                and material.hs_code
            )

        precursors_hs_codes = get_sorted_hs_codes(self.precursors)
        products_hs_codes = get_sorted_hs_codes(self.products)

        return hash((tuple(precursors_hs_codes), tuple(products_hs_codes)))


class RemoveProcessInstruction(BaseModel):
    """
    Instruction to remove a process from the research state.
    Requires a 'process_id' field with the ID of the process to remove.
    """

    proces_id: str = Field(
        description="ID of the process to remove from the research state"
    )


class AddProcessInstruction(BaseModel):
    """
    Instruction to add a new process to the research state.
    Requires a 'process' field with a MaterialProcess object.
    """

    process: MaterialProcess = Field(
        description="New process to add to the research state"
    )


class AddMaterialToProcessInstruction(BaseModel):
    """
    Instruction to add a new material to to a process.
    - process_id: ID of the process to add the material to
    - action: 'add_material'
    - addition_type: 'material type' (either 'precursor' or 'product', depending on whether the material is a precursor or product in the process)
    - material: SuggestedMaterialReference object or string epresenting the material to add
    """

    process_id: str = Field(description="ID of the process to add the material to")
    addition_type: str = Field(
        "material",
        description="Either Precursor or Product, depending on whether the material is a precursor or product in the process.",
    )
    material: Union[str, SuggestedMaterialReference, MaterialReference] = Field(
        description="Material to add to the research state. Can be a string (for minor materials), a MaterialReference, or a SuggestedMaterialReference."
    )


class RemoveMaterialFromProcessInstruction(BaseModel):
    """
    Instruction to remove a material from the research state.
    - process_id: ID of the process to remove the material from
    - action: 'remove_material'
    - removal_type: 'material type' (either 'precursor' or 'product', depending on whether the material is a precursor or product in the process)
    - material: MaterialReference or SuggestedMaterialsReference object or string representing the material to remove
    """

    process_id: str = Field(description="ID of the process to remove the material from")
    removal_type: str = Field(
        "material",
        description="Either Precursor or Product, depending on whether the material is a precursor or product in the process.",
    )
    material: Union[str, SuggestedMaterialReference, MaterialReference] = Field(
        description="Material to remove from the research state. Can be a string (for minor materials), a MaterialReference, or a SuggestedMaterialReference."
    )


class SetProcessInstruction(BaseModel):
    """
    Updates an existing process in the research state.
    - action: 'set_process'
    - process_id: ID of the process to set or update
    - description: New description for the process. None if no updates
    - scale: New scale for the process. None if no updates
    """

    process_id: str = Field(description="ID of the process to set or update")
    description: Union[str, None] = Field(
        description="New description for the process. None if no updates"
    )
    scale: Union[float, None] = Field(
        description="New scale for the process. None if no updates"
    )


class AddReferenceToProcessInstruction(BaseModel):
    """
    Instruction to add a reference to an existing process in the research state.
    - action: 'add_reference'
    - process_id: ID of the process to add the reference to
    - references: List of URLs to add to the process
    """

    process_id: str = Field(description="ID of the process to add the reference to")
    references: List[str] = Field(
        description="List of URLs or ReviewedReference objects to add to the process"
    )  # List of references to add to the process


class ResearchMaterial(BaseModel):
    """
    Information about a particular material gathered through preliminary research
    - 'name' - Canonical name of the material
    - 'mined' - True if this material is a mined material
    - 'aliases' - List of other names the material is known by. Includes common names and industry specific names
    - 'primary_uses' - The primary downstream uses of the material
    - 'processes' - A List of MaterialProcess that are used in order mine,refine, or otherwise produce material
    - 'hs_code' - The Harmonized System code for the material
    - 'hs_description' - The Harmonized System description for the material
    """

    name: str
    hs_code: str
    mined: bool = False  # True if this material is a mined material, False if it is an intermediate or other type
    aliases: List[str] = Field(default_factory=list)
    primary_uses: List[str] = Field(default_factory=list)
    hs_description: str | None


class ResearchPipelineOptions(BaseModel):
    """
    Options for the research pipeline
    - 'model_name' - The name of the LLM model to use
    - 'llm_api_url' - The URL of the LLM API
    - 'llm_api_key' - The API key for the LLM API
    - 'reference_cache_folder' - Folder to cache reference content
    - 'save_state' - Whether to save the state after each step
    - 'debug' - Whether to enable debug mode
    - 'agent_architecture' - Whether to use specialized multi-agent prompts ("multi")
      or a generalist prompt across all roles ("generalist")
    """

    model_name: str = "llama3.3"
    llm_api_url: str | None = "http://localhost:11434/v1"
    llm_api_key: str = ""
    google_api_key: str | None = None
    google_custom_search_engine_id: str | None = None
    wikimedia_access_token: str | None = None

    # Agent prompt architecture:
    # - "multi": role-specialized prompts (default; current behavior)
    # - "generalist": a shared generalist prompt used for all roles
    agent_architecture: str = "multi"

    research_folder: Union[str, Path] = "."
    reference_cache_folder: str | None = None
    generate_materials: bool = True
    regenerate_materials: bool = False
    material_generation_rounds: int = 1
    generate_processess: bool = True
    process_score_threshold: float = 0.5
    minimum_process_references: int = 2
    maximum_reference_reviews: int = 2
    distinct_domains_required: int = 2
    force_reference_review: bool = False
    merge_duplicate_processes: bool = True
    purge_processes: bool = True
    purge_dry_run: bool = False
    purge_scale_threshold: float = 0.4
    maximum_material_expansion_rounds: int = 2
    expand_process_materials: bool = True
    expand_product_family_materials: bool = True
    expansion_filter: Union[List[str], None] = (
        None  # List of HS codes to limit expansion to
    )
    reset_reference_reviews_on_material_expansion: bool = True
    generate_network: bool = True
    generate_visualizations: bool = True
    save_state: bool = True
    start: Union[str, None] = (
        None  # Starting point in the pipeline (generate, review, purge)
    )
    solo: bool = (
        False  # Whether to run the pipeline in solo mode (only run a single task node)
    )
    debug: bool = False


class ResearchPipelineState(BaseModel):
    """
    State of the research pipeline
    - 'research_config' - The research configuration (excluded from serialization)
    - 'agents' - The agents used in the pipeline (excluded from serialization)
    - 'options' - The ResearchPipelinesOptions options for the pipeline (excluded from serialization)
    - 'materials' - A dictionary of material name to ResearchMaterial
    - 'unresearched' - A list of materials that have not yet been researched/expanded into the materials dictionary
    """

    research_config: ResearchConfig = Field(default_factory=None, exclude=True)
    agents: Dict[str, Any] = Field(default_factory=dict, exclude=True)
    options: ResearchPipelineOptions = Field(
        default_factory=ResearchPipelineOptions, exclude=True
    )
    materials: Dict[str, ResearchMaterial] = Field(default_factory=dict)
    processes: Dict[str, MaterialProcess] = Field(
        default_factory=dict
    )  # Keyed by material HS code
    material_generation_passes: int = Field(default=0, exclude=True)
    review_passes: int = Field(default=0, exclude=True)
    expansion_passes: int = Field(default=0, exclude=True)

    def get_processes_for_material(self, hs_code: str) -> List[MaterialProcess]:
        """
        Get all processes for a material by its HS code
        """

        processes = []
        for process in self.processes.values():
            if any(
                isinstance(product, (MaterialReference, SuggestedMaterialReference))
                and product.hs_code == hs_code
                for product in process.products
            ):
                processes.append(process)

        return processes

    def add_process(self, process: MaterialProcess, overwrite: bool = False):
        print(f"add_process: {process.id}")

        if process.id in self.processes and not overwrite:
            raise ValueError(f"Process with ID {process.id} already exists")

        newp = MaterialProcess(
            id=process.id, scale=process.scale, description=process.description
        )

        self.processes[process.id] = newp

        for product in process.products:
            self.add_product(process.id, product)

        for precursor in process.precursors:
            self.add_precursor(process.id, precursor)

        for reference in process.references:
            self.add_reference(process.id, reference)

    def replace_process(
        self, process_id: str, new_process: MaterialProcess, replace_id: bool = False
    ):
        """
        Replace an existing process in the state by its ID
        """

        if process_id not in self.processes:
            raise ValueError(f"Process with ID {process_id} does not exist")

        if new_process.id != process_id and not replace_id:
            raise ValueError("New process ID must match the existing process ID")
        elif new_process.id != process_id:
            new_process.id = process_id

        self.processes[process_id] = new_process

    def remove_process(self, process_id: str):
        """
        Remove a process from the state by its ID
        """
        if process_id in self.processes:
            del self.processes[process_id]

    def add_reference(
        self,
        process_id: str,
        reference: Union[str, MaterialReference, SuggestedMaterialReference],
    ):
        """
        Add a reference to an existing process by its ID
        """
        if process_id not in self.processes:
            raise ValueError(f"Process with ID {process_id} does not exist")

        if isinstance(reference, ReviewedReference):
            # If the reference is already a ReviewedReference, use its URL
            url = reference.url
            normalized_url = url.split("#")[0]
            reference.url = normalized_url
        else:
            url = reference
            normalized_url = url.split("#")[0]

        found_ref = False
        for ref in self.processes[process_id].references:
            if isinstance(ref, ReviewedReference) and ref.url == normalized_url:
                found_ref = True
                break
            else:
                if ref == normalized_url:
                    found_ref = True
                    break

        if not found_ref:
            if isinstance(reference, ReviewedReference):
                self.processes[process_id].references.append(reference)
            else:
                self.processes[process_id].references.append(ReviewedReference(url=url))

    def remove_reference(
        self,
        process_id: str,
        reference: Union[str, MaterialReference, SuggestedMaterialReference],
    ):
        """
        Remove a reference from an existing process by its url
        """
        if process_id not in self.processes:
            raise ValueError(f"Process with ID {process_id} does not exist")

        if isinstance(reference, ReviewedReference):
            url = reference.url
            normalized_url = url.split("#")[0]
        else:
            url = reference
            normalized_url = url.split("#")[0]

        self.processes[process_id].references = [
            ref
            for ref in self.processes[process_id].references
            if not (isinstance(ref, ReviewedReference) and ref.url == normalized_url)
            and ref != normalized_url
        ]

    def add_precursor(
        self,
        process_id: str,
        material: Union[str, MaterialReference, SuggestedMaterialReference],
    ):
        """
        Add a precursor material to an existing process by its ID
        """
        if process_id not in self.processes:
            raise ValueError(f"Process with ID {process_id} does not exist")

        # Check if the material is already in products
        for product in self.processes[process_id].products:
            if isinstance(product, (MaterialReference, SuggestedMaterialReference)):
                if (
                    isinstance(
                        material, (MaterialReference, SuggestedMaterialReference)
                    )
                    and product.hs_code == material.hs_code
                ):
                    raise ValueError(
                        "Cannot add a precursor that is already in products"
                    )
                elif material == product.name:
                    raise ValueError(
                        "Cannot add a precursor that is already in products"
                    )
            elif product == material:
                raise ValueError("Cannot add a precursor that is already in products")

        found = False
        for precursor in self.processes[process_id].precursors:
            if isinstance(precursor, (MaterialReference, SuggestedMaterialReference)):
                if (
                    isinstance(
                        material, (MaterialReference, SuggestedMaterialReference)
                    )
                    and precursor.hs_code == material.hs_code
                ):
                    found = True
                    break
                elif material == precursor.name:
                    found = True
                    break
            elif precursor == material:
                found = True
                break

        if not found:
            self.processes[process_id].precursors.append(material)

    def remove_precursor(
        self,
        process_id: str,
        material: Union[str, MaterialReference, SuggestedMaterialReference],
    ):
        """
        Remove a precursor material from an existing process by its ID
        """
        if process_id not in self.processes:
            raise ValueError(f"Process with ID {process_id} does not exist")

        self.processes[process_id].precursors = [
            precursor
            for precursor in self.processes[process_id].precursors
            if not (
                isinstance(precursor, (MaterialReference, SuggestedMaterialReference))
                and isinstance(
                    material, (MaterialReference, SuggestedMaterialReference)
                )
                and precursor.hs_code == material.hs_code
            )
            and precursor != material
        ]

    def add_product(
        self,
        process_id: str,
        material: Union[str, MaterialReference, SuggestedMaterialReference],
    ):
        """
        Add a product material to an existing process by its ID
        """
        if process_id not in self.processes:
            raise ValueError(f"Process with ID {process_id} does not exist")

        # Check if the material is already in precursors
        for precursor in self.processes[process_id].precursors:
            if isinstance(precursor, (MaterialReference, SuggestedMaterialReference)):
                if (
                    isinstance(
                        material, (MaterialReference, SuggestedMaterialReference)
                    )
                    and precursor.hs_code == material.hs_code
                ):
                    raise ValueError(
                        "Cannot add a product that is already in precursors"
                    )
                elif material == precursor.name:
                    raise ValueError(
                        "Cannot add a product that is already in precursors"
                    )
            elif precursor == material:
                raise ValueError("Cannot add a product that is already in precursors")

        found = False
        for product in self.processes[process_id].products:
            if isinstance(product, (MaterialReference, SuggestedMaterialReference)):
                if (
                    isinstance(
                        material, (MaterialReference, SuggestedMaterialReference)
                    )
                    and product.hs_code == material.hs_code
                ):
                    found = True
                    break
                elif material == product.name:
                    found = True
                    break
            elif product == material:
                found = True
                break

        if not found:
            self.processes[process_id].products.append(material)

    def remove_product(
        self,
        process_id: str,
        material: Union[str, MaterialReference, SuggestedMaterialReference],
    ):
        """
        Remove a product material from an existing process by its ID
        """
        if process_id not in self.processes:
            raise ValueError(f"Process with ID {process_id} does not exist")

        self.processes[process_id].products = [
            product
            for product in self.processes[process_id].products
            if not (
                isinstance(product, (MaterialReference, SuggestedMaterialReference))
                and isinstance(
                    material, (MaterialReference, SuggestedMaterialReference)
                )
                and product.hs_code == material.hs_code
            )
            and product != material
        ]

    def add_material(self, material: ResearchMaterial):
        """
        Add a material to the state
        """
        if material.hs_code in self.materials:
            if (
                material.name != self.materials[material.hs_code].name
                and material.name not in self.materials[material.hs_code].aliases
            ):
                self.materials[material.hs_code].aliases.append(material.name)

            for alias in material.aliases:
                if (
                    alias != self.materials[material.hs_code].name
                    and alias not in self.materials[material.hs_code].aliases
                ):
                    self.materials[material.hs_code].aliases.append(alias)
        else:
            self.materials[material.hs_code] = material

    def remove_material(self, hs_code: str):
        """
        Remove a material from the state by its HS code
        """
        if hs_code in self.materials:
            del self.materials[hs_code]

    def material_exists(self, hs_code: str) -> bool:
        """
        Check if a material exists in the state by its HS code
        """
        return hs_code in self.materials

    def get_material_by_alias(self, alias: str) -> Union[ResearchMaterial, None]:
        """
        Get a material by its alias
        """
        if alias in self.materials:
            return self.materials[alias]

        for material in self.materials.values():
            if alias == material.name or alias in material.aliases:
                return material

        return None

    def purge_for_scale(
        self, scale_threshold: float = 0.4, dry_run: bool = False
    ) -> List[str]:
        """
        Purge processes that are below a certain scale threshold.
        Returns a list of process IDs that were purged.
        """
        purged_processes = []

        process_purged = False
        for process_id, process in list(self.processes.items()):
            if process.scale < scale_threshold:
                if not dry_run:
                    del self.processes[process_id]
                purged_processes.append(process_id)

        return purged_processes

    def purge_low_content_quality_references(
        self, minimum_content_score: float = 0.3, dry_run: bool = False
    ) -> List[str]:
        """
        Purge references from processes that have a content quality score below a certain threshold.
        Returns a list of process IDs that had references purged.
        """
        purged_processes = []

        for process_id, process in self.processes.items():
            original_references = process.references[:]

            new_refs = [
                ref
                for ref in process.references
                if not (
                    isinstance(ref, ReviewedReference)
                    and ref.content_quality_score is not None
                    and ref.content_quality_score < minimum_content_score
                )
            ]

            if not dry_run and len(new_refs) < len(original_references):
                process.references = new_refs
                process.process_score = (
                    None  # Reset process score since references have changed
                )

    def identify_duplicate_processes(self) -> List[List[MaterialProcess]]:
        """
        Identify duplicate processes in the state.
        Returns a list of lists, where each inner list contains processes that are duplicates of each other.
        """
        duplicates = []
        seen = set()

        for process_id, process in self.processes.items():
            if process_id in seen:
                continue

            matching_processes = [process]
            for other_id, other_process in self.processes.items():
                if (
                    other_id != process_id
                    and other_id not in seen
                    and process == other_process
                ):
                    matching_processes.append(other_process)

            if len(matching_processes) > 1:
                duplicates.append(matching_processes)
                seen.update(p.id for p in matching_processes)

        return duplicates

    def graph_is_connected(self) -> bool:
        """
        Check if the graph of processes is connected using networkx.
        Returns True if the graph is weakly connected and has only one component, False otherwise.
        """

        if not self.processes:
            return True

        graph = nx.DiGraph()

        # Add nodes and edges to the graph

        for materials in self.materials.values():
            graph.add_node(materials.hs_code)

        uncreated_material_nodes = set()

        for process in self.processes.values():
            for precursor in process.precursors:
                if isinstance(
                    precursor, (MaterialReference, SuggestedMaterialReference)
                ):
                    if precursor.hs_code not in graph:
                        uncreated_material_nodes.add(precursor.hs_code)
                        graph.add_edge(precursor.hs_code, process.id)

            for product in process.products:
                if isinstance(product, (MaterialReference, SuggestedMaterialReference)):
                    if product.hs_code not in graph:
                        uncreated_material_nodes.add(product.hs_code)
                        graph.add_edge(process.id, product.hs_code)

        # # Check the number of connected components
        # components = nx.number_weakly_connected_components(graph)
        # if components > 1:
        #     # Attempt to add uncreated material nodes to improve connectivity
        #     for material_node in uncreated_material_nodes:
        #         graph.add_node(material_node)

        #         # Recheck connectivity after adding nodes
        #         components = nx.number_weakly_connected_components(graph)
        #         if components > 1:
        #             return False

        # Check if the graph is weakly connected
        return nx.is_weakly_connected(graph)

        # Check the number of connected components
        components = nx.number_weakly_connected_components(graph)
        if components > 1:
            return False

        # Check if the graph is weakly connected
        return nx.is_weakly_connected(graph)
