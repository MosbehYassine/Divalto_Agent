USE DataWarehouseDB;
GO

SELECT GETDATE() AS checked_at;

SELECT COUNT(*) AS dim_customer_rows FROM dbo.DimCustomer;
SELECT COUNT(*) AS dim_product_rows  FROM dbo.DimProduct;
SELECT COUNT(*) AS fact_sales_rows   FROM dbo.FactSales;

SELECT TOP (5)
    DateKey,
    CustomerKey,
    ProductKey,
    Quantity,
    UnitPrice,
    Amount,
    SourceDocumentNo
FROM dbo.FactSales
ORDER BY DateKey DESC, SourceDocumentNo DESC;

USE msdb;
GO

SELECT TOP (10)
    h.step_id,
    h.step_name,
    h.run_status,
    h.run_date,
    h.run_time,
    h.run_duration,
    h.message
FROM dbo.sysjobhistory h
JOIN dbo.sysjobs j ON j.job_id = h.job_id
WHERE j.name = N'ETL_Mock_To_DW'
ORDER BY h.instance_id DESC;
