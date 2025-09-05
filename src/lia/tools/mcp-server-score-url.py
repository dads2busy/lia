import asyncio
import httpx
from bs4 import BeautifulSoup
import markdownify
import typer
import sys
from typing import Annotated, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel,OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from fastmcp import FastMCP

class URLQualityRequest(BaseModel):
    url: str


class URLQualityResponse(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reason: str


def extract_text_from_url(url: str) -> Optional[str]:
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True)
        if response.status_code != 200 or 'text/html' not in response.headers.get('content-type', ''):
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        main_content = soup.body or soup
        text = markdownify.markdownify(str(main_content), heading_style="ATX")
        return text.strip() if len(text.strip()) > 100 else None
    except Exception:
        return None


def create_mcp(model: str, llm_api_url: Optional[str], llm_api_key: str) -> FastMCP:
    provider = OpenAIProvider(base_url=llm_api_url,api_key=llm_api_key)
    default_model = OpenAIModel(model,provider=provider)
    agent = Agent(name="URL Quality Evaluator", result_type=URLQualityResponse,model=default_model)
    mcp = FastMCP(name="url-quality-evaluator", version="0.1")

    @mcp.tool(name="evaluate_url_quality", description="Evaluate the trustworthiness of a URL based on its url domain and content.")
    async def evaluate_url_quality(request: URLQualityRequest, ctx) -> URLQualityResponse:
        print(f"ctx: {ctx}", file=sys.stderr)
        content = extract_text_from_url(request.url)

        if not content:
            return URLQualityResponse(score=0.0, reason="URL not retrievable, spammy, or no substantial content.")

        prompt = f"""You are a trust evaluator for online content. You are reviewing the following URL:
{request.url}

Evaluate its overall trustworthiness. 
Do not visit or describe the page, the content is embedded below. 

Use this scale:

- 1.0 : Highly authoritative (e.g., peer-reviewed papers, government reports, scientific publishers)
- 0.8 : Supplier datasheets, technical industry white papers
- 0.6 : Educational sources (Wikipedia, LibreTexts, university-hosted material)
- 0.4 : Commercial websites with unclear authorship
- 0.2 : Blogs, message boards, social media
- 0.0 : Spam, broken pages, empty content

Content:
---
{content[:4000]}
---

Respond with a JSON object in this format:
{"score": float, "reason": "short justification"}

"""
        r = await agent.run(prompt, model_settings={'temperature': 0})
        print("r.output: ", r.output, file=sys.stderr)
        return r.output

    return mcp


app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def run_server(
    model: Annotated[str, typer.Option("--model", "-m", help="Default Base Model Name")] = "llama3.3",
    llm_api_url: Annotated[Optional[str], typer.Option("--llm-api-url", "-u", help="URL to LLM API")] = None,
    llm_api_key: Annotated[str, typer.Option("--llm-api-key", "-k", help="API Key if needed for LLM")] = "None",
):
    mcp = create_mcp(model, llm_api_url, llm_api_key)
    asyncio.run(mcp.run(transport='stdio'))


if __name__ == "__main__":
    app()
