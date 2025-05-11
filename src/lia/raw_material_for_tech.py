from pydantic_graph import BaseNode,End,GraphRunContext,Graph
from typing import List,Any,Union
from dataclasses import dataclass,field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic import BaseModel,Field
import asyncio

class GenerateSupplyChainNetworkOptions(BaseModel):
    model_name: str = "llama3.3"
    llm_api_url: str | None = "http://localhost:11434/v1"
    llm_api_key: str = ""
    max_component_reviews: int | None = 6
    min_component_reviews: int | None = 3
  
@dataclass 
class RawMaterial:
    name: str
    type: str | None = None
    hscode: str|None = None

@dataclass
class SuggestedChanges:
    has_updates: bool = False
    recommendations: str = ""
    
@dataclass
class ComponentAssemblyState:
    component: str
    description: str|None = None
    suggested_changes: SuggestedChanges = field(default_factory=lambda: SuggestedChanges(has_updates=False))
    reviews = int(0)
    material: List[RawMaterial] = field(default_factory=list)
    options: GenerateSupplyChainNetworkOptions = field(default_factory=GenerateSupplyChainNetworkOptions)
    reviewer_history: List = field(default_factory=list)
    constructor_history: List = field(default_factory=list)


async def get_raw_materials(component: str, options: GenerateSupplyChainNetworkOptions):

    default_model = OpenAIModel(model_name=options.model_name,base_url=options.llm_api_url,api_key=options.llm_api_key) 

    @dataclass
    class GetRawMaterials(BaseNode[ComponentAssemblyState]):

        async def run(self, ctx: GraphRunContext) -> 'ReviewRawMaterials':

                
            print(f"Getting raw materials for {ctx.state.component}")
            if ctx.state.suggested_changes.has_updates:
                print(f"Updating list with recommendations:\n {ctx.state.suggested_changes.recommendations}")
                
            if ctx.state.reviews == 0:
                temperature = 0
            else:               
                temperature = ctx.state.reviews / ctx.state.options.max_component_reviews
             
            print(f"Current Temperature: {temperature}")
            system_prompt = ' '.join([f"""
                You are an expert in manufacturing and product design.

                Raw Materials are the basic, unprocessed or minimally processed substances that are used as inputs in the manufacturing or production of goods. 
                They are the fundamental components from which finished products are made. Examples include minerals, metals, wood, oil, grain, plastic, and natural gas. 
                Examples of raw materials include:
                    Mining-based: Metals like iron ore, nickel, and cobalt. 
                    Plant-based: Wood, resins, wheat, and corn. 
                    Animal-based: Milk and meat. 
                    Other: Petroleum products, plastic, and chemicals. 
                    
                Raw materials must be categorized as direct or indirect. Direct raw materials are those that are directly incorporated into the finished product (e.g., the wood used to make furniture).
                Indirect raw materials are used in the production process but are not part of the final product (e.g., fuel for machinery).
                
                Given the name of a single component, identify all Raw Materials used in the construction of the component or any of its subcomponents.
                Each material must be assigned a raw material type (indirect or direct) and a valid 6 to 10 digit Harmonized System (HS) Code.
                Do not include any components or subcomponents that are not raw materials.
                Return exactly one JSON array containing the list of raw materials in RawMaterial format:
                """,
                '[{"name": str, "type": str, "hscode": str)},...]\n',
                'Example Output:\n',
                '[{"name":"copper","type":"direct","hscode":"7403.11"},...]'])
            
            
            # print(f"System prompt: {system_prompt}")
            
            agent = Agent(model=default_model, result_type=list[RawMaterial],system_prompt=system_prompt,retries=5)
            try: 
                if not ctx.state.suggested_changes.has_updates:
                    r = await agent.run(f"Please generate a list of the raw materials required to assemble '{ctx.state.component}' and its subcomponents. ",message_history=ctx.state.constructor_history,model_settings={'temperature': temperature})

                    if isinstance(r.data,list):
                        ctx.state.material = r.data
                        ctx.state.constructor_history += r.new_messages()

                else:
                    prompt = f"""
                        The current set of raw materials is  {','.join([material.name for material in ctx.state.material])}.
                        {ctx.state.suggested_changes.recommendations if ctx.state.suggested_changes.recommendations else ""}
                        Please update and return the list of raw materials.
                    """
                    r = await agent.run(prompt, model_settings={'temperature': temperature})
                    ctx.state.constructor_history += r.new_messages()
                    if isinstance(r.data,list):
                        ctx.state.material = r.data
                    
            except Exception as err:
                print(f"Error in GetRawMaterials: {err}")
        
            return ReviewRawMaterials()

    @dataclass
    class ReviewRawMaterials(BaseNode[ComponentAssemblyState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetRawMaterials','End']:
            if ctx.state.reviews < ctx.state.options.max_component_reviews:
                print(f"({ctx.state.reviews+1} of {ctx.state.options.max_component_reviews}) Reviewing Components:")
                for material in ctx.state.material:
                    print(f"\t - {material.name} ({material.type}, {material.hscode})")
                ctx.state.reviews += 1
                temperature = 1 - (ctx.state.reviews / ctx.state.options.max_component_reviews)
                print(f"Review Temperature: {temperature}")

                system_prompt = f"""
                    You are an expert in manufacturing and product design.
                    Your task is to review the raw materials used to manufacture {ctx.state.component} and its subcomponents
            
                    Raw Materials are the basic, unprocessed or minimally processed substances that are used as inputs in the manufacturing or production of goods. 
                    They are the fundamental components from which finished products are made. Examples include minerals, metals, wood, oil, grain, plastic, and natural gas. 
                    Examples of raw materials include:
                        Mining-based: Metals like iron ore, nickel, and cobalt. 
                        Plant-based: Wood, resins, wheat, and corn. 
                        Animal-based: Milk and meat. 
                        Other: Petroleum products, plastic, and chemicals. 
                        
                    Raw materials must be categorized as direct or indirect. Direct raw materials are those that are directly incorporated into the finished product (e.g., the wood used to make furniture).
                    Indirect raw materials are used in the production process but are not part of the final product (e.g., fuel for machinery).

                    Identify any missing raw materials, duplicates, incorrectly classified raw materials, or invalid Harmonized System (HS) Codes.    
                    Each material must be assigned a type (indirect or direct) and a valid 6 to 10 digit HS Code.
                    Items that are not raw materials must be removed from the list.
                    
                    Respond with a SuggestedChanges object that contains the following fields:
                    - has_updates: boolean indicating if there are any recommended changes to the list.   
                    - recommendations: string containing the recommendations for changes to the list if there are any. This field must exist if has_updates is True.
                    
           
                """
                agent = Agent(model=default_model, result_type=SuggestedChanges,system_prompt=system_prompt,retries=5)
                try: 
                    prompt = [f"""
                        Identify and suggest specific changes for any missing raw materials, duplicates, incorrectly classified raw materials, or invalid HS Codes in the following list of raw materials:
                    """]
                    for material in ctx.state.material:
                        prompt += f"\t - {material.name} ({material.type}, {material.hscode})"
                        
                    prompt += "If you have no suggestions, return a SuggestChanges object with has_updates set to False."
                    
                    r = await agent.run(prompt,message_history=ctx.state.reviewer_history,model_settings={'temperature': temperature})
                    # print(f"Review result: {r.data}")
                    # if 'no changes required' not in r.data.lower():
                    # if r.data.lower() != 'no changes required':
                    ctx.state.reviewer_history += r.new_messages()
                    ctx.state.suggested_changes = r.data
                    # print(f"Suggested changes: {r.data}")
                    if r.data.has_updates or ctx.state.reviews < ctx.state.options.min_component_reviews:
                        if not r.data.has_updates:
                            # if there were no suggested changes and we're still less than the minimum number of reviews, we need to run the review again
                            ctx.state.suggested_changes = SuggestedChanges(has_updates=True,recommendations="Ensure that the list of raw materials is complete and accurate. Pay close attention to common raw materials used in the associated techonology")
                        return GetRawMaterials()
                        
                except Exception as err:
                    print(f"Error in ReviewRawMaterials: {err}")
        
            return End(data={
                'material': ctx.state.material
            })
            

    TaskGraph = Graph(nodes=(GetRawMaterials,ReviewRawMaterials))
    state = ComponentAssemblyState(component,options=options)
    result = await TaskGraph.run(GetRawMaterials(),state=state)
    return state.material


async def main():
    product = 'STM32 family of 32-bit microcontrollers'
    print(f"Analyzing product: {product}")
    result= await get_raw_materials(product,options=GenerateSupplyChainNetworkOptions(model_name="llama-3.3-lia-maxctx:latest",llm_api_url="http://udc-aj38-35:11434/v1",llm_api_key="none"))
    print(f"Raw Materials for {product}:")
    for material in result:
        print(f"\t - {material.name} ({material.type}, {material.hscode})")
            
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())