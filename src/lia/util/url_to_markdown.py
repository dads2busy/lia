#!/usr/bin/env python3
import typer
from typing import List,Dict,Any,Union
from pathlib import Path
from crawl4ai import AsyncWebCrawler,BrowserConfig, CrawlerRunConfig, CacheMode

app = typer.Typer(help="Fetch a URL or file and output its content as Markdown using crawl4ai.")

async def fetch_url_as_markdown(url: str, max_redirects: int = 5, timeout: float = 60.0) -> str:
    """
    Fetch a URL or local file and return its content as Markdown using crawl4ai.
    """

    async with AsyncWebCrawler(max_redirects=5, use_user_agent=True) as crawler:
        run_conf = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=15,
            # process_iframes=True,
            excluded_tags=["nav", "footer","header","form","input","button"],
            exclude_external_images=True,
            only_text=True,
            page_timeout=timeout * 1000
        )
        
        out = await crawler.arun(url=url,config=run_conf)
        if not out.success or out.status_code >= 300:
            raise Exception(f"Failed to fetch URL: Success: {out.success}, Status Code: {out.status_code}, Error: {out.error_message}")
        
        return out.markdown
    
    
@app.command()
def main(
    url: str = typer.Argument(..., help="URL or local file path to fetch and convert to Markdown."),
    max_redirects: int = typer.Option(5, "--max-redirects", "-r", help="Maximum number of redirects to follow."),
    timeout: float = typer.Option(10.0, "--timeout", "-t", help="Request timeout in seconds."),
):
    """
    CLI entry point to fetch a URL or file and print Markdown output.
    """
    try:
        markdown = fetch_url_as_markdown(url, max_redirects=max_redirects, timeout=timeout)
        typer.echo(markdown)
    except crawl4ai.FetchError as e:
        typer.secho(f"Fetch error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except FileNotFoundError as e:
        typer.secho(f"File error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Unexpected error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
