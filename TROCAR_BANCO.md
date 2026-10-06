# Trocar o NOOB pelo banco original

O `NOOB` é uma cópia. O telecheck- e o SACI que estão rodando hoje apontam para essa cópia. Este guia troca os dois para o banco de origem (a "mãe" do `NOOB`) e diz o que alterar quando o executável vier de outro código-fonte do SACI.

Os dois têm de apontar para **o mesmo** banco. A liberação gravada pelo telecheck- fica em `dbo.LIBERACAO_WHATSAPP`. O SACI grava o cliente em `dbo.CLIENTE`. Se um falar com a mãe e o outro com o `NOOB`, o código aprovado não encontra o cadastro.

Não coloque senha neste arquivo nem no git. A senha do telecheck- fica só em `db/config.env`. A do SACI fica só em `C:\Arquivos Saci\conexao.udl`.

## Onde cada um lê o banco hoje

| Quem | Arquivo | O que está valendo |
| --- | --- | --- |
| telecheck- | `db/config.env`, chave `DB_ODBC_CONNECTION_STRING` | `SERVER=server-sz2;DATABASE=NOOB` |
| SACI (o exe) | `C:\Arquivos Saci\conexao.udl` | `Data Source=server-sz2;Initial Catalog=NOOB` |
| Código Delphi | `saci/UDM.dfm` | `FILE NAME=C:\Arquivos Saci\conexao.udl` |

O Python não tem o nome `NOOB` no código. Trocar o telecheck- é editar o `config.env` e reiniciar o processo. O Delphi também não escolhe o banco na maioria das units: o exe abre o `.udl` na hora em que sobe.

## 1. Descobrir o nome da mãe

No SSMS, conecte em `server-sz2` e rode:

```sql
SELECT name, create_date
FROM sys.databases
WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')
ORDER BY name;
```

O `NOOB` aparece na lista. A mãe é o outro banco do SACI, aquele de onde o `NOOB` foi copiado. Anote o nome exato, com a mesma maiúscula e minúscula. Daqui em diante ele se chama `NOME_DA_MAE`.

Confira que é o banco certo antes de escrever nele:

```sql
SELECT DB_NAME() AS banco, COUNT(*) AS clientes
FROM NOME_DA_MAE.dbo.CLIENTE;
```

Troque `NOME_DA_MAE` pelo nome real. O número de clientes da mãe e o do `NOOB` não precisam ser iguais: a cópia pode estar defasada.

## 2. Preparar a mãe para o telecheck-

A tabela `LIBERACAO_WHATSAPP` foi criada no `NOOB` pelo `db/schema.sql`. Copiar o `NOOB` a partir da mãe **não** leva essa tabela de volta para a mãe. Rode o script na mãe, uma vez, como `sysdba`:

```text
sqlcmd -S server-sz2 -U sysdba -d NOME_DA_MAE -i db\schema.sql
```

O script só cria `dbo.LIBERACAO_WHATSAPP` se ela ainda não existir. Não altera `CLIENTE`.

O login `telecheck_app` existe no servidor, mas o usuário dele foi criado **dentro** do `NOOB`. No outro banco ele não existe, e a connection string com `DATABASE=NOME_DA_MAE` falha. Rode o mesmo script de permissão, agora com `-d NOME_DA_MAE`:

```text
sqlcmd -S server-sz2 -U sysdba -d NOME_DA_MAE -i db\usuario_restrito.sql -v SENHA="a-senha-que-ja-esta-no-config.env"
```

Isso reaproveita o login, cria o usuário na mãe e dá `SELECT`, `INSERT` e `UPDATE` só em `dbo.LIBERACAO_WHATSAPP`. Também muda o banco padrão do login para a mãe. O `DATABASE=` da connection string continua mandando; o padrão só importa se um dia a string for aberta sem `DATABASE`.

Confira:

```sql
USE NOME_DA_MAE;
SELECT COUNT(*) FROM dbo.LIBERACAO_WHATSAPP;
EXECUTE AS USER = 'telecheck_app';
SELECT TOP 1 LIB_ID FROM dbo.LIBERACAO_WHATSAPP;
REVERT;
```

A primeira consulta pode devolver 0. A segunda não pode devolver "permissão negada".

## 3. Apontar o telecheck- para a mãe

Em `db/config.env`, na linha `DB_ODBC_CONNECTION_STRING`, troque só o nome do banco:

```text
DATABASE=NOOB
```

por:

```text
DATABASE=NOME_DA_MAE
```

Deixe `SERVER=server-sz2`, o driver, o `UID=telecheck_app` e o `PWD` como estão. Esse arquivo não vai para o git.

Reinicie o processo do telecheck- (o `uvicorn`). A string é lida na subida. Sem reiniciar, os pedidos novos continuam caindo no `NOOB`.

Teste com um pedido de liberação de mentira e confira em qual banco a linha nasceu:

```sql
SELECT LIB_ID, LIB_PHONE, LIB_STATUS, LIB_CRIADO_EM
FROM NOME_DA_MAE.dbo.LIBERACAO_WHATSAPP
ORDER BY LIB_CRIADO_EM DESC;
```

A linha nova tem de aparecer aqui, e não em `NOOB.dbo.LIBERACAO_WHATSAPP`.

## 4. Apontar o SACI que já está instalado

O exe lê `C:\Arquivos Saci\conexao.udl`. Abra esse arquivo num editor de texto. A linha útil é parecida com:

```text
Provider=SQLOLEDB.1;Password=...;User ID=sysdba;Initial Catalog=NOOB;Data Source=server-sz2
```

Troque `Initial Catalog=NOOB` por `Initial Catalog=NOME_DA_MAE`. Não mude `Data Source`, usuário nem senha. Feche o SACI por completo e abra de novo: conexão já aberta não relê o `.udl`.

Esse `.udl` é compartilhado. Qualquer SACI nesta máquina que use `C:\Arquivos Saci\conexao.udl` passa a gravar na mãe no mesmo instante, inclusive o exe de produção. Se a ideia for só experimentar, não edite esse arquivo. Use o caminho da seção 5, com um `.udl` separado.

Antes de deixar a operadora cadastrar, confira na mãe as colunas que o fonte atual grava e que a cópia pode ter ganhado depois:

```sql
SELECT COLUMN_NAME
FROM NOME_DA_MAE.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'CLIENTE'
  AND COLUMN_NAME IN ('CLI_WHATSAPP', 'CLI_FONE_ADICIONAL');
```

`CLI_WHATSAPP` já existe no SACI original. `CLI_FONE_ADICIONAL` foi acrescentada no fonte novo (`uCadastrarCliFor.pas` e `uCadCliFor.pas`). Se a segunda não aparecer, o INSERT do fonte novo quebra na mãe. Crie a coluna na mãe com o mesmo tipo que ela tem no `NOOB` antes de abrir esse exe contra a mãe.

O endereço da API não muda com o banco. Continua em `C:\Arquivos Saci\conf.ini`:

```ini
[Telecheck]
BaseUrl=http://192.168.0.125:8080
```

Sem essa chave, `uTelecheck.pas` usa `http://192.168.0.125:8080`.

## 5. Usar outro código-fonte do SACI

O banco não está espalhado pelo fonte. Está no `.udl` que o `UDM.dfm` abre:

```text
ConnectionString = 'FILE NAME=C:\Arquivos Saci\conexao.udl;'
```

Compilar outra pasta não troca o banco. O exe novo, se levar esse `UDM.dfm`, continua lendo o mesmo `conexao.udl` da seção 4.

### O outro fonte deve continuar no NOOB, e o atual ir para a mãe

Não altere o `conexao.udl` compartilhado. No fonte que deve ficar no `NOOB`:

1. Copie `C:\Arquivos Saci\conexao.udl` para um arquivo só desse fonte, por exemplo `C:\Arquivos Saci\conexao-noob.udl`, e deixe `Initial Catalog=NOOB` nele.
2. No `UDM.dfm` **dessa** pasta, troque o `FILE NAME` para esse arquivo novo.
3. Compile e rode esse exe. O outro exe, o que aponta para `conexao.udl`, segue a mãe depois da seção 4.

Cada exe fica preso ao `.udl` que estava no `UDM.dfm` no momento da compilação.

### O outro fonte ainda não tem o telecheck-

Leve estes três pontos do fonte `saci` (projeto `SACICheckWhats`) para o fonte antigo. Sem eles o exe compila, sobe, e o cadastro não chama a API.

1. Copie `uTelecheck.pas` para a pasta do outro fonte.
2. No `.dpr` desse fonte, na lista de units, inclua a mesma linha que está no `SACICheckWhats.dpr`:

```pascal
uTelecheck in 'uTelecheck.pas';
```

3. Leve de `uCadastrarCliFor.pas` a chamada que valida o número antes de gravar (`ValidarTelefonesTelecheck`) e, de `uCadCliFor.pas`, a leitura de `CLI_WHATSAPP` e `CLI_FONE_ADICIONAL`. O campo na tela nova se chama `edtWhastapp` (com o "h" no lugar do "a") e grava em `CLIENTE.CLI_WHATSAPP`.

`uTelecheck.pas` lê o endereço da API em `C:\Arquivos Saci\conf.ini`, seção `[Telecheck]`, chave `BaseUrl`. Esse caminho está fixo na unit. Outro fonte, compilado em outra pasta, continua lendo esse mesmo `conf.ini`.

### O que não precisa mudar

- Não procure `DATABASE` ou `NOOB` nas units para "apontar" o exe. A conexão de verdade é o `.udl`.
- Em `uLogin.pas` existe um bloco que cita `NOOB.sys.columns` e `ALTER TABLE`. Ele está comentado entre `{` e `}` e não roda. Deixe comentado. Se alguém descomentar, aqueles `ALTER TABLE` passam a executar no banco do `.udl`, seja `NOOB` ou a mãe.
- Em `uFuncoes.pas` há uma connection string comentada (`Initial Catalog=SACI_TARCIO` em outro servidor). Também não está em uso. Não descomente.

## 6. Ordem segura

1. Descobrir `NOME_DA_MAE` e conferir a quantidade de clientes.
2. Rodar `db/schema.sql` na mãe.
3. Rodar `db/usuario_restrito.sql` na mãe.
4. Conferir `CLI_WHATSAPP` e, se o fonte novo for usado, `CLI_FONE_ADICIONAL`.
5. Trocar `DATABASE=` em `db/config.env` e reiniciar o telecheck-.
6. Fazer um pedido de teste e ver a linha em `NOME_DA_MAE.dbo.LIBERACAO_WHATSAPP`.
7. Só então trocar `Initial Catalog` no `.udl` do SACI que deve gravar na mãe, e reabrir o exe.
8. Se houver um segundo fonte, dar a ele um `.udl` próprio antes de compilar.

Para voltar ao `NOOB`, desfaça o passo 5 e o passo 7: `DATABASE=NOOB` no `config.env`, `Initial Catalog=NOOB` no `.udl`, e reinicie os dois. As liberações já gravadas na mãe ficam na mãe. O `NOOB` não as vê.
