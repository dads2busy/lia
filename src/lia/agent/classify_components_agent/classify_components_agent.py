from pydantic_ai import Agent
from dataclasses import dataclass
from pydantic import BaseModel
from typing import List, Optional
from lia.agent import load_agent_tool
from pydantic_ai.models.openai import OpenAIModel


class RawCompOutput(BaseModel):
    raw_materials: list[str]
    components: list[str]
    software: list[str]
    manufacturing_equipment: list[str]

class ClassifyComponentsAgent(Agent):
    """
        ClassifyComponentsAgent distinguishes between raw materials and components.
    """
    def __init__(self, model:OpenAIModel,name:str="ClassifyComponentsAgent",tools=[], result_type=RawCompOutput,retries:int=5):
        system_prompt = f"""
            Categorize the individual components into one of these categories: 'raw_materials', 'manufacturing_equipment', 'software', or 'components'. 
            Raw materials are:
                ABRASIVES
                ALUMINUM
                ANTIMONY
                ARSENIC
                ASBESTOS
                BARITE
                BAUXITE
                BERYLLIUM
                BISMUTH
                BORON
                BROMINE
                CADMIUM
                CEMENT
                CHROMIUM
                CLAYS
                COBALT
                COPPER
                DIAMOND
                DIATOMITE
                FELDSPAR
                FLUORSPAR
                GALLIUM
                GARNET 
                GEMSTONES
                GERMANIUM
                GOLD
                GRAPHITE
                GYPSUM
                HELIUM
                INDIUM
                IODINE
                IRON AND STEEL
                IRON ORE
                IRON OXIDE PIGMENTS
                KYANITE AND RELATED MINERALS
                LEAD
                LIME
                LITHIUM
                MAGNESIUM COMPOUNDS
                MAGNESIUM METAL
                MANGANESE
                MERCURY
                MICA (NATURAL)
                MOLYBDENUM
                NICKEL
                NIOBIUM
                NITROGEN 
                AMMONIA
                PEAT
                PERLITE
                PHOSPHATE ROCK
                PLATINUM-GROUP METALS
                POTASH
                PUMICE AND PUMICITE
                RARE EARTHS
                RHENIUM
                SALT
                SAND AND GRAVEL (INDUSTRIAL)
                SELENIUM
                SILICON
                SILVER
                SODA ASH
                STONE (DIMENSION)
                STRONTIUM
                SULFUR
                TALC
                TANTALUM
                TELLURIUM
                TIN
                TITANIUM
                TITANIUM DIOXIDE
                TITANIUM MINERAL CONCENTRATES
                TUNGSTEN
                VANADIUM
                VERMICULITE
                WOLLASTONITE
                ZEOLITES (NATURAL)
                ZINC
                ZIRCONIUM AND HAFNIUM
                
            Alternative names for the raw materials should be considered as the same raw material and converted to the name above.
            Manufacturing equipment is any equipment used in the manufacturing process.
            Software is any software used in the manufacturing process or in product itself.
            Components represent everything not in the prior categories.
            Return an object containing an array for each category.
            For any elemental raw materials, convert their name to the Element symbol.
            Respond with JSON.
        """
            
        super().__init__(model=model, name=name, system_prompt=system_prompt,
                         deps_type=None, result_type=result_type, tools=tools,retries=retries)
    