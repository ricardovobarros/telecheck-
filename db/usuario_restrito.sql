-- Login do telecheck- no SQL Server do SACI. So enxerga dbo.LIBERACAO_WHATSAPP.
-- O override_store.py faz apenas SELECT, INSERT e UPDATE nessa tabela: sem DELETE, sem DDL,
-- sem acesso a CLIENTE ou a qualquer outra tabela do SACI.
--
-- Rodar como sysadmin, no banco do SACI, depois do db/schema.sql. A senha entra por variavel
-- do sqlcmd, para nao ficar gravada neste arquivo:
--   sqlcmd -S server-sz2 -U sysdba -P ... -d NOOB -i db\usuario_restrito.sql -v SENHA="..."
-- A mesma senha vai em PWD= do DB_ODBC_CONNECTION_STRING, em db/config.env.
--
-- Idempotente: rodar de novo troca a senha e reaplica as permissoes.

SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.LIBERACAO_WHATSAPP', N'U') IS NULL
BEGIN
    RAISERROR(N'Rode o db/schema.sql antes: dbo.LIBERACAO_WHATSAPP nao existe neste banco.', 16, 1);
    RETURN;
END;

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'telecheck_app')
    CREATE LOGIN [telecheck_app] WITH PASSWORD = N'$(SENHA)', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
ELSE
    ALTER LOGIN [telecheck_app] WITH PASSWORD = N'$(SENHA)';

DECLARE @sql NVARCHAR(400) = N'ALTER LOGIN [telecheck_app] WITH DEFAULT_DATABASE = ' + QUOTENAME(DB_NAME());
EXEC (@sql);

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'telecheck_app')
    CREATE USER [telecheck_app] FOR LOGIN [telecheck_app] WITH DEFAULT_SCHEMA = dbo;
ELSE
    ALTER USER [telecheck_app] WITH LOGIN = [telecheck_app];

GRANT SELECT, INSERT, UPDATE ON dbo.LIBERACAO_WHATSAPP TO [telecheck_app];
