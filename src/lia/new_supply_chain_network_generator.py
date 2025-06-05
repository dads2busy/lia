from pydantic_graph import BaseNode,End,GraphRunContext,Graph
from typing import List,Dict,Any,Union
from dataclasses import dataclass,field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic import BaseModel,Field
import asyncio
import pprint
import json

max_recursion_depth:int = 3


class MaterialNetworkGeneratorOptions(BaseModel):
    model_name: str = "llama3.3"
    llm_api_url: str | None = "http://localhost:11434/v1"
    llm_api_key: str = ""
    max_component_reviews: int | None = 6
  
@dataclass 
class Component:
    name: str
    type: str | None = Field(None, pattern="^(Component|RawMaterial|ManufacturingEquipment|ManufacturingSupplies)$")
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
    components: List[Component] = field(default_factory=list)
    options: MaterialNetworkGeneratorOptions = field(default_factory=MaterialNetworkGeneratorOptions)
    reviewer_history: List = field(default_factory=list)
    constructor_history: List = field(default_factory=list)

@dataclass
class ComponentNetwork:
    component: Component|None
    subcomponents: List[Component] = field(default_factory=list)


async def get_component_network(component_name: str, options: MaterialNetworkGeneratorOptions, component_index:dict|None=None, depth:int=0, parent:Component|None=None) -> ComponentNetwork:     
    default_model = OpenAIModel(model_name=options.model_name,base_url=options.llm_api_url,api_key=options.llm_api_key) 
    print(f"get_component_network: {component_name} {depth}")
    if component_index is None:
        component_index = {}
        
    if component_name in component_index:
        return component_index[component_name]
    
    components = await get_component_assembly(component_name,options,parent=parent)

    subcomponents=[]

    parent = Component(name=component_name)

    for component in components.output['components']:
        if component.type == 'Component' or component.type == 'ManufacturingSupplies':
            subs = await get_component_network(component.name,options,component_index,depth+1,parent=parent)
            component_index[component.name] = ComponentNetwork(component=component,subcomponents=subs)
        else:
            component_index[component.name] = ComponentNetwork(component=component,subcomponents=[])

        subcomponents.append(component_index[component.name])
        
    component_index[component_name] = ComponentNetwork(component=Component(name=component_name),subcomponents=subcomponents)
    return component_index[component_name]

async def get_component_assembly(component: str, options: MaterialNetworkGeneratorOptions, parent:Component|None=None):

    default_model = OpenAIModel(model_name=options.model_name,base_url=options.llm_api_url,api_key=options.llm_api_key) 

    @dataclass
    class GetComponents(BaseNode[ComponentAssemblyState]):

        async def run(self, ctx: GraphRunContext) -> 'ReviewComponents':
            if parent is not None:
                compId = f'{ctx.state.component} component(s) of the {parent.name}.'
            else:
                compId = f'{ctx.state.component} component(s)'
                
            print(f"GetComponents...{compId}")
            if ctx.state.suggested_changes.has_updates:
                print(f"Updating list with recommendations: {ctx.state.suggested_changes.recommendations}")
                
            system_prompt = f"""
                You are an expert in manufacturing and product design.

                Given the name of a single component, {compId}, list only the first-level items that appear in its bill of materials (BOM). Do not list any sub-parts of those items.

                CHECKLIST
                • Return only items directly consumed in the manufacture or assembly of <COMPONENT_NAME>.
                • Exclude sub-components of the items you name.
                • A thing cannot be made of itself.
                • Avoid functionally duplicate items.

                For each item provide:
                – name
                – type  ∈  [Component | RawMaterial | ManufacturingEquipment | ManufacturingSupplies]
                – brief description (≤ 15 words)
                – 6-digit HS code (use 000000 if unknown)

                TYPE DEFINITIONS
                Component ................ assembled part that remains in the product  
                RawMaterial .............. direct material embedded in the part  
                ManufacturingSupplies .... consumables not in final product (lubricant, flux)  
                ManufacturingEquipment ... machinery/tools used to build the part  

            """
            agent = Agent(model=default_model, result_type=list[Component],system_prompt=system_prompt,retries=5)
            try: 
                if not ctx.state.suggested_changes.has_updates:
                    r = await agent.run(f"Please generate a list of the components required to assemble '{ctx.state.component}'. ",message_history=ctx.state.constructor_history,model_settings={'temperature': .5})

                    if isinstance(r.data,list):
                        ctx.state.components = r.data
                else:
                    prompt = f"""
                        The current set of componets is  {','.join([component.name for component in ctx.state.components])}.
                        {ctx.state.suggested_changes.recommendations if ctx.state.suggested_changes.recommendations else ""}
                        Please update the list of components to reflect the changes.
                        Return the updated list of components.  
                    """
                    r = await agent.run(prompt, model_settings={'temperature': .5})
                    ctx.state.constructor_history += r.new_messages()
                    if isinstance(r.data,list):
                        ctx.state.components = r.data
                    
            except Exception as err:
                print(f"Error in GetComponents: {err}")
        
            return ReviewComponents()

    @dataclass
    class ReviewComponents(BaseNode[ComponentAssemblyState]):
        async def run(self, ctx: GraphRunContext) -> Union['GetComponents','End']:
            if ctx.state.reviews < ctx.state.options.max_component_reviews:
                print(f"({ctx.state.reviews+1} of {ctx.state.options.max_component_reviews}) Reviewing components: {','.join([component.name for component in ctx.state.components])}")
                ctx.state.reviews += 1
                
                if parent is not None:
                    compId = f'{ctx.state.component} component(s) of the {parent.name}.'
                else:
                    compId = f'{ctx.state.component} components(s)'
                
                system_prompt = f"""
                    You are an expert in manufacturing and product design.
                    Your task is to review the components used to manufacture {compId}
                    You must verify the components,raw materials, manufacturing equipment, and manufacturing supplies are used to manufacture or assemble the {compId}.
                    Ensure that no required components are missing.
                    DO NOT not include the subcomponents or raw materials of any components you identify.
                    The component type should be categorized as one of 'Component','RawMaterial','ManufacturingEquipment', or 'ManufacturingSupplies'.
                    Manufacturing Equipment ('ManufacturingEquipment') are the machines and tools used to build the component.
                    Manufacturing Supplies ('ManufacturingSupplies') are the materials used in the manufacturing process that do not end up in the final product.
                    Components are the individual parts that make up a product.
                    Raw Materials ('RawMaterial') are the basic, unprocessed or minimally processed substances that are used as inputs in the manufacturing or production of goods. 
                    They are the fundamental components from which finished products are made. Examples include minerals, metals, wood, oil, grain, plastic, and natural gas. 
                    Examples of raw materials include:
                        Mining-based: Metals like iron ore, nickel, and cobalt. 
                        Plant-based: Wood, resins, wheat, and corn. 
                        Animal-based: Milk and meat. 
                        Other: Petroleum products, plastic, and chemicals. 
                        
                    Raw materials can be categorized as direct or indirect. Direct raw materials are those that are directly incorporated into the finished product (e.g., the wood used to make furniture) and should be categorized as "RawMaterials".
                    Indirect raw materials are used in the production process but are not part of the final product (e.g., fuel for machinery) and should be categorized as "ManufacturingSupplies".
                    For example, 'steel frame' or 'copper wire' should be classified as components, not a raw material.
                    The hscode should be a valid 6 digit Harmonized System Code(HS Code) for the component.
                    Avoid duplicating components or raw materials both in name and in function.
                    For example, if the component is a car, you might return a list of components such as 'engine', 'transmission', 'wheels', 'brakes', 'suspension', 'body', 'interior', 'electronics', 'fuel system', 'exhaust system'.
                    Components MUST NOT be made of themselves (e.g. copper wire cannot be made of copper wire).
                    If there are any missing components or raw materials, or any components that are not directly used in to manufacture the component, or any incorrect HS Codes, or any duplicates, please provide a list of the changes required.
                    Respond with a SuggestedChanges object that contains the following fields:
                    - has_updates: boolean indicating if there are any updates to the component list    
                    - recommendations: string containing the recommendations for changes to the component list if there are any. This field must exist if has_updates is True.
                """
                agent = Agent(model=default_model, result_type=SuggestedChanges,system_prompt=system_prompt,retries=5)
                try: 
                    prompt = f"""
                        Please review the following list of components and identify any missing components or raw materials, andy components that are not directly used in to manufacture the components,  any incorrect HS Codes, or any duplicates.
                        Components: {','.join([component.name for component in ctx.state.components])}
                    """
                    r = await agent.run(prompt,message_history=ctx.state.reviewer_history,model_settings={'temperature': .7})
                    # print(f"Review result: {r.data}")
                    # if 'no changes required' not in r.data.lower():
                    # if r.data.lower() != 'no changes required':
                    ctx.state.reviewer_history += r.new_messages()
                    ctx.state.suggested_changes = r.data
                    if r.data.has_updates:
                        # print(f"Suggested changes: {r.data}")
                        ctx.state.suggested_changes = r.data
                        return GetComponents()
                        
                except Exception as err:
                    print(f"Error in ReviewComponents: {err}")
        
            return End({
                'description': ctx.state.description,
                'components': ctx.state.components
            })

    @dataclass
    class GetComponentDescription(BaseNode[ComponentAssemblyState]):
        async def run(self, ctx: GraphRunContext) -> 'GetComponents':
            print(f"Getting product description for {ctx.state.component}")
            system_prompt = f"""
                    You are an expert in manufacturing and product design.
            """
            agent = Agent(model=default_model, result_type=str,system_prompt=system_prompt,retries=5)
            result = await agent.run(f"Please provide a short description of the '{ctx.state.component}' component.",model_settings={'temperature': .1})
            print(f"Description: {result.data}")
            ctx.state.description = result.data
            return GetComponents()

    TaskGraph = Graph(nodes=(GetComponents,ReviewComponents,GetComponentDescription))
    state = ComponentAssemblyState(component,options=options)
    result = await TaskGraph.run(GetComponents(),state=state)
    print("GetComponentAssembly Result:")
    print(f"\n{result}")
    return result

    # def serialize_component_tree(root):
    #     nodes = []
    #     links = []

    #     def traverse(component):
    #         # Add the current component as a node
    #         nodes.append({
    #             "id": component.id,
    #             "name": component.name,
    #             "type": component.type,
    #         })
    #         # If the component has subcomponents, create links and traverse them
    #         if component.subcomponents:
    #             for child in component.subcomponents:
    #                 links.append({
    #                     "source": component.id,
    #                     "target": child.id
    #                 })
    #                 traverse(child)

    #     traverse(root)
    #     network = {"nodes": nodes, "edges": links}
    #     return network


async def main():
    product = 'Intel Core i9-9900K'
    print(f"Analyzing product: {product}")
    result= await get_component_network(product,options=MaterialNetworkGeneratorOptions(model_name="llama3.3",llm_api_url="http://udc-aj38-35:11434/v1",llm_api_key="none"))
    print("Graph Run Complete.")
    pprint.pp(result,indent=4)

            
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())