import typer

from cli.commands import account, bootstrap

app = typer.Typer(help="Admin/dev CLI for doc-pipeline.")
app.add_typer(account.app, name="account")
app.command("setup")(bootstrap.setup)

if __name__ == "__main__":
    app()
