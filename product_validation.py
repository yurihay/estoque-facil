"""Validação independente dos campos do cadastro de produtos."""
import re
from datetime import date
from typing import Mapping


def validate_product_form(form: Mapping[str, str]) -> tuple[str, str, int, str | None]:
    """Normaliza e valida código, nome, estoque mínimo e validade."""
    sku = form.get("sku", "").strip().upper()
    name = form.get("name", "").strip()
    expiry = form.get("expiry_date", "").strip() or None
    if not re.fullmatch(r"[A-Z0-9._-]{2,32}", sku):
        raise ValueError("Código deve ter 2 a 32 letras, números, pontos ou hífens.")
    if not 2 <= len(name) <= 100:
        raise ValueError("Nome deve conter entre 2 e 100 caracteres.")
    try:
        minimum = int(form.get("min_qty", ""))
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

