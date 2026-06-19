"""
Learning loop commands.

Layer: Adapter
"""

import typer

from src.adapters.cli.learn_opening_commands import grade, prompt, snapshot, track, tune

learn_app = typer.Typer(
    name="learn",
    help="Learning loop — snapshot, track, grade, prompt, and tune opening sessions.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

learn_app.command("snapshot")(snapshot)
learn_app.command("track")(track)
learn_app.command("grade")(grade)
learn_app.command("prompt")(prompt)
learn_app.command("tune")(tune)
