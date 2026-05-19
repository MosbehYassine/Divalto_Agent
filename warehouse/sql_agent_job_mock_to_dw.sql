:setvar ETL_JOB_NAME "ETL_Mock_To_DW"
:setvar ETL_PROXY_NAME "proxy_etl_runner"
:setvar ETL_USE_PROXY_CMD "0"
:setvar ETL_USE_PROXY_SSAS "1"
:setvar ETL_CMD "cmd /d /c ""d:\PFE_final\mock database\run_etl_mock_to_dw.cmd"""
:setvar ETL_CMD_LOG "d:\PFE_final\mock database\etl_mock_to_dw_cmdexec.log"
:setvar ETL_SSAS_SERVER "localhost\MSSQLS_YR"
:setvar ETL_SSAS_DBID "DWCubeProject"

USE msdb;
GO

/* -----------------------------------------------------------------------
   OPTIONAL ONE-TIME SETUP (Proxy for CmdExec step)
   Why: avoids SQL Agent service-account DLL/runtime issues.

   1) Set the password below, run once.
   2) Then you can keep rerunning this script; Step 1 will use proxy if found.
------------------------------------------------------------------------ */
DECLARE @credential_name SYSNAME = N'cred_etl_runner';
DECLARE @proxy_name      SYSNAME = N'$(ETL_PROXY_NAME)';
DECLARE @identity_name   NVARCHAR(256) = N'DESKTOP-R2U56NT\etl_runner';
DECLARE @identity_pwd    NVARCHAR(256) = N'__PUT_WINDOWS_PASSWORD_HERE__';

IF @identity_pwd <> N'__PUT_WINDOWS_PASSWORD_HERE__'
BEGIN
    IF NOT EXISTS (SELECT 1 FROM master.sys.credentials WHERE name = @credential_name)
    BEGIN
        DECLARE @sql_create_cred NVARCHAR(MAX) =
            N'CREATE CREDENTIAL ' + QUOTENAME(@credential_name) +
            N' WITH IDENTITY = ' + QUOTENAME(@identity_name, '''') +
            N', SECRET = ' + QUOTENAME(@identity_pwd, '''') + N';';
        EXEC (@sql_create_cred);
    END

    IF NOT EXISTS (SELECT 1 FROM msdb.dbo.sysproxies WHERE name = @proxy_name)
    BEGIN
        EXEC msdb.dbo.sp_add_proxy
            @proxy_name = @proxy_name,
            @credential_name = @credential_name,
            @enabled = 1;
    END

    -- Ensure proxy is authorized for required subsystems and caller login.
    IF NOT EXISTS (
        SELECT 1
        FROM msdb.dbo.sysproxysubsystem ps
        JOIN msdb.dbo.sysproxies p ON p.proxy_id = ps.proxy_id
        WHERE p.name = @proxy_name
          AND ps.subsystem_id = 3 -- CmdExec
    )
    BEGIN
        EXEC msdb.dbo.sp_grant_proxy_to_subsystem
            @proxy_name = @proxy_name,
            @subsystem_id = 3;
    END

    DECLARE @analysis_subsystem_id INT;
    SELECT @analysis_subsystem_id = subsystem_id
    FROM msdb.dbo.syssubsystems
    WHERE subsystem = N'ANALYSISCOMMAND';

    IF @analysis_subsystem_id IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM msdb.dbo.sysproxysubsystem ps
            JOIN msdb.dbo.sysproxies p ON p.proxy_id = ps.proxy_id
            WHERE p.name = @proxy_name
              AND ps.subsystem_id = @analysis_subsystem_id
       )
    BEGIN
        EXEC msdb.dbo.sp_grant_proxy_to_subsystem
            @proxy_name = @proxy_name,
            @subsystem_id = @analysis_subsystem_id;
    END

    DECLARE @current_login SYSNAME = ORIGINAL_LOGIN();

    IF NOT EXISTS (
        SELECT 1
        FROM msdb.dbo.sysproxylogin pl
        JOIN msdb.dbo.sysproxies p ON p.proxy_id = pl.proxy_id
        WHERE p.name = @proxy_name
          AND SUSER_SNAME(pl.sid) = @current_login
    )
    BEGIN
        EXEC msdb.dbo.sp_grant_login_to_proxy
            @proxy_name = @proxy_name,
            @login_name = @current_login;
    END
END
GO

DECLARE @job_name SYSNAME = N'$(ETL_JOB_NAME)';

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE [name] = @job_name)
BEGIN
    EXEC msdb.dbo.sp_delete_job @job_name = @job_name;
END
GO

EXEC msdb.dbo.sp_add_job
    @job_name = N'$(ETL_JOB_NAME)',
    @enabled = 1,
    @notify_level_eventlog = 2, -- write to Windows Event Log on failure
    @description = N'Run Python ETL from SQLite mock to StagingDB/DataWarehouseDB.',
    @category_name = N'[Uncategorized (Local)]';
GO

IF $(ETL_USE_PROXY_CMD) = 1
   AND EXISTS (SELECT 1 FROM msdb.dbo.sysproxies WHERE name = N'$(ETL_PROXY_NAME)')
BEGIN
    EXEC msdb.dbo.sp_add_jobstep
        @job_name = N'$(ETL_JOB_NAME)',
        @step_name = N'Run Python ETL Script',
        @subsystem = N'CmdExec',
        @proxy_name = N'$(ETL_PROXY_NAME)',
        @command = N'$(ETL_CMD)',
        @output_file_name = N'$(ETL_CMD_LOG)',
        @flags = 2, -- append output to file (valid for CmdExec)
        @retry_attempts = 0,
        @retry_interval = 0,
        @on_success_action = 3, -- go to next step
        @on_fail_action = 2;    -- quit with failure
END
ELSE
BEGIN
    PRINT 'WARNING: CmdExec proxy disabled or $(ETL_PROXY_NAME) not found. Step 1 will run under SQL Agent service account.';

    EXEC msdb.dbo.sp_add_jobstep
        @job_name = N'$(ETL_JOB_NAME)',
        @step_name = N'Run Python ETL Script',
        @subsystem = N'CmdExec',
        @command = N'$(ETL_CMD)',
        @output_file_name = N'$(ETL_CMD_LOG)',
        @flags = 2, -- append output to file (valid for CmdExec)
        @retry_attempts = 0,
        @retry_interval = 0,
        @on_success_action = 3, -- go to next step
        @on_fail_action = 2;    -- quit with failure
END
GO

EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'$(ETL_JOB_NAME)',
    @step_name = N'Validate Fact Row Count',
    @subsystem = N'TSQL',
    @database_name = N'DataWarehouseDB',
    @command = N'
IF NOT EXISTS (SELECT 1 FROM dbo.FactSales)
BEGIN
    THROW 51000, ''FactSales is empty after ETL.'', 1;
END
',
    @on_success_action = 3, -- go to next step
    @on_fail_action = 2;    -- quit with failure
GO

DECLARE @analysis_subsystem_id_step3 INT;
SELECT @analysis_subsystem_id_step3 = subsystem_id
FROM msdb.dbo.syssubsystems
WHERE subsystem = N'ANALYSISCOMMAND';

IF @analysis_subsystem_id_step3 IS NOT NULL
   AND $(ETL_USE_PROXY_SSAS) = 1
   AND EXISTS (
        SELECT 1
        FROM msdb.dbo.sysproxies p
        JOIN msdb.dbo.sysproxysubsystem ps ON ps.proxy_id = p.proxy_id
        WHERE p.name = N'$(ETL_PROXY_NAME)'
          AND ps.subsystem_id = @analysis_subsystem_id_step3
   )
BEGIN
    EXEC msdb.dbo.sp_add_jobstep
        @job_name = N'$(ETL_JOB_NAME)',
        @step_name = N'Process SSAS Cube',
        @subsystem = N'ANALYSISCOMMAND',
        @proxy_name = N'$(ETL_PROXY_NAME)',
        @server = N'$(ETL_SSAS_SERVER)',
        @command = N'
<Batch xmlns="http://schemas.microsoft.com/analysisservices/2003/engine">
  <Parallel>
    <Process>
      <Object>
        <DatabaseID>$(ETL_SSAS_DBID)</DatabaseID>
      </Object>
      <Type>ProcessFull</Type>
      <WriteBackTableCreation>UseExisting</WriteBackTableCreation>
    </Process>
  </Parallel>
</Batch>
',
        @on_success_action = 1, -- quit with success
        @on_fail_action = 2;    -- quit with failure
END
ELSE
BEGIN
    PRINT 'WARNING: SSAS proxy disabled or $(ETL_PROXY_NAME) not granted to ANALYSISCOMMAND. Step 3 will run under SQL Agent service account.';

    EXEC msdb.dbo.sp_add_jobstep
        @job_name = N'$(ETL_JOB_NAME)',
        @step_name = N'Process SSAS Cube',
        @subsystem = N'ANALYSISCOMMAND',
        @server = N'$(ETL_SSAS_SERVER)',
        @command = N'
<Batch xmlns="http://schemas.microsoft.com/analysisservices/2003/engine">
  <Parallel>
    <Process>
      <Object>
        <DatabaseID>$(ETL_SSAS_DBID)</DatabaseID>
      </Object>
      <Type>ProcessFull</Type>
      <WriteBackTableCreation>UseExisting</WriteBackTableCreation>
    </Process>
  </Parallel>
</Batch>
',
        @on_success_action = 1, -- quit with success
        @on_fail_action = 2;    -- quit with failure
END
GO

EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'$(ETL_JOB_NAME)',
    @name = N'Daily_01_00',
    @enabled = 1,
    @freq_type = 4,         -- daily
    @freq_interval = 1,     -- every day
    @active_start_time = 010000; -- 01:00:00
GO

EXEC msdb.dbo.sp_add_jobserver
    @job_name = N'$(ETL_JOB_NAME)',
    @server_name = N'(local)';
GO

PRINT 'SQL Agent job created: $(ETL_JOB_NAME)';
