import typer

from cli.commands import account, setup

app = typer.Typer(help="Admin/dev CLI for doc-pipeline.")
app.add_typer(account.app, name="account")
app.command("setup")(setup.setup)
app.command("migrate")(setup.migrate)

if __name__ == "__main__":
    app()
