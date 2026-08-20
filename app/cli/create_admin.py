"""
create_admin CLI command.

Usage:
    python -m app.cli.create_admin --email admin@yourdomain.com --password 'YourStr0ngP@ss!'

Or via the clienthunter CLI (M6):
    clienthunter create-admin --email admin@yourdomain.com

Creates the first admin user or promotes an existing user to admin.
Safe to run multiple times (idempotent).
"""
from __future__ import annotations

import sys
import getpass

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., "--email", "-e", help="Admin email address"),
    password: str = typer.Option(
        None, "--password", "-p",
        help="Password (will prompt if omitted)",
    ),
    promote_only: bool = typer.Option(
        False, "--promote-only",
        help="Promote existing user to admin without changing password",
    ),
) -> None:
    """
    Create the first admin user or promote an existing user to admin.

    Safe to run multiple times. If the user already exists:
      - Without --promote-only: updates the password and sets is_admin=True
      - With --promote-only: only sets is_admin=True
    """
    if not password and not promote_only:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            console.print("[red]Passwords do not match.[/red]")
            raise typer.Exit(code=1)

    try:
        from app.core.database import SessionLocal
        from app.models.user import User
        from app.services.auth import hash_password

        # Hash with THE APPLICATION'S hasher, not a second one.
        #
        # This used to build its own passlib CryptContext(schemes=["bcrypt"]),
        # while app/services/auth.py hashes with pbkdf2_sha256 and
        # verify_password() parses that exact "pbkdf2_sha256$iters$salt$digest"
        # format. A bcrypt hash does not parse, so verify_password returned
        # False and an admin created by this CLI could NEVER log in - and this
        # CLI is the documented way to create the first admin on a fresh
        # deployment. (It was also outright broken here: passlib 1.7.4 reads
        # bcrypt.__about__, removed in bcrypt 4.1+, which surfaced as the
        # bogus "password cannot be longer than 72 bytes".)
        db = SessionLocal()

        try:
            existing_user = db.query(User).filter_by(email=email).first()

            if existing_user:
                existing_user.is_admin = True
                if not promote_only and password:
                    existing_user.password_hash = hash_password(password)
                db.commit()
                action = "promoted to admin" if promote_only else "updated + promoted to admin"
                console.print(f"[green]OK: User {email} {action}.[/green]")
            else:
                if not password:
                    console.print("[red]Password required when creating a new admin user.[/red]")
                    raise typer.Exit(code=1)
                new_user = User(
                    email=email,
                    password_hash=hash_password(password),
                    is_admin=True,
                )
                db.add(new_user)
                db.commit()
                console.print(f"[green]OK: Admin user created: {email}[/green]")

            # Print a summary table
            table = Table(title="Admin User Created")
            table.add_column("Field")
            table.add_column("Value")
            table.add_row("Email", email)
            table.add_row("Is Admin", "Yes")
            table.add_row("Action", "Created" if not existing_user else "Updated")
            console.print(table)

        finally:
            db.close()

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("list-admins")
def list_admins() -> None:
    """List all admin users."""
    try:
        from app.core.database import SessionLocal
        from app.models.user import User

        db = SessionLocal()
        try:
            admins = db.query(User).filter_by(is_admin=True).all()

            table = Table(title=f"Admin Users ({len(admins)} total)")
            table.add_column("ID")
            table.add_column("Email")
            table.add_column("Created At")
            for admin in admins:
                table.add_row(
                    str(admin.id)[:8] + "...",
                    admin.email,
                    str(getattr(admin, "created_at", "")).split(".")[0],
                )
            console.print(table)
        finally:
            db.close()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
