from lia.util.url_to_markdown import fetch_url_as_markdown
from typing import List,Union
from pydantic import BaseModel
import hashlib
import json
import os

class ReferenceContent(BaseModel):
    """
        A structure to hold the content of a reference URL.
        - 'url' - The URL of the reference
        - 'content' - The content of the reference as markdown
    """
    url: str
    content: str|None = None
    error: str | None = None
    
class ReferenceContentOptions(BaseModel):
    """
        Options for content fetcher
    """
    reference_cache_folder: str|None = None
    save: bool = False
    refresh: bool = False
    
async def fetch_references(urls=list[str],options:Union[ReferenceContentOptions|None]=None) -> list[ReferenceContent]:
    """
        Fetch the content for a list of urls, return a list of ReferenceContent objects.
    """
    out=[]
    for url in urls:
        reference_content = await fetch_content(url,options)    

    return out

def strip_url_fragment(url: str) -> str:
    return url.split('#', 1)[0]

async def fetch_content(url: str,options:Union[ReferenceContentOptions|None]=None) -> ReferenceContent:
    """
    Fetch the content of a URL and return it as a ReferenceContent object.
    If the URL cannot be fetched, return an empty content with an error message.
    """
    
    if options is None:
        options = ReferenceContentOptions()
    
    url = strip_url_fragment(url)  # Strip any URL fragments
    
    filename = hashlib.md5(url.encode('utf-8')).hexdigest()
    # print(f"Options: {options}")
    try:
        if not options.refresh and options.reference_cache_folder is not None:
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
        else:
            print(f"Fetching content for {url} (not cached or refresh requested)")
            
        content = await fetch_url_as_markdown(url, max_redirects=5, timeout=20.0)
        # print(f"content: {content}")
        reference_content=ReferenceContent(url=url, content=content)
        
                
    except Exception as e:
        print(f"❌ Error in fetch_content() from URL {url}: {e}")
        reference_content=ReferenceContent(url=url,error=f"Error fetching URL: {e}")

    if options.reference_cache_folder and options.save:
        await cache_content(reference_content,options)
        
    return reference_content

async def cache_content(reference_content:ReferenceContent,options:ReferenceContent):
    if options.reference_cache_folder is not None:
        os.makedirs(options.reference_cache_folder,mode=777,exist_ok=True)
        filename = hashlib.md5(reference_content.url.encode('utf-8')).hexdigest()
        cache_file = f"{options.reference_cache_folder}/{filename}.json"
            
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(reference_content.model_dump_json())
            print(f"✅ Cached content for {reference_content.url} at {cache_file}")