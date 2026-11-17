"""Estoque Fácil: MVP para pequenos comércios alimentícios."""
import getpass
import os
import re
import secrets
import sqlite3
import time
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

import click
from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=str(Path(app.instance_path) / "estoque.sqlite3"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"], timeout=5)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.cli.command("init-db")
    def init_db_command():
        """Cria as tabelas, preservando dados existentes."""
        with app.open_resource("schema.sql") as schema:
            db().executescript(schema.read().decode("utf-8"))
        click.echo("Banco de dados inicializado.")

    @app.cli.command("create-user")
    @click.option("--username", prompt="Usuário")
    @click.option(
        "--role", type=click.Choice(["admin", "operador"]),
        default="admin", show_default=True
    )
    def create_user_command(username, role):
        """Cria usuário com senha digitada de forma reservada."""
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
            raise click.ClickException("Usuário deve ter 3-40 caracteres simples.")
        password = getpass.getpass("Senha (mínimo 12 caracteres): ")
        confirm = getpass.getpass("Confirme a senha: ")
        if password != confirm or len(password) < 12:
            raise click.ClickException("Senhas diferentes ou menores que 12 caracteres.")
        try:
            with db():
                db().execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password, method="scrypt"), role),
                )
        except sqlite3.IntegrityError as exc:
            raise click.ClickException("Nome de usuário já cadastrado.") from exc
        click.echo("Usuário criado com sucesso.")

    @app.context_processor
    def shared_template_values():
        def csrf_token():
            if "_csrf_token" not in session:
                session["_csrf_token"] = secrets.token_urlsafe(32)
            return session["_csrf_token"]
        return {"csrf_token": csrf_token, "current_user": g.get("user")}

    @app.before_request
    def load_user_and_check_csrf():
        user_id = session.get("user_id")
        g.user = (
            db().execute(
                "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if user_id else None
        )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("_csrf_token", "")
            received = request.form.get("_csrf_token", "")
            if not expected or not secrets.compare_digest(expected, received):
                abort(400, "Requisição inválida. Recarregue a página.")

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; img-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'"
        )
        return response

    def login_required(view):
        @wraps(view)
        def wrapped(**kwargs):
            if g.user is None:
                return redirect(url_for("login"))
            return view(**kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped(**kwargs):
            if g.user["role"] != "admin":
                abort(403)
            return view(**kwargs)
        return wrapped

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            record = db().execute(
                "SELECT failures, blocked_until FROM login_attempts WHERE username = ?",
                (username,),
            ).fetchone()
            now = int(time.time())
            if record and record["blocked_until"] > now:
                flash("Aguarde alguns minutos antes de tentar novamente.", "error")
            else:
                user = db().execute(
                    "SELECT id, password_hash FROM users WHERE username = ?",
                    (username,),
                ).fetchone()
                if user and check_password_hash(user["password_hash"], password):
                    with db():
                        db().execute(
                            "DELETE FROM login_attempts WHERE username = ?", (username,)
                        )
                    session.clear()
                    session["user_id"] = user["id"]
                    session.permanent = True
                    return redirect(url_for("dashboard"))
                failures = (record["failures"] if record else 0) + 1
                blocked_until = now + 300 if failures >= 5 else 0
                with db():
                    db().execute(
                        "INSERT INTO login_attempts(username, failures, blocked_until) "
                        "VALUES (?, ?, ?) ON CONFLICT(username) DO UPDATE SET "
                        "failures = excluded.failures, blocked_until = excluded.blocked_until",
                        (username, failures, blocked_until),
                    )
                flash("Usuário ou senha inválidos.", "error")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        products = db().execute(
            "SELECT * FROM products ORDER BY name COLLATE NOCASE"
        ).fetchall()
        alerts = []
        today = date.today()
        for item in products:
            if item["quantity"] <= item["min_qty"]:
                alerts.append({
                    "product": item["name"], "message": "Estoque baixo",
                    "detail": f'{item["quantity"]} unidade(s) disponível(is)'
                })
            if item["expiry_date"]:
                expiry = date.fromisoformat(item["expiry_date"])
                if expiry < today:
                    status = "Validade vencida"
                elif expiry <= today + timedelta(days=7):
                    status = "Vence em até 7 dias"
                else:
                    status = None
                if status:
                    alerts.append({
                        "product": item["name"], "message": status,
                        "detail": expiry.strftime("%d/%m/%Y"),
                    })
        return render_template(
            "dashboard.html", products=products, alerts=alerts,
            total_products=len(products),
            total_units=sum(p["quantity"] for p in products),
        )

    def validate_product_form():
        sku = request.form.get("sku", "").strip().upper()
        name = request.form.get("name", "").strip()
        expiry = request.form.get("expiry_date", "").strip() or None
        if not re.fullmatch(r"[A-Z0-9._-]{2,32}", sku):
            raise ValueError("Código deve ter 2 a 32 letras, números, pontos ou hífens.")
        if not 2 <= len(name) <= 100:
            raise ValueError("Nome deve conter entre 2 e 100 caracteres.")
        try:
            minimum = int(request.form.get("min_qty", ""))
        except ValueError as exc:
            raise ValueError("Estoque mínimo deve ser um número inteiro.") from exc
        if not 0 <= minimum <= 1000000:
            raise ValueError("Estoque mínimo deve estar entre 0 e 1.000.000.")
        if expiry:
            try:
                date.fromisoformat(expiry)
            except ValueError as exc:
                raise ValueError("Data de validade inválida.") from exc
        return sku, name, minimum, expiry

    @app.route("/products", methods=["GET", "POST"])
    @login_required
    def products():
        if request.method == "POST":
            if g.user["role"] != "admin":
                abort(403)
            try:
                sku, name, minimum, expiry = validate_product_form()
                with db():
                    db().execute(
                        "INSERT INTO products(sku, name, min_qty, expiry_date) "
                        "VALUES (?, ?, ?, ?)", (sku, name, minimum, expiry)
                    )
                flash("Produto cadastrado. Registre uma entrada para adicionar unidades.", "success")
                return redirect(url_for("products"))
            except ValueError as exc:
                flash(str(exc), "error")
            except sqlite3.IntegrityError:
                flash("Este código de produto já está cadastrado.", "error")
        items = db().execute(
            "SELECT * FROM products ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return render_template("products.html", products=items, editing=None)

    @app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
    @admin_required
    def edit_product(product_id):
        item = db().execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if item is None:
            abort(404)
        if request.method == "POST":
            try:
                sku, name, minimum, expiry = validate_product_form()
                if sku != item["sku"]:
                    raise ValueError("Código do produto não pode ser alterado.")
                with db():
                    db().execute(
                        "UPDATE products SET name = ?, min_qty = ?, expiry_date = ? "
                        "WHERE id = ?", (name, minimum, expiry, product_id)
                    )
                flash("Produto atualizado.", "success")
                return redirect(url_for("products"))
            except ValueError as exc:
                flash(str(exc), "error")
        items = db().execute(
            "SELECT * FROM products ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return render_template("products.html", products=items, editing=item)

    @app.route("/movements", methods=["GET", "POST"])
    @login_required
    def movements():
        if request.method == "POST":
            try:
                product_id = int(request.form.get("product_id", ""))
                amount = int(request.form.get("amount", ""))
                kind = request.form.get("kind", "")
                if amount <= 0 or amount > 1000000 or kind not in {"entrada", "saida"}:
                    raise ValueError("Informe tipo e quantidade válidos.")
                connection = db()
                connection.execute("BEGIN IMMEDIATE")
                try:
                    if kind == "saida":
                        changed = connection.execute(
                            "UPDATE products SET quantity = quantity - ? "
                            "WHERE id = ? AND quantity >= ?",
                            (amount, product_id, amount),
                        ).rowcount
                    else:
                        changed = connection.execute(
                            "UPDATE products SET quantity = quantity + ? WHERE id = ?",
                            (amount, product_id),
                        ).rowcount
                    if changed != 1:
                        raise ValueError("Produto inexistente ou saldo insuficiente.")
                    connection.execute(
                        "INSERT INTO movements(product_id, user_id, kind, amount) "
                        "VALUES (?, ?, ?, ?)",
                        (product_id, g.user["id"], kind, amount),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                flash("Movimentação registrada com sucesso.", "success")
                return redirect(url_for("movements"))
            except (ValueError, TypeError) as exc:
                flash(str(exc) or "Valores inválidos.", "error")
        items = db().execute(
            "SELECT * FROM products ORDER BY name COLLATE NOCASE"
        ).fetchall()
        history = db().execute(
            "SELECT m.*, p.name AS product_name, u.username "
            "FROM movements m JOIN products p ON p.id = m.product_id "
            "JOIN users u ON u.id = m.user_id "
            "ORDER BY m.id DESC LIMIT 50"
        ).fetchall()
        return render_template("movements.html", products=items, history=history)

    return app


if __name__ == "__main__":
    create_app().run()
