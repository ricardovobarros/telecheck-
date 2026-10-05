-- telecheck-: tabela de liberacao de cadastro sem WhatsApp.
--
-- Rode este script UMA VEZ no banco do SACI (SQL Server), no SSMS.
-- E aditivo: cria uma tabela nova e nao toca em CLIENTE nem em nada existente,
-- entao pode ser aplicado antes de o SACI estar adaptado.
--
-- A trigger que BLOQUEIA cadastro sem liberacao NAO esta aqui de proposito.
-- Ela derruba o cadastro do SACI atual no instante em que for criada.
-- Veja IMPLEMENTACAO_LIBERACAO_WHATSAPP.md, secao "Impor a regra no banco".

IF OBJECT_ID('dbo.LIBERACAO_WHATSAPP', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LIBERACAO_WHATSAPP (
        LIB_ID            VARCHAR(32)  NOT NULL,
        LIB_PHONE         VARCHAR(20)  NOT NULL,
        LIB_CODIGO_HASH   CHAR(64)     NOT NULL,
        LIB_STATUS        VARCHAR(12)  NOT NULL,
        LIB_TENTATIVAS    INT          NOT NULL
            CONSTRAINT DF_LIBERACAO_TENTATIVAS DEFAULT (0),
        LIB_OPERADOR      VARCHAR(60)  NOT NULL,
        LIB_CLIENTE_NOME  VARCHAR(120) NULL,
        LIB_MOTIVO        VARCHAR(300) NULL,
        LIB_GESTORA_PHONE VARCHAR(20)  NOT NULL,
        LIB_CRIADO_EM     DATETIME2(0) NOT NULL,
        LIB_EXPIRA_EM     DATETIME2(0) NOT NULL,
        LIB_CONSUMIDO_EM  DATETIME2(0) NULL,
        LIB_CLI_CODIGO    INT          NULL,
        CONSTRAINT PK_LIBERACAO_WHATSAPP PRIMARY KEY (LIB_ID),
        CONSTRAINT CK_LIBERACAO_STATUS CHECK (LIB_STATUS IN
            ('PENDENTE', 'APROVADA', 'BLOQUEADA', 'EXPIRADA', 'FALHA_ENVIO'))
    );

    CREATE INDEX IX_LIBERACAO_PHONE_STATUS
        ON dbo.LIBERACAO_WHATSAPP (LIB_PHONE, LIB_STATUS, LIB_CONSUMIDO_EM);

    CREATE INDEX IX_LIBERACAO_CRIADO_EM
        ON dbo.LIBERACAO_WHATSAPP (LIB_CRIADO_EM DESC);
END
GO

-- Significado das colunas
--
-- LIB_ID            request_id devolvido ao SACI. E o unico identificador que a
--                   maquina da operadora conhece; o codigo nunca passa por ela.
-- LIB_CODIGO_HASH   HMAC-SHA256 de "LIB_ID:codigo" com o OVERRIDE_PEPPER do
--                   servidor. O codigo em claro nao e gravado em lugar nenhum.
-- LIB_STATUS        PENDENTE     aguardando a operadora digitar
--                   APROVADA     codigo conferido e consumido (uso unico)
--                   BLOQUEADA    estourou OVERRIDE_MAX_ATTEMPTS
--                   EXPIRADA     passou de LIB_EXPIRA_EM sem uso
--                   FALHA_ENVIO  o Z-API nao entregou a mensagem a gestora
-- LIB_PHONE         telefone normalizado a que a liberacao esta presa. O
--                   /override/confirm recusa se o telefone enviado for outro.
-- LIB_CLI_CODIGO    preenchido pela trigger (opcional) com o CLI_CODIGO que
--                   consumiu a liberacao, para amarrar liberacao e cadastro.

-- Consultas uteis de auditoria
--
-- Liberacoes dos ultimos 30 dias, com o desfecho de cada pedido:
--   SELECT LIB_CRIADO_EM, LIB_OPERADOR, LIB_CLIENTE_NOME, LIB_PHONE,
--          LIB_STATUS, LIB_TENTATIVAS, LIB_MOTIVO
--     FROM dbo.LIBERACAO_WHATSAPP
--    WHERE LIB_CRIADO_EM >= DATEADD(DAY, -30, SYSDATETIME())
--    ORDER BY LIB_CRIADO_EM DESC;
--
-- Quem mais pede liberacao (o numero que interessa de verdade):
--   SELECT LIB_OPERADOR,
--          COUNT(*) AS PEDIDOS,
--          SUM(CASE WHEN LIB_STATUS = 'APROVADA' THEN 1 ELSE 0 END) AS APROVADOS
--     FROM dbo.LIBERACAO_WHATSAPP
--    WHERE LIB_CRIADO_EM >= DATEADD(DAY, -30, SYSDATETIME())
--    GROUP BY LIB_OPERADOR
--    ORDER BY PEDIDOS DESC;
