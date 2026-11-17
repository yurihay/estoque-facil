# Estoque Fácil 📦

MVP acadêmico de controle de estoque para pequenos comércios alimentícios de Carapicuíba, São Paulo. O projeto é uma aplicação web responsiva para cadastro de produtos, registro de entradas/saídas e identificação de estoque baixo ou validade próxima. Relaciona-se ao **ODS 12 — Consumo e Produção Responsáveis**, pela possibilidade de reduzir perdas por falta de acompanhamento das mercadorias.

> **Estado atual:** implementação inicial para estudo, testes e revisão. Não é um sistema pronto para uso comercial, produção ou armazenamento de dados reais de terceiros.

## Tecnologias e arquitetura

- **Padrão principal autorizado:** Python 3.12.
- **Framework:** Flask 3.x para rotas, formulários e templates HTML.
- **Interface:** HTML, CSS responsivo e templates Jinja, sem JavaScript obrigatório.
- **Banco de dados:** SQLite relacional, arquivo local na pasta ignorada pelo Git 'instance/'.
- **Segurança:** senhas com hash scrypt (Werkzeug), sessão com cookie HttpOnly e SameSite, token CSRF em formulários, queries parametrizadas, saída escapada automaticamente, permissões e limitação básica de tentativas de login.
- **Testes/CI:** pytest e GitHub Actions.

A aplicação adota uma **arquitetura monolítica em três camadas**:
1. **Apresentação** — templates em 'templates/' e estilos em 'static/'.
2. **Regras de negócio** — 'app.py': cadastro, validações, saldo, alertas, login e autorização.
3. **Persistência** — SQLite por conexão de requisição e tabelas definidas em 'schema.sql'.

O fluxo principal é: usuário autenticado → cadastro de produto → entrada/saída com validação → persistência da movimentação e do saldo na mesma transação → retorno no painel com alertas.

## Executar localmente (Windows PowerShell)

Requer Python 3.12 instalado.

1. Clone ou baixe o repositório:

   ```powershell
git clone https://github.com/yurihay/estoque-facil.git
cd estoque-facil
```

2. Crie o ambiente virtual e instale as dependências:

   ```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. Defina uma chave aleatória para assinar sessões (não publique essa chave):

   ```powershell
$env:SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
```

4. Prepare o banco e crie o usuário administrador. A senha será solicitada sem eco no terminal e precisa ter **pelo menos 12 caracteres**:

   ```powershell
python -m flask --app app:create_app init-db
python -m flask --app app:create_app create-user --username gerente --role admin
```

5. Inicie o servidor local:

   ```powershell
python -m flask --app app:create_app run
```

Acesse **http://127.0.0.1:5000**. O Flask executado assim é um servidor de desenvolvimento; **não o exponha à internet**.

No Linux/macOS, substitua o comando de criação do ambiente por 'python3.12 -m venv .venv' e a ativação por 'source .venv/bin/activate'. Use 'export SECRET_KEY=...' para definir a variável no seu terminal.

## Primeiros passos no sistema

1. Entre com o usuário administrador.
2. Em **Produtos**, crie um item com código, nome, estoque mínimo e validade opcional.
3. Em **Movimentações**, registre uma **entrada** (o saldo inicial do cadastro é sempre zero).
4. Registre uma **saída**; valores maiores que o saldo são rejeitados.
5. Confira o saldo e os alertas no **Painel**.

Usuários com papel 'operador' podem consultar e registrar movimentações, mas não criar ou editar produtos. Novos usuários são criados somente pelo comando CLI 'create-user'.

## Testes automatizados

```powershell
python -m pytest -q
```

Os testes utilizam um banco temporário e cobrem autenticação, CSRF, permissões, cadastro, saldo, alertas, entrada inválida e escape HTML. O workflow '.github/workflows/testes.yml' executa o pytest a cada push ou pull request.

## Arquivos

```text
app.py                     rotas, validações e regras de negócio
schema.sql                  esquema relacional com chaves e restrições
templates/base.html         navegação e estrutura semântica
templates/login.html        autenticação
templates/dashboard.html    painel e alertas
templates/products.html     cadastro/edição
templates/movements.html    entradas e saídas
static/site.css             identidade visual e responsividade
tests/test_app.py           testes automatizados
.github/workflows/testes.yml integração contínua
requirements.txt            dependências
.gitignore                  exclusão de banco, segredos e cache
```

## Limites e evolução planejada

- O SQLite é **local e embarcado**: não oferece sincronização automática entre computadores ou acesso remoto simultâneo. Para hospedagem com usuários remotos, é necessário configurar um servidor e persistência durável ou migrar para PostgreSQL.
- Há **uma data de validade por produto**, não gerenciamento de múltiplos lotes. Lotes diferentes serão uma evolução futura.
- Não há integração com PDV, emissão fiscal, recuperação de senha por email ou geração de relatórios avançados.
- O bloqueio básico de login não substitui proteção adicional contra abuso, observabilidade e mecanismos de recuperação de conta.
- HTTPS e cookie 'Secure' exigem configuração do ambiente de hospedagem ('COOKIE_SECURE=1'); não se deve usar dados reais sem revisão de segurança, backups, políticas de privacidade e testes adequados.
- A experiência prática ainda exige validação real de usabilidade com representante do público externo; **testes automatizados não substituem essa etapa**.

## Versionamento

A branch 'feat/mvp-flask-inicial' foi criada para um **Pull Request**, permitindo revisar o código, executar a integração contínua e registrar a evolução incremental do MVP. Consulte a aba **Actions** do GitHub para ver o resultado dos testes após o envio dos commits.
