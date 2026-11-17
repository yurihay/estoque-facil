"""Testes do MVP Estoque Fácil: autenticação, estoque e segurança."""
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "chave-local-exclusiva-para-testes",
        "DATABASE": str(tmp_path / "teste.sqlite3"),
    })
    with sqlite3.connect(application.config["DATABASE"]) as connection:
        connection.executescript(
            Path(__file__).resolve().parents[1].joinpath("schema.sql").read_text(
                encoding="utf-8"
            )
        )
        connection.execute(
            "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
            ("gerente", generate_password_hash("senha-de-teste-123"), "admin"),
        )
        connection.execute(
            "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
            ("operador", generate_password_hash("senha-de-operador-123"), "operador"),
        )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    with client.session_transaction() as sess:
        return sess["_csrf_token"]


def login(client, username="gerente", password="senha-de-teste-123"):
    client.get("/login")
    response = client.post(
        "/login",
        data={
            "_csrf_token": csrf(client),
            "username": username,
            "password": password,
        },
        follow_redirects=True,
    )
    return response


def post(client, path, **fields):
    return client.post(
        path, data={"_csrf_token": csrf(client), **fields}, follow_redirects=True
    )


def create_product(client, sku="ARROZ01", name="Arroz 5 kg", expiry=None):
    return post(
        client, "/products", sku=sku, name=name,
        min_qty="5", expiry_date=expiry or ""
    )


def test_pages_require_authentication(client):
    assert client.get("/").status_code == 302
    assert client.get("/products").status_code == 302
    assert client.get("/movements").status_code == 302


def test_login_and_logout(client):
    assert b"Painel de estoque" in login(client).data
    # A sessão da aplicação se encerra com uma requisição POST protegida.
    assert post(client, "/logout").status_code == 200
    assert b"Entrar no Estoque" in client.get("/login").data
    assert client.get("/").status_code == 302


def test_csrf_required(client):
    client.get("/login")
    assert client.post("/login", data={
        "username": "gerente", "password": "senha-de-teste-123"
    }).status_code == 400
    login(client)
    assert client.post("/products", data={
        "sku": "CAFE01", "name": "Café", "min_qty": 5
    }).status_code == 400


def test_product_stock_and_insufficient_balance(client, app):
    login(client)
    assert b"Produto cadastrado" in create_product(client).data
    assert b"Movimenta" in post(
        client, "/movements", product_id="1", kind="entrada", amount="10"
    ).data
    post(client, "/movements", product_id="1", kind="saida", amount="3")
    result = post(client, "/movements", product_id="1", kind="saida", amount="50")
    assert "saldo insuficiente".encode() in result.data
    with sqlite3.connect(app.config["DATABASE"]) as db:
        qty = db.execute("SELECT quantity FROM products WHERE id = 1").fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM movements").fetchone()[0]
    assert qty == 7
    assert count == 2


def test_duplicate_sku_rejected(client):
    login(client)
    create_product(client)
    assert b"cadastrado" in create_product(client).data


def test_operator_cannot_create_or_edit_product(client):
    assert b"Painel de estoque" in login(
        client, "operador", "senha-de-operador-123"
    ).data
    assert post(client, "/products", sku="AAA", name="Produto", min_qty="1").status_code == 403
    assert client.get("/products/1/edit").status_code == 403


def test_expiry_and_low_stock_alerts(client):
    login(client)
    soon = (date.today() + timedelta(days=4)).isoformat()
    create_product(client, expiry=soon)
    page = client.get("/")
    assert b"Estoque baixo" in page.data
    assert b"Vence em at" in page.data


def test_output_is_escaped_to_prevent_xss(client):
    login(client)
    create_product(client, name="<script>alert(1)</script>")
    html = client.get("/products").data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert b"<script>alert(1)</script>" not in html


def test_login_blocks_repeated_failures(client):
    client.get("/login")
    for _ in range(5):
        post(client, "/login", username="gerente", password="senha-errada")
    response = post(
        client, "/login", username="gerente", password="senha-de-teste-123"
    )
    assert b"Aguarde alguns minutos" in response.data


def test_accessible_labels_and_navigation(client):
    login(client)
    page = client.get("/products").data
    assert b'for="name"' in page
    assert b'for="expiry_date"' in page
    assert b'Ir para o conte' in page
    assert b'aria-current="page"' in page
