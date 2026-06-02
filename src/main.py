import asyncio
import typer
from rich.console import Console
from src.agents.basic_agent import BasicAgent
from src.utils.ollama_client import OllamaConfig, OllamaClient
from src.config import settings

app = typer.Typer()
console = Console()


@app.command()
def chat():
    """Chat interativo com o agente."""
    ollama_config = OllamaConfig(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=settings.ollama_temperature,
        max_tokens=settings.ollama_max_tokens
    )
    
    try:
        agent = BasicAgent(ollama_config)
        console.print("[green]✓ Agente conectado ao Ollama[/green]")
    except Exception as e:
        console.print(f"[red]✗ Erro ao conectar: {str(e)}[/red]")
        raise
    
    console.print("\n[cyan]Chat com Second Brain[/cyan]")
    console.print("Digite 'sair' para encerrar\n")
    
    while True:
        try:
            user_input = console.input("[bold]Você:[/bold] ")
            
            if user_input.lower() in ["sair", "exit"]:
                console.print("[yellow]Até logo![/yellow]")
                break
            
            if not user_input.strip():
                continue
            
            console.print("[dim]Pensando...[/dim]")
            response = asyncio.run(agent.process_message(user_input))
            console.print(f"[cyan]Agente:[/cyan] {response}\n")
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrompido.[/yellow]")
            break


@app.command()
def test_ollama():
    """Testa conexão com Ollama."""
    config = OllamaConfig(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model
    )
    client = OllamaClient(config)
    
    if client.health_check():
        console.print("[green]✓ Ollama está rodando[/green]")
        # Test simple generation
        response = client.generate("Responda em uma palavra: Como você está?")
        console.print(f"[cyan]Resposta de teste:[/cyan] {response}")
    else:
        console.print("[red]✗ Ollama não está acessível[/red]")


if __name__ == "__main__":
    app()
